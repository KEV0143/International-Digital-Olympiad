import base64
import hashlib
import io
import json
import sys
from subprocess import TimeoutExpired
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import pytest

from tools.environment import bootstrap
from utils.reporting.terminal import Terminal


def prepare_npm(monkeypatch, tmp_path, error, failures):
    reporter = tmp_path / "tools/reporting"
    reporter.mkdir(parents=True)
    (reporter / "package-lock.json").write_text("{}", encoding="utf-8")
    script = tmp_path / "fake npm.py"
    script.write_text(
        "import sys\n"
        "from pathlib import Path\n"
        "counter = Path('attempts.txt')\n"
        "attempt = int(counter.read_text()) + 1 if counter.exists() else 1\n"
        "counter.write_text(str(attempt))\n"
        "if attempt <= int(sys.argv[2]):\n"
        "    Path('node_modules/partial').mkdir(parents=True, exist_ok=True)\n"
        "    print('npm warn cleanup EPERM ECONNRESET')\n"
        "    print('npm error code ' + sys.argv[1])\n"
        "    sys.exit(1)\n"
        "cli = Path('node_modules/.bin') / ('allure.cmd' "
        "if sys.platform == 'win32' else 'allure')\n"
        "cli.parent.mkdir(parents=True, exist_ok=True)\n"
        "cli.write_text('@echo off\\necho 3.22.0\\n' if sys.platform == 'win32' "
        "else '#!/bin/sh\\necho 3.22.0\\n')\n"
        "cli.chmod(0o755)\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        bootstrap, "ensure_node", lambda _: [sys.executable, str(script), error, str(failures)]
    )
    delays = Mock()
    monkeypatch.setattr(bootstrap, "sleep", delays)
    monkeypatch.setattr(bootstrap, "repair_reporter_cache", Mock())
    return reporter, delays


@pytest.mark.parametrize("error", ["ECONNRESET", "EPERM"])
def test_install_retries_temporary_errors_and_reuses_completed_install(
    monkeypatch, tmp_path, error
):
    output = io.StringIO()
    monkeypatch.setattr(bootstrap, "console", Terminal(output))
    reporter, delays = prepare_npm(monkeypatch, tmp_path, error, 1)
    cli = bootstrap.ensure_reporter(tmp_path)
    assert cli.is_file()
    assert (reporter / "attempts.txt").read_text() == "2"
    assert (reporter / "node_modules/.lock-sha256").read_text() == hashlib.sha256(b"{}").hexdigest()
    delays.assert_called_once_with(2)
    assert f"npm ci: {error} | повтор через 2 с" in output.getvalue()
    assert "npm warn cleanup" not in output.getvalue()
    if error == "ECONNRESET":
        bootstrap.repair_reporter_cache.assert_called_once()
    else:
        bootstrap.repair_reporter_cache.assert_not_called()
    logs = list((tmp_path / "data/results/setup").glob("*/npm-ci-1.log"))
    assert len(logs) == 1 and f"npm error code {error}" in logs[0].read_text()
    assert bootstrap.ensure_reporter(tmp_path) == cli
    assert (reporter / "attempts.txt").read_text() == "2"


def test_failed_cache_recovery_does_not_stop_network_retry(monkeypatch, tmp_path):
    reporter, _ = prepare_npm(monkeypatch, tmp_path, "ECONNRESET", 1)
    bootstrap.repair_reporter_cache.side_effect = OSError("connection interrupted")
    bootstrap.ensure_reporter(tmp_path)
    assert (reporter / "attempts.txt").read_text() == "2"


@pytest.mark.parametrize("valid_integrity", [True, False])
def test_cache_recovery_checks_missing_tarball_before_adding_it(
    monkeypatch, tmp_path, valid_integrity
):
    body = b"downloaded tarball"
    integrity = "sha512-" + base64.b64encode(hashlib.sha512(body).digest()).decode("ascii")
    present = "https://registry.npmjs.org/present/-/present-1.0.0.tgz"
    missing = "https://registry.npmjs.org/missing/-/missing-1.0.0.tgz"
    lock = {
        "packages": {
            "node_modules/present": {"resolved": present, "integrity": integrity},
            "node_modules/missing": {
                "resolved": missing,
                "integrity": integrity if valid_integrity else "sha512-wrong",
            },
        }
    }
    (tmp_path / "package-lock.json").write_text(json.dumps(lock), encoding="utf-8")
    execute = Mock(return_value=SimpleNamespace(stdout=present))
    monkeypatch.setattr(bootstrap, "run", execute)
    download = Mock(return_value=io.BytesIO(body))
    monkeypatch.setattr(bootstrap.urllib.request, "urlopen", download)
    if valid_integrity:
        bootstrap.repair_reporter_cache(["npm"], tmp_path, tmp_path / "downloads")
        archive = tmp_path / "downloads/1.tgz"
        assert archive.read_bytes() == body
        assert execute.call_args.args[0] == [
            "npm",
            "cache",
            "add",
            str(archive),
            "--offline",
            "--no-audit",
            "--no-fund",
        ]
    else:
        with pytest.raises(bootstrap.BootstrapError, match="Контрольная сумма пакета"):
            bootstrap.repair_reporter_cache(["npm"], tmp_path, tmp_path / "downloads")
        assert execute.call_count == 1
        assert not (tmp_path / "downloads").exists()
    download.assert_called_once_with(missing, timeout=30)


