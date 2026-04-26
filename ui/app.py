"""
ui/app.py
=========
Production-ready accessibility interface.

Architecture:
  VisionEngine (thread)  →  InputStrategy  →  GridUI (main thread)
                                          →  HabitualMemory
                                          →  TTSEngine (thread)
"""

import customtkinter as ctk
import tkinter as tk
import sys
import os
import time

# Allow running from project root
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from core.vision_engine    import VisionEngine
from core.input_strategies import IrisBlinkStrategy, IrisDwellStrategy, SwitchScanStrategy
from memory.habitual_memory import HabitualMemory
from voice.tts_engine      import TTSEngine, phrase_for


# ──────────────────────────────────────────────────────────────────────
# Theme
# ──────────────────────────────────────────────────────────────────────

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

PALETTE = {
    "TopLeft":     {"bg": "#12294a", "hover": "#1a3a66", "icon": "💧", "label": "Water / Drink"},
    "TopRight":    {"bg": "#3a1f0d", "hover": "#4d2a10", "icon": "🍽", "label": "Food / Eat"},
    "BottomLeft":  {"bg": "#0d2e1a", "hover": "#113d22", "icon": "🚻", "label": "Washroom"},
    "BottomRight": {"bg": "#2e0d0d", "hover": "#3d1010", "icon": "🆘", "label": "Emergency / Help"},
}

HIGHLIGHT_COLOR  = "#00ff88"
EMERGENCY_COLOR  = "#ff4444"
FONT_ICON        = ("Segoe UI Emoji", 44)
FONT_LABEL       = ("Arial", 28, "bold")
FONT_SUB         = ("Arial", 13)
FONT_DEBUG       = ("Courier New", 11)
FONT_STATUS      = ("Arial", 16, "bold")
FONT_MODE        = ("Arial", 11, "bold")

UPDATE_MS = 33   # ~30 fps


# ──────────────────────────────────────────────────────────────────────
# Dwell progress canvas widget
# ──────────────────────────────────────────────────────────────────────

class DwellRing(ctk.CTkCanvas):
    SIZE = 36

    def __init__(self, parent, **kwargs):
        super().__init__(parent,
                         width=self.SIZE, height=self.SIZE,
                         bg="#000001",
                         highlightthickness=0,
                         **kwargs)
        self._progress = 0.0
        self._draw()

    def set_progress(self, p: float):
        self._progress = max(0.0, min(1.0, p))
        self._draw()

    def _draw(self):
        self.delete("all")
        s = self.SIZE
        pad = 4
        self.create_arc(pad, pad, s - pad, s - pad,
                        start=90, extent=-359.9,
                        style="arc", outline="#333333", width=3)
        if self._progress > 0:
            self.create_arc(pad, pad, s - pad, s - pad,
                            start=90, extent=-(self._progress * 359.9),
                            style="arc", outline=HIGHLIGHT_COLOR, width=3)


# ──────────────────────────────────────────────────────────────────────
# Quadrant cell
# ──────────────────────────────────────────────────────────────────────

class QuadrantCell(ctk.CTkFrame):
    def __init__(self, parent, key: str, **kwargs):
        cfg  = PALETTE[key]
        super().__init__(parent, fg_color=cfg["bg"],
                         corner_radius=18, **kwargs)

        self.key = key
        self._cfg = cfg

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure((0, 1, 2), weight=1)

        self._icon_lbl = ctk.CTkLabel(self, text=cfg["icon"],
                                       font=FONT_ICON, text_color="white")
        self._icon_lbl.grid(row=0, column=0, pady=(20, 0))

        self._main_lbl = ctk.CTkLabel(self, text=cfg["label"],
                                       font=FONT_LABEL, text_color="white")
        self._main_lbl.grid(row=1, column=0)

        self._sub_lbl  = ctk.CTkLabel(self, text="",
                                       font=FONT_SUB,
                                       text_color="#aaaaaa",
                                       wraplength=280)
        self._sub_lbl.grid(row=2, column=0, pady=(0, 20))

        self._ring = DwellRing(self)
        self._ring.place(relx=1.0, rely=1.0, anchor="se", x=-10, y=-10)

        self._selected_flash = 0

    def set_active(self, active: bool):
        if active:
            self.configure(border_width=5, border_color=HIGHLIGHT_COLOR)
        else:
            self.configure(border_width=0)
            self._ring.set_progress(0.0)

    def set_sub(self, text: str):
        self._sub_lbl.configure(text=text)

    def set_dwell(self, progress: float):
        self._ring.set_progress(progress)

    def flash_selected(self):
        self.configure(fg_color=HIGHLIGHT_COLOR)
        self.after(220, lambda: self.configure(fg_color=self._cfg["bg"]))


