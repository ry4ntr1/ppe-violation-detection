import os.path
import cv2
import validators
from flask import Flask, render_template, request, Response
from send_mail import prepare_and_send_email
from detection import get_detector, DETECTOR_REGISTRY
import time

# Initialize the Flask application
app = Flask(__name__)
app.config["VIDEO_UPLOADS"] = "static/video"
app.config["ALLOWED_VIDEO_EXTENSIONS"] = ["MP4", "MOV", "AVI", "WMV", "WEBM"]

# Secret key for the session
app.config['SECRET_KEY'] = 'ppe_violation_detection'

# global variables
frames_buffer = []  # buffer to store frames from a stream
vid_path = app.config["VIDEO_UPLOADS"] + '/vid.mp4'  # path to uploaded/stored video file
video_frames = cv2.VideoCapture(vid_path)  # video capture object
# detectors enabled for processing
selected_detectors = list(DETECTOR_REGISTRY.keys())


def allowed_video(filename):
    """
    A function to check if the uploaded file is a video

    Args:
        filename (str): name of the uploaded file

    Returns:
        bool: True if the file is a video, False otherwise
    """
    if "." not in filename:
        return False

    extension = filename.rsplit(".", 1)[1]

    if extension.upper() in app.config["ALLOWED_VIDEO_EXTENSIONS"]:
        return True
    else:
        return False


def generate_raw_frames():
    """
    A function to yield unprocessed frames from stored video file or ip cam stream

    Yields:
        bytes: a frame from the video file or ip cam stream
    """
    global video_frames

    while True:
        # Keep reading the frames from the video file or ip cam stream
        success, frame = video_frames.read()

        if success:
            # create a copy of the frame to store in the buffer
            frame_copy = frame.copy()

            # store the frame in the buffer for violation detection
            frames_buffer.append(frame_copy)

            # compress the frame and store it in the memory buffer
            _, buffer = cv2.imencode('.jpg', frame)
            # convert the buffer to bytes
            frame = buffer.tobytes()
            # yield the frame to the browser
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')


def generate_processed_frames(detectors=None, conf_=0.25):
    """
    A function to yield processed frames from stored video file or ip cam stream after violation detection

    Args:
        conf_ (float, optional): confidence threshold for the detection. Defaults to 0.25.

    Yields:
        bytes: a processed frame from the video file or ip cam stream
    """
    global frames_buffer

    if detectors is None:
        detectors = selected_detectors
    detector_instances = []
    for name in detectors:
        DetClass = get_detector(name)
        det = DetClass(conf=conf_)
        det.load_model()
        detector_instances.append(det)

    while True:
        if not frames_buffer:
            time.sleep(0.01)
            continue
        frame = frames_buffer.pop(0)
        for det in detector_instances:
            results = det.detect(frame)
            for box, label in results:
                x1, y1, x2, y2 = box
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                cv2.putText(frame, label, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX,
                            0.5, (0, 255, 0), 1, cv2.LINE_AA)
        _, buffer = cv2.imencode('.jpg', frame)
        frame = buffer.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')


@app.route('/video_raw')
def video_raw():
    """
    A function to handle the requests for the raw video stream

    Returns:
        Response: a response object containing the raw video stream
    """

    return Response(generate_raw_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')


@app.route('/video_processed')
def video_processed():
    """Return the processed video stream with selected detectors."""
    conf = float(request.args.get('conf', 0.75))
    detectors_arg = request.args.get('detectors')
    detectors = None
    if detectors_arg:
        detectors = [d.strip() for d in detectors_arg.split(',') if d.strip()]
    return Response(generate_processed_frames(detectors=detectors, conf_=conf),
                    mimetype='multipart/x-mixed-replace; boundary=frame')


@app.route('/', methods=["GET", "POST"])
def index():
    """
    A function to handle the requests from the web page

    Returns:
        render_template: the index.html page (home page)
    """
    return render_template('index.html')


@app.route('/submit', methods=['POST'])
def submit_form():
    """
    A function to handle the requests from the HTML form on the web page

    Returns:
        str: a string containing the response message
    """
    # global variables
    # noinspection PyGlobalUndefined
    global vid_path, video_frames, frames_buffer, selected_detectors

    # if the request is a POST request made by user interaction with the HTML form
    if request.method == "POST":
        # print(request.form)vid_ip_path.startswith('http://')

        # handle video upload request
        if request.files:
            video = request.files['video']

            # check if video file is uploaded or not
            if video.filename == '':
                # display a flash alert message on the web page
                return "That video must have a file name"

            # check if the uploaded file is a video
            elif not allowed_video(video.filename):
                # display a flash alert message on the web page
                return "Unsupported video. The video file must be in MP4, MOV, AVI, WEBM or WMV format."
            else:
                # default video name
                filename = 'vid.mp4'
                # ensure video size is less than 200MB
                if video.content_length > 200 * 1024 * 1024:
                    return "Error! That video is too large"
                else:
                    # noinspection PyBroadException
                    try:
                        video.save(os.path.join(app.config["VIDEO_UPLOADS"], filename))
                        return "That video is successfully uploaded"
                    except Exception as e:
                        print(e)
                        return "Error! The video could not be saved"

        # update selected detectors if provided
        if 'detectors' in request.form:
            selected_detectors = [d for d in request.form.getlist('detectors') if d]

        # handle inference request for a video file
        elif 'inference_video_button' in request.form:
            video_frames = cv2.VideoCapture(vid_path)
            # clear the buffer of frames that may have been stored from a previous inference
            frames_buffer.clear()
            # check if the video is opened
            if not video_frames.isOpened():
                return 'Error in opening video', 500
            else:
                frames_buffer.clear()
                return 'success'

        # handle inference request for a live stream via IP camera
        elif 'live_inference_button' in request.form:
            # to be implemented
            pass

        # handle email request# handle alert email request
        elif 'alert_email_checkbox' in request.form:
            email_checkbox_value = request.form['alert_email_checkbox']
            if email_checkbox_value == 'false':
                return "Alert email is disabled"
            else:
                alert_recipient = request.form['alert_email_textbox']
                # send email
                prepare_and_send_email(sender='hamza2019cs148@abesit.edu.in',
                                       recipient=alert_recipient,
                                       subject='Greeting from Global Infoventures',
                                       message_text='Hello, this is a test email from Global Infoventures',
                                       im0=cv2.imread('static/test.jpg'))
                return f"Alert email is sent at {alert_recipient} with the attached image"

        # handle download request for the detections summary report
        elif 'download_button' in request.form:
            return Response(open('static/reports/detections_summary.txt', 'r').read(),
                            mimetype='text/plain',
                            headers={"Content-Disposition": "attachment;filename=detections_summary.txt"})


if __name__ == "__main__":
    app.run(debug=True)
