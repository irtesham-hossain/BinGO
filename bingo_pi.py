#!/usr/bin/env python3
"""BinGo demo program for the Raspberry Pi 3B.

Raised hand seen by the USB webcam (MoveNet)  ->  letters to the ESP32  ->  robot drives to the person,
stops at 80 cm, opens the lid (optional) and says ধন্যবাদ in Bangla.

Run:      python3 bingo_pi.py
Options:  --show      camera window with dots on the body (needs a monitor, slower)
          --test      do not talk to the ESP32, only print what would be sent
          --lid       open the lid on arrival and close it afterwards (servo connected)
          --say       play ধন্যবাদ once to test the speaker, then quit
          --lid-test  open and close the lid once, then quit
          --cam N     webcam number, if /dev/video0 is not the right one
          --flip      mirror the image if the robot turns away from you
          --port P    ESP32 serial port (found automatically if left out)
          --no-web    turn off the web page (on by default at http://<pi-address>:8000)
          --web-port  web page port, default 8000
"""
import sys, os, glob, time, argparse

import bingo_speech as bangla

HERE = os.path.dirname(os.path.abspath(__file__))

ap = argparse.ArgumentParser()
ap.add_argument("--port", default=None)
ap.add_argument("--model", default=os.path.join(HERE, "movenet_lightning.tflite"))
ap.add_argument("--cam", type=int, default=0)
ap.add_argument("--show", action="store_true")
ap.add_argument("--flip", action="store_true")
ap.add_argument("--test", action="store_true")
ap.add_argument("--lid", action="store_true")
ap.add_argument("--say", action="store_true")
ap.add_argument("--lid-test", action="store_true")
ap.add_argument("--no-web", action="store_true")
ap.add_argument("--web-port", type=int, default=8000)
args = ap.parse_args()

if args.say:
    print(bangla.speak("thanks", wait=True))
    sys.exit(0)

import numpy as np, cv2
try:
    from tflite_runtime.interpreter import Interpreter
except ImportError:
    try:
        from ai_edge_litert.interpreter import Interpreter
    except ImportError:
        from tensorflow.lite.python.interpreter import Interpreter

# ---------------- settings you can tune ----------------
SCORE_MIN    = 0.30   # keypoint confidence needed
RAISE_MARGIN = 0.05   # wrist must be this far above the shoulder (fraction of frame height)
NEED_FRAMES  = 3      # frames in a row with a raised hand before the robot moves
HOLD_S       = 0.6    # keep following this long if the hand drops out of view for a moment
DEADZONE     = 0.12   # person within this of the image centre counts as straight ahead
LOWERED_S    = 3.0    # after arriving, hand down this long resets the robot for the next person
SEND_EVERY   = 0.10   # seconds between serial commands
SAY_COMING   = True   # say আসছি when the robot starts moving toward you

# ---------------- serial link to the ESP32 (reconnects by itself) ----------------
ser = None
last_try = 0.0
esp_state = {"text": "test mode, not connected" if args.test else "not connected", "dist": None}

