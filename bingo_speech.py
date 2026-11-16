"""Bangla speech for BinGo. Plays a saved audio file; falls back to espeak-ng if there is none.

Audio files go in the same folder as this file, named after the phrase:
    dhonnobad.wav   (or .mp3)    says  ধন্যবাদ
    aschi.wav       (or .mp3)    says  আসছি   (optional)
Best quality: record your own voice on a phone, or run make_audio.py once while the Pi has internet.
No file? It tries   espeak-ng -v bn   (sudo apt install espeak-ng), which works offline but sounds robotic.
"""
import os, shutil, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))

# key: (Bangla text, audio file name without extension)
PHRASES = {
    "thanks": ("ধন্যবাদ", "dhonnobad"),
    "coming": ("আসছি", "aschi"),
}

_proc = None


def _player_for(path):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".wav" and shutil.which("aplay"):
        return ["aplay", "-q", path]
    if ext == ".mp3" and shutil.which("mpg123"):
        return ["mpg123", "-q", path]
    if shutil.which("ffplay"):
        return ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", path]
    return None


def _find_audio(stem):
    for folder in (HERE, os.path.join(HERE, "audio")):
        for ext in (".wav", ".mp3", ".ogg", ".m4a"):
            p = os.path.join(folder, stem + ext)
            if os.path.isfile(p):
                cmd = _player_for(p)
                if cmd:
                    return cmd
    return None


def busy():
    return _proc is not None and _proc.poll() is None


def speak(key, wait=False):
    """Play a phrase without blocking the robot. Returns a short note about what was used."""
    global _proc
    text, stem = PHRASES[key]
    if busy():
        if not wait:
            return "skipped, still speaking"
        _proc.wait()
    cmd = _find_audio(stem)
    how = "audio file"
    if cmd is None:
        for tts in ("espeak-ng", "espeak"):
            if shutil.which(tts):
                cmd = [tts, "-v", "bn", "-s", "125", text]
                how = tts
                break
    if cmd is None:
        return f"NO AUDIO for {text}: add {stem}.wav next to the script or install espeak-ng"
    try:
        _proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if wait:
            _proc.wait()
        return f"{how}: {text}"
    except OSError as e:
        return f"audio error: {e}"
