#!/usr/bin/env python3
"""BinGo Stage 1 on the Raspberry Pi 3B.
Camera frame, MoveNet Lightning, raised hand check, then one letter to the ESP32.

Setup on the Pi:
  sudo apt install python3-opencv python3-serial
  pip install ai-edge-litert --break-system-packages   (64-bit Raspberry Pi OS)
  Put movenet_lightning.tflite next to this file (download "MoveNet SinglePose Lightning" tflite).
Run:  python3 bingo_pi.py            (add --show to see the camera window, --test to skip the ESP32)
Camera: USB webcam. If it is not found, try --cam 1 (list cameras with: ls /dev/video*)
"""
import sys, time, argparse
import numpy as np, cv2

try:
    from tflite_runtime.interpreter import Interpreter
except ImportError:
    try:
        from ai_edge_litert.interpreter import Interpreter      # pip install ai-edge-litert
    except ImportError:
        from tensorflow.lite.python.interpreter import Interpreter

ap = argparse.ArgumentParser()
ap.add_argument("--port", default="/dev/ttyUSB0")
ap.add_argument("--model", default="movenet_lightning.tflite")
ap.add_argument("--show", action="store_true")
ap.add_argument("--cam", type=int, default=0, help="webcam index, /dev/videoN")
ap.add_argument("--flip", action="store_true", help="mirror the image if left and right come out swapped")
ap.add_argument("--test", action="store_true", help="no serial, only print what it would send")
args = ap.parse_args()

# ---- settings you can tune ----
SCORE_MIN   = 0.30   # keypoint confidence needed
RAISE_MARGIN = 0.05  # wrist must be this far above the shoulder (fraction of frame height)
NEED_FRAMES = 3      # consecutive frames with a raised hand before we move
HOLD_S      = 0.6    # keep tracking this long after the hand disappears for a moment
DEADZONE    = 0.12   # person within this of the centre counts as straight ahead
LOWERED_S   = 2.0    # hand down this long after arriving resets the robot
SEND_EVERY  = 0.10   # seconds between serial commands

# ---- model ----
try:
    interp = Interpreter(model_path=args.model, num_threads=4)   # use all 4 cores of the Pi 3B
except TypeError:
    interp = Interpreter(model_path=args.model)
interp.allocate_tensors()
inp = interp.get_input_details()[0]
out = interp.get_output_details()[0]
SIZE = inp["shape"][1]

def pose(rgb):
    img = cv2.resize(rgb, (SIZE, SIZE))
    img = np.expand_dims(img, 0)
    img = img.astype(np.uint8 if inp["dtype"] == np.uint8 else np.float32)
    interp.set_tensor(inp["index"], img)
    interp.invoke()
    return interp.get_tensor(out["index"])[0, 0]   # 17 rows of (y, x, score)

def raised_hand(kp):
    """Return centre x (0 to 1) of the person if a hand is up, else None."""
    ls, rs, lw, rw = kp[5], kp[6], kp[9], kp[10]
    up = False
    if lw[2] > SCORE_MIN and ls[2] > SCORE_MIN and lw[0] < ls[0] - RAISE_MARGIN: up = True
    if rw[2] > SCORE_MIN and rs[2] > SCORE_MIN and rw[0] < rs[0] - RAISE_MARGIN: up = True
    if not up:
        return None
    xs = [p[1] for p in (ls, rs) if p[2] > SCORE_MIN]
    return float(np.mean(xs))

# ---- camera: USB webcam ----
cap = cv2.VideoCapture(args.cam, cv2.CAP_V4L2)
if not cap.isOpened():
    sys.exit(f"Webcam {args.cam} not found. Check the cable or try --cam 1")
cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))   # less USB load on the Pi 3B
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 320)                           # MoveNet only needs 192x192
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 240)
cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)                              # always use the newest frame
def grab():
    cap.grab()                       # drop a stale frame so the robot reacts to now, not the past
    ok, f = cap.read()
    if not ok:
        return None
    return cv2.flip(f, 1) if args.flip else f

# ---- serial ----
ser = None
if not args.test:
    import serial
    ser = serial.Serial(args.port, 115200, timeout=0)
    time.sleep(2)

def send(c):
    if ser: ser.write((c + "\n").encode())

hand_count = 0
last_hand = 0.0
last_x = 0.5
arrived = False
no_hand_since = None
last_send = 0.0
buf = b""
fps_t = time.time()

print("BinGo Stage 1 running. Raise a hand. Ctrl+C to stop.")
try:
    while True:
        frame = grab()
        if frame is None:
            continue
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        kp = pose(rgb)
        x = raised_hand(kp)
        now = time.time()

        if x is not None:
            hand_count += 1
            last_x = x
            if hand_count >= NEED_FRAMES:
                last_hand = now
        else:
            hand_count = 0

        tracking = (now - last_hand) < HOLD_S

        # messages from the ESP32
        if ser:
            buf += ser.read(256)
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                line = line.decode(errors="ignore").strip()
                if line == "ARRIVED":
                    arrived = True
                    no_hand_since = None
                    print("ARRIVED at the person. (Stage 2 hook: open lid, play audio)")

        if arrived:
            if tracking:
                no_hand_since = None
            else:
                no_hand_since = no_hand_since or now
                if now - no_hand_since > LOWERED_S:
                    arrived = False
                    print("Reset, waiting for the next hand.")
            cmd = "S"
        elif tracking:
            err = last_x - 0.5
            cmd = "F" if abs(err) < DEADZONE else ("L" if err < 0 else "R")
        else:
            cmd = "S"

        frames = globals().get("frames", 0) + 1; globals()["frames"] = frames
        if now - fps_t >= 5:
            print(f"FPS: {frames / (now - fps_t):.1f}")
            fps_t, frames = now, 0; globals()["frames"] = 0

        if now - last_send >= SEND_EVERY:
            send(cmd)
            last_send = now
            if args.test or args.show:
                print(f"hand={'yes' if tracking else 'no '} x={last_x:.2f} cmd={cmd}")

        if args.show:
            h, w = frame.shape[:2]
            for (y, xx, s) in kp:
                if s > SCORE_MIN:
                    cv2.circle(frame, (int(xx * w), int(y * h)), 4, (0, 255, 0), -1)
            cv2.putText(frame, f"{cmd}  hand={'yes' if tracking else 'no'}", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2)
            cv2.imshow("BinGo", frame)
            if cv2.waitKey(1) == 27:
                break
finally:
    send("S")
    cap.release()