def find_port():
    if args.port:
        return args.port
    ports = sorted(glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*"))
    return ports[0] if ports else None

def serial_ok():
    """Return True when the ESP32 is connected. Tries again every 2 s if it is not."""
    global ser, last_try
    if args.test:
        return False
    if ser is not None:
        return True
    if time.time() - last_try < 2.0:
        return False
    last_try = time.time()
    port = find_port()
    if port is None:
        print("ESP32 not found, waiting. Plug in the USB cable.")
        esp_state["text"] = "not found, plug in USB"
        return False
    try:
        import serial
        ser = serial.Serial(port, 115200, timeout=0)
        time.sleep(2)             # the ESP32 restarts when the port opens
        print("ESP32 connected on", port)
        esp_state["text"] = "connected on " + port
        return True
    except Exception as e:
        print("Could not open", port, "-", e)
        ser = None
        return False

def send(c):
    global ser
    if not serial_ok():
        return
    try:
        ser.write((c + "\n").encode())
    except Exception as e:
        print("Lost the ESP32:", e)
        esp_state["text"] = "lost, reconnecting"
        try: ser.close()
        except Exception: pass
        ser = None

rxbuf = b""

def read_lines():
    """Complete lines received from the ESP32 since the last call."""
    global ser, rxbuf
    if ser is None:
        return []
    try:
        rxbuf += ser.read(256)
    except Exception as e:
        print("Lost the ESP32:", e)
        esp_state["text"] = "lost, reconnecting"
        ser = None
        return []
    lines = []
    while b"\n" in rxbuf:
        line, rxbuf = rxbuf.split(b"\n", 1)
        lines.append(line.decode(errors="ignore").strip())
    return lines

if args.lid_test:
    while not serial_ok():
        time.sleep(0.5)
    print("lid open"); send("O"); time.sleep(3)
    print("lid closed"); send("C"); time.sleep(2)
    sys.exit(0)

# ---------------- model ----------------
if not os.path.isfile(args.model):
    sys.exit(f"Model file not found: {args.model}")
try:
    interp = Interpreter(model_path=args.model, num_threads=4)
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
    return interp.get_tensor(out["index"])[0, 0]      # 17 rows of (y, x, score)

def raised_hand(kp):
    """Centre x (0 to 1) of the person if a hand is up, else None."""
    ls, rs, lw, rw = kp[5], kp[6], kp[9], kp[10]
    up = False
    if lw[2] > SCORE_MIN and ls[2] > SCORE_MIN and lw[0] < ls[0] - RAISE_MARGIN: up = True
    if rw[2] > SCORE_MIN and rs[2] > SCORE_MIN and rw[0] < rs[0] - RAISE_MARGIN: up = True
    if not up:
        return None
    xs = [p[1] for p in (ls, rs) if p[2] > SCORE_MIN]
    return float(np.mean(xs))

# ---------------- web page ----------------
web = None
if not args.no_web:
    import socket
    import bingo_web
    web = bingo_web.Shared()
    try:
        bingo_web.start(web, args.web_port)
        try:
            s_ = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s_.connect(("8.8.8.8", 80))
            ip = s_.getsockname()[0]; s_.close()
        except OSError:
            ip = "<pi-address>"
        print(f"Web page: http://{ip}:{args.web_port}")
    except OSError as e:
        print("Web page could not start:", e)
        web = None

# ---------------- webcam (keeps trying until it appears) ----------------
cap = None
def open_cam():
    global cap
    c = cv2.VideoCapture(args.cam, cv2.CAP_V4L2)
    if not c.isOpened():
        return False
    c.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    c.set(cv2.CAP_PROP_FRAME_WIDTH, 320)
    c.set(cv2.CAP_PROP_FRAME_HEIGHT, 240)
    c.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    cap = c
    return True

def grab():
    cap.grab()                         # drop one stale frame so the robot reacts to now
    ok, f = cap.read()
    if not ok:
        return None
    return cv2.flip(f, 1) if args.flip else f

# ---------------- main loop ----------------
hand_count, last_hand, last_x = 0, 0.0, 0.5
arrived, no_hand_since = False, None
said_coming = False
last_send, fps_t, nframes, fps_now = 0.0, time.time(), 0, 0.0
lid_is_open = False

print("BinGo running. Raise a hand in front of the camera. Ctrl+C to stop.")
send("C")
try:
    while True:
        if cap is None:
            if not open_cam():
                print(f"Webcam {args.cam} not found, waiting. Check the USB cable.")
                time.sleep(2)
                continue
            print("Webcam ready.")
        frame = grab()
        if frame is None:
            time.sleep(0.05)
            continue
        kp = pose(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
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

        # buttons pressed on the web page
        manual = web is not None and web.mode == "manual"
        if web is not None:
            for r in web.pop_requests():
                if r == "lid_open":
                    send("O"); lid_is_open = True
                elif r == "lid_close":
                    send("C"); lid_is_open = False
                elif r == "say_thanks":
                    print("Web:", bangla.speak("thanks"))
                elif r == "say_coming":
                    print("Web:", bangla.speak("coming"))
                elif r == "reset":
                    arrived, said_coming, no_hand_since = False, False, None
                    send("C"); lid_is_open = False
                    print("Web: reset, waiting for the next hand.")
            with web.lock:
                web.lid_open = lid_is_open

        # messages from the ESP32
        for line in read_lines():
            if line.startswith("D,"):
                esp_state["dist"] = line[2:]
            if line == "ARRIVED" and manual:
                continue
            if line == "ARRIVED" and not arrived:
                arrived, no_hand_since = True, None
                print("ARRIVED:", bangla.speak("thanks"))
                if args.lid:
                    send("O"); lid_is_open = True

        if manual:
            cmd = web.manual(now)
        elif arrived:
            if tracking:
                no_hand_since = None
            else:
                no_hand_since = no_hand_since or now
                if now - no_hand_since > LOWERED_S:
                    arrived, said_coming = False, False
                    if args.lid:
                        send("C"); lid_is_open = False
                    print("Reset, waiting for the next hand.")
            cmd = "S"
        elif tracking:
            err = last_x - 0.5
            cmd = "F" if abs(err) < DEADZONE else ("L" if err < 0 else "R")
            if SAY_COMING and not said_coming:
                print("Coming:", bangla.speak("coming"))
                said_coming = True
        else:
            cmd = "S"
            if said_coming and now - last_hand > 5.0:
                said_coming = False

        nframes += 1
        if now - fps_t >= 5:
            fps_now = nframes / (now - fps_t)
            print(f"FPS: {fps_now:.1f}")
            fps_t, nframes = now, 0

        if now - last_send >= SEND_EVERY:
            send(cmd)
            last_send = now
            if args.test or args.show:
                print(f"hand={'yes' if tracking else 'no '} x={last_x:.2f} cmd={cmd}")

        if args.show or web is not None:
            h, w = frame.shape[:2]
            for (y, xx, s) in kp:
                if s > SCORE_MIN:
                    cv2.circle(frame, (int(xx * w), int(y * h)), 3, (0, 255, 0), -1)
            label = ("MANUAL " if manual else "") + f"{cmd} hand={'yes' if tracking else 'no'}"
            cv2.putText(frame, label, (6, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 255), 2)
        if web is not None:
            ok, jpg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
            if ok:
                web.set_frame(jpg.tobytes())
            with web.lock:
                web.status = {"cmd": cmd, "hand": bool(tracking), "dist": esp_state["dist"],
                              "fps": round(fps_now, 1), "esp": esp_state["text"], "arrived": arrived}
        if args.show:
            cv2.imshow("BinGo", frame)
            if cv2.waitKey(1) == 27:
                break
except KeyboardInterrupt:
    print("Stopped.")
finally:
    send("S")
    if args.lid:
        send("C")
    if cap is not None:
        cap.release()
