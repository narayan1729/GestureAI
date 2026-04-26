# GestureAI

**Offline, zero-latency AAC communication tool for individuals with severe motor impairments.**

No cloud. No internet. No expensive eye-tracker hardware. Just a standard webcam.

---

## What is GestureAI?

GestureAI replaces $/£5,000+ infrared eye-tracking hardware with a standard laptop or tablet webcam and fully local AI processing. It is designed for users with ALS, severe Cerebral Palsy, or any condition that eliminates voluntary limb movement but preserves some eye or head control.

The user communicates by:
1. **Looking** at one of four high-contrast panels (Water, Food, Washroom, Emergency)
2. **Selecting** via blink hold, dwell gaze, or external switch
3. **Hearing** GestureAI speak their need aloud using a local AI voice

No frame ever leaves the device. Everything runs 100% offline.

---

## Demo

![GestureAI Interface](assets/demo.png)

---

## Quick Start

```bash
# 1. Clone the repo
git clone https://github.com/narayan1729/GestureAI.git
cd GestureAI

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

## Installation on Windows (Python 3.13)

The standard mediapipe package on PyPI only ships versions 0.10.30+ for Python 3.13. GestureAI uses the newer MediaPipe Tasks API which is compatible with these versions.

```bash
pip install -r requirements.txt
```

On first run, GestureAI will automatically download the required face landmark model (~6 MB) from Google.

---

## Calibration

When you first launch, click the **🎯 Calibrate Gaze Center** button in the sidebar. Look straight at the center of the screen for 2.5 seconds — GestureAI will auto-detect your personal gaze center and apply it instantly. Run this once every time you sit down.

You can also watch the `H=... | V=...` debug bar at the bottom to fine-tune manually.

---

## Input Modes

### 1. Iris + Dwell (recommended)
Look at a panel and hold your gaze for 2.5 seconds. A circular progress ring fills as the timer counts down. Fires once — no accidental triggers. Best for most users.

### 2. Iris + Blink
Hold your eyes closed for 1.2 seconds to select the panel you are looking at. A rolling 150-frame EAR baseline auto-adapts the threshold as your eyelids fatigue — so it stays accurate over long sessions.

### 3. Switch Scan
GestureAI cycles through all four panels every 2 seconds. Press **spacebar** (or any external switch mapped to spacebar) to select the highlighted panel. Best for users with only a single point of voluntary muscle control (sip-and-puff, toe switch, one-finger switch).

---

## Voice Output (TTS)

GestureAI auto-detects the best available offline TTS backend:

| Priority | Backend | Quality | Notes |
|----------|---------|---------|-------|
| 1 | **Piper TTS** | ★★★★★ Neural | Best quality. Setup below. |
| 2 | **pyttsx3** | ★★★☆☆ Robotic | Works out of the box on Windows. |
| 3 | **espeak-ng** | ★★☆☆☆ Basic | Linux fallback. |

### Setting up Piper TTS (Windows)

1. Download the Piper binary from [github.com/rhasspy/piper/releases](https://github.com/rhasspy/piper/releases) and add it to your PATH.
2. Place the voice model files in `assets/piper_models/`:

```
assets/
  piper_models/
    en_US-lessac-medium.onnx
    en_US-lessac-medium.onnx.json
```

Download the model files from [HuggingFace](https://huggingface.co/rhasspy/piper-voices/tree/main/en/en_US/lessac/medium).

Once set up, the sidebar will show `Backend: piper` and you will hear a clear, natural voice.

---

## Architecture

```
main.py
  └── ui/app.py                   ← Main UI (customtkinter, 30fps loop)
        ├── core/vision_engine.py       ← Camera capture (background thread)
        ├── core/input_strategies.py    ← Pluggable gaze/click logic
        │     ├── IrisBlinkStrategy     ← Iris gaze + EAR blink
        │     ├── IrisDwellStrategy     ← Iris gaze + dwell timer
        │     └── SwitchScanStrategy    ← Auto-scan + external switch
        ├── memory/habitual_memory.py   ← SQLite habit tracking + prediction
        └── voice/tts_engine.py         ← Offline TTS (Piper / pyttsx3 / espeak)
```

### Key Design Decisions

**Threaded capture:** The vision engine runs in a background thread and writes to a shared slot. The UI reads at 30fps without ever blocking on camera I/O.

**Pluggable strategies:** All gaze and click logic lives behind the `InputStrategy` ABC. Swapping input methods at runtime requires zero changes to the UI layer.

**Dynamic EAR baseline:** The blink threshold is not a fixed constant. It is 72% of a rolling 150-frame average of the user's resting EAR. As eyelids droop with fatigue, the threshold drops automatically — this is why GestureAI stays usable over multi-hour sessions where fixed-threshold systems fail.

**Gaze smoothing:** Iris position is averaged over a rolling 6–8 frame window before quadrant mapping. This eliminates the jitter that causes panels to flicker when gaze is near a boundary.

**Auto-calibration:** The built-in calibration assistant samples 2.5 seconds of gaze data and sets the quadrant crosshair to the user's personal median gaze position — no manual tuning required.

**Local habit prediction:** The habitual memory layer uses pure SQL frequency counts grouped by time-of-day bucket (morning / afternoon / evening / night). No vector database, no embedding model — just frequency statistics that are fast, interpretable, and explainable to caregivers.

---

## Roadmap

- [ ] Smart home integration (Philips Hue, Google Home local API)
- [ ] Head-pose gaze as fallback when iris is not detected
- [ ] Caregiver alert via local network (push to phone on LAN)
- [ ] Exportable usage reports (weekly summary PDF)
- [ ] Web UI port (TensorFlow.js + IndexedDB for zero-install tablet use)

---

## Built With

- [MediaPipe](https://mediapipe.dev/) — Face landmark detection
- [OpenCV](https://opencv.org/) — Camera capture
- [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter) — UI framework
- [Piper TTS](https://github.com/rhasspy/piper) — Neural voice output
- [pyttsx3](https://pyttsx3.readthedocs.io/) — Offline TTS fallback

---

## License

MIT — Built for the disability community. Use freely, modify freely, share widely.