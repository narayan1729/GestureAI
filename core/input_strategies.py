"""
core/input_strategies.py
========================
Pluggable input detection strategies.

Each strategy implements get_gaze_and_click() → (h_ratio, v_ratio, is_clicked).
Swap strategies at runtime without touching the UI layer.

Improvements over v1:
  - Gaze smoothing via rolling average (reduces jitter)
  - Blink default raised to 1.2s (fewer accidental triggers)
  - Dwell default raised to 2.5s (more forgiving)
  - Scan interval default raised to 2.0s (more reaction time)
"""

from abc import ABC, abstractmethod
import time
import math
from collections import deque


class InputStrategy(ABC):

    @abstractmethod
    def get_gaze_and_click(self, face_landmarks, frame_shape) -> tuple[float, float, bool]:
        ...

    def reset(self):
        pass


# ---------------------------------------------------------------------------
# Strategy 1 — Iris Gaze + Blink-to-Click
# ---------------------------------------------------------------------------

class IrisBlinkStrategy(InputStrategy):

    _LEFT_EYE  = [362, 385, 387, 263, 373, 380]
    _RIGHT_EYE = [33,  160, 158, 133, 153, 144]
    _OUTER_CORNER = 33
    _INNER_CORNER = 133
    _TOP_LID      = 159
    _BOT_LID      = 145
    _IRIS_CENTER  = 468

    def __init__(self,
                 click_duration: float = 1.2,    # raised from 0.8
                 baseline_len: int = 150,
                 threshold_ratio: float = 0.72,
                 smooth_frames: int = 6):         # NEW: gaze smoothing
        self.click_duration    = click_duration
        self.threshold_ratio   = threshold_ratio
        self.baseline          = deque(maxlen=baseline_len)
        self.dynamic_threshold = 0.20
        self._eye_closed       = False
        self._blink_start      = 0.0
        self._click_consumed   = False

        # Gaze smoothing buffers
        self._h_buf = deque(maxlen=smooth_frames)
        self._v_buf = deque(maxlen=smooth_frames)

    @staticmethod
    def _dist(p1, p2) -> float:
        return math.dist(p1, p2)

    def _ear(self, pts) -> float:
        v1 = self._dist(pts[1], pts[5])
        v2 = self._dist(pts[2], pts[4])
        h  = self._dist(pts[0], pts[3])
        return (v1 + v2) / (2.0 * h) if h > 0 else 0.0

    def get_gaze_and_click(self, face_landmarks, frame_shape) -> tuple[float, float, bool]:
        h, w = frame_shape[:2]
        lm   = face_landmarks.landmark

        def px(idx):
            return (lm[idx].x * w, lm[idx].y * h)

        # ── EAR (blink) ──────────────────────────────────────────────
        left_pts  = [px(i) for i in self._LEFT_EYE]
        right_pts = [px(i) for i in self._RIGHT_EYE]
        avg_ear   = (self._ear(left_pts) + self._ear(right_pts)) / 2.0

        if self.baseline:
            self.dynamic_threshold = (
                sum(self.baseline) / len(self.baseline)
            ) * self.threshold_ratio

        is_clicked = False
        now = time.monotonic()

        if avg_ear < self.dynamic_threshold:
            if not self._eye_closed:
                self._eye_closed     = True
                self._blink_start    = now
                self._click_consumed = False
            else:
                if (now - self._blink_start >= self.click_duration
                        and not self._click_consumed):
                    is_clicked           = True
                    self._click_consumed = True
        else:
            self._eye_closed     = False
            self._click_consumed = False
            self.baseline.append(avg_ear)

        # ── Iris gaze (smoothed) ──────────────────────────────────────
        iris_x  = lm[self._IRIS_CENTER].x * w
        iris_y  = lm[self._IRIS_CENTER].y * h
        outer_x = lm[self._OUTER_CORNER].x * w
        inner_x = lm[self._INNER_CORNER].x * w
        top_y   = lm[self._TOP_LID].y * h
        bot_y   = lm[self._BOT_LID].y * h

        raw_h = ((iris_x - outer_x) / (inner_x - outer_x)
                 if abs(inner_x - outer_x) > 1 else 0.5)
        raw_v = ((iris_y - top_y) / (bot_y - top_y)
                 if abs(bot_y - top_y) > 1 else 0.5)

        raw_h = max(0.0, min(1.0, raw_h))
        raw_v = max(0.0, min(1.0, raw_v))

        self._h_buf.append(raw_h)
        self._v_buf.append(raw_v)

        h_ratio = sum(self._h_buf) / len(self._h_buf)
        v_ratio = sum(self._v_buf) / len(self._v_buf)

        return h_ratio, v_ratio, is_clicked

    @property
    def ear_info(self) -> dict:
        return {
            "threshold": self.dynamic_threshold,
            "baseline_size": len(self.baseline),
        }

    def reset(self):
        self._eye_closed     = False
        self._click_consumed = False
        self._blink_start    = 0.0
        self._h_buf.clear()
        self._v_buf.clear()


