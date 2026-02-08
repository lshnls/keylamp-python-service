import asyncio
import logging
import os
import sys
from typing import Optional

import serial
import signal

from serial.tools import list_ports

from dbus_fast import DBusError
from dbus_fast.aio import MessageBus, ProxyInterface

START_TIMEOUT_SECONDS = 15

BUS_NAME = "org.gnome.InputSourceMonitor"
BUS_PATH = "/org/gnome/InputSourceMonitor"

RED = "1"
GREEN = "2"
BLUE = "3"
GRAY = "8"
WHITE = "9"
BLACK = "0"

COLORS = {
    "us": BLUE,
    "ru": RED,
}

logger = logging.getLogger("kb_indicator")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stdout,
)


async def wait_for_input_source_interface(bus: MessageBus) -> Optional[ProxyInterface]:
    for attempt in range(1, START_TIMEOUT_SECONDS + 1):
        try:
            introspection = await bus.introspect(BUS_NAME, BUS_PATH)
            proxy = bus.get_proxy_object(BUS_NAME, BUS_PATH, introspection)
            logger.info("Connected to D-Bus")
            return proxy.get_interface(BUS_NAME)
        except DBusError:
            logger.info(f"Try #{attempt}: D-Bus not ready")
            await asyncio.sleep(1)

    return None


def list_serial_ports():
    return [
        p for p in list_ports.comports()
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


async def main():

    stop_event = asyncio.Event()

    # Обработчик сигнала SIGTERM и SIGINT
    def handle_termination():
        logger.info("Received termination signal, stopping...")
        stop_event.set()

    loop = asyncio.get_running_loop()
    loop.add_signal_handler(signal.SIGTERM, handle_termination)
    loop.add_signal_handler(signal.SIGINT, handle_termination)

    if "HOME" not in os.environ:
        logger.error("HOME is not set, cannot connect to session D-Bus")
        return

    
    ser = await connect_to_arduino()
    if not ser:
        return

    last_color: Optional[str] = None

    def send_color(color: str):
        nonlocal last_color

        if color == last_color:
            return

        if not ser.is_open:
            logger.error("Serial port closed")
            stop_event.set()
            return

        try:
            ser.write(color.encode())
            last_color = color
            logger.info(f"Sent color {color}")
        except Exception as e:
            logger.error(f"Serial write error: {e}")
            stop_event.set()

    try:
        bus = await MessageBus().connect()
        interface = await wait_for_input_source_interface(bus)

        if not interface:
            logger.error("D-Bus service unavailable")
            return
        
        # Здесь можно поставить цвет при запуске
        if ser.is_open:
            send_color(GRAY)
            
        def handle_source_change(source: str):
            color = COLORS.get(source)
            if color:
                send_color(color)
                logger.info(f"Layout: {source}")

        interface.on_source_changed(handle_source_change)  # type: ignore

        logger.info("Listening for input source changes")

        await stop_event.wait()

    except DBusError as e:
        logger.error(f"D-Bus error: {e}")

    finally:
        try:
            if ser.is_open:
                send_color(BLACK)
                ser.close()
        except Exception:
            pass

        try:
            bus.disconnect()
        except Exception:
            pass
    await stop_event.wait()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
