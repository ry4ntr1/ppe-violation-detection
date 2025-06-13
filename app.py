import os
import time
import cv2
import numpy as np
from flask import (
    Flask,
    render_template,
    request,
    Response,
    send_file,
    jsonify,
    redirect,
    url_for,
)
from send_mail import prepare_and_send_email
from detection import get_detector  # UPDATED
import json
from io import BytesIO
import threading
import uuid
from datetime import datetime, timedelta
import queue
import re

# Initialize the Flask application
app = Flask(__name__)
app.config["VIDEO_UPLOADS"] = "static/video"
app.config["ALLOWED_VIDEO_EXTENSIONS"] = ["MP4", "MOV", "AVI", "WMV", "WEBM"]
app.config["SECRET_KEY"] = "ppe_violation_detection"

# ensure upload folder exists
os.makedirs(app.config["VIDEO_UPLOADS"], exist_ok=True)

# Multi-source management
sources = {}  # {source_id: SourceInfo}
source_threads = {}  # {source_id: Thread}
event_queue = queue.Queue()  # For Server-Sent Events
detection_events = []  # Store recent detection events

# Legacy global state (for backward compatibility)
frames_buffer = []
current_video_name = None
vid_path = None
video_frames = None

# email alert globals
email_alert_enabled = False
email_recipient = None
last_email_time = 0  # epoch seconds
EMAIL_COOLDOWN_SEC = 60  # avoid spamming

# violation tracking globals
violation_log = {}  # {class_name: {'count': int, 'first_seen': timestamp}}
tracking_loop_count = 0
current_loop_violations = {}

# Default confidence threshold
default_confidence = 0.5


class SourceInfo:
    def __init__(self, source_id, name, source_type, path):
        self.id = source_id
        self.name = name
        self.type = source_type  # 'file' or 'stream'
        self.path = path
        self.status = "inactive"
        self.fps = 0
        self.frames_buffer = []
        self.video_capture = None
        self.violation_counts = {}
        self.last_detection = None
        self.detection_thread = None
        self.alerts_sent = (
            set()
        )  # Track unique alerts sent (violation_type, timestamp_minute)
        self.total_frames_processed = 0  # For compliance rate calculation
        self.frames_with_violations = 0  # For compliance rate calculation


def reset_violation_tracking():
    """Reset violation tracking for a new video or loop."""
    global violation_log, current_loop_violations, tracking_loop_count
    violation_log = {}
    current_loop_violations = {}
    tracking_loop_count = 0


def record_violation(class_name):
    """Record a violation detection."""
    global current_loop_violations

    if class_name not in current_loop_violations:
        current_loop_violations[class_name] = {
            "count": 0,
            "first_seen": time.strftime("%Y-%m-%d %H:%M:%S"),
            "first_frame": len(frames_buffer),  # Approximate frame number
        }
    current_loop_violations[class_name]["count"] += 1


def allowed_video(filename: str) -> bool:
    if "." not in filename:
        return False
    ext = filename.rsplit(".", 1)[1].upper()
    return ext in app.config["ALLOWED_VIDEO_EXTENSIONS"]


# Multi-source management functions
def add_source(name, source_type, path):
    """Add a new video source."""
    source_id = str(uuid.uuid4())
    source = SourceInfo(source_id, name, source_type, path)

    # Initialize video capture
    if source_type == "file":
        full_path = os.path.join(app.config["VIDEO_UPLOADS"], path)
        source.video_capture = cv2.VideoCapture(full_path)
    else:  # stream
        source.video_capture = cv2.VideoCapture(path)

    if source.video_capture.isOpened():
        source.status = "active"
        source.fps = source.video_capture.get(cv2.CAP_PROP_FPS) or 30
        sources[source_id] = source

        # Start frame processing thread
        frame_thread = threading.Thread(target=process_source, args=(source_id,))
        frame_thread.daemon = True
        frame_thread.start()
        source_threads[source_id] = frame_thread

        # Start detection processing thread
        detection_thread = threading.Thread(
            target=process_detections, args=(source_id,)
        )
        detection_thread.daemon = True
        detection_thread.start()
        source.detection_thread = detection_thread

        return source
    else:
        return None


