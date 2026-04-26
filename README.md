# Edge-AI Accessibility Interface  v2.0

**Offline, zero-latency AAC communication tool for individuals with severe motor impairments.**

No cloud. No internet. No expensive eye-tracker hardware. Just a standard webcam.

---

## What it does

This system replaces $/£5,000+ infrared eye-tracking hardware with a standard laptop/tablet webcam and local AI processing. It is designed for users with ALS, severe Cerebral Palsy, or any condition that eliminates voluntary limb movement but preserves some eye or head control.

The user communicates by:
1. **Looking** at one of four high-contrast panels (Water, Food, Washroom, Emergency)
2. **Selecting** via blink hold, dwell gaze, or external switch
3. **Hearing** the system speak their need aloud using a local AI voice

No frame ever leaves the device.

---

## Quick start

```bash
# 1. Clone / unzip the project
cd edge_ai_accessibility

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run
python main.py
```

**Requirements:**
- Python 3.10+
- Webcam (built-in or USB)
- Windows 10/11, macOS 12+, or Ubuntu 20.04+

---

## Calibration

When you first launch, watch the **EAR baseline bar** at the bottom. It needs ~5 seconds of normal blinking to calibrate. The red line (dynamic threshold) will settle automatically.

If the system is too sensitive (clicking on light blinks), drag the **Blink hold** slider right (toward 1.5–2.0 s).

If you cannot reach the bottom panels, set `V_CENTER` in `ui/app.py` higher (e.g. `0.55`).

---

## Input modes

### 1. Iris + Blink (default)
Uses MediaPipe iris landmark 468 for horizontal/vertical gaze ratios. A sustained eye closure beyond the blink-hold threshold fires a click. A rolling 150-frame baseline auto-adapts the closure threshold as the user fatigues — the key advantage over static-threshold systems.

### 2. Iris + Dwell
Same iris gaze tracking. Instead of blinking, the user holds their gaze in one quadrant for the dwell duration (default 2 s). A circular progress ring fills to give visual feedback. Best for users who cannot voluntarily control eyelid closure.

### 3. Switch Scan
The system automatically cycles through all four panels at the scan interval (default 1.5 s). The user presses the **spacebar** (or an external switch mapped to spacebar) to select the highlighted panel. For users with single voluntary muscle control (sip-and-puff, one-finger switch, toe switch).

---

## Voice output (TTS)

The system auto-detects the best available offline TTS backend:

| Priority | Backend | Quality | Notes |
|----------|---------|---------|-------|
| 1 | **Piper TTS** | ★★★★★ Neural | Best. See setup below. |
| 2 | **pyttsx3** | ★★★☆☆ Robotic | Works out of box. |
| 3 | **espeak-ng** | ★★☆☆☆ Basic | Linux fallback. |

### Installing Piper TTS (recommended)

Piper is a fast, local neural TTS that runs on CPU with ~50ms latency.

**Linux / macOS:**
```bash
pip install piper-tts

# Download a voice model (en_US-lessac-medium is recommended)
mkdir -p ~/.local/share/piper
cd ~/.local/share/piper
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json
```

**Windows:**
Download the Piper release binary from https://github.com/rhasspy/piper/releases and add it to your PATH. Place the `.onnx` model file in `assets/piper_models/`.

Once Piper is installed and a model is found, the app will automatically use it. The backend label in the sidebar will show `piper`.

---

## Architecture

```
main.py
  └── ui/app.py              ← Main UI (customtkinter, 30fps loop)
        ├── core/vision_engine.py       ← Camera capture (background thread)
        ├── core/input_strategies.py    ← Pluggable gaze/click logic
        │     ├── IrisBlinkStrategy     ← Iris gaze + EAR blink
        │     ├── IrisDwellStrategy     ← Iris gaze + dwell timer
        │     └── SwitchScanStrategy    ← Auto-scan + external switch
        ├── memory/habitual_memory.py   ← SQLite habit tracking + prediction
        └── voice/tts_engine.py         ← Offline TTS (Piper / pyttsx3 / espeak)
```

### Key design decisions

**Threaded capture:** The vision engine runs in a background thread and writes to a shared `_last_result` slot. The UI reads this at 30fps without ever blocking on camera I/O.

**Pluggable strategies:** All gaze + click logic is isolated behind the `InputStrategy` ABC. Swapping input methods at runtime requires zero changes to the UI layer.

**Dynamic EAR baseline:** The blink threshold is not a fixed constant — it is 72% of a rolling 150-frame average of the user's resting EAR. As eyelids droop with fatigue, the threshold drops automatically. This is why the system stays usable over multi-hour sessions where fixed-threshold systems fail.

**Click-consumed flag:** Each strategy uses an internal `_click_consumed` or `_fired` flag to ensure a click fires for exactly one frame, preventing double-triggers on slow renders.

**Local RAG prediction:** The habitual memory layer uses pure SQL frequency counts grouped by time-of-day bucket (morning/afternoon/evening/night). No vector database, no embedding model — just frequency statistics. Fast, interpretable, and explainable to caregivers.

---

## Adjusting the crosshair

If the gaze quadrant mapping feels off, edit these two lines in `ui/app.py`:

```python
H_CENTER = 0.50   # < this: looking left. > this: looking right
V_CENTER = 0.45   # < this: looking up.   > this: looking down
```

Watch the `H=... | V=...` debug display to find your resting gaze ratios, then set the centers to bisect them.

---

## Adding new intents / panels

The system currently uses a 2×2 grid. To add more panels:

1. Add entries to `PALETTE` in `ui/app.py`
2. Update the grid layout (`grid_rowconfigure`, `grid_columnconfigure`)
3. Add spoken phrases to `SPOKEN_PHRASES` in `voice/tts_engine.py`
4. Add default predictions to `DEFAULT_PREDICTIONS` in `memory/habitual_memory.py`

---

## Roadmap

- [ ] Smart home integration (Philips Hue, Google Home local API)
- [ ] Head-pose gaze as fallback when iris is not detected
- [ ] Caregiver alert via local network (push to phone on LAN)
- [ ] Exportable usage reports (weekly summary PDF)
- [ ] Web UI port (TensorFlow.js + IndexedDB for zero-install tablet use)

---

## License

MIT. Built for the disability community. Use freely, modify freely, share widely.
