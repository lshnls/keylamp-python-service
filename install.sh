#!/usr/bin/env bash

set -e

SERVICE_NAME="keylamp"

PROJECT_DIR="$HOME/keylamp"
VENV_DIR="$PROJECT_DIR/venv"
PYTHON_BIN="/usr/bin/python3"

SYSTEMD_USER_DIR="$HOME/.config/systemd/user"
SERVICE_FILE="$SYSTEMD_USER_DIR/${SERVICE_NAME}.service"

MAIN_SCRIPT="$PROJECT_DIR/keylamp.py"
VENV_PYTHON="$VENV_DIR/bin/python"

echo "==> Creating project directory"
mkdir -p "$PROJECT_DIR"
cp keylamp.py "$PROJECT_DIR/"

echo "==> Creating virtualenv"
$PYTHON_BIN -m venv "$VENV_DIR"

echo "==> Activating venv and installing dependencies"
source "$VENV_DIR/bin/activate"

pip install --upgrade pip
pip install pyserial dbus-fast

deactivate

echo "==> Creating systemd user directory"
mkdir -p "$SYSTEMD_USER_DIR"

echo "==> Writing systemd user service"
cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=Keyboard layout lamp indicator
After=graphical-session.target
Wants=graphical-session.target

[Service]
Type=simple
ExecStart=${VENV_PYTHON} ${MAIN_SCRIPT}
Restart=on-failure
RestartSec=2

# Чтобы systemd не убивал процесс при logout, если нужно
KillMode=process

[Install]
WantedBy=default.target
EOF

echo "==> Reloading user systemd"
systemctl --user daemon-reexec
systemctl --user daemon-reload

echo "==> Enabling service"
systemctl --user enable ${SERVICE_NAME}.service

echo "==> Starting service"
systemctl --user start ${SERVICE_NAME}.service

echo "==> Done!"
