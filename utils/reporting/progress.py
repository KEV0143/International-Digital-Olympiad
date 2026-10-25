import re
from collections import Counter
from time import monotonic

from utils.reporting.catalog import definitions
from utils.reporting.terminal import elapsed_time

OUTCOMES = "PASSED|FAILED|ERROR|SKIPPED|XFAIL|XPASS"
RESULT = re.compile(
    rf"^(?:\[gw\d+\]\s+\[\s*\d+%\]\s+(?P<parallel>{OUTCOMES})\s+(?P<pnode>.+::.+?)"
    rf"|(?P<snode>.+::.+?)\s+(?P<serial>{OUTCOMES})"
    rf"(?:\s+\([^\r\n]*\))?(?:\s+\[\s*\d+%\])?)\s*$"
)
RANK = {"PASSED": 0, "XFAIL": 1, "SKIPPED": 2, "XPASS": 3, "FAILED": 4, "ERROR": 5}


def scenario_names(root):
    return {
        f"{path.relative_to(root).as_posix()}::{name}": f"{row[0]}. {row[1]}"
        for path, name, row in definitions(root)
    }


class PytestProgress:
    def __init__(self, browser, terminal, names=None):
        self.browser = browser.capitalize()
        self.terminal = terminal
        self.names = names or {}
        self.started = monotonic()
        self.last_heartbeat = self.started
        self.total = None
        self.results = {}
        self.active = set()

    def counter(self):
        if self.total is None:
            return "сбор тестов"
        done = len(self.results)
        percent = min(100, done * 100 // self.total) if self.total else 0
        return f"{done}/{self.total} ({percent}%)"

    def consume(self, line):
        parallel = re.search(r"\d+ workers \[(\d+) items\]", line)
        serial = re.search(r"collected (\d+) items?", line)
        if parallel or serial:
            selected = re.search(r"/ (\d+) selected", line)
            self.total = int((selected or parallel or serial).group(1))
            self.tick()
            self.terminal.write(
                f"{self.browser} | собрано тестов: {self.total} | {self.counter()}",
                elapsed=monotonic() - self.started,
            )
            return
        match = RESULT.match(line)
        if match:
            node = (match.group("pnode") or match.group("snode")).replace("\\", "/")
            outcome = match.group("parallel") or match.group("serial")
            old = self.results.get(node)
            self.active.discard(node)
            if old is not None and RANK[old] >= RANK[outcome]:
                return
            self.results[node] = outcome
            self.tick()
            level, status = (
                ("Info", "+")
                if outcome == "PASSED"
                else ("Error", "-")
                if outcome in ("FAILED", "ERROR", "XPASS")
                else ("Warn", "!")
            )
            label = self.names.get(node, node.split("::")[-1])
            suffix = "" if outcome == "PASSED" else f" | {outcome}"
            self.terminal.write(
                f"{self.browser} | {self.counter()} | {label}{suffix}",
                level=level,
                status=status,
                elapsed=monotonic() - self.started,
            )
        elif re.fullmatch(r"\S+\.py::[^\r\n]+", line.strip()):
            self.active.add(line.strip().replace("\\", "/"))

    def tick(self):
        message = f"{self.browser} | {self.counter()}"
        if self.active:
            ids = [
                self.names.get(node, node.split("::")[-1]).split(".", 1)[0] for node in self.active
            ]
            message += " | " + ", ".join(sorted(ids))
        elif self.total is not None and len(self.results) == self.total:
            message += " | завершение"
        self.terminal.progress(self.browser, message)
        now = monotonic()
        if not self.terminal.interactive and now - self.last_heartbeat >= 10:
            self.terminal.write(message, elapsed=now - self.started)
            self.last_heartbeat = now

    def finish(self, code):
        self.terminal.finish(self.browser)
        counts = Counter(self.results.values())
        self.terminal.write(
            f"{self.browser} | {self.counter()} | PASSED: {counts['PASSED']} | "
            f"FAILED/ERROR: {counts['FAILED'] + counts['ERROR']} | "
            f"SKIPPED/XFAIL/XPASS: {counts['SKIPPED'] + counts['XFAIL'] + counts['XPASS']} | "
            f"код {code} | время {elapsed_time(monotonic() - self.started)}",
            level="Error" if code else "Info",
            status="-" if code else "+",
            elapsed=monotonic() - self.started,
        )
