import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

from tools.runner import run_suite
from tools.verification import verify_run

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("phase", ["tests", "report"])
def test_interrupted_run_saves_nonzero_status(monkeypatch, tmp_path, phase):
    monkeypatch.setattr(run_suite, "ROOT", tmp_path)
    run_browser = Mock(return_value={"exit_code": 0})
    report = Mock(return_value=0)
    (run_browser if phase == "tests" else report).side_effect = KeyboardInterrupt
    monkeypatch.setattr(run_suite, "run_browser", run_browser)
    monkeypatch.setattr(run_suite, "generate_report", report)
    monkeypatch.setattr(sys, "argv", ["run_suite", "--report"])

    assert run_suite.main() == 130
    folder = Path((tmp_path / "data/results/last-run.txt").read_text(encoding="utf-8"))
    saved = json.loads((folder / "run.json").read_text(encoding="utf-8"))
    assert saved["exit_code"] == 130
    assert saved["status"] == "interrupted"
    assert saved["requested_browsers"] == ["chrome"]
    if phase == "tests":
        assert run_browser.call_args.args[3].is_set()
        assert saved["browsers"]["chrome"]["exit_code"] == 130
        report.assert_not_called()
    else:
        assert saved["browsers"]["chrome"]["exit_code"] == 0


@pytest.mark.parametrize(
    ("requested", "browsers", "status", "message"),
    [
        ([], {}, "passed", "Не указаны браузеры"),
        (["chrome"], {}, "passed", "не для всех браузеров"),
        (["chrome", "firefox"], {"chrome": {}}, "passed", "не для всех браузеров"),
        (["edge"], {"edge": {}}, "passed", "Неизвестный браузер"),
        (["chrome", "chrome"], {"chrome": {}}, "passed", "Не указаны браузеры"),
        (["chrome"], {"chrome": {}}, "interrupted", "Нет подтверждения завершения"),
    ],
)
def test_verify_rejects_empty_or_incomplete_run(
    monkeypatch, tmp_path, requested, browsers, status, message
):
    run = {
        "exit_code": 0,
        "status": status,
        "browsers": browsers,
        "requested_browsers": requested,
    }
    (tmp_path / "run.json").write_text(json.dumps(run), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["verify_run", str(tmp_path)])
    with pytest.raises(AssertionError, match=message):
        verify_run.main()
    assert not (tmp_path / "verification.json").exists()


@pytest.mark.parametrize("value", ["nan", "inf", "-1", "not-a-number"])
@pytest.mark.parametrize("entrypoint", ["app", "runner", "pytest"])
def test_invalid_timeout_stops_before_collection(tmp_path, entrypoint, value):
    commands = {
        "app": ["app.py"],
        "runner": ["-m", "tools.runner.run_suite"],
        "pytest": [
            "-m",
            "pytest",
            "-c",
            str(ROOT / "data/config/pytest.ini"),
            f"--rootdir={ROOT}",
            "--collect-only",
            f"--alluredir={tmp_path / 'allure-results'}",
            "-o",
            f"cache_dir={tmp_path / 'cache'}",
        ],
    }
    result = subprocess.run(
        [sys.executable, "-B", *commands[entrypoint], f"--ui-timeout={value}"],
        cwd=ROOT,
        env=os.environ | {"PYTEST_ADDOPTS": "", "PYTHONIOENCODING": "utf-8"},
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=20,
    )
    assert result.returncode == (4 if entrypoint == "pytest" else 2), result.stdout + result.stderr
    assert "Нужно конечное число больше нуля" in result.stderr
    assert not (tmp_path / "collected-scenarios.json").exists()


def test_verify_rejects_disabled_assertions(tmp_path):
    result = subprocess.run(
        [sys.executable, "-B", "-O", "-m", "tools.verification.verify_run", str(tmp_path)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=20,
        env=os.environ | {"PYTHONIOENCODING": "utf-8"},
    )
    assert result.returncode != 0
    assert "без -O и PYTHONOPTIMIZE" in result.stderr


def test_verify_accepts_a_complete_run(monkeypatch, tmp_path):
    case = ("FF-P01", "Отправка формы", "Заполнить и отправить.", "Данные приняты.")
    monkeypatch.setattr(verify_run, "catalog", lambda: [case])
    browser = tmp_path / "chrome"
    results = browser / "allure-results"
    results.mkdir(parents=True)
    documents = {
        tmp_path / "run.json": {
            "status": "passed",
            "exit_code": 0,
            "requested_browsers": ["chrome"],
            "browsers": {"chrome": {"exit_code": 0, "collected": 1, "test_counts": {"PASSED": 1}}},
            "wall_seconds": 0.3,
            "execution": "sequential",
        },
        browser / "collected-scenarios.json": [
            {
                "id": case[0],
                "title": case[1],
                "steps": case[2],
                "expected": case[3],
                "nodeid": "tests/ui/test_example.py::test_example",
            }
        ],
        browser / "durations.json": [
            {
                "id": case[0],
                "phases": {
                    phase: {"seconds": 0.1, "outcome": "passed"}
                    for phase in ("setup", "call", "teardown")
                },
            }
        ],
        results / "example-result.json": {
            "name": f"{case[0]}. {case[1]}",
            "status": "passed",
            "description": f"Шаги: {case[2]}\n\nОжидаемый результат: {case[3]}",
            "steps": [{"name": "Отправить форму", "status": "passed"}],
            "parameters": [{"name": "browser", "value": "'chrome'"}],
            "labels": [{"name": "as_id", "value": case[0]}],
        },
    }
    for path, content in documents.items():
        path.write_text(json.dumps(content, ensure_ascii=False), encoding="utf-8")
    (browser / "junit.xml").write_text(
        '<testsuites><testsuite tests="1" failures="0" errors="0" skipped="0" time="0.3">'
        '<testcase classname="tests.ui.test_example" name="test_example" time="0.3" />'
        "</testsuite></testsuites>",
        encoding="utf-8",
    )
    monkeypatch.setattr(sys, "argv", ["verify_run", str(tmp_path), "--browser", "chrome"])
    verify_run.main()
    proof = json.loads((tmp_path / "verification.json").read_text(encoding="utf-8"))
    assert proof["chrome"]["statuses"] == {"passed": 1}
    assert proof["chrome"]["junit_cases_match"]