# ──────────────────────────────────────────────────────────────────────
# EAR calibration bar
# ──────────────────────────────────────────────────────────────────────

class EARBar(ctk.CTkFrame):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, fg_color="#1a1a1e", corner_radius=10, **kwargs)

        self.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(self, text="EAR baseline",
                     font=("Arial", 11), text_color="#555555").grid(
            row=0, column=0, columnspan=3, sticky="w", padx=12, pady=(8, 0))

        self._bar_frame = ctk.CTkFrame(self, fg_color="#252528",
                                       corner_radius=4, height=6)
        self._bar_frame.grid(row=1, column=0, columnspan=3,
                             sticky="ew", padx=12, pady=(4, 8))
        self._bar_frame.grid_propagate(False)
        self._bar_frame.grid_columnconfigure(0, weight=1)

        self._fill = ctk.CTkFrame(self._bar_frame, fg_color="#4ade80",
                                   corner_radius=3, height=6)
        self._fill.place(relx=0, rely=0, relwidth=0.5, relheight=1)

        self._thresh_line = ctk.CTkFrame(self._bar_frame,
                                          fg_color="#f87171",
                                          width=2, corner_radius=0)
        self._thresh_line.place(relx=0.44, rely=-0.5, relheight=2)

        self._val_lbl = ctk.CTkLabel(self, text="EAR: 0.000",
                                      font=FONT_DEBUG, text_color="#4ade80")
        self._val_lbl.grid(row=2, column=0, columnspan=3,
                           sticky="e", padx=12, pady=(0, 6))

    def update(self, ear: float, threshold: float, max_ear: float = 0.5):
        fill_pct   = min(1.0, ear       / max_ear)
        thresh_pct = min(1.0, threshold / max_ear)
        self._fill.place(relwidth=fill_pct)
        self._thresh_line.place(relx=thresh_pct)
        self._val_lbl.configure(
            text=f"EAR: {ear:.3f}  │  threshold: {threshold:.3f}")


# ──────────────────────────────────────────────────────────────────────
# Main application
# ──────────────────────────────────────────────────────────────────────