def remove_source(source_id):
    """Remove a video source."""
    if source_id in sources:
        source = sources[source_id]
        source.status = "inactive"

        # Stop video capture
        if source.video_capture:
            source.video_capture.release()

        # Remove from dictionaries
        del sources[source_id]
        if source_id in source_threads:
            del source_threads[source_id]

        return True
    return False


def process_source(source_id):
    """Process video frames from a source."""
    source = sources.get(source_id)
    if not source:
        return

    frame_count = 0
    frame_delay = 1.0 / source.fps
    last_frame_time = time.time()

    while source.status == "active" and source_id in sources:
        success, frame = source.video_capture.read()
        if not success:
            if source.type == "file":
                # Restart video from beginning
                source.video_capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
                success, frame = source.video_capture.read()
                if not success:
                    time.sleep(0.01)
                    continue
            else:
                # Stream error
                source.status = "error"
                break

        # Control frame rate
        current_time = time.time()
        time_since_last_frame = current_time - last_frame_time
        if time_since_last_frame < frame_delay:
            time.sleep(frame_delay - time_since_last_frame)
        last_frame_time = time.time()

        # Add frame to buffer
        frame_count += 1
        source.frames_buffer.append(frame.copy())

        # Keep buffer size reasonable
        if len(source.frames_buffer) > 60:
            source.frames_buffer = source.frames_buffer[-60:]

    source.status = "inactive"


def process_detections(source_id):
    """Process detections for a source in the background."""
    source = sources.get(source_id)
    if not source:
        return

    # Initialize detector
    detector = get_detector("ppe")(conf=default_confidence)
    processed_index = 0

    while source.status == "active" and source_id in sources:
        if len(source.frames_buffer) == 0:
            time.sleep(0.1)
            continue

        buffer_len = len(source.frames_buffer)

        # If we've processed all frames, wait for new ones
        if processed_index >= buffer_len:
            # If way behind, catch up
            if processed_index < buffer_len - 30:
                processed_index = buffer_len - 10
            else:
                time.sleep(0.1)
                continue

        try:
            frame = source.frames_buffer[processed_index].copy()
            processed_index += 1
        except IndexError:
            processed_index = max(0, buffer_len - 1)
            continue

        # Track total frames for compliance rate
        source.total_frames_processed += 1
        frame_has_violation = False

        # Run detection
        for box, label in detector.detect(frame):
            # Check if this is a violation
            if any(v in label for v in ["NO-Hardhat", "NO-Mask", "NO-Safety Vest"]):
                frame_has_violation = True
                # Extract violation info
                violation_class = label.split()[0]
                confidence = float(label.split()[-1])

                # Create unique event ID for tracking
                timestamp = datetime.now()
                event_id = f"{violation_class}_{timestamp.strftime('%Y%m%d_%H%M%S')}_{processed_index}"

                # Send detection event
                event_data = {
                    "source_id": source_id,
                    "timestamp": timestamp.isoformat(),
                    "violation_type": violation_class,
                    "confidence": confidence,
                    "event_id": event_id,
                    "frame_number": processed_index,
                }
                event_queue.put(("detection", event_data))

                # Store detection event for timeline
                detection_events.append(
                    {
                        "source_id": source_id,
                        "timestamp": timestamp,
                        "violation_type": violation_class,
                        "confidence": confidence,
                        "event_id": event_id,
                        "frame_number": processed_index,
                    }
                )

                # Keep only last hour of events
                cutoff_time = datetime.now() - timedelta(hours=1)
                detection_events[:] = [
                    e for e in detection_events if e["timestamp"] > cutoff_time
                ]

                # Update source stats
                source.last_detection = timestamp
                if violation_class not in source.violation_counts:
                    source.violation_counts[violation_class] = 0
                source.violation_counts[violation_class] += 1

                # Email alert - only send once per violation instance (per minute to avoid spam)
                alert_key = (violation_class, timestamp.strftime("%Y%m%d_%H%M"))
                if (
                    email_alert_enabled
                    and email_recipient
                    and alert_key not in source.alerts_sent
                ):
                    source.alerts_sent.add(alert_key)
                    try:
                        prepare_and_send_email(
                            sender="support.ai@giindia.com",
                            recipient=email_recipient,
                            subject=f"PPE Violation Detected - {source.name}",
                            message_text=f"A {violation_class} violation was detected at {source.name} at "
                            + timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                            im0=frame,
                        )
                    except Exception as e:
                        print("Email send failed:", e)

        # Update compliance tracking
        if frame_has_violation:
            source.frames_with_violations += 1

        # Small delay to prevent CPU overload
        time.sleep(0.05)


