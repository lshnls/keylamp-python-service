#!/usr/bin/env bash
# ===============================
# KeyLamp User Installer (no admin)
# Bash version mirrors Windows installer with -Uninstall option
# ===============================

set -e

SERVICE_NAME="keylamp"

PROJECT_DIR="$HOME/keylamp"
VENV_DIR="$PROJECT_DIR/venv"
PYTHON_BIN="/usr/bin/python3"

SYSTEMD_USER_DIR="$HOME/.config/systemd/user"
SERVICE_FILE="$SYSTEMD_USER_DIR/${SERVICE_NAME}.service"

MAIN_SCRIPT="$PROJECT_DIR/keylamp.py"
VENV_PYTHON="$VENV_DIR/bin/python"

# parse command-line
if [[ "$1" == "-Uninstall" || "$1" == "-u" ]]; then
    echo "==> Uninstalling KeyLamp service and files"
    systemctl --user stop ${SERVICE_NAME}.service 2>/dev/null || true
    systemctl --user disable ${SERVICE_NAME}.service 2>/dev/null || true
    rm -f "$SERVICE_FILE"
    systemctl --user daemon-reload
    echo "==> Removed systemd service"
    echo "==> Deleting project directory $PROJECT_DIR"
    rm -rf "$PROJECT_DIR"
    echo "==> Uninstallation complete"
    exit 0
fi

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