class AccessibilityApp:

    # Crosshair defaults — auto-calibrated or set manually
    H_CENTER = 0.43   # calibrated to user's resting gaze
    V_CENTER = 0.47   # calibrated to user's resting gaze

    GRID_KEYS = ["TopLeft", "TopRight", "BottomLeft", "BottomRight"]

    def __init__(self):
        self.root = ctk.CTk()
        self.root.title("Edge-AI Accessibility Interface  •  Offline")
        self.root.geometry("1020x760")
        self.root.resizable(True, True)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # Subsystems
        self.vision  = VisionEngine()
        self.memory  = HabitualMemory()
        self.tts     = TTSEngine()
        self._announce_tts_backend()

        # Active strategy
        # IMPROVED DEFAULTS:
        #   - Blink hold raised to 1.2s  (reduces accidental triggers)
        #   - Dwell time set to 2.5s     (more forgiving)
        #   - Scan interval raised to 2.0s (more time to react)
        self._strategies = {
            "Iris + Blink":  IrisBlinkStrategy(click_duration=1.2),
            "Iris + Dwell":  IrisDwellStrategy(dwell_time=2.5,
                                               h_center=self.H_CENTER,
                                               v_center=self.V_CENTER),
            "Switch Scan":   SwitchScanStrategy(scan_interval=2.0),
        }
        self._active_strategy_name = "Iris + Dwell"   # Dwell is most reliable by default
        self._strategy = self._strategies["Iris + Dwell"]

        # State
        self._current_key    = "TopLeft"
        self._last_ear       = 0.30
        self._last_h         = 0.50
        self._last_v         = 0.50
        self._tts_enabled    = True
        self._debug_visible  = True
        self._last_selection = ""

        # Calibration state
        self._calibrating      = False
        self._calib_samples_h  = []
        self._calib_samples_v  = []
        self._calib_deadline   = 0.0

        # Build UI
        self._build_layout()
        self._update_predictions("TopLeft")
        self._start_switch_bind()

    # ──────────────────────────────────────────────────────────────────
    # Layout
    # ──────────────────────────────────────────────────────────────────

    def _build_layout(self):
        self.root.grid_columnconfigure(0, weight=3)
        self.root.grid_columnconfigure(1, weight=1, minsize=260)
        self.root.grid_rowconfigure(0, weight=1)

        self._left = ctk.CTkFrame(self.root, fg_color="transparent")
        self._left.grid(row=0, column=0, sticky="nsew", padx=(12, 6), pady=12)
        self._left.grid_columnconfigure((0, 1), weight=1)
        self._left.grid_rowconfigure((0, 1), weight=1)
        self._left.grid_rowconfigure(2, weight=0)
        self._left.grid_rowconfigure(3, weight=0)

        self._cells: dict[str, QuadrantCell] = {}
        positions = {
            "TopLeft": (0, 0), "TopRight": (0, 1),
            "BottomLeft": (1, 0), "BottomRight": (1, 1),
        }
        for key, (row, col) in positions.items():
            cell = QuadrantCell(self._left, key)
            cell.grid(row=row, column=col, padx=6, pady=6, sticky="nsew")
            self._cells[key] = cell

        self._status_bar = ctk.CTkFrame(self._left, fg_color="#1a1a1e",
                                         corner_radius=10, height=44)
        self._status_bar.grid(row=2, column=0, columnspan=2,
                               sticky="ew", pady=(6, 0))
        self._status_bar.grid_propagate(False)
        self._status_bar.grid_columnconfigure(1, weight=1)

        self._debug_lbl = ctk.CTkLabel(self._status_bar,
                                        text="H=0.50 | V=0.50",
                                        font=FONT_DEBUG, text_color="#555555")
        self._debug_lbl.grid(row=0, column=0, padx=12, sticky="w")

        self._status_lbl = ctk.CTkLabel(self._status_bar,
                                         text="System ready — look at a panel",
                                         font=FONT_STATUS, text_color="#888888")
        self._status_lbl.grid(row=0, column=1, padx=12, sticky="e")

        self._ear_bar = EARBar(self._left)
        self._ear_bar.grid(row=3, column=0, columnspan=2,
                            sticky="ew", pady=(6, 0))

        self._sidebar = ctk.CTkFrame(self.root, fg_color="#111114",
                                      corner_radius=0)
        self._sidebar.grid(row=0, column=1, sticky="nsew", padx=(0, 0), pady=0)
        self._sidebar.grid_columnconfigure(0, weight=1)

        self._build_sidebar()

    def _build_sidebar(self):
        sb  = self._sidebar
        pad = {"padx": 14, "pady": (10, 0), "sticky": "ew"}

        ctk.CTkLabel(sb, text="Controls",
                     font=("Arial", 14, "bold"),
                     text_color="#888888").grid(row=0, column=0,
                                                padx=14, pady=(16, 6),
                                                sticky="w")

        # ── Input mode ────────────────────────────────────────────────
        ctk.CTkLabel(sb, text="Input mode",
                     font=("Arial", 11), text_color="#555555").grid(
            row=1, column=0, **pad)

        self._mode_var = ctk.StringVar(value=self._active_strategy_name)
        self._mode_menu = ctk.CTkOptionMenu(
            sb,
            values=list(self._strategies.keys()),
            variable=self._mode_var,
            command=self._on_mode_change,
            font=("Arial", 12),
            fg_color="#1e1e22",
            button_color="#2a2a2e",
        )
        self._mode_menu.grid(row=2, column=0, **pad)

        # ── Blink duration ────────────────────────────────────────────
        ctk.CTkLabel(sb, text="Blink hold (seconds)",
                     font=("Arial", 11), text_color="#555555").grid(
            row=3, column=0, **pad)

        self._blink_var = ctk.DoubleVar(value=1.2)   # improved default
        self._blink_slider = ctk.CTkSlider(
            sb, from_=0.3, to=2.0, variable=self._blink_var,
            command=self._on_blink_change)
        self._blink_slider.grid(row=4, column=0, **pad)

        self._blink_lbl = ctk.CTkLabel(sb, text="1.2 s",
                                        font=FONT_DEBUG, text_color="#aaaaaa")
        self._blink_lbl.grid(row=5, column=0, padx=14, sticky="e")

        # ── Dwell time ────────────────────────────────────────────────
        ctk.CTkLabel(sb, text="Dwell time (seconds)",
                     font=("Arial", 11), text_color="#555555").grid(
            row=6, column=0, **pad)

        self._dwell_var = ctk.DoubleVar(value=2.5)   # improved default
        self._dwell_slider = ctk.CTkSlider(
            sb, from_=0.5, to=5.0, variable=self._dwell_var,
            command=self._on_dwell_change)
        self._dwell_slider.grid(row=7, column=0, **pad)

        self._dwell_lbl = ctk.CTkLabel(sb, text="2.5 s",
                                        font=FONT_DEBUG, text_color="#aaaaaa")
        self._dwell_lbl.grid(row=8, column=0, padx=14, sticky="e")

        # ── Calibrate button ──────────────────────────────────────────
        self._calib_btn = ctk.CTkButton(
            sb, text="🎯  Calibrate Gaze Center",
            command=self._start_calibration,
            fg_color="#1a3a1a", hover_color="#22502a",
            font=("Arial", 12, "bold"), height=36, corner_radius=8)
        self._calib_btn.grid(row=9, column=0, padx=14, pady=(14, 0), sticky="ew")

        self._calib_lbl = ctk.CTkLabel(
            sb, text="Look straight at screen, then click",
            font=("Arial", 10), text_color="#444444")
        self._calib_lbl.grid(row=10, column=0, padx=14, sticky="w")

        # ── TTS toggle ────────────────────────────────────────────────
        ctk.CTkLabel(sb, text="Voice output",
                     font=("Arial", 11), text_color="#555555").grid(
            row=11, column=0, **pad)

        self._tts_switch = ctk.CTkSwitch(
            sb, text="Speak selections",
            command=self._on_tts_toggle,
            font=("Arial", 12))
        self._tts_switch.select()
        self._tts_switch.grid(row=12, column=0, **pad)

        self._tts_backend_lbl = ctk.CTkLabel(
            sb, text=f"Backend: {self.tts.backend_name}",
            font=("Arial", 10), text_color="#444444")
        self._tts_backend_lbl.grid(row=13, column=0, padx=14, sticky="w")

        # ── Predictions panel ─────────────────────────────────────────
        ctk.CTkLabel(sb, text="Predicted needs",
                     font=("Arial", 11), text_color="#555555").grid(
            row=14, column=0, padx=14, pady=(18, 4), sticky="w")

        self._pred_frame = ctk.CTkFrame(sb, fg_color="#1a1a1e", corner_radius=10)
        self._pred_frame.grid(row=15, column=0, **pad)
        self._pred_frame.grid_columnconfigure(0, weight=1)
        self._pred_buttons: list[ctk.CTkButton] = []
        for i in range(3):
            btn = ctk.CTkButton(
                self._pred_frame, text="",
                command=lambda j=i: self._on_prediction_click(j),
                fg_color="#252528", hover_color="#303035",
                text_color="#cccccc",
                font=("Arial", 12),
                corner_radius=8, height=34,
            )
            btn.grid(row=i, column=0, padx=8, pady=(6 if i == 0 else 3, 3 if i < 2 else 6),
                     sticky="ew")
            self._pred_buttons.append(btn)

        # ── History ───────────────────────────────────────────────────
        ctk.CTkLabel(sb, text="Recent selections",
                     font=("Arial", 11), text_color="#555555").grid(
            row=16, column=0, padx=14, pady=(18, 4), sticky="w")

        self._history_box = ctk.CTkTextbox(sb, height=100,
                                            font=("Courier New", 11),
                                            fg_color="#1a1a1e",
                                            text_color="#777777",
                                            corner_radius=10)
        self._history_box.grid(row=17, column=0, **pad)
        self._history_box.configure(state="disabled")

        # ── Debug toggle ──────────────────────────────────────────────
        self._debug_btn = ctk.CTkButton(
            sb, text="Hide debug info",
            command=self._toggle_debug,
            fg_color="#222226", hover_color="#2a2a2e",
            font=("Arial", 11), height=32, corner_radius=8)
        self._debug_btn.grid(row=18, column=0, padx=14, pady=(18, 6), sticky="ew")

        ctk.CTkLabel(sb, text="Edge-AI Accessibility  v2.0\nOffline · No cloud",
                     font=("Arial", 10), text_color="#333333",
                     justify="center").grid(row=19, column=0,
                                            padx=14, pady=(6, 14))

    # ──────────────────────────────────────────────────────────────────
    # Calibration assistant
    # ──────────────────────────────────────────────────────────────────

    def _start_calibration(self):
        """
        Collect 60 frames (~2 seconds) of gaze data while the user looks
        straight at the screen, then set H_CENTER / V_CENTER to the median.
        """
        self._calibrating     = True
        self._calib_samples_h = []
        self._calib_samples_v = []
        self._calib_deadline  = time.monotonic() + 2.5

        self._calib_btn.configure(text="⏳  Look straight at screen…",
                                   fg_color="#3a3a10")
        self._calib_lbl.configure(text="Collecting 2.5 s of gaze data…",
                                   text_color="#f0c040")
        self._status_lbl.configure(
            text="CALIBRATING — look straight at the screen",
            text_color="#f0c040")

    def _finish_calibration(self):
        self._calibrating = False

        if len(self._calib_samples_h) < 10:
            self._calib_btn.configure(text="🎯  Calibrate Gaze Center",
                                       fg_color="#1a3a1a")
            self._calib_lbl.configure(text="Failed — no face detected",
                                       text_color="#ff6060")
            return

        # Use median to ignore outliers
        sorted_h = sorted(self._calib_samples_h)
        sorted_v = sorted(self._calib_samples_v)
        new_h = sorted_h[len(sorted_h) // 2]
        new_v = sorted_v[len(sorted_v) // 2]

        self.H_CENTER = round(new_h, 3)
        self.V_CENTER = round(new_v, 3)

        # Push new centers into dwell strategy
        self._strategies["Iris + Dwell"].h_center = self.H_CENTER
        self._strategies["Iris + Dwell"].v_center = self.V_CENTER

        self._calib_btn.configure(
            text=f"✅  H={self.H_CENTER:.2f}  V={self.V_CENTER:.2f}",
            fg_color="#0d3020")
        self._calib_lbl.configure(
            text="Calibration applied! Re-run anytime.",
            text_color="#4ade80")
        self._status_lbl.configure(
            text="Calibration done — gaze center updated",
            text_color=HIGHLIGHT_COLOR)
        self.root.after(3000, self._reset_status)

        print(f"[CALIB] H_CENTER={self.H_CENTER}  V_CENTER={self.V_CENTER}")

    # ──────────────────────────────────────────────────────────────────
    # Control callbacks
    # ──────────────────────────────────────────────────────────────────

    def _on_mode_change(self, name: str):
        self._active_strategy_name = name
        self._strategy = self._strategies[name]
        self._strategy.reset()
        self._status_lbl.configure(
            text=f"Mode: {name}", text_color="#60a5fa")

    def _on_blink_change(self, val):
        v = round(float(val), 1)
        self._blink_lbl.configure(text=f"{v} s")
        self._strategies["Iris + Blink"].click_duration = v

    def _on_dwell_change(self, val):
        v = round(float(val), 1)
        self._dwell_lbl.configure(text=f"{v} s")
        self._strategies["Iris + Dwell"].dwell_time = v

    def _on_tts_toggle(self):
        self._tts_enabled = not self._tts_enabled

    def _toggle_debug(self):
        self._debug_visible = not self._debug_visible
        self._debug_lbl.configure(
            text="" if not self._debug_visible else "H=0.50 | V=0.50")
        self._debug_btn.configure(
            text="Show debug info" if not self._debug_visible else "Hide debug info")

    def _on_prediction_click(self, idx: int):
        if idx < len(self._current_predictions):
            specific = self._current_predictions[idx]
            self._trigger_selection(self._current_key, specific)

    def _start_switch_bind(self):
        self.root.bind("<space>", lambda e: self._strategies["Switch Scan"].advance())

    # ──────────────────────────────────────────────────────────────────
    # Core update loop
    # ──────────────────────────────────────────────────────────────────

    def _update_loop(self):
        payload = self.vision.get_latest()

        if payload is not None:
            frame, landmarks, h_shape, w_shape = payload

            if landmarks is not None:
                h_ratio, v_ratio, is_clicked = self._strategy.get_gaze_and_click(
                    landmarks, (h_shape, w_shape))

                self._last_h = h_ratio
                self._last_v = v_ratio

                # Collect calibration samples
                if self._calibrating:
                    self._calib_samples_h.append(h_ratio)
                    self._calib_samples_v.append(v_ratio)
                    if time.monotonic() >= self._calib_deadline:
                        self._finish_calibration()

                # EAR readout
                if hasattr(self._strategy, "ear_info"):
                    info = self._strategy.ear_info
                    self._last_ear = info.get("threshold", self._last_ear) / 0.72
                    self._ear_bar.update(self._last_ear,
                                         info.get("threshold", 0.20))

                # Map gaze to quadrant
                if self._active_strategy_name == "Switch Scan":
                    new_key = self._strategies["Switch Scan"].current_scan_key
                else:
                    new_key = self._gaze_to_key(h_ratio, v_ratio)

                if new_key != self._current_key:
                    self._cells[self._current_key].set_active(False)
                    self._current_key = new_key
                    self._cells[new_key].set_active(True)
                    self._update_predictions(new_key)

                # Dwell progress ring
                if self._active_strategy_name == "Iris + Dwell":
                    dwell_s = self._strategies["Iris + Dwell"]
                    self._cells[self._current_key].set_dwell(dwell_s.dwell_progress)

                # Debug overlay
                if self._debug_visible:
                    self._debug_lbl.configure(
                        text=f"H={h_ratio:.2f} | V={v_ratio:.2f} | "
                             f"EAR≈{self._last_ear:.3f} | "
                             f"center=({self.H_CENTER:.2f},{self.V_CENTER:.2f})")

                # Handle click (suppress during calibration)
                if is_clicked and not self._calibrating:
                    self._on_click()

        self.root.after(UPDATE_MS, self._update_loop)

    # ──────────────────────────────────────────────────────────────────
    # Selection logic
    # ──────────────────────────────────────────────────────────────────

    def _gaze_to_key(self, h: float, v: float) -> str:
        row = "Top"    if v < self.V_CENTER else "Bottom"
        col = "Left"   if h < self.H_CENTER else "Right"
        return row + col

    def _on_click(self):
        key   = self._current_key
        label = PALETTE[key]["label"]
        self._trigger_selection(key, label)

    def _trigger_selection(self, key: str, specific: str):
        label = PALETTE[key]["label"]
        self.memory.log_selection(label, specific)
        self._cells[key].flash_selected()

        self._status_lbl.configure(
            text=f"SELECTED: {specific}",
            text_color=EMERGENCY_COLOR if "Emergency" in label else HIGHLIGHT_COLOR)
        self.root.after(3000, self._reset_status)

        if self._tts_enabled:
            phrase = phrase_for(specific)
            self.tts.speak(phrase)

        self._update_predictions(key)
        self._refresh_history()

        print(f"[SELECT] {label} → {specific}")

    def _reset_status(self):
        self._status_lbl.configure(
            text=f"Looking at: {PALETTE[self._current_key]['label']}",
            text_color="#888888")

    # ──────────────────────────────────────────────────────────────────
    # Predictions
    # ──────────────────────────────────────────────────────────────────

    _current_predictions: list[str] = []

    def _update_predictions(self, key: str):
        label       = PALETTE[key]["label"]
        predictions = self.memory.predict(label, top_n=3)
        self._current_predictions = predictions

        for i, btn in enumerate(self._pred_buttons):
            if i < len(predictions):
                p = predictions[i]
                btn.configure(text=p, state="normal",
                              fg_color="#0d2010" if i == 0 else "#252528",
                              text_color="#4ade80" if i == 0 else "#cccccc")
                self._cells[key].set_sub(", ".join(predictions))
            else:
                btn.configure(text="—", state="disabled", fg_color="#1a1a1e",
                              text_color="#444444")

    def _refresh_history(self):
        recent = self.memory.recent_selections(limit=8)
        self._history_box.configure(state="normal")
        self._history_box.delete("1.0", "end")
        for r in recent:
            self._history_box.insert(
                "end", f"{r['time']}  {r['specific']}\n")
        self._history_box.configure(state="disabled")

    # ──────────────────────────────────────────────────────────────────
    # TTS helpers
    # ──────────────────────────────────────────────────────────────────

    def _announce_tts_backend(self):
        if self.tts.available:
            print(f"[TTS] Backend: {self.tts.backend_name}")
        else:
            print("[TTS] No TTS backend found. Voice output disabled.")

    # ──────────────────────────────────────────────────────────────────
    # Lifecycle
    # ──────────────────────────────────────────────────────────────────

    def run(self):
        self._cells[self._current_key].set_active(True)
        self._update_predictions(self._current_key)
        self.root.after(UPDATE_MS, self._update_loop)
        self.root.mainloop()

    def _on_close(self):
        self.vision.release()
        self.tts.stop()
        self.root.destroy()