def generate_source_frames(source_id, processed=False, conf_=0.5, detector_names=None):
    """Generate frames for a specific source."""
    source = sources.get(source_id)
    if not source:
        # Return placeholder
        placeholder = np.zeros((480, 640, 3), dtype=np.uint8)
        cv2.putText(
            placeholder,
            "Source not found",
            (150, 240),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.2,
            (255, 255, 255),
            2,
        )
        _, buf = cv2.imencode(".jpg", placeholder)
        while True:
            yield (
                b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + buf.tobytes() + b"\r\n"
            )
            time.sleep(0.1)

    if processed:
        if detector_names is None:
            detector_names = ["ppe"]

        # Instantiate detectors for rendering
        detectors = [get_detector(n)(conf=conf_) for n in detector_names]
        colour_map = {
            "ppe": (255, 0, 0),  # Blue
        }

    processed_index = 0

    while source_id in sources:
        if len(source.frames_buffer) == 0:
            time.sleep(0.01)
            continue

        buffer_len = len(source.frames_buffer)

        if processed_index >= buffer_len:
            if processed_index > buffer_len + 30:
                processed_index = max(0, buffer_len - 10)
            else:
                time.sleep(0.01)
                continue

        try:
            frame = source.frames_buffer[processed_index].copy()
            processed_index += 1
        except IndexError:
            processed_index = max(0, buffer_len - 1)
            continue

        if processed:
            # Run detectors just for visualization (detection happens in background)
            for name, det in zip(detector_names, detectors):
                colour = colour_map.get(name, (0, 255, 0))
                for box, label in det.detect(frame):
                    # Draw bounding box
                    x1, y1, x2, y2 = box
                    cv2.rectangle(frame, (x1, y1), (x2, y2), colour, 2)
                    cv2.putText(
                        frame,
                        label,
                        (x1, max(0, y1 - 6)),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.5,
                        colour,
                        2,
                        cv2.LINE_AA,
                    )

        _, buf = cv2.imencode(".jpg", frame)
        yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + buf.tobytes() + b"\r\n")


# Auto-select first available video after functions are defined
def initialize_video():
    global current_video_name, vid_path, video_frames
    video_dir = app.config["VIDEO_UPLOADS"]
    if os.path.exists(video_dir):
        # Get all video files and sort them
        video_files = [f for f in os.listdir(video_dir) if allowed_video(f)]
        video_files.sort()

        for filename in video_files:
            current_video_name = filename
            vid_path = os.path.join(video_dir, filename)
            video_frames = cv2.VideoCapture(vid_path)
            if video_frames.isOpened():
                print(f"Auto-selected video: {filename}")
                reset_violation_tracking()
                break
            else:
                video_frames = None
                current_video_name = None
                vid_path = None


initialize_video()