# ---------------------------------------------------------------------------
# Strategy 2 — Iris Gaze + Dwell-to-Click
# ---------------------------------------------------------------------------

class IrisDwellStrategy(InputStrategy):

    _OUTER_CORNER = 33
    _INNER_CORNER = 133
    _TOP_LID      = 159
    _BOT_LID      = 145
    _IRIS_CENTER  = 468

    def __init__(self,
                 dwell_time: float = 2.5,        # raised from 2.0
                 h_center: float = 0.50,
                 v_center: float = 0.50,          # raised from 0.45
                 smooth_frames: int = 8):         # NEW: more smoothing for dwell
        self.dwell_time   = dwell_time
        self.h_center     = h_center
        self.v_center     = v_center
        self._dwell_start = 0.0
        self._last_quad   = None
        self._fired       = False
        self._progress    = 0.0

        # Gaze smoothing buffers
        self._h_buf = deque(maxlen=smooth_frames)
        self._v_buf = deque(maxlen=smooth_frames)

    def _quadrant(self, h, v) -> str:
        row = "Top"    if v < self.v_center else "Bottom"
        col = "Left"   if h < self.h_center else "Right"
        return row + col

    def get_gaze_and_click(self, face_landmarks, frame_shape) -> tuple[float, float, bool]:
        h_shape, w_shape = frame_shape[:2]
        lm = face_landmarks.landmark

        iris_x  = lm[self._IRIS_CENTER].x * w_shape
        iris_y  = lm[self._IRIS_CENTER].y * h_shape
        outer_x = lm[self._OUTER_CORNER].x * w_shape
        inner_x = lm[self._INNER_CORNER].x * w_shape
        top_y   = lm[self._TOP_LID].y * h_shape
        bot_y   = lm[self._BOT_LID].y * h_shape

        raw_h = max(0.0, min(1.0,
            (iris_x - outer_x) / (inner_x - outer_x)
            if abs(inner_x - outer_x) > 1 else 0.5))
        raw_v = max(0.0, min(1.0,
            (iris_y - top_y) / (bot_y - top_y)
            if abs(bot_y - top_y) > 1 else 0.5))

        # Smooth gaze before quadrant decision
        self._h_buf.append(raw_h)
        self._v_buf.append(raw_v)
        h_ratio = sum(self._h_buf) / len(self._h_buf)
        v_ratio = sum(self._v_buf) / len(self._v_buf)

        quad = self._quadrant(h_ratio, v_ratio)
        now  = time.monotonic()

        if quad != self._last_quad:
            self._last_quad   = quad
            self._dwell_start = now
            self._fired       = False
            self._progress    = 0.0
        else:
            elapsed        = now - self._dwell_start
            self._progress = min(1.0, elapsed / self.dwell_time)

        is_clicked = False
        if self._progress >= 1.0 and not self._fired:
            is_clicked   = True
            self._fired  = True

        return h_ratio, v_ratio, is_clicked

    @property
    def dwell_progress(self) -> float:
        return self._progress

    def reset(self):
        self._last_quad   = None
        self._dwell_start = 0.0
        self._fired       = False
        self._progress    = 0.0
        self._h_buf.clear()
        self._v_buf.clear()


# ---------------------------------------------------------------------------
# Strategy 3 — Switch Scan
# ---------------------------------------------------------------------------

class SwitchScanStrategy(InputStrategy):

    QUAD_ORDER = ["TopLeft", "TopRight", "BottomLeft", "BottomRight"]

    def __init__(self, scan_interval: float = 2.0):   # raised from 1.5
        self.scan_interval   = scan_interval
        self._idx            = 0
        self._last_advance   = time.monotonic()
        self._switch_pressed = False

    def advance(self):
        self._switch_pressed = True

    def get_gaze_and_click(self, face_landmarks, frame_shape) -> tuple[float, float, bool]:
        now = time.monotonic()
        if now - self._last_advance >= self.scan_interval:
            self._idx          = (self._idx + 1) % 4
            self._last_advance = now

        is_clicked = False
        if self._switch_pressed:
            is_clicked           = True
            self._switch_pressed = False

        return 0.5, 0.5, is_clicked

    @property
    def current_scan_key(self) -> str:
        return self.QUAD_ORDER[self._idx]

    def reset(self):
        self._idx            = 0
        self._switch_pressed = False
        self._last_advance   = time.monotonic()