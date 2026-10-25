import io
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import app
from tools.environment import bootstrap
from tools.runner import run_suite
from utils.reporting.terminal import Terminal


@pytest.mark.parametrize("value", ["0", "-1", "nan", "inf", "-inf"])
def test_invalid_timeout_rejected(value):
    with pytest.raises(app.argparse.ArgumentTypeError):
        app.positive_number(value)


def test_failed_install_does_not_write_dependency_stamp(monkeypatch, tmp_path):
    environment = tmp_path / "tools/.venv"
    environment.mkdir(parents=True)
    dependencies = tmp_path / "data/dependencies"
    dependencies.mkdir(parents=True)
    (dependencies / "requirements.txt").write_text("pytest==9.1.1\n", encoding="utf-8")
    monkeypatch.setattr(bootstrap, "supported_python", lambda _: Path(sys.executable))
    failed = Mock(return_value=SimpleNamespace(returncode=1, stdout=""))
    monkeypatch.setattr(bootstrap.subprocess, "run", failed)
    with pytest.raises(bootstrap.BootstrapError, match="кодом 1"):
        bootstrap.ensure_python(tmp_path)
    assert not (environment / "dependencies.json").exists()


def test_report_failure_preserves_test_outcome_and_summary(monkeypatch, tmp_path):
    monkeypatch.setattr(run_suite, "ROOT", tmp_path)
    monkeypatch.setattr(run_suite, "run_browser", lambda *_: {"exit_code": 0})

    def broken_report(*_):
        raise OSError("report generator unavailable")

    monkeypatch.setattr(run_suite, "generate_report", broken_report)
    monkeypatch.setattr(sys, "argv", ["run_suite", "--report"])
    assert run_suite.main() == 2
    folder = Path((tmp_path / "data/results/last-run.txt").read_text(encoding="utf-8"))
    saved = json.loads((folder / "run.json").read_text(encoding="utf-8"))
    assert saved["browsers"]["chrome"]["exit_code"] == 0
    assert saved["report_exit_code"] == saved["exit_code"] == 2
    assert saved["report_error"] == "report generator unavailable"


def test_browser_failure_cannot_be_overridden_by_successful_report(monkeypatch, tmp_path):
    monkeypatch.setattr(run_suite, "ROOT", tmp_path)
    monkeypatch.setattr(run_suite, "run_browser", lambda *_: {"exit_code": 1})
    monkeypatch.setattr(run_suite, "generate_report", lambda *_: 0)
    monkeypatch.setattr(sys, "argv", ["run_suite", "--browser", "both", "--report"])
    assert run_suite.main() == 1
    folder = Path((tmp_path / "data/results/last-run.txt").read_text(encoding="utf-8"))
    saved = json.loads((folder / "run.json").read_text(encoding="utf-8"))
    assert set(saved["browsers"]) == {"chrome", "firefox"}
    assert all(result["exit_code"] == 1 for result in saved["browsers"].values())
    assert saved["report_exit_code"] == 0
    assert saved["exit_code"] == 1


@pytest.mark.parametrize(
    ("stdin_tty", "stdout_tty", "no_pause", "expected"),
    [
        (True, True, False, True),
        (True, True, True, False),
        (False, True, False, False),
        (True, False, False, False),
        (False, False, False, False),
    ],
)
def test_pause_requires_interactive_input_and_output(
    monkeypatch, stdin_tty, stdout_tty, no_pause, expected
):
    stream = io.StringIO()
    monkeypatch.setattr(app, "console", Terminal(stream))
    monkeypatch.setattr(sys.stdin, "isatty", lambda: stdin_tty)
    monkeypatch.setattr(sys.stdout, "isatty", lambda: stdout_tty)
    read_enter = Mock(return_value="")
    monkeypatch.setattr("builtins.input", read_enter)
    assert app.finish_run(1, no_pause) == 1
    assert read_enter.called == expected
    assert ("нажмите Enter для закрытия программы" in stream.getvalue()) == expected


@pytest.mark.parametrize("exception", [EOFError, KeyboardInterrupt])
def test_closing_pause_preserves_original_exit_code(monkeypatch, exception):
    monkeypatch.setattr(app, "console", Terminal(io.StringIO()))
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    monkeypatch.setattr("builtins.input", Mock(side_effect=exception))
    assert app.finish_run(2) == 2


@pytest.mark.parametrize("report_code", [0, 2])
def test_summary_counts_both_browsers_and_reports_html_availability(
    monkeypatch, tmp_path, report_code
):
    stream = io.StringIO()
    monkeypatch.setattr(run_suite, "console", Terminal(stream))
    report = tmp_path / "allure-report/index.html"
    if report_code == 0:
        report.parent.mkdir()
        report.write_text("report", encoding="utf-8")
    summary = {
        "browsers": {
            "chrome": {"collected": 50, "test_counts": {"PASSED": 49, "ERROR": 1}},
            "firefox": {"collected": 50, "test_counts": {"PASSED": 50}},
        },
        "wall_seconds": 321.078,
        "exit_code": 1 if report_code == 0 else 2,
        "report_exit_code": report_code,
    }
    run_suite.show_summary(tmp_path, summary)
    output = stream.getvalue()
    assert "выполнено: 100/100 | успешно: 99 | ошибок: 1 | пропущено: 0" in output
    assert "Затраченное время: 05:21 (321.1 с)" in output
    assert (
        output.index("Статистика") < output.index("Затраченное время") < output.index("HTML-отчёт")
    )
    if report_code == 0:
        assert f"HTML-отчёт: {report}" in output
    else:
        assert "HTML-отчёт не создан. Журнал сборки:" in output
        assert f"HTML-отчёт: {report}" not in output