def generate_raw_frames():
    global \
        video_frames, \
        frames_buffer, \
        tracking_loop_count, \
        violation_log, \
        current_loop_violations

    # If no video is loaded, yield a placeholder image
    if video_frames is None or not video_frames.isOpened():
        # Create a black frame with "No video selected" text
        placeholder = np.zeros((480, 640, 3), dtype=np.uint8)
        cv2.putText(
            placeholder,
            "No video selected",
            (150, 240),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.2,
            (255, 255, 255),
            2,
        )
        _, buf = cv2.imencode(".jpg", placeholder)
        while True:
            yield (
                b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + buf.tobytes() + b"\r\n"
            )
            time.sleep(0.1)

    frame_count = 0
    fps = video_frames.get(cv2.CAP_PROP_FPS) or 60  # Default to 30 fps if not available
    frame_delay = 1.0 / fps
    last_frame_time = time.time()

    while True:
        success, frame = video_frames.read()
        if not success:
            # If video ended, restart from beginning
            video_frames.set(cv2.CAP_PROP_POS_FRAMES, 0)
            frame_count = 0

            # Save violations from completed loop
            if tracking_loop_count == 0 and current_loop_violations:
                violation_log = current_loop_violations.copy()
                tracking_loop_count += 1
                print(f"Saved violations: {violation_log}")

            success, frame = video_frames.read()
            if not success:
                time.sleep(0.01)
                continue

        # Control frame rate
        current_time = time.time()
        time_since_last_frame = current_time - last_frame_time
        if time_since_last_frame < frame_delay:
            time.sleep(frame_delay - time_since_last_frame)
        last_frame_time = time.time()

        # Add frame to buffer with frame number
        frame_count += 1
        frames_buffer.append(frame.copy())

        # Keep buffer size reasonable (max 60 frames for smoother playback)
        if len(frames_buffer) > 60:
            # Remove oldest frames
            frames_buffer = frames_buffer[-60:]

        _, buf = cv2.imencode(".jpg", frame)
        yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + buf.tobytes() + b"\r\n")


def generate_processed_frames(
    conf_: float = 0.25, detector_names: list[str] | None = None
):
    """Read frames, run multiple detectors, overlay boxes and yield MJPEG."""
    global last_email_time

    # If no video is loaded, yield a placeholder image
    if video_frames is None or not video_frames.isOpened():
        # Create a black frame with "No video selected" text
        placeholder = np.zeros((480, 640, 3), dtype=np.uint8)
        cv2.putText(
            placeholder,
            "No video selected",
            (150, 240),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.2,
            (255, 255, 255),
            2,
        )
        _, buf = cv2.imencode(".jpg", placeholder)
        while True:
            yield (
                b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + buf.tobytes() + b"\r\n"
            )
            time.sleep(0.1)

    if detector_names is None:
        detector_names = ["ppe"]

    # Instantiate each detector once
    detectors = [get_detector(n)(conf=conf_) for n in detector_names]

    # Assign a colour per detector (BGR)
    colour_map = {
        "ppe": (255, 0, 0),  # Blue
    }

    processed_index = 0
    while True:
        if len(frames_buffer) == 0:
            time.sleep(0.01)
            continue

        # Process frames sequentially to avoid skipping
        buffer_len = len(frames_buffer)

        # If we've processed all frames, wait for new ones
        if processed_index >= buffer_len:
            # If way ahead, reset to catch up with buffer
            if processed_index > buffer_len + 30:
                processed_index = max(0, buffer_len - 10)
            else:
                time.sleep(0.01)
                continue

        # Get the frame at our current index
        try:
            frame = frames_buffer[processed_index].copy()
            processed_index += 1
        except IndexError:
            # Buffer was trimmed, reset index
            processed_index = max(0, buffer_len - 1)
            continue

        # Iterate over detectors
        violations_detected = False
        for name, det in zip(detector_names, detectors):
            colour = colour_map.get(name, (0, 255, 0))
            for box, label in det.detect(frame):
                # Check if this is a violation
                if name == "ppe" and any(
                    v in label for v in ["NO-Hardhat", "NO-Mask", "NO-Safety Vest"]
                ):
                    violations_detected = True
                    # Extract the class name from the label (e.g., "NO-Hardhat 0.95" -> "NO-Hardhat")
                    violation_class = label.split()[0]
                    record_violation(violation_class)

                # PPE detector returns (x1, y1, x2, y2) for bounding box
                x1, y1, x2, y2 = box
                cv2.rectangle(frame, (x1, y1), (x2, y2), colour, 2)
                text_origin = (x1, max(0, y1 - 6))

                cv2.putText(
                    frame,
                    label,
                    text_origin,
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    colour,
                    2,
                    cv2.LINE_AA,
                )

        # Email alert: only if violations detected
        if violations_detected and email_alert_enabled and email_recipient:
            current_time = time.time()
            if current_time - last_email_time > EMAIL_COOLDOWN_SEC:
                # capture JPEG bytes
                _, jpeg_buf = cv2.imencode(".jpg", frame)
                try:
                    prepare_and_send_email(
                        sender="support.ai@giindia.com",
                        recipient=email_recipient,
                        subject="PPE Violation Detected",
                        message_text="A PPE violation was detected at "
                        + time.strftime("%Y-%m-%d %H:%M:%S"),
                        im0=frame,
                    )
                    last_email_time = current_time
                except Exception as e:
                    print("Email send failed:", e)

        _, buf = cv2.imencode(".jpg", frame)
        yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + buf.tobytes() + b"\r\n")


