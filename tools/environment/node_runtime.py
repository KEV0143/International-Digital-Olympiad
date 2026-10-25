import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path, PurePosixPath
from zipfile import BadZipFile, ZipFile

from utils.reporting.terminal import console


class NodeRuntimeError(RuntimeError):
    pass


def node_version(node):
    try:
        result = subprocess.run(
            [str(node), "--version"], capture_output=True, text=True, timeout=15
        )
        version = tuple(int(part) for part in result.stdout.strip().removeprefix("v").split("."))
        return version if result.returncode == 0 and len(version) == 3 else ()
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return ()


def supported_node(version):
    return len(version) == 3 and (version[0] == 20 and version >= (20, 19, 0) or version[0] >= 22)


def use_node(node, npm):
    os.environ["PATH"] = str(node.parent) + os.pathsep + os.environ.get("PATH", "")
    return [str(part) for part in npm]


def local_commands(folder):
    if sys.platform == "win32":
        return folder / "node.exe", folder / "node_modules/npm/bin/npm-cli.js"
    return folder / "bin/node", folder / "lib/node_modules/npm/bin/npm-cli.js"


def download(url, destination, expected_hash):
    digest = hashlib.sha256()
    received, last_percent = 0, 0
    with urllib.request.urlopen(url, timeout=30) as response, destination.open("wb") as output:
        total = int(response.headers.get("Content-Length", 0))
        while block := response.read(1024 * 1024):
            output.write(block)
            digest.update(block)
            received += len(block)
            percent = min(100, received * 100 // total) if total else 0
            if percent >= last_percent + 10 or percent == 100:
                console.write(f"Node.js | загрузка: {percent}%")
                last_percent = percent
    if digest.hexdigest() != expected_hash:
        raise NodeRuntimeError("Контрольная сумма архива Node.js не совпала; установка остановлена")


def unpack(archive, destination, folder_name):
    def check_name(name):
        parts = PurePosixPath(name).parts
        if not parts or parts[0] != folder_name or ".." in parts or "\\" in name:
            raise NodeRuntimeError("Недопустимый путь в архиве Node.js")

    if archive.suffix == ".zip":
        with ZipFile(archive) as bundle:
            for name in bundle.namelist():
                check_name(name)
            bundle.extractall(destination)
    else:
        with tarfile.open(archive) as bundle:
            for member in bundle.getmembers():
                check_name(member.name)
            bundle.extractall(destination, filter="data")


def ensure_node(root):
    manifest = json.loads(
        (root / "data/dependencies/node-runtime.json").read_text(encoding="utf-8")
    )
    version = manifest["version"]
    architecture = {"amd64": "x64", "x86_64": "x64", "aarch64": "arm64"}.get(
        platform.machine().lower(), platform.machine().lower()
    )
    operating_system = {"win32": "win", "linux": "linux", "darwin": "darwin"}.get(sys.platform)
    target = f"{operating_system}-{architecture}"
    folder_name = f"node-v{version}-{target}"
    cache = root / "tools/.runtime"
    folder = cache / folder_name
    node, npm_cli = local_commands(folder)
    expected_version = tuple(int(part) for part in version.split("."))
    if npm_cli.is_file() and node_version(node) == expected_version:
        return use_node(node, [node, npm_cli])

    system_node = shutil.which("node")
    system_npm = shutil.which("npm.cmd" if sys.platform == "win32" else "npm")
    if system_node and system_npm and supported_node(node_version(system_node)):
        return use_node(Path(system_node), [system_npm])
    if target not in manifest["sha256"]:
        raise NodeRuntimeError(
            "Для этой платформы установите Node.js 20.19+ ветки 20 или 22+ с npm"
        )
    if folder.exists():
        raise NodeRuntimeError(
            f"Локальный Node.js повреждён. Переместите {folder} и запустите снова"
        )

    console.write(f"Node.js | установка локальной версии {version}")
    cache.mkdir(parents=True, exist_ok=True)
    extension = ".zip" if sys.platform == "win32" else ".tar.xz"
    archive_name = folder_name + extension
    url = f"https://nodejs.org/dist/v{version}/{archive_name}"
    try:
        with tempfile.TemporaryDirectory(prefix="download-", dir=cache) as temporary:
            staging = Path(temporary)
            archive = staging / archive_name
            try:
                download(url, archive, manifest["sha256"][target])
            except OSError:
                console.write("Node.js | загрузка прервана; повторная попытка", status="!")
                download(url, archive, manifest["sha256"][target])
            unpack(archive, staging, folder_name)
            extracted = staging / folder_name
            candidate, candidate_npm = local_commands(extracted)
            if not candidate_npm.is_file() or node_version(candidate) != expected_version:
                raise NodeRuntimeError("Скачанный Node.js не прошёл проверку запуска")
            extracted.rename(folder)
    except NodeRuntimeError:
        raise
    except (OSError, ValueError, tarfile.TarError, BadZipFile) as error:
        raise NodeRuntimeError(f"Не удалось подготовить Node.js: {error}") from error
    console.write(f"Node.js | локальная версия {version} готова", status="+")
    return use_node(node, [node, npm_cli])
