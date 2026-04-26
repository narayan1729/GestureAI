"""
voice/tts_engine.py
====================
Offline, local text-to-speech with automatic backend selection.

Priority order (best quality → most compatible):
  1. Piper TTS    — neural, natural-sounding, runs on CPU, ~50ms latency
  2. pyttsx3      — SAPI/espeak wrapper, zero-install on Windows/Linux/macOS
  3. espeak-ng    — direct subprocess fallback, always available on Linux

All speech runs in a background thread so the UI never freezes.
"""

import threading
import queue
import subprocess
import shutil
import os
import sys
import tempfile
import time


class TTSEngine:
    """
    Thread-safe, non-blocking TTS.
    Call speak(text) from any thread; audio plays in the background.
    """

    def __init__(self, rate: int = 160, volume: float = 1.0):
        self.rate   = rate      # words per minute (pyttsx3 / espeak)
        self.volume = volume    # 0.0 – 1.0

        self._q      = queue.Queue()
        self._stop   = threading.Event()
        self._backend, self._engine = self._detect_backend()

        print(f"[TTS] Backend: {self._backend}")

        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

    # ------------------------------------------------------------------
    # Backend detection
    # ------------------------------------------------------------------

    def _detect_backend(self) -> tuple[str, object]:
        # 1. Piper TTS — only use if a model file actually exists
        piper_exe = shutil.which("piper") or shutil.which("piper-tts")
        if piper_exe and self._find_piper_model():
            return "piper", None

        # 2. pyttsx3
        try:
            import pyttsx3
            engine = pyttsx3.init()
            engine.setProperty("rate",   self.rate)
            engine.setProperty("volume", self.volume)
            return "pyttsx3", engine
        except Exception:
            pass

        # 3. espeak-ng / espeak
        for cmd in ("espeak-ng", "espeak"):
            if shutil.which(cmd):
                return "espeak", cmd

        return "none", None

    @property
    def backend_name(self) -> str:
        return self._backend

    @property
    def available(self) -> bool:
        return self._backend != "none"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def speak(self, text: str, interrupt: bool = True):
        """
        Queue `text` for speech.
        If interrupt=True, discard any pending utterance first.
        """
        if not self.available:
            return
        if interrupt:
            # Drain the queue
            while not self._q.empty():
                try:
                    self._q.get_nowait()
                except queue.Empty:
                    break
        self._q.put(text)

    def stop(self):
        self._stop.set()
        self._thread.join(timeout=2.0)

    # ------------------------------------------------------------------
    # Worker thread
    # ------------------------------------------------------------------

    def _worker(self):
        while not self._stop.is_set():
            try:
                text = self._q.get(timeout=0.2)
            except queue.Empty:
                continue

            self._say(text)

    def _say(self, text: str):
        try:
            if self._backend == "pyttsx3":
                self._engine.say(text)
                self._engine.runAndWait()

            elif self._backend == "piper":
                piper_exe  = shutil.which("piper") or shutil.which("piper-tts")
                model_path = self._find_piper_model()
                if not model_path:
                    # No model found — fall back to pyttsx3
                    self._pyttsx3_fallback(text)
                    return

                if sys.platform == "win32":
                    # Windows: write to a temp WAV file, play with PowerShell
                    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                        tmp_path = tmp.name
                    try:
                        subprocess.run(
                            [piper_exe, "--model", model_path,
                             "--output_file", tmp_path],
                            input=text.encode(),
                            check=True,
                            stderr=subprocess.DEVNULL,
                        )
                        # Play the WAV with PowerShell (no extra installs needed)
                        subprocess.run(
                            [
                                "powershell", "-c",
                                f'(New-Object Media.SoundPlayer "{tmp_path}").PlaySync()'
                            ],
                            check=False,
                            stderr=subprocess.DEVNULL,
                        )
                    finally:
                        try:
                            os.remove(tmp_path)
                        except OSError:
                            pass
                else:
                    # Linux / macOS: pipe raw PCM to aplay / afplay
                    player = self._audio_player()
                    piper_proc = subprocess.Popen(
                        [piper_exe, "--model", model_path, "--output-raw"],
                        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                        stderr=subprocess.DEVNULL
                    )
                    play_proc = subprocess.Popen(
                        player,
                        stdin=piper_proc.stdout, stderr=subprocess.DEVNULL
                    )
                    piper_proc.stdin.write(text.encode())
                    piper_proc.stdin.close()
                    play_proc.wait()

            elif self._backend == "espeak":
                self._espeak_say(text)

        except Exception as e:
            print(f"[TTS] Error in backend '{self._backend}': {e}")

    def _pyttsx3_fallback(self, text: str):
        try:
            import pyttsx3
            engine = pyttsx3.init()
            engine.setProperty("rate",   self.rate)
            engine.setProperty("volume", self.volume)
            engine.say(text)
            engine.runAndWait()
        except Exception as e:
            print(f"[TTS] pyttsx3 fallback error: {e}")

    def _espeak_say(self, text: str):
        cmd = self._engine if self._backend == "espeak" else "espeak-ng"
        rate_wpm = str(self.rate)
        subprocess.run(
            [cmd, "-s", rate_wpm, "-a", str(int(self.volume * 200)), text],
            check=False, stderr=subprocess.DEVNULL
        )

    @staticmethod
    def _find_piper_model() -> str | None:
        """Search common install locations for a Piper ONNX voice model."""
        search_dirs = [
            os.path.expanduser("~/.local/share/piper"),
            "/usr/share/piper",
            "/usr/local/share/piper",
            os.path.join(os.path.dirname(__file__), "..", "assets", "piper_models"),
        ]
        for d in search_dirs:
            if not os.path.isdir(d):
                continue
            for f in os.listdir(d):
                if f.endswith(".onnx"):
                    return os.path.join(d, f)
        return None

    @staticmethod
    def _audio_player() -> list[str]:
        """Find a suitable raw-PCM player for Piper output (Linux/macOS only)."""
        if shutil.which("aplay"):
            return ["aplay", "-r", "22050", "-f", "S16_LE", "-c", "1", "-"]
        if shutil.which("paplay"):
            return ["paplay", "--raw", "--rate=22050",
                    "--format=s16le", "--channels=1"]
        if shutil.which("afplay"):
            return ["afplay", "-"]
        if shutil.which("ffplay"):
            return ["ffplay", "-autoexit", "-nodisp",
                    "-f", "s16le", "-ar", "22050", "-ac", "1", "-"]
        return ["cat"]