# New routes for multi-source dashboard
@app.route("/dashboard")
def dashboard():
    """Main dashboard view."""
    return render_template(
        "dashboard.html",
        email_recipient=email_recipient,
        email_alert_enabled=email_alert_enabled,
    )


@app.route("/camera/<source_id>")
def camera_view(source_id):
    """Individual camera view."""
    source = sources.get(source_id)
    if not source:
        return redirect(url_for("dashboard"))
    return render_template("camera_view.html", source=source)


@app.route("/source_video_raw/<source_id>")
def source_video_raw(source_id):
    """Raw video stream for a specific source."""
    return Response(
        generate_source_frames(source_id, processed=False),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )


@app.route("/source_video_processed/<source_id>")
def source_video_processed(source_id):
    """Processed video stream for a specific source."""
    conf = float(request.args.get("conf", default_confidence))
    detector_param = request.args.get("detectors", "ppe")
    detector_names = [d.strip() for d in detector_param.split(",") if d.strip()]

    return Response(
        generate_source_frames(
            source_id, processed=True, conf_=conf, detector_names=detector_names
        ),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )


# API endpoints
@app.route("/api/sources", methods=["GET", "POST"])
def api_sources():
    """Get all sources or add a new source."""
    if request.method == "GET":
        # Return all sources
        sources_list = []
        for source_id, source in sources.items():
            sources_list.append(
                {
                    "id": source.id,
                    "name": source.name,
                    "type": source.type,
                    "path": source.path,
                    "status": source.status,
                    "fps": source.fps,
                }
            )
        return jsonify(sources_list)

    elif request.method == "POST":
        # Add new source
        data = request.get_json()
        name = data.get("name", "").strip()
        source_type = data.get("type")
        path = data.get("path")

        if not all([source_type, path]):
            return jsonify({"error": "Missing required fields"}), 400

        if source_type == "file" and not allowed_video(path):
            return jsonify({"error": "Invalid video file type"}), 400

        # Auto-generate name if not provided
        if not name:
            if source_type == "file":
                # Use filename without extension
                name = path.rsplit(".", 1)[0].replace("_", " ").title()
            else:
                # Use stream URL domain or IP
                match = re.search(r"://([^:/]+)", path)
                if match:
                    name = f"Stream - {match.group(1)}"
                else:
                    name = f"Stream {len(sources) + 1}"

        source = add_source(name, source_type, path)
        if source:
            return jsonify(
                {
                    "id": source.id,
                    "name": source.name,
                    "type": source.type,
                    "path": source.path,
                    "status": source.status,
                    "fps": source.fps,
                }
            )
        else:
            return jsonify({"error": "Failed to add source"}), 500