def test_cache_recovery_does_not_download_cached_packages(monkeypatch, tmp_path):
    url = "https://registry.npmjs.org/present/-/present-1.0.0.tgz"
    lock = {"packages": {"node_modules/present": {"resolved": url, "integrity": "sha512-present"}}}
    (tmp_path / "package-lock.json").write_text(json.dumps(lock), encoding="utf-8")
    monkeypatch.setattr(bootstrap, "run", Mock(return_value=SimpleNamespace(stdout=url)))
    download = Mock()
    monkeypatch.setattr(bootstrap.urllib.request, "urlopen", download)
    bootstrap.repair_reporter_cache(["npm"], tmp_path, tmp_path / "downloads")
    download.assert_not_called()


def test_install_does_not_retry_dependency_conflicts(monkeypatch, tmp_path):
    reporter, delays = prepare_npm(monkeypatch, tmp_path, "ERESOLVE", 9)
    with pytest.raises(bootstrap.BootstrapError, match=r"ERESOLVE.*npm-ci-1.log"):
        bootstrap.ensure_reporter(tmp_path)
    assert (reporter / "attempts.txt").read_text() == "1"
    delays.assert_not_called()
    assert not (reporter / "node_modules/.lock-sha256").exists()


def test_install_stops_after_three_network_failures(monkeypatch, tmp_path):
    reporter, delays = prepare_npm(monkeypatch, tmp_path, "ECONNRESET", 9)
    with pytest.raises(bootstrap.BootstrapError, match=r"ECONNRESET.*npm-ci-3.log"):
        bootstrap.ensure_reporter(tmp_path)
    assert (reporter / "attempts.txt").read_text() == "3"
    assert [call.args[0] for call in delays.call_args_list] == [2, 4]
    assert len(list((tmp_path / "data/results/setup").glob("*/npm-ci-*.log"))) == 3
    assert not (reporter / "node_modules/.lock-sha256").exists()


def test_install_without_allure_executable_is_not_marked_complete(monkeypatch, tmp_path):
    reporter, _ = prepare_npm(monkeypatch, tmp_path, "", 0)
    monkeypatch.setattr(bootstrap, "install_reporter", Mock())
    with pytest.raises(bootstrap.BootstrapError, match="исполняемый файл Allure отсутствует"):
        bootstrap.ensure_reporter(tmp_path)
    assert not (reporter / "node_modules/.lock-sha256").exists()


@pytest.mark.parametrize(
    "failure", [bootstrap.BootstrapError("broken cli"), TimeoutExpired([], 30)]
)
def test_failed_allure_probe_does_not_write_stamp(monkeypatch, tmp_path, failure):
    reporter, _ = prepare_npm(monkeypatch, tmp_path, "", 0)
    monkeypatch.setattr(bootstrap, "run", Mock(side_effect=failure))
    with pytest.raises(bootstrap.BootstrapError):
        bootstrap.ensure_reporter(tmp_path)
    assert not (reporter / "node_modules/.lock-sha256").exists()


@pytest.mark.parametrize("timed_out", [False, True])
def test_interrupted_install_stops_its_process(monkeypatch, tmp_path, timed_out):
    process = MagicMock()
    process.__enter__.return_value = process
    monkeypatch.setattr(bootstrap.subprocess, "Popen", Mock(return_value=process))
    terminate = Mock()
    monkeypatch.setattr(bootstrap, "terminate_tree", terminate)
    monkeypatch.setattr(bootstrap, "monotonic", Mock(side_effect=[0, 601]))

    def follow(*args, on_tick):
        if timed_out:
            on_tick()
        raise KeyboardInterrupt

    monkeypatch.setattr(bootstrap, "follow_process", follow)
    with pytest.raises(bootstrap.BootstrapError if timed_out else KeyboardInterrupt):
        bootstrap.run_reporter_install(["npm", "ci"], tmp_path, tmp_path / "npm.log")
    terminate.assert_called_once_with(process)


def test_install_reports_progress_while_npm_is_silent(monkeypatch, tmp_path):
    output = io.StringIO()
    monkeypatch.setattr(bootstrap, "console", Terminal(output))
    process = MagicMock()
    process.__enter__.return_value = process
    monkeypatch.setattr(bootstrap.subprocess, "Popen", Mock(return_value=process))
    monkeypatch.setattr(bootstrap, "monotonic", Mock(side_effect=[0, 11]))

    def follow(*args, on_tick):
        on_tick()
        return 0

    monkeypatch.setattr(bootstrap, "follow_process", follow)
    assert bootstrap.run_reporter_install(["npm", "ci"], tmp_path, tmp_path / "npm.log") == 0
    assert "Allure | установка зависимостей | выполняется npm ci" in output.getvalue()
