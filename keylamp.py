
"""Монитор раскладки клавиатуры.

Программа отслеживает изменение раскладки (US/RU) на Linux‑GNOME и Windows,
и посылает соответствующую команду по последовательному порту к Arduino,
который управляет светодиодом (RGB). Цвета задаются константами ниже.
"""
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
# Значения, отправляемые на Arduino. Arduino ожидает
# символьные команды: '1' – красный, '2' – зелёный и т.д.
# Программа маппит раскладки -> цвет с помощью словарей ниже.

RED = "1"
GREEN = "2"
BLUE = "3"
GRAY = "8"
WHITE = "9"
BLACK = "0"

COLORS_LINUX = {
    "us": GREEN,
    "ru": RED,
}

# Для Windows используется идентификатор языка (LANGID)
# из WinAPI. Здесь маппим только US и RU.
COLORS_WINDOWS = {
    0x0409: GREEN,   # English (US)
    0x0419: RED,    # Russian
}

# Сколько секунд ждать появления D-Bus интерфейса при старте
START_TIMEOUT_SECONDS = 15

# =========================
# LOGGING
# =========================
# Настройка простого логгера, выводящего в stdout. Используется для
# сообщений о проверке портов, отправке цветов и ошибках.

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
    """Вернуть список доступных последовательных портов.

    На Windows возвращаются все доступные com-порты. На Unix фильтруются
    только устройства, начинающиеся с /dev/ttyUSB или /dev/ttyACM, так как
    обычно Arduino монтируются именно там.
    """
    ports = list_ports.comports()

    if platform.system() == "Windows":
        return ports
    else:
        return [
            p for p in ports
            if p.device.startswith(("/dev/ttyUSB", "/dev/ttyACM"))
        ]


async def connect_to_arduino() -> Optional[serial.Serial]:
    """Ищет Arduino по последовательным портам и возвращает объект Serial.

    Перебираются доступные порты, по каждому открывается соединение на 9600
    бод с таймаутом. После ожидания 2 секунд отправляется "?" – Arduino по
    протоколу должен ответить строкой "ARDUINO_OK". Только в этом случае
    соединение считается установленным; иначе порт закрывается и ищется
    следующий.
    Если ни один порт не подошёл, возвращается None.
    """
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
    """Следит за изменением раскладки в GNOME через D-Bus и посылает цвет.

    ser -- открытый объект serial.Serial для передачи команд Arduino.
    """
    from dbus_fast import DBusError, Message
    from dbus_fast.aio import MessageBus

    BUS_NAME = "org.gnome.InputSourceMonitor"
    BUS_PATH = "/org/gnome/InputSourceMonitor"

    async def wait_for_interface(bus):
        # Пытаемся получить интерфейс сервиса, дергая introspect.
        # Интерфейс может появиться чуть позже, поэтому пробуем несколько
        # раз и делаем паузу. Если по истечении таймаута не получилось,
        # возвращаем None.
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

    # заводской сигнал в начале, чтобы LED сразу перешёл в US
    # (некоторые прошивки Arduino ожидают явный статус при старте)
    try:
        msg = Message(
            destination=BUS_NAME,
            path=BUS_PATH,
            interface=BUS_NAME,
            member="SourceChanged",
            signature="s",
            body=["us"],
        )
        await bus.send(msg)
        logger.info("Emitted startup SourceChanged('us') signal")
    except Exception as e:
        logger.warning(f"Could not emit startup signal: {e}")

    last_color = None

    def send_color(color: str):
        # Отправляем команду Arduino, но не делаем лишних записей
        # если цвет не изменился. last_color хранит предыдущий.
        nonlocal last_color
        if color == last_color:
            return

        try:
            ser.write(color.encode())
            last_color = color
        #    logger.info(f"Sent color {color}")
        except Exception as e:
            logger.error(f"Serial error: {e}")
            os._exit(1)

    
    def handle_source_change(source: str):
        # callback D-Bus, получает идентификатор раскладки ('us','ru',...)
        color = COLORS_LINUX.get(source)
        if color:
            send_color(color)
        #    logger.info(f"Layout: {source}")

    # Попытка определить текущую раскладку через gsettings
    try:
        import subprocess, ast
        out = subprocess.check_output(
            ["gsettings", "get", "org.gnome.desktop.input-sources", "current"],
            text=True,
        ).strip()
        idx = int(out.split()[-1])
        sources_out = subprocess.check_output(
            ["gsettings", "get", "org.gnome.desktop.input-sources", "sources"],
            text=True,
        )
        sources = ast.literal_eval(sources_out)
        if 0 <= idx < len(sources):
            layout = sources[idx][1]
            color = COLORS_LINUX.get(layout)
            if color:
                send_color(color)
                logger.info(f"Initial layout {layout}, sent color {color}")
            else:
                logger.info(f"Initial layout {layout} has no mapped color")
        else:
            logger.info("gsettings reports invalid index")
    except Exception as e:
        logger.info(f"Could not determine initial layout via gsettings: {e}")

    interface.on_source_changed(handle_source_change)

    logger.info("Listening for Linux input source changes")

    await asyncio.Future()  # run forever


# =========================
# WINDOWS
# =========================

def get_windows_layout():
    """Возвращает LANGID текущей раскладки через WinAPI.

    Получается дескриптор окна, затем поток, и вызывается
    GetKeyboardLayout. Из resulting HKL берётся нижние 16 бит как LANGID.
    """
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
    """Поллинг раскладки на Windows и отправка цвета по serial.

    stop_event позволяет безопасно завершить цикл извне (например, при
    получении сигнала). Интервал опроса 0.3 секунды.
    """
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

async def main():
    """Точка входа: подключается к Arduino и запускает монитор нужной ОС.

    Регистрирует обработчики сигналов и гарантирует выключение светодиода
    при выходе.
    """
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

        # установка обработчиков сигналов. Windows не поддерживает
        # asyncio.loop.add_signal_handler, поэтому ловим SIGINT вручную.
        if platform.system() == "Windows":
            # Обработка Ctrl+C на Windows
            def handle_windows_exit(signum, frame):
                logger.info("Termination signal received")
                cleanup()
                sys.exit(0)

            signal.signal(signal.SIGINT, handle_windows_exit)
        else:
            # Обработка Unix-сигналов через asyncio loop.
            # кнопка Ctrl+C и SIGTERM приводят к тому же поведению.
            def handle_signal():
                logger.info("Termination signal received")
                cleanup()
                os._exit(1)

            loop = asyncio.get_running_loop()
            loop.add_signal_handler(signal.SIGTERM, handle_signal)
            loop.add_signal_handler(signal.SIGINT, handle_signal)


        # В зависимости от платформы запускаем соответствующий монитор.
        # Для Windows мы передаём stop_event, который при необходимости
        # может быть установлен извне (например, при завершении программы),
        # хотя в данном скрипте он остаётся неиспользованным.
        if platform.system() == "Windows":
            await monitor_windows_layout(ser, stop_event)
        else:
            await monitor_linux_layout(ser)

    finally:
        # Убедиться, что светодиод отключен при выходе
        cleanup()



if __name__ == "__main__":
    # При запуске скрипта напрямую стартуем asyncio цикл. В случае
    # KeyboardInterrupt (Ctrl+C) или любой другой ошибки мы аккуратно
    # логируем причину и завершаем процесс с кодом 0.
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
    finally:
        logger.info("Application terminated")
        sys.exit(0)