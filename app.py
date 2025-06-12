import os
import time
import cv2
import numpy as np
from flask import Flask, render_template, request, Response, send_file
from send_mail import prepare_and_send_email
from detection import get_detector  # UPDATED
import json
from io import BytesIO

# Initialize the Flask application
app = Flask(__name__)
app.config["VIDEO_UPLOADS"] = "static/video"
app.config["ALLOWED_VIDEO_EXTENSIONS"] = ["MP4", "MOV", "AVI", "WMV", "WEBM"]
app.config["SECRET_KEY"] = "ppe_violation_detection"

# ensure upload folder exists
os.makedirs(app.config["VIDEO_UPLOADS"], exist_ok=True)

# global state
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
