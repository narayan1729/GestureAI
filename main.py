"""
Edge-AI Accessibility Interface
================================
Offline, zero-latency AAC tool for individuals with severe motor impairments.
No cloud. No internet. No expensive hardware. Just a webcam.

Run: python main.py
"""

import sys
import os

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(__file__))

from ui.app import AccessibilityApp

if __name__ == "__main__":
    app = AccessibilityApp()
    app.run()
