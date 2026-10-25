import codecs
import os
import shutil
import sys
import threading
from time import monotonic, sleep


def elapsed_time(seconds):
    hours, rest = divmod(max(0, int(seconds)), 3600)
    minutes, seconds = divmod(rest, 60)
    return f"{hours:02}:{minutes:02}:{seconds:02}" if hours else f"{minutes:02}:{seconds:02}"


def enable_windows_colors(stream):
    if sys.platform != "win32":
        return True
    import ctypes
    import msvcrt
    from ctypes import wintypes

    try:
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GetConsoleMode.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel.SetConsoleMode.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        mode = wintypes.DWORD()
        handle = msvcrt.get_osfhandle(stream.fileno())
        return bool(
            kernel.GetConsoleMode(handle, ctypes.byref(mode))
            and kernel.SetConsoleMode(handle, mode.value | 0x0004)
        )
    except (OSError, ValueError, AttributeError):
        return False


class Terminal:
    COLORS = {
        "pipe": "\x1b[38;2;122;204;198m",
        "Info": "\x1b[38;2;255;255;170m",
        "Warn": "\x1b[38;2;255;218;117m",
        "Error": "\x1b[38;2;255;115;115m",
        "text": "\x1b[38;2;184;203;219m",
        "+": "\x1b[38;2;128;255;128m",
        "": "\x1b[38;2;255;218;117m",
        "!": "\x1b[38;2;255;218;117m",
        "-": "\x1b[38;2;255;115;115m",
    }

    def __init__(self, stream=None):
        self.stream = stream if stream is not None else sys.stdout
        self.started = monotonic()
        self.interactive = self.stream.isatty()
        self.color = "NO_COLOR" not in os.environ and (
            (self.interactive and enable_windows_colors(self.stream))
            or os.environ.get("FORCE_COLOR") == "1"
        )
        self.lock = threading.RLock()
        self.status = {}

    def paint(self, value, color):
        return self.COLORS[color] + value + "\x1b[0m" if self.color else value

    def line(self, message, level, status, elapsed):
        pipe = self.paint("|", "pipe")
        return (
            f" {pipe} {self.paint(level, level)} {pipe} "
            f"{self.paint(elapsed_time(elapsed), 'text')} {pipe} "
            f"{self.paint(message, 'text')} {self.paint('[' + status + ']', status)}"
        )

    def clear(self):
        if self.interactive and self.status:
            self.stream.write("\r\x1b[2K")

    def redraw(self):
        if self.interactive and self.status:
            message = " | ".join(self.status.values())
            width = max(20, shutil.get_terminal_size((120, 20)).columns - 1)
            prefix = f" | Info | {elapsed_time(monotonic() - self.started)} | "
            available = max(1, width - len(prefix) - len(" []"))
            if len(message) > available:
                message = message[: max(0, available - 1)] + "…"
            self.stream.write(self.line(message, "Info", "", monotonic() - self.started))
            self.stream.flush()

    def write(self, message, level="Info", status="", elapsed=None):
        if elapsed is None:
            elapsed = monotonic() - self.started
        with self.lock:
            self.clear()
            for line in str(message).splitlines() or [""]:
                self.stream.write(self.line(line, level, status, elapsed) + "\n")
            self.redraw()
            self.stream.flush()

    def gap(self):
        with self.lock:
            self.clear()
            self.stream.write(" \n")
            self.redraw()
            self.stream.flush()

    def progress(self, key, message):
        with self.lock:
            self.clear()
            self.status[key] = message
            self.redraw()

    def finish(self, key):
        with self.lock:
            self.clear()
            self.status.pop(key, None)
            self.redraw()


def follow_process(process, path, on_line, on_tick=None):
    decoder = codecs.getincrementaldecoder("utf-8")("replace")
    pending = ""
    next_tick = 0
    with path.open("rb") as reader:
        while True:
            pending += decoder.decode(reader.read())
            while "\n" in pending:
                line, pending = pending.split("\n", 1)
                on_line(line.rstrip("\r"))
            now = monotonic()
            if on_tick is not None and now >= next_tick:
                on_tick()
                next_tick = now + 1
            code = process.poll()
            if code is not None:
                pending += decoder.decode(reader.read(), final=True)
                for line in pending.splitlines():
                    on_line(line)
                return code
            sleep(0.1)


console = Terminal()
