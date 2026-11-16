#!/usr/bin/env python3
"""Run this ONCE on the Pi while it has internet (phone hotspot is fine). It saves the Bangla
phrases as audio files next to bingo_pi.py, so the robot needs no internet afterwards.

    pip install gTTS --break-system-packages
    sudo apt install -y mpg123 alsa-utils
    python3 make_audio.py
    python3 bingo_pi.py --say        (plays ধন্যবাদ through the speaker)
"""
import os, sys
from bingo_speech import PHRASES, HERE

try:
    from gtts import gTTS
except ImportError:
    sys.exit("Run first:  pip install gTTS --break-system-packages")

for key, (text, stem) in PHRASES.items():
    path = os.path.join(HERE, stem + ".mp3")
    try:
        gTTS(text, lang="bn").save(path)
        print("saved", path, "for", text)
    except Exception as e:
        print("FAILED for", text, ":", e)
        print("Check the internet connection, or record the phrase on a phone and copy it here as", stem + ".mp3")
