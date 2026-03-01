import asyncio
import logging
import os
import sys
import platform
import signal
from typing import Optional

import serial
from serial.tools import list_ports

# =========================
# CONFIG
# =========================

RED = "1"
GREEN = "2"
BLUE = "3"
GRAY = "8"
WHITE = "9"
BLACK = "0"

COLORS_LINUX = {
    "us": BLUE,
    "ru": RED,
}

COLORS_WINDOWS = {
    0x0409: BLUE,   # English (US)
    0x0419: RED,    # Russian
}

START_TIMEOUT_SECONDS = 15

# =========================
# LOGGING
# =========================

logger = logging.getLogger("kb_indicator")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stdout,
)

# =========================
# SERIAL
# =========================

def list_serial_ports():
    ports = list_ports.comports()

    if platform.system() == "Windows":
        return ports
    else:
        return [
            p for p in ports
            if p.device.startswith(("/dev/ttyUSB", "/dev/ttyACM"))
        ]


async def connect_to_arduino() -> Optional[serial.Serial]:
    ports = list_serial_ports()

    if not ports:
        logger.warning("No serial devices found")
        return None

    for p in ports:
        logger.info(f"Trying {p.device}")
        try:
            ser = serial.Serial(p.device, 9600, timeout=1)
            await asyncio.sleep(2)

            ser.write(b"?")
            reply = await asyncio.to_thread(ser.readline)
            reply = reply.decode(errors="ignore").strip()

            if reply == "ARDUINO_OK":
                logger.info(f"Connected to {p.device}")
                return ser

            ser.close()

        except serial.SerialException as e:
            logger.warning(f"{p.device}: {e}")

    return None


# =========================
# LINUX (GNOME)
# =========================

async def monitor_linux_layout(ser: serial.Serial):
    from dbus_fast import DBusError
    from dbus_fast.aio import MessageBus

    BUS_NAME = "org.gnome.InputSourceMonitor"
    BUS_PATH = "/org/gnome/InputSourceMonitor"

    async def wait_for_interface(bus):
        for _ in range(START_TIMEOUT_SECONDS):
            try:
                introspection = await bus.introspect(BUS_NAME, BUS_PATH)
                proxy = bus.get_proxy_object(BUS_NAME, BUS_PATH, introspection)
                return proxy.get_interface(BUS_NAME)
            except DBusError:
                await asyncio.sleep(1)
        return None

    bus = await MessageBus().connect()
    interface = await wait_for_interface(bus)

    if not interface:
        logger.error("D-Bus service unavailable")
        sys.exit(1)

    last_color = None

    def send_color(color: str):
        nonlocal last_color
        if color == last_color:
            return

        try:
            ser.write(color.encode())
            last_color = color
            logger.info(f"Sent color {color}")
        except Exception as e:
            logger.error(f"Serial error: {e}")
            os._exit(1)

    send_color(GRAY)

    def handle_source_change(source: str):
        color = COLORS_LINUX.get(source)
        if color:
            send_color(color)
            logger.info(f"Layout: {source}")

    interface.on_source_changed(handle_source_change)

    logger.info("Listening for Linux input source changes")

    await asyncio.Future()  # run forever


# =========================
# WINDOWS
# =========================

def get_windows_layout():
    import ctypes
    import ctypes.wintypes
    #from dbus_fast import DBusError
    #from dbus_fast.aio import MessageBus

    user32 = ctypes.WinDLL("user32", use_last_error=True)

    GetForegroundWindow = user32.GetForegroundWindow
    GetWindowThreadProcessId = user32.GetWindowThreadProcessId
    GetKeyboardLayout = user32.GetKeyboardLayout

    hwnd = GetForegroundWindow()
    thread_id = GetWindowThreadProcessId(hwnd, None)
    hkl = GetKeyboardLayout(thread_id)

    return hkl & 0xFFFF


async def monitor_windows_layout(ser: serial.Serial, stop_event: asyncio.Event):
    last_lang = None
    last_color = None

    logger.info("Listening for Windows layout changes")

    while not stop_event.is_set():
        try:
            lang = get_windows_layout()

            if lang != last_lang:
                color = COLORS_WINDOWS.get(lang)
                if color and color != last_color:
                    ser.write(color.encode())
                    last_color = color
                    logger.info(f"Sent color {color} for lang {hex(lang)}")

                last_lang = lang

            await asyncio.sleep(0.3)

        except Exception as e:
            logger.error(f"Serial error: {e}")
            os._exit(1)
    logger.info("Windows layout monitor exiting")


# =========================
# MAIN
# =========================

async def handle_ipc(reader, writer, ser, stop_event: asyncio.Event):
    data = await reader.readline()
    cmd = data.decode().strip().lower()
    addr = writer.get_extra_info('peername')
    logger.info(f"Received IPC command '{cmd}' from {addr}")
    if cmd in ('off', 'shutdown'):
        try:
            ser.write(BLACK.encode())
            logger.info("LED turned off via IPC")
        except Exception as e:
            logger.error(f"Failed to write to serial during IPC: {e}")
    if cmd == 'shutdown':
        stop_event.set()
    writer.close()

async def start_ipc_server(ser, stop_event: asyncio.Event):
    server = await asyncio.start_server(
        lambda r, w: handle_ipc(r, w, ser, stop_event),
        '127.0.0.1', 8765
    )
    logger.info("IPC server listening on 127.0.0.1:8765")
    async with server:
        await server.serve_forever()

async def main():
    stop_event = asyncio.Event()
    ser = None

    def cleanup():
        """Отключить светодиод и закрыть соединение"""
        try:
            if ser and ser.is_open:
                logger.info("Turning off LED")
                ser.write(BLACK.encode())
                ser.close()
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")

    try:
        ser = await connect_to_arduino()
        if not ser:
            sys.exit(1)

        # atexit на всякий случай
        import atexit
        atexit.register(cleanup)

        if platform.system() == "Windows":
            # Обработка Ctrl+C на Windows
            def handle_windows_exit(signum, frame):
                logger.info("Termination signal received")
                cleanup()
                sys.exit(0)

            signal.signal(signal.SIGINT, handle_windows_exit)
        else:
            # Обработка Unix-сигналов
            def handle_signal():
                logger.info("Termination signal received")
                cleanup()
                os._exit(0)

            loop = asyncio.get_running_loop()
            loop.add_signal_handler(signal.SIGTERM, handle_signal)
            loop.add_signal_handler(signal.SIGINT, handle_signal)

        # запустить IPC сервер на Windows
        if platform.system() == "Windows":
            asyncio.create_task(start_ipc_server(ser, stop_event))
            await monitor_windows_layout(ser, stop_event)
        else:
            await monitor_linux_layout(ser)

    finally:
        # Убедиться, что светодиод отключен при выходе
        cleanup()



if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
    finally:
        logger.info("Application terminated")
        sys.exit(0)