@app.route("/api/sources/<source_id>", methods=["DELETE"])
def api_source_delete(source_id):
    """Delete a source."""
    if remove_source(source_id):
        return jsonify({"success": True})
    else:
        return jsonify({"error": "Source not found"}), 404


@app.route("/api/settings", methods=["POST"])
def api_settings():
    """Update application settings."""
    global email_alert_enabled, email_recipient, default_confidence

    data = request.get_json()
    if "email_recipient" in data:
        email_recipient = data["email_recipient"]
    if "email_alert_enabled" in data:
        email_alert_enabled = data["email_alert_enabled"]
    if "confidence_threshold" in data:
        default_confidence = data["confidence_threshold"]

    return jsonify({"success": True})


# Server-Sent Events endpoint
@app.route("/events")
def events():
    """Server-Sent Events endpoint for real-time updates."""

    def generate():
        # Send initial stats
        stats = get_dashboard_stats()
        yield f"event: stats\ndata: {json.dumps(stats)}\n\n"

        # Send existing detection events from the last hour
        cutoff_time = datetime.now() - timedelta(hours=1)
        recent_events = [e for e in detection_events if e["timestamp"] > cutoff_time]

        # Convert datetime objects to ISO format for JSON serialization
        for event in recent_events:
            event_data = {
                "source_id": event["source_id"],
                "timestamp": event["timestamp"].isoformat(),
                "violation_type": event["violation_type"],
                "confidence": event["confidence"],
                "event_id": event.get("event_id", ""),
                "frame_number": event.get("frame_number", 0),
            }
            yield f"event: detection\ndata: {json.dumps(event_data)}\n\n"

        # Send periodic stats updates
        last_stats_update = time.time()

        while True:
            try:
                # Get event from queue with short timeout
                event_type, event_data = event_queue.get(timeout=1)
                yield f"event: {event_type}\ndata: {json.dumps(event_data)}\n\n"
            except queue.Empty:
                # Check if we should send stats update
                current_time = time.time()
                if current_time - last_stats_update > 5:  # Update stats every 5 seconds
                    stats = get_dashboard_stats()
                    yield f"event: stats\ndata: {json.dumps(stats)}\n\n"
                    last_stats_update = current_time
            except Exception as e:
                print(f"SSE error: {e}")
                break

    return Response(generate(), mimetype="text/event-stream")


def get_dashboard_stats():
    """Get current dashboard statistics."""
    active_sources = sum(1 for s in sources.values() if s.status == "active")
    total_violations = sum(sum(s.violation_counts.values()) for s in sources.values())

    # Calculate compliance rate based on frames without violations
    total_frames = sum(s.total_frames_processed for s in sources.values())
    frames_with_violations = sum(s.frames_with_violations for s in sources.values())

    if total_frames > 0:
        compliance_rate = ((total_frames - frames_with_violations) / total_frames) * 100
    else:
        compliance_rate = 100

    # Get last detection time
    last_detections = [s.last_detection for s in sources.values() if s.last_detection]
    last_detection = max(last_detections).isoformat() if last_detections else None

    return {
        "active_sources": active_sources,
        "active_violations": total_violations,
        "compliance_rate": compliance_rate,
        "last_detection": last_detection,
    }


# Legacy routes (keeping for backward compatibility)
@app.route("/video_raw")
def video_raw():
    return Response(
        generate_raw_frames(), mimetype="multipart/x-mixed-replace; boundary=frame"
    )


@app.route("/video_processed")
def video_processed():
    conf = float(request.args.get("conf", 0.5))
    detector_param = request.args.get("detectors", "ppe")
    detector_names = [d.strip() for d in detector_param.split(",") if d.strip()]

    return Response(
        generate_processed_frames(conf_=conf, detector_names=detector_names),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )


