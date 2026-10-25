import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import app
from tools.environment import node_runtime
from tools.verification import verify_run
from utils import pytest_plugin as plugin

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("index_content", [None, ""])
def test_html_summary_without_a_page_is_rejected(tmp_path, index_content):
    report = tmp_path / "allure-report"
    report.mkdir()
    (report / "summary.json").write_text(
        json.dumps(
            {
                "stats": {"total": 1, "passed": 1},
                "retryTests": [],
                "flakyTests": [],
            }
        ),
        encoding="utf-8",
    )
    if index_content is not None:
        (report / "index.html").write_text(index_content, encoding="utf-8")
    with pytest.raises(AssertionError, match="Нет HTML-страницы"):
        verify_run.verify_html_report(tmp_path, 1)


@pytest.mark.parametrize("selected", ["firefox", "both"])
def test_verify_rejects_a_different_requested_browser(monkeypatch, tmp_path, selected):
    (tmp_path / "run.json").write_text(
        json.dumps(
            {
                "exit_code": 0,
                "status": "passed",
                "requested_browsers": ["chrome"],
                "browsers": {"chrome": {}},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(sys, "argv", ["verify_run", str(tmp_path), "--browser", selected])
    with pytest.raises(AssertionError, match="не соответствует выбранному браузеру"):
        verify_run.main()
    assert not (tmp_path / "verification.json").exists()


def test_app_passes_the_single_browser_to_verification(monkeypatch, tmp_path):
    monkeypatch.setattr(app, "ROOT", tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["app.py", "verify", "--browser", "firefox"])
    execute = Mock(return_value=0)
    monkeypatch.setattr(app.subprocess, "call", execute)
    assert app.main() == 0
    assert execute.call_args.args[0][-2:] == ["--browser", "firefox"]


@pytest.mark.parametrize(
    "module",
    [
        "tools.verification.verify_run",
        "tools.documentation.generate_scenarios",
        "tools.runner.run_suite",
        "pytest",
        "app",
    ],
)
def test_optimized_python_cannot_bypass_validation(module, tmp_path):
    process = subprocess.run(
        [
            sys.executable,
            "-B",
            "-O",
            "-m",
            module,
            *(
                [
                    "-c",
                    str(ROOT / "data/config/pytest.ini"),
                    f"--rootdir={ROOT}",
                    "--collect-only",
                    f"--alluredir={tmp_path / 'allure-results'}",
                    "-o",
                    f"cache_dir={tmp_path / 'cache'}",
                ]
                if module == "pytest"
                else ["--help"]
            ),
        ],
        cwd=ROOT,
        env=os.environ | {"PYTHONDONTWRITEBYTECODE": "1", "PYTHONIOENCODING": "utf-8"},
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=20,
    )
    assert process.returncode != 0
    assert "без -O и PYTHONOPTIMIZE" in process.stderr


@pytest.mark.parametrize("failure", ["snapshot", "quit"])
def test_cleanup_cannot_replace_an_active_exception(monkeypatch, failure):
    browser = Mock()
    browser.command_executor.client_config.timeout = 45
    node = SimpleNamespace(stash=pytest.Stash())
    capture = Mock(return_value={})
    (capture if failure == "snapshot" else browser.quit).side_effect = RuntimeError(
        failure + " failed"
    )
    monkeypatch.setattr(plugin, "snapshot", capture)
    monkeypatch.setattr(plugin, "attach", Mock())
    primary = AssertionError("primary failure")
    with pytest.raises(AssertionError) as caught:
        try:
            raise primary
        finally:
            plugin.cleanup_browser(node, browser, screenshots=False)
    assert caught.value is primary
    assert any(failure + " failed" in note for note in primary.__notes__)
    browser.quit.assert_called_once()
    assert node.stash[plugin.DRIVER] is None


def test_cleanup_error_after_a_pass_is_not_silenced(monkeypatch):
    browser = Mock()
    browser.command_executor.client_config.timeout = 45
    browser.quit.side_effect = RuntimeError("quit failed")
    monkeypatch.setattr(plugin, "snapshot", lambda *args, **kwargs: {})
    monkeypatch.setattr(plugin, "attach", Mock())
    node = SimpleNamespace(stash=pytest.Stash())
    with pytest.raises(ExceptionGroup, match="Ошибка завершения браузера"):
        plugin.cleanup_browser(node, browser, screenshots=False)


def test_cleanup_notes_are_attached_to_an_existing_failed_report(monkeypatch):
    browser = Mock()
    browser.command_executor.client_config.timeout = 45
    browser.quit.side_effect = RuntimeError("quit failed")
    monkeypatch.setattr(plugin, "snapshot", lambda *args, **kwargs: {})
    monkeypatch.setattr(plugin, "attach", Mock())
    node = SimpleNamespace(stash=pytest.Stash())
    report = SimpleNamespace(failed=True, sections=[])
    node.stash[plugin.REPORTS] = {"call": report}
    plugin.cleanup_browser(node, browser, screenshots=False)
    assert report.sections == [("Browser cleanup", "RuntimeError: quit failed")]


@pytest.mark.parametrize(
    ("version", "supported"),
    [
        ((), False),
        ((18, 20, 0), False),
        ((20, 18, 9), False),
        ((20, 19, 0), True),
        ((20, 20, 0), True),
        ((21, 0, 0), False),
        ((22, 0, 0), True),
        ((24, 22, 1), True),
    ],
)
def test_node_engine_version_boundaries(version, supported):
    assert node_runtime.supported_node(version) is supported


def test_serial_session_rejects_mixed_browser_versions(monkeypatch, tmp_path):
    options = {
        "--browser": "chrome",
        "--headed": False,
        "--no-screenshots": True,
        "allure_report_dir": str(tmp_path / "allure-results"),
        "--base-url": "https://example.test",
    }
    config = SimpleNamespace(getoption=lambda key: options[key], stash=pytest.Stash())
    browser = Mock(capabilities={"browserName": "chrome", "browserVersion": "1.0"})
    browser.command_executor.client_config.timeout = 45
    monkeypatch.setattr(plugin, "create_browser", lambda *args: browser)
    monkeypatch.setattr(plugin, "snapshot", lambda *args, **kwargs: {})
    monkeypatch.setattr(plugin.allure.dynamic, "parameter", Mock())
    first = plugin.driver.__wrapped__(
        SimpleNamespace(config=config, node=SimpleNamespace(stash=pytest.Stash()))
    )
    assert next(first) is browser
    with pytest.raises(StopIteration):
        next(first)
    browser.capabilities["browserVersion"] = "2.0"
    second = plugin.driver.__wrapped__(
        SimpleNamespace(config=config, node=SimpleNamespace(stash=pytest.Stash()))
    )
    with pytest.raises(pytest.UsageError, match="Параметры окружения изменились"):
        next(second)
    assert browser.quit.call_count == 2


@pytest.mark.parametrize("phase", ["setup", "call"])
def test_pytest_keeps_primary_failure_when_both_cleanup_operations_fail(tmp_path, phase):
    probe = tmp_path / "test_cleanup_probe.py"
    probe.write_text(
        "\n".join(
            [
                "from types import SimpleNamespace",
                "from unittest.mock import Mock",
                "import pytest",
                "from utils import pytest_plugin as plugin",
                "@pytest.fixture(autouse=True)",
                "def fake_browser(monkeypatch):",
                "    browser = Mock(capabilities="
                "{'browserName': 'chrome', 'browserVersion': 'unit'})",
                "    browser.command_executor.client_config.timeout = 45",
                "    browser.quit.side_effect = RuntimeError('quit failed')",
                "    monkeypatch.setattr(plugin, 'create_browser', lambda *args: browser)",
                "    monkeypatch.setattr(plugin, 'snapshot', "
                "Mock(side_effect=RuntimeError('snapshot failed')))",
                *(
                    [
                        "    monkeypatch.setattr(plugin.allure.dynamic, 'parameter', "
                        "Mock(side_effect=AssertionError('primary failure')))"
                    ]
                    if phase == "setup"
                    else []
                ),
                "def test_primary(driver):",
                "    raise AssertionError('primary failure')",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            "-m",
            "pytest",
            str(probe),
            "-c",
            str(ROOT / "data/config/pytest.ini"),
            f"--rootdir={tmp_path}",
            "--no-screenshots",
            "-q",
            "--tb=short",
            f"--alluredir={tmp_path / 'allure-results'}",
            "-o",
            f"cache_dir={tmp_path / 'cache'}",
        ],
        cwd=ROOT,
        env=os.environ | {"PYTEST_ADDOPTS": "", "PYTHONIOENCODING": "utf-8"},
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    assert result.returncode == 1, result.stdout + result.stderr
    assert "primary failure" in result.stdout
    assert "snapshot failed" in result.stdout and "quit failed" in result.stdout
    assert "INTERNALERROR" not in result.stdout
    assert ("1 error" if phase == "setup" else "1 failed") in result.stdout
