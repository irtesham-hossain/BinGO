#!/bin/bash
# BinGo one-time Pi setup: fixed web address (http://bingo.local:8000) and auto-start on boot.
# Run from the bingo folder:   cd ~/bingo && bash setup_pi.sh
# With the lid servo fitted:   bash setup_pi.sh --lid
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
USER_NAME="$(whoami)"
EXTRA="$1"

if [ "$USER_NAME" = "root" ]; then
  echo "Run this as your normal user, not with sudo:  bash setup_pi.sh"
  exit 1
fi
if [ ! -f "$DIR/bingo_pi.py" ]; then
  echo "bingo_pi.py not found in $DIR. Run this script from the bingo folder."
  exit 1
fi

echo "1/4  Setting the Pi name to 'bingo'"
OLD="$(hostname)"
if [ "$OLD" != "bingo" ]; then
  sudo hostnamectl set-hostname bingo
  sudo sed -i "s/127\.0\.1\.1.*/127.0.1.1\tbingo/" /etc/hosts
  grep -q "127.0.1.1" /etc/hosts || echo -e "127.0.1.1\tbingo" | sudo tee -a /etc/hosts > /dev/null
fi

echo "2/4  Turning on the name service (avahi) so bingo.local works"
sudo apt install -y avahi-daemon > /dev/null 2>&1 || echo "     could not install avahi-daemon, check the internet"
sudo systemctl enable --now avahi-daemon > /dev/null 2>&1 || true

echo "3/4  Giving $USER_NAME access to the webcam and the ESP32"
sudo usermod -aG dialout,video,audio "$USER_NAME"

echo "4/4  Creating the auto-start service"
sudo tee /etc/systemd/system/bingo.service > /dev/null <<EOF
[Unit]
Description=BinGo robot
After=network-online.target sound.target
Wants=network-online.target

[Service]
User=$USER_NAME
WorkingDirectory=$DIR
ExecStartPre=/bin/sleep 5
ExecStart=/usr/bin/python3 $DIR/bingo_pi.py $EXTRA
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable bingo > /dev/null 2>&1

echo
echo "Done. Now reboot:   sudo reboot"
echo "After about 40 seconds, open   http://bingo.local:8000   on a phone or laptop on the same Wi-Fi."
echo "If bingo.local does not open, use the IP from:  hostname -I"
echo "See what the robot is doing:   journalctl -u bingo -f"
