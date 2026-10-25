import io
import os
import signal
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import monotonic

import pytest

from utils.reporting.progress import PytestProgress, scenario_names
from utils.reporting.terminal import Terminal, elapsed_time, follow_process


@pytest.mark.parametrize(
    ("collection", "result", "total"),
    [
        ("2 workers [8 items]", "[gw0] [ 12%] PASSED tests/ui/test_a.py::test_one", 8),
        (
            "collected 50 items / 42 deselected / 8 selected",
            "tests/ui/test_a.py::test_one PASSED [ 12%]",
            8,
        ),
        ("collected 1 item", "tests/ui/test_a.py::test_one PASSED [100%]", 1),
    ],
)
def test_selected_count_and_progress_in_parallel_and_serial_output(collection, result, total):
    stream = io.StringIO()
    progress = PytestProgress("chrome", Terminal(stream))
    progress.consume(collection)
    progress.consume(result)
    assert progress.total == total
    assert progress.counter() == f"1/{total} ({100 // total}%)"
    assert "test_one [+]" in stream.getvalue()


def test_teardown_error_replaces_pass_without_counting_test_twice():
    stream = io.StringIO()
    progress = PytestProgress("firefox", Terminal(stream))
    progress.consume("2 workers [2 items]")
    for status in ("PASSED", "ERROR", "ERROR", "PASSED"):
        progress.consume(f"[gw0] [ 50%] {status} tests/ui/test_a.py::test_one")
    assert progress.results == {"tests/ui/test_a.py::test_one": "ERROR"}
    assert progress.counter() == "1/2 (50%)"
    assert stream.getvalue().count("test_one") == 2
    assert "ERROR [-]" in stream.getvalue()


def test_failure_summary_does_not_create_extra_results():
    progress = PytestProgress("chrome", Terminal(io.StringIO()))
    progress.consume("collected 50 items / 50 deselected / 0 selected")
    progress.consume("FAILED tests/ui/test_a.py::test_one - AssertionError")
    assert progress.counter() == "0/0 (0%)"
    assert not progress.results


def test_real_process_streams_split_utf8_and_finishes_with_inherited_stdout(tmp_path):
    log_path = tmp_path / "child.log"
    pid_file = tmp_path / "grandchild.pid"
    payload = "Живой прогресс\n".encode()
    program = "\n".join(
        [
            "import subprocess, sys, time",
            "from pathlib import Path",
            "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(10)'])",
            "Path(sys.argv[1]).write_text(str(child.pid))",
            f"payload = bytes.fromhex('{payload.hex()}')",
            "sys.stdout.buffer.write(payload[:1]); sys.stdout.buffer.flush()",
            "time.sleep(0.15)",
            "sys.stdout.buffer.write(payload[1:]); sys.stdout.buffer.flush()",
            "time.sleep(0.5)",
            "sys.stdout.write('last line without newline'); sys.stdout.flush()",
            "sys.exit(7)",
        ]
    )
    seen = []
    try:
        with log_path.open("w", encoding="utf-8") as log:
            with subprocess.Popen(
                [sys.executable, "-u", "-c", program, str(pid_file)],
                stdout=log,
                stderr=subprocess.STDOUT,
            ) as process:
                started = monotonic()
                code = follow_process(
                    process, log_path, lambda line: seen.append((line, process.poll()))
                )
                seconds = monotonic() - started
        assert code == 7
        assert seen[0] == ("Живой прогресс", None)
        assert seen[1][0] == "last line without newline"
        assert seconds < 5, "Parent exit must not wait for the inherited child handle"
        assert log_path.read_text(encoding="utf-8") == "Живой прогресс\nlast line without newline"
    finally:
        if pid_file.exists():
            try:
                os.kill(int(pid_file.read_text()), signal.SIGTERM)
            except ProcessLookupError:
                pass


def test_redirected_multithreaded_output_has_complete_plain_lines(monkeypatch):
    monkeypatch.delenv("FORCE_COLOR", raising=False)
    stream = io.StringIO()
    terminal = Terminal(stream)

    def write(browser):
        for index in range(20):
            terminal.progress(browser, f"{browser} {index}/20")
            terminal.write(f"{browser} {index}/20", status="+", elapsed=65)
        terminal.finish(browser)

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(write, ("Chrome", "Firefox")))
    lines = stream.getvalue().splitlines()
    assert len(lines) == 40
    assert all(line.startswith(" | Info | 01:05 | ") and line.endswith("[+]") for line in lines)
    assert "\x1b" not in stream.getvalue()
    assert "\r" not in stream.getvalue()
    assert not terminal.status


def test_colors_and_no_color_setting(monkeypatch):
    monkeypatch.setenv("FORCE_COLOR", "1")
    monkeypatch.delenv("NO_COLOR", raising=False)
    stream = io.StringIO()
    Terminal(stream).write("готово", status="+", elapsed=0)
    assert "\x1b[38;2;255;255;170mInfo" in stream.getvalue()
    assert "\x1b[38;2;128;255;128m[+]" in stream.getvalue()
    monkeypatch.setenv("NO_COLOR", "1")
    plain = io.StringIO()
    Terminal(plain).write("готово", status="+", elapsed=0)
    assert plain.getvalue() == " | Info | 00:00 | готово [+]\n"


def test_interactive_footer_updates_immediately_and_is_cleared_at_finish(monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    stream = io.StringIO()
    stream.isatty = lambda: True
    terminal = Terminal(stream)
    progress = PytestProgress("chrome", terminal)
    progress.consume("2 workers [1 items]")
    progress.consume("[gw0] [100%] PASSED tests/ui/test_a.py::test_one")
    assert terminal.status == {"Chrome": "Chrome | 1/1 (100%) | завершение"}
    assert "\r\x1b[2K" in stream.getvalue()
    progress.finish(0)
    assert not terminal.status
    assert stream.getvalue().endswith("[+]\n")


def test_scenario_labels_are_read_from_current_decorators():
    root = Path(__file__).resolve().parents[2]
    names = scenario_names(root)
    assert len(names) == 55
    assert names["tests/ui/test_form_fields.py::test_automation_tools_are_pasted_into_message"] == (
        "FF-S01. Список Automation Tools переносится в Message"
    )


def test_elapsed_time_formats_hours_minutes_and_seconds():
    assert elapsed_time(3661) == "01:01:01"


@pytest.mark.parametrize("parallel", [False, True])
def test_parameter_ids_with_spaces_are_not_truncated(parallel):
    node = "tests/ui/test_a.py::test_case[foo bar]"
    line = f"[gw0] [100%] PASSED {node}" if parallel else f"{node} PASSED [100%]"
    progress = PytestProgress("chrome", Terminal(io.StringIO()))
    progress.consume("collected 1 item")
    progress.consume(node)
    progress.consume(line)
    assert progress.results == {node: "PASSED"}
    assert not progress.active
