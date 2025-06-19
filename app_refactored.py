"""
PPE Detection Application - Refactored with optimized performance
"""

import os
import cv2
import json
import uuid
import logging
from flask import Flask, render_template, request, Response, jsonify, redirect, url_for
from datetime import datetime

# Configuration and services
from config import get_config
from services import VideoService, DetectionService, EventService, EmailService
from models import VideoSource, DetectionEvent
from utils import create_placeholder_frame, logger

# Initialize Flask app
app = Flask(__name__)

# Load configuration
config = get_config(os.environ.get("FLASK_ENV", "production"))
config.init_app(app)

# Initialize services
video_service = VideoService(config)
detection_service = DetectionService(config)
event_service = EventService(config, video_service, detection_service)
email_service = EmailService(config)

# Start services
event_service.start()

# Legacy compatibility globals
current_video_name = None
frames_buffer = []
violation_log = {}
tracking_loop_count = 0
current_loop_violations = {}


def initialize_app():
    """Initialize the application on startup"""
    # Configure email service from environment or defaults
    email_enabled = os.environ.get("EMAIL_ALERTS_ENABLED", "false").lower() == "true"
    email_recipient = os.environ.get("EMAIL_RECIPIENT", "")

    if email_enabled and email_recipient:
        email_service.configure(True, email_recipient)
        email_service.start()

    # Set up detection service to use email service
    detection_service.event_queue = event_service.event_queue

    # Initialize a default video if available
    initialize_default_video()

    logger.info("Application initialized successfully")


def initialize_default_video():
    """Initialize first available video for legacy compatibility"""
    global current_video_name

    video_dir = config.VIDEO_UPLOADS
    if os.path.exists(video_dir):
        video_files = [
            f
            for f in os.listdir(video_dir)
            if f.upper().endswith(tuple(config.ALLOWED_VIDEO_EXTENSIONS))
        ]
        if video_files:
            video_files.sort()
            current_video_name = video_files[0]
            logger.info(f"Auto-selected default video: {current_video_name}")


# ============= Dashboard Routes =============


@app.route("/")
def index():
    """Redirect to dashboard"""
    return redirect(url_for("dashboard"))


@app.route("/dashboard")
def dashboard():
    """Main dashboard view"""
    return render_template(
        "dashboard.html",
        email_recipient=email_service.recipient or "",
        email_alert_enabled=email_service.enabled,
    )


@app.route("/camera/<source_id>")
def camera_view(source_id):
    """Individual camera view"""
    source = video_service.get_source(source_id)
    if not source:
        return redirect(url_for("dashboard"))
    return render_template("camera_view.html", source=source)


# ============= Video Streaming Routes =============


@app.route("/source_video_raw/<source_id>")
def source_video_raw(source_id):
    """Raw video stream for a specific source"""
    return Response(
        video_service.generate_frames(source_id, processed=False),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )


@app.route("/source_video_processed/<source_id>")
def source_video_processed(source_id):
    """Processed video stream with detections"""

    def detector_func(frame):
        source = video_service.get_source(source_id)
        if source:
            # Get frame index from buffer position
            frame_index = len(source.frames) - 1
            return detection_service.apply_detections_to_frame(
                frame, source_id, frame_index
            )
        return frame

    return Response(
        video_service.generate_frames(
            source_id, processed=True, detector_func=detector_func
        ),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )


# ============= API Endpoints =============


@app.route("/api/sources", methods=["GET", "POST"])
def api_sources():
    """Get all sources or add a new source"""
    if request.method == "GET":
        sources = video_service.get_all_sources()
        return jsonify([source.to_dict() for source in sources])

    elif request.method == "POST":
        data = request.get_json()
        name = data.get("name", "").strip()
        source_type = data.get("type")
        path = data.get("path")

        if not all([source_type, path]):
            return jsonify({"error": "Missing required fields"}), 400

        # Auto-generate name if not provided
        if not name:
            if source_type == "file":
                name = path.rsplit(".", 1)[0].replace("_", " ").title()
            else:
                import re

                match = re.search(r"://([^:/]+)", path)
                if match:
                    name = f"Stream - {match.group(1)}"
                else:
                    name = f"Stream {len(video_service.get_all_sources()) + 1}"

        # Add source
        source = video_service.add_source(name, source_type, path)
        if source:
            # Start detection
            detection_service.start_detection(source)
            return jsonify(source.to_dict())
        else:
            return jsonify({"error": "Failed to add source"}), 500


@app.route("/api/sources/<source_id>", methods=["DELETE"])
def api_source_delete(source_id):
    """Delete a source"""
    # Stop detection first
    detection_service.stop_detection(source_id)

    if video_service.remove_source(source_id):
        return jsonify({"success": True})
    else:
        return jsonify({"error": "Source not found"}), 404


