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
pip install serial

deactivate

echo "==> Adding user to serial port access group"
TARGET_USER="$USER"
if [[ -n "$SUDO_USER" ]]; then
    TARGET_USER="$SUDO_USER"
elif [[ -n "$(logname 2>/dev/null)" ]]; then
    TARGET_USER="$(logname)"
fi

DEVICE_GROUP=""
for GROUP in dialout uucp tty; do
    if getent group "$GROUP" > /dev/null 2>&1; then
        DEVICE_GROUP="$GROUP"
        break
    fi
 done

if [[ -z "$DEVICE_GROUP" ]]; then
    DEVICE_GROUP="dialout"
    echo "==> Group '$DEVICE_GROUP' not found, creating group..."
    sudo groupadd "$DEVICE_GROUP"
fi

echo "==> Using device group '$DEVICE_GROUP'"

echo "==> Adding user '$TARGET_USER' to group '$DEVICE_GROUP'..."
sudo usermod -aG "$DEVICE_GROUP" "$TARGET_USER"

echo "==> Note: log out and log back in (or run 'newgrp $DEVICE_GROUP') for group membership to take effect"

echo "==> Creating udev rule for serial devices"
UDEV_RULE="SUBSYSTEM==\"tty\", KERNEL==\"ttyUSB[0-9]*\", GROUP=\"$DEVICE_GROUP\", MODE=\"0660\"\nSUBSYSTEM==\"tty\", KERNEL==\"ttyACM[0-9]*\", GROUP=\"$DEVICE_GROUP\", MODE=\"0660\"\n"

echo -e "$UDEV_RULE" | sudo tee /etc/udev/rules.d/99-keylamp-serial.rules >/dev/null
sudo udevadm control --reload-rules || true
sudo udevadm trigger --type=devices --action=change || true

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