@app.route("/", methods=["GET", "POST"])
def index():
    # Redirect to dashboard by default
    return redirect(url_for("dashboard"))


@app.route("/legacy", methods=["GET", "POST"])
def legacy_view():
    # Keep the old single-source view for backward compatibility
    return render_template(
        "index.html", current_video=current_video_name or "No video selected"
    )


@app.route("/video_list", methods=["GET"])
def video_list():
    """Return list of available videos in the video folder."""
    video_dir = app.config["VIDEO_UPLOADS"]
    videos = []

    if os.path.exists(video_dir):
        for filename in os.listdir(video_dir):
            if allowed_video(filename):
                videos.append(filename)

    # Sort videos alphabetically
    videos.sort()

    return json.dumps({"videos": videos, "current": current_video_name})


@app.route("/submit", methods=["POST"])
def submit_form():
    global \
        video_frames, \
        frames_buffer, \
        vid_path, \
        current_video_name, \
        email_alert_enabled, \
        email_recipient, \
        violation_log

    # Change video source
    if "change_video" in request.form:
        video_name = request.form.get("video_name", "")

        if not video_name:
            return "No video specified", 400

        new_path = os.path.join(app.config["VIDEO_UPLOADS"], video_name)
        if not os.path.exists(new_path):
            return f"Video {video_name} not found", 404

        # Update globals
        current_video_name = video_name
        vid_path = new_path
        video_frames = cv2.VideoCapture(vid_path)
        frames_buffer.clear()
        reset_violation_tracking()  # Reset violation tracking for new video

        if not video_frames.isOpened():
            return f"Error opening video {video_name}", 500

        # Get the new video's FPS
        fps = video_frames.get(cv2.CAP_PROP_FPS)
        print(f"Loaded {video_name} with {fps:.2f} FPS")

        return f"Switched to {video_name}"

    # Download report
    if "download_button" in request.form:
        # Create detailed violation report
        violation_details = ""
        if violation_log:
            violation_details = "\n\nViolation Details:\n"
            violation_details += "-" * 50 + "\n"
            violation_categories = []
            for violation_class, data in sorted(violation_log.items()):
                violation_details += f"\n{violation_class}:\n"
                violation_details += f"  - Number of Detections: {data['count']}\n"
                violation_details += f"  - First Detected: {data['first_seen']}\n"
                violation_categories.append(violation_class)
            violation_details += (
                f"\nTotal Violation Categories: {len(violation_categories)}\n"
            )
        else:
            violation_details = "\n\nNo violations detected.\n"

        report_content = f"""PPE Violation Detection Report
Generated: {time.strftime("%Y-%m-%d %H:%M:%S")}
Current Video: {current_video_name}

Email Alerts: {"Enabled" if email_alert_enabled else "Disabled"}
Alert Recipient: {email_recipient if email_recipient else "Not set"}

Detection Configuration:
- Confidence Threshold: 0.5
- Active Detectors: PPE
{violation_details}

Note: Violations are tracked from video start until the first complete loop.
"""

        # Create a BytesIO object to send as file
        report_bytes = BytesIO(report_content.encode("utf-8"))
        report_bytes.seek(0)

        return send_file(
            report_bytes,
            mimetype="text/plain",
            as_attachment=True,
            download_name=f"ppe_report_{time.strftime('%Y%m%d_%H%M%S')}.txt",
        )

    # Email alert toggle
    if "alert_email_checkbox" in request.form:
        enabled_str = request.form.get("alert_email_checkbox", "false")
        email_alert_enabled = enabled_str.lower() in ("true", "1", "on")
        email_recipient = request.form.get("alert_email_textbox", None)
        status_msg = f"Email alerts {'enabled' if email_alert_enabled else 'disabled'} for {email_recipient}"
        return status_msg

    return "No action taken"


if __name__ == "__main__":
    # Allow overriding the port via environment variable, default to 5000.
    port = int(os.getenv("PORT", 5001))
    app.run(debug=True, host="0.0.0.0", port=port)