@app.route("/api/settings", methods=["POST"])
def api_settings():
    """Update application settings"""
    data = request.get_json()

    if "email_recipient" in data:
        email_service.recipient = data["email_recipient"]
    if "email_alert_enabled" in data:
        email_service.enabled = data["email_alert_enabled"]
        if email_service.enabled and not email_service.email_thread:
            email_service.start()
    if "confidence_threshold" in data:
        config.DEFAULT_CONFIDENCE = float(data["confidence_threshold"])

    # Save settings
    email_service.configure(email_service.enabled, email_service.recipient)

    return jsonify({"success": True})


@app.route("/events")
def events():
    """Server-Sent Events endpoint"""
    client_id = str(uuid.uuid4())
    source_id = request.args.get("source_id")

    return Response(
        event_service.generate_events(client_id, source_id),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@app.route("/video_list", methods=["GET"])
def video_list():
    """Get list of available video files"""
    video_dir = config.VIDEO_UPLOADS
    videos = []

    if os.path.exists(video_dir):
        videos = [
            f
            for f in os.listdir(video_dir)
            if f.upper().endswith(tuple(config.ALLOWED_VIDEO_EXTENSIONS))
        ]
        videos.sort()

    return json.dumps({"videos": videos, "current": current_video_name})


@app.route("/api/sample_videos", methods=["GET"])
def api_sample_videos():
    """Return list of sample videos stored in static/ppe_videos/video"""
    sample_dir = os.path.join("static", "ppe_videos", "video")
    videos = []
    if os.path.exists(sample_dir):
        videos = [
            f
            for f in os.listdir(sample_dir)
            if f.lower().endswith((".mp4", ".mov", ".avi", ".wmv", ".webm"))
        ]
        videos.sort()
    return jsonify({"videos": videos})


# ============= Legacy Routes (for backward compatibility) =============


@app.route("/legacy", methods=["GET", "POST"])
def legacy_view():
    """Legacy single-source view"""
    return render_template("index.html", current_video=current_video_name)


@app.route("/video_raw")
def video_raw():
    """Legacy raw video stream"""
    if current_video_name:
        # Create a temporary source for legacy video
        path = os.path.join(config.VIDEO_UPLOADS, current_video_name)

        # Check if already exists
        legacy_source = None
        for source in video_service.get_all_sources():
            if source.path == path:
                legacy_source = source
                break

        if not legacy_source:
            legacy_source = video_service.add_source(
                f"Legacy - {current_video_name}", "file", current_video_name
            )

        if legacy_source:
            return redirect(url_for("source_video_raw", source_id=legacy_source.id))

    # Return placeholder
    def generate():
        placeholder = create_placeholder_frame(text="No Video Selected")
        _, buf = cv2.imencode(".jpg", placeholder)
        while True:
            yield (
                b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + buf.tobytes() + b"\r\n"
            )

    return Response(generate(), mimetype="multipart/x-mixed-replace; boundary=frame")


@app.route("/video_processed")
def video_processed():
    """Legacy processed video stream"""
    conf = float(request.args.get("conf", config.DEFAULT_CONFIDENCE))

    if current_video_name:
        # Similar to video_raw, create/find legacy source
        path = os.path.join(config.VIDEO_UPLOADS, current_video_name)

        legacy_source = None
        for source in video_service.get_all_sources():
            if source.path == path:
                legacy_source = source
                break

        if not legacy_source:
            legacy_source = video_service.add_source(
                f"Legacy - {current_video_name}", "file", current_video_name
            )
            if legacy_source:
                detection_service.start_detection(legacy_source)

        if legacy_source:
            return redirect(
                url_for("source_video_processed", source_id=legacy_source.id, conf=conf)
            )

    return redirect(url_for("video_raw"))


@app.route("/submit", methods=["POST"])
def submit_form():
    """Legacy form submission"""
    global current_video_name, email_service

    try:
        # Handle video selection
        video_file = request.form.get("video_file")
        if video_file and video_file != current_video_name:
            current_video_name = video_file
            logger.info(f"Video changed to: {current_video_name}")

        # Handle email settings
        email_address = request.form.get("email_address", "").strip()
        enable_email = request.form.get("enable_email") == "on"

        email_service.configure(enable_email, email_address)
        if enable_email and not email_service.email_thread:
            email_service.start()

        return jsonify(
            {
                "success": True,
                "message": "Settings updated successfully",
                "video": current_video_name,
                "email_enabled": email_service.enabled,
            }
        )

    except Exception as e:
        logger.error(f"Error in submit_form: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


# ============= PPE Screening Routes =============


@app.route("/screening")
def screening():
    """PPE screening interface"""
    return render_template("screening.html")


@app.route("/screening/history")
def screening_history():
    """Get screening history"""
    # This would typically query a database
    # For now, return empty history
    return jsonify({"history": []})


@app.route("/api/screening/sites", methods=["GET"])
def api_screening_sites():
    """Get available screening sites"""
    sites = [
        {
            "id": "main-entrance",
            "name": "Main Entrance",
            "requirements": ["hardhat", "safety-vest", "safety-shoes"],
        },
        {
            "id": "construction-a",
            "name": "Construction Site A",
            "requirements": ["hardhat", "safety-vest", "mask", "safety-shoes"],
        },
        {
            "id": "warehouse",
            "name": "Warehouse",
            "requirements": ["safety-vest", "safety-shoes"],
        },
        {
            "id": "lab",
            "name": "Laboratory",
            "requirements": ["safety-vest", "mask", "gloves"],
        },
    ]
    return jsonify({"sites": sites})


@app.route("/api/screening/requirements", methods=["GET"])
def api_screening_requirements():
    """Get PPE requirements"""
    requirements = {
        "hardhat": {"name": "Hard Hat", "icon": "🪖", "class": "Hardhat"},
        "safety-vest": {"name": "Safety Vest", "icon": "🦺", "class": "Safety Vest"},
        "mask": {"name": "Face Mask", "icon": "😷", "class": "Mask"},
        "safety-shoes": {"name": "Safety Shoes", "icon": "👷", "class": "Safety Shoes"},
        "gloves": {"name": "Safety Gloves", "icon": "🧤", "class": "Gloves"},
    }
    return jsonify({"requirements": requirements})


@app.route("/api/screening/detect", methods=["POST"])
def api_screening_detect():
    """Perform PPE detection on uploaded image"""
    try:
        data = request.get_json()
        image_data = data.get("image")
        site_id = data.get("site_id")

        if not image_data:
            return jsonify({"error": "No image provided"}), 400

        # Decode base64 image
        import base64
        import numpy as np

        image_bytes = base64.b64decode(image_data.split(",")[1])
        nparr = np.frombuffer(image_bytes, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        # Run detection
        detector = detection_service.get_detector()
        detections = detector.detect(frame)

        # Process results
        detected_items = []
        for box, label in detections:
            class_name = label.split()[0]
            confidence = float(label.split()[-1])
            detected_items.append(
                {"class": class_name, "confidence": confidence, "box": box}
            )

        return jsonify(
            {
                "success": True,
                "detections": detected_items,
                "timestamp": datetime.now().isoformat(),
            }
        )

    except Exception as e:
        logger.error(f"Error in screening detection: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/screening/complete", methods=["POST"])
def api_screening_complete():
    """Complete screening and save results"""
    try:
        data = request.get_json()

        # In a real app, this would save to a database
        result = {
            "id": str(uuid.uuid4()),
            "timestamp": datetime.now().isoformat(),
            "site_id": data.get("site_id"),
            "compliance": data.get("compliance"),
            "missing_items": data.get("missing_items", []),
            "detected_items": data.get("detected_items", []),
        }

        # If non-compliant, could trigger an alert
        if not result["compliance"] and email_service.enabled:
            message = f"PPE Screening Failed at {result['site_id']}\n"
            message += f"Missing items: {', '.join(result['missing_items'])}"

            # Create a pseudo event for email
            event = DetectionEvent(
                source_id="screening",
                timestamp=datetime.now(),
                violation_type="Screening Non-Compliance",
                confidence=1.0,
                event_id=result["id"],
                frame_number=0,
            )

            # Create pseudo source
            source = VideoSource("screening", "PPE Screening", "screening", "")
            source.compliance_rate = 0.0

            email_service.send_immediate_alert(source, event)

        return jsonify({"success": True, "result": result})

    except Exception as e:
        logger.error(f"Error completing screening: {e}")
        return jsonify({"error": str(e)}), 500


# ============= Application Lifecycle =============


@app.before_request
def before_request():
    """Initialize app on first request"""
    if not hasattr(app, "_initialized"):
        initialize_app()
        app._initialized = True


@app.teardown_appcontext
def teardown(error):
    """Cleanup on teardown"""
    if error:
        logger.error(f"App teardown with error: {error}")


def shutdown_services():
    """Gracefully shutdown all services"""
    logger.info("Shutting down services...")

    email_service.shutdown()
    event_service.shutdown()
    detection_service.shutdown()
    video_service.shutdown()

    logger.info("All services shut down successfully")


# Register shutdown handler
import atexit

atexit.register(shutdown_services)


if __name__ == "__main__":
    # Development server
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=config.DEBUG,
        threaded=True,
        use_reloader=False,  # Disable reloader to prevent duplicate initialization
    )
