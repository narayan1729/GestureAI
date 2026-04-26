"""
core/vision_engine.py
=====================
Handles camera capture and MediaPipe face mesh processing.
Returns raw landmark data; gaze/click interpretation is in input_strategies.py.

Patched for mediapipe >= 0.10.30 (Tasks API).
"""

import cv2
import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision as mp_vision
from mediapipe.tasks.python.vision import FaceLandmarkerOptions, RunningMode
import threading
import queue
import time
import urllib.request
import os


# ---------------------------------------------------------------------------
# Download the required model file if not already present
# ---------------------------------------------------------------------------
MODEL_PATH = os.path.join(os.path.dirname(__file__), "face_landmarker.task")
MODEL_URL  = (
    "https://storage.googleapis.com/mediapipe-models/"
    "face_landmarker/face_landmarker/float16/latest/face_landmarker.task"
)

def _ensure_model():
    if not os.path.exists(MODEL_PATH):
        print("[VisionEngine] Downloading face_landmarker.task (~6 MB) …")
        urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)
        print("[VisionEngine] Model downloaded.")

# ---------------------------------------------------------------------------


class VisionEngine:
    """
    Runs face mesh detection in a background thread, feeding frames
    into a bounded queue so the UI thread never blocks on camera I/O.
    """

    def __init__(self, camera_index: int = 0, target_fps: int = 30):
        self.target_fps   = target_fps
        self._frame_q     = queue.Queue(maxsize=2)
        self._running     = False
        self._lock        = threading.Lock()
        self._last_result = None  # (image, landmarks_or_None, h, w)

        # --- MediaPipe Tasks API (mediapipe >= 0.10.30) ---
        _ensure_model()

        options = FaceLandmarkerOptions(
            base_options=mp_python.BaseOptions(model_asset_path=MODEL_PATH),
            running_mode=RunningMode.VIDEO,
            num_faces=1,
            output_face_blendshapes=False,
            output_facial_transformation_matrixes=False,
        )
        self.face_landmarker = mp_vision.FaceLandmarker.create_from_options(options)
        # --------------------------------------------------

        self.cap = cv2.VideoCapture(camera_index)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH,  640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        self.cap.set(cv2.CAP_PROP_FPS,          target_fps)

        if not self.cap.isOpened():
            raise RuntimeError(
                "Cannot open camera. Check that a webcam is connected "
                "and not in use by another application."
            )

        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()

    # ------------------------------------------------------------------
    # Background capture loop
    # ------------------------------------------------------------------

    def _capture_loop(self):
        self._running = True
        interval      = 1.0 / self.target_fps

        while self._running:
            t0 = time.monotonic()

            ok, frame = self.cap.read()
            if not ok:
                time.sleep(interval)
                continue

            frame     = cv2.flip(frame, 1)                        # mirror
            rgb       = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_image  = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)

            # Tasks API requires a timestamp in milliseconds
            timestamp_ms = int(time.monotonic() * 1000)
            detection    = self.face_landmarker.detect_for_video(mp_image, timestamp_ms)

            h, w = frame.shape[:2]

            # Wrap result in a lightweight object so input_strategies.py
            # keeps working unchanged (it reads .landmark[i].x / .y / .z)
            landmarks = None
            if detection.face_landmarks:
                landmarks = _LandmarkList(detection.face_landmarks[0])

            payload = (frame, landmarks, h, w)

            with self._lock:
                self._last_result = payload

            try:
                self._frame_q.put_nowait(payload)
            except queue.Full:
                pass

            elapsed = time.monotonic() - t0
            sleep   = interval - elapsed
            if sleep > 0:
                time.sleep(sleep)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_latest(self):
        """
        Returns the most recent (frame, landmarks, h, w) without blocking.
        Returns None if no frame has been captured yet.
        """
        with self._lock:
            return self._last_result

    def release(self):
        self._running = False
        self._thread.join(timeout=2.0)
        self.cap.release()
        self.face_landmarker.close()


# ---------------------------------------------------------------------------
# Compatibility shim
# ---------------------------------------------------------------------------

class _LandmarkList:
    """
    Wraps the new NormalizedLandmark list so existing code that accesses
    landmarks via  .landmark[i].x / .y / .z  keeps working without changes.
    """
    def __init__(self, landmark_list):
        self.landmark = landmark_list   # already a list of NormalizedLandmark