# ---------------------------------------------------------------------------
# Phrase library — what gets spoken for each selection
# ---------------------------------------------------------------------------

SPOKEN_PHRASES = {
    # ── Water / Drink ──────────────────────────────────────────────────
    "Hot coffee":      "I would like a hot coffee please.",
    "Green tea":       "I would like some green tea please.",
    "Water":           "I need some water please.",
    "Iced coffee":     "I would like an iced coffee please.",
    "Juice":           "I would like some juice please.",
    "Herbal tea":      "I would like some herbal tea please.",
    "Warm milk":       "I would like some warm milk please.",
    "Chamomile tea":   "I would like some chamomile tea please.",
    "Water / Drink":   "I am thirsty. I need something to drink.",

    # ── Food / Eat ─────────────────────────────────────────────────────
    "Oatmeal":         "I would like some oatmeal please.",
    "Toast":           "I would like some toast please.",
    "Eggs":            "I would like some eggs please.",
    "Sandwich":        "I would like a sandwich please.",
    "Soup":            "I would like some soup please.",
    "Salad":           "I would like a salad please.",
    "Dinner":          "I am ready for dinner please.",
    "Rice bowl":       "I would like a rice bowl please.",
    "Pasta":           "I would like some pasta please.",
    "Light snack":     "I would like a light snack please.",
    "Crackers":        "I would like some crackers please.",
    "Fruit":           "I would like some fruit please.",
    "Food / Eat":      "I am hungry. I need something to eat.",

    # ── Washroom ───────────────────────────────────────────────────────
    "Need help now":   "I need help with the washroom right now.",
    "Urgently":        "This is urgent. I need the washroom immediately.",
    "Can wait 5 min":  "I need the washroom but can wait about five minutes.",
    "Washroom":        "I need help getting to the washroom.",

    # ── Emergency ──────────────────────────────────────────────────────
    "Call caregiver":  "Please call my caregiver immediately.",
    "I am in pain":    "I am in pain. I need help right now.",
    "Help me move":    "I need help adjusting my position.",
    "Emergency / Help": "EMERGENCY. I need immediate assistance.",
}


def phrase_for(selection: str) -> str:
    return SPOKEN_PHRASES.get(selection, f"I need {selection}.")