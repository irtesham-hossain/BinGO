#!/usr/bin/env python3
"""Drive BinGo from the Pi keyboard to test the motors (needs bingo_esp32.ino on the ESP32).

    cd ~/bingo && python3 drive_test.py

Hold a key:  W forward   A left   D right   (let go and it stops)
             O open lid  C close lid   Q quit
"""
import curses, glob, sys, time
import serial

ports = sorted(glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*"))
if not ports:
    sys.exit("ESP32 not found. Plug in the USB cable and try again.")
ser = serial.Serial(ports[0], 115200, timeout=0)
time.sleep(2)

def main(scr):
    scr.nodelay(True)
    curses.curs_set(0)
    keys = {ord("w"): "F", ord("a"): "L", ord("d"): "R"}
    last_key_t, cmd, dist = 0.0, "S", "?"
    buf = b""
    while True:
        k = scr.getch()
        now = time.time()
        if k in (ord("q"), ord("Q")):
            break
        k = k | 0x20 if 0 < k < 128 else k          # accept capitals too
        if k in keys:
            cmd, last_key_t = keys[k], now
        elif k == ord("o"):
            ser.write(b"O\n")
        elif k == ord("c"):
            ser.write(b"C\n")
        elif k == ord(" ") or k == ord("s"):
            cmd = "S"
        if now - last_key_t > 0.25:                   # key released
            cmd = "S"
        ser.write((cmd + "\n").encode())
        buf += ser.read(256)
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            line = line.decode(errors="ignore").strip()
            if line.startswith("D,"):
                dist = line[2:]
            elif line == "ARRIVED":
                dist += "  (stopped: something is close)"
        scr.erase()
        scr.addstr(0, 0, f"BinGo drive test on {ports[0]}")
        scr.addstr(2, 0, "Hold W forward, A left, D right. O open lid, C close lid, Q quit.")
        scr.addstr(4, 0, f"Sending: {cmd}     Distance: {dist} cm")
        scr.addstr(6, 0, "Forward is blocked when something is closer than 80 cm.")
        scr.refresh()
        time.sleep(0.05)

try:
    curses.wrapper(main)
finally:
    ser.write(b"S\n")
    print("Stopped.")
