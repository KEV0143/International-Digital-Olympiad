import hashlib
import io
import json
import os
from pathlib import Path
from unittest.mock import Mock
from zipfile import ZipFile

import pytest

from tools.environment import bootstrap, node_runtime


@pytest.fixture
def node_archive(monkeypatch, tmp_path):
    monkeypatch.setattr(node_runtime.sys, "platform", "win32")
    monkeypatch.setattr(node_runtime.platform, "machine", lambda: "AMD64")
    monkeypatch.setattr(node_runtime.shutil, "which", lambda _: None)
    monkeypatch.setattr(
        node_runtime, "node_version", lambda path: (24, 21, 0) if Path(path).is_file() else ()
    )
    monkeypatch.setenv("PATH", "original-path")
    name = "node-v24.21.0-win-x64"
    content = io.BytesIO()
    with ZipFile(content, "w") as bundle:
        bundle.writestr(f"{name}/node.exe", b"node")
        bundle.writestr(f"{name}/node_modules/npm/bin/npm-cli.js", b"npm")
    data = content.getvalue()
    manifest = tmp_path / "data/dependencies/node-runtime.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        json.dumps({"version": "24.21.0", "sha256": {"win-x64": hashlib.sha256(data).hexdigest()}}),
        encoding="utf-8",
    )

    def response(*_, **kwargs):
        assert kwargs["timeout"] == 30
        stream = io.BytesIO(data)
        stream.headers = {"Content-Length": str(len(data))}
        return stream

    request = Mock(side_effect=response)
    monkeypatch.setattr(node_runtime.urllib.request, "urlopen", request)
    return name, request


def test_install_without_system_node_is_local_and_reused(node_archive, tmp_path):
    name, request = node_archive
    npm = node_runtime.ensure_node(tmp_path)
    folder = tmp_path / "tools/.runtime" / name
    assert npm == [str(folder / "node.exe"), str(folder / "node_modules/npm/bin/npm-cli.js")]
    assert os.environ["PATH"] == str(folder) + os.pathsep + "original-path"
    assert request.call_args.args[0] == f"https://nodejs.org/dist/v24.21.0/{name}.zip"
    assert [path.name for path in folder.parent.iterdir()] == [name]
    assert node_runtime.ensure_node(tmp_path) == npm
    assert request.call_count == 1


def test_checksum_mismatch_does_not_unpack_or_keep_partial_install(
    node_archive, monkeypatch, tmp_path
):
    name, _ = node_archive
    manifest = tmp_path / "data/dependencies/node-runtime.json"
    config = json.loads(manifest.read_text(encoding="utf-8"))
    config["sha256"]["win-x64"] = "0" * 64
    manifest.write_text(json.dumps(config), encoding="utf-8")
    unpack = Mock()
    monkeypatch.setattr(node_runtime, "unpack", unpack)
    with pytest.raises(node_runtime.NodeRuntimeError, match="Контрольная сумма"):
        node_runtime.ensure_node(tmp_path)
    unpack.assert_not_called()
    assert not (tmp_path / "tools/.runtime" / name).exists()
    assert list((tmp_path / "tools/.runtime").iterdir()) == []


def test_interrupted_download_leaves_no_installed_runtime(node_archive, tmp_path):
    _, request = node_archive
    request.side_effect = OSError("connection lost")
    with pytest.raises(node_runtime.NodeRuntimeError, match="connection lost"):
        node_runtime.ensure_node(tmp_path)
    assert list((tmp_path / "tools/.runtime").iterdir()) == []


def test_interrupted_download_is_repeated_before_installation(node_archive, tmp_path):
    name, request = node_archive
    valid_response = request.side_effect
    attempts = 0

    def interrupted_once(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise OSError("connection lost")
        return valid_response(*args, **kwargs)

    request.side_effect = interrupted_once
    assert node_runtime.ensure_node(tmp_path)[0] == str(
        tmp_path / "tools/.runtime" / name / "node.exe"
    )
    assert request.call_count == 2


def test_downloaded_node_must_start_before_install_is_promoted(node_archive, monkeypatch, tmp_path):
    monkeypatch.setattr(node_runtime, "node_version", lambda _: ())
    with pytest.raises(node_runtime.NodeRuntimeError, match="не прошёл проверку запуска"):
        node_runtime.ensure_node(tmp_path)
    assert list((tmp_path / "tools/.runtime").iterdir()) == []


def test_existing_supported_node_and_npm_do_not_trigger_download(
    node_archive, monkeypatch, tmp_path
):
    _, request = node_archive
    programs = {
        "node": str(tmp_path / "system/node.exe"),
        "npm.cmd": str(tmp_path / "system/npm.cmd"),
    }
    monkeypatch.setattr(node_runtime.shutil, "which", programs.get)
    monkeypatch.setattr(node_runtime, "node_version", lambda _: (24, 0, 0))
    assert node_runtime.ensure_node(tmp_path) == [programs["npm.cmd"]]
    request.assert_not_called()
    assert not (tmp_path / "tools/.runtime").exists()


@pytest.mark.parametrize("version", [(18, 20, 0), ()])
def test_old_or_broken_system_node_uses_local_runtime(node_archive, monkeypatch, tmp_path, version):
    name, request = node_archive
    monkeypatch.setattr(node_runtime.shutil, "which", lambda name: f"system/{name}")
    installed_version = node_runtime.node_version
    monkeypatch.setattr(
        node_runtime,
        "node_version",
        lambda path: version if str(path).startswith("system/") else installed_version(path),
    )
    assert node_runtime.ensure_node(tmp_path)[0] == str(
        tmp_path / "tools/.runtime" / name / "node.exe"
    )
    assert request.call_count == 1


@pytest.mark.parametrize(
    "name",
    ["../outside.txt", "node/../../outside.txt", "/node/outside.txt", "node/..\\..\\outside.txt"],
)
def test_archive_paths_cannot_escape_install_directory(tmp_path, name):
    archive = tmp_path / "archive.zip"
    with ZipFile(archive, "w") as bundle:
        bundle.writestr(name, "outside")
    with pytest.raises(node_runtime.NodeRuntimeError, match="Недопустимый путь"):
        node_runtime.unpack(archive, tmp_path / "extract", "node")
    assert not (tmp_path / "extract").exists()


def test_failed_allure_install_does_not_write_lock_stamp(monkeypatch, tmp_path):
    reporter = tmp_path / "tools/reporting"
    reporter.mkdir(parents=True)
    (reporter / "package-lock.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(bootstrap, "ensure_node", lambda _: ["node", "npm-cli.js"])
    install = Mock(side_effect=bootstrap.BootstrapError("npm failed"))
    monkeypatch.setattr(bootstrap, "install_reporter", install)
    with pytest.raises(bootstrap.BootstrapError, match="npm failed"):
        bootstrap.ensure_reporter(tmp_path)
    assert not (reporter / "node_modules/.lock-sha256").exists()
    assert install.call_args.args == (["node", "npm-cli.js"], reporter, tmp_path)
