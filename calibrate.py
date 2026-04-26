"""
calibrate.py
============
Standalone calibration helper.

Run this BEFORE using the main app to find your optimal H_CENTER and V_CENTER
crosshair values. Displays your live iris ratios with directional prompts.

Usage:
    python calibrate.py
"""

import cv2
import mediapipe as mp
import math
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from core.input_strategies import IrisBlinkStrategy


def main():
    mp_fm    = mp.solutions.face_mesh
    face_mesh = mp_fm.FaceMesh(max_num_faces=1, refine_landmarks=True,
                                min_detection_confidence=0.5,
                                min_tracking_confidence=0.5)
    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    strat = IrisBlinkStrategy()

    print("\n=== Calibration Mode ===")
    print("Look at each corner when prompted. Press Q to quit.\n")

    PROMPTS = [
        ("Look TOP-LEFT",     (0.1, 0.1)),
        ("Look TOP-RIGHT",    (0.9, 0.1)),
        ("Look BOTTOM-LEFT",  (0.1, 0.9)),
        ("Look BOTTOM-RIGHT", (0.9, 0.9)),
        ("Look CENTER",       (0.5, 0.5)),
    ]
    prompt_idx = 0
    samples: dict[str, list] = {p[0]: [] for p in PROMPTS}
    SAMPLES_NEEDED = 60
    collecting = False

    while True:
        ok, frame = cap.read()
        if not ok:
            break
        frame = cv2.flip(frame, 1)
        h, w  = frame.shape[:2]
        rgb   = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        res   = face_mesh.process(rgb)

        h_ratio, v_ratio = 0.5, 0.5
        if res.multi_face_landmarks:
            lm = res.multi_face_landmarks[0]
            h_ratio, v_ratio, _ = strat.get_gaze_and_click(lm, (h, w))

        # Overlay
        prompt_name, _ = PROMPTS[prompt_idx]
        n = len(samples[prompt_name])

        cv2.putText(frame, prompt_name,
                    (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 128), 2)
        cv2.putText(frame, f"H={h_ratio:.3f}  V={v_ratio:.3f}",
                    (20, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 200, 200), 1)
        cv2.putText(frame, f"Samples: {n}/{SAMPLES_NEEDED}   (SPACE=collect, N=next, Q=quit)",
                    (20, 130), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (180, 180, 180), 1)

        # Progress bar
        pct = n / SAMPLES_NEEDED
        cv2.rectangle(frame, (20, 150), (620, 170), (50, 50, 50), -1)
        cv2.rectangle(frame, (20, 150), (20 + int(600 * pct), 170), (0, 255, 128), -1)

        cv2.imshow("Calibration — Edge-AI Accessibility", frame)

        key = cv2.waitKey(1) & 0xFF
        if key == ord("q"):
            break
        if key == ord(" "):
            collecting = True
        if key == ord("n"):
            prompt_idx = (prompt_idx + 1) % len(PROMPTS)
            collecting = False

        if collecting and n < SAMPLES_NEEDED:
            samples[prompt_name].append((h_ratio, v_ratio))
            if n + 1 == SAMPLES_NEEDED:
                collecting = False
                avg_h = sum(x[0] for x in samples[prompt_name]) / SAMPLES_NEEDED
                avg_v = sum(x[1] for x in samples[prompt_name]) / SAMPLES_NEEDED
                print(f"  {prompt_name}: H={avg_h:.3f}, V={avg_v:.3f}")

    cap.release()
    cv2.destroyAllWindows()
    face_mesh.close()

    # Summary
    print("\n=== Results ===")
    for name, pts in samples.items():
        if pts:
            ah = sum(x[0] for x in pts) / len(pts)
            av = sum(x[1] for x in pts) / len(pts)
            print(f"  {name:20s}: H={ah:.3f}  V={av:.3f}")

    print("\nSuggested values for ui/app.py:")
    all_h = [x[0] for pts in samples.values() for x in pts]
    all_v = [x[1] for pts in samples.values() for x in pts]
    if all_h:
        print(f"  H_CENTER = {sum(all_h)/len(all_h):.2f}")
        print(f"  V_CENTER = {sum(all_v)/len(all_v):.2f}")


if __name__ == "__main__":
    main()
