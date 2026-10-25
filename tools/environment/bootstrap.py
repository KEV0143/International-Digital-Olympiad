import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic, sleep

from tools.environment.node_runtime import NodeRuntimeError, ensure_node
from tools.runner.processes import process_options, terminate_tree
from utils.reporting.terminal import console, follow_process


class BootstrapError(RuntimeError):
    pass


def run(command, **kwargs):
    try:
        result = subprocess.run(command, **kwargs)
    except OSError as error:
        raise BootstrapError(f"Не удалось запустить {command[0]}: {error}") from error
    if result.returncode:
        raise BootstrapError(f"Команда завершилась с кодом {result.returncode}: {command[0]}")
    return result


def supported_python(command):
    try:
        result = subprocess.run(
            command
            + ["-c", "import sys; print(sys.executable); print(sys.version_info >= (3,12))"],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    lines = result.stdout.strip().splitlines()
    return (
        Path(lines[0])
        if result.returncode == 0 and len(lines) == 2 and lines[1] == "True"
        else None
    )


def find_python(explicit=None):
    if explicit:
        selected = supported_python([str(explicit)])
        if selected:
            return selected
        raise BootstrapError("Указанный интерпретатор недоступен или его версия ниже Python 3.12")
    candidates = [[sys.executable]]
    if os.environ.get("PYTHON_BINARY"):
        candidates.insert(0, [os.environ["PYTHON_BINARY"]])
    if sys.platform == "win32" and shutil.which("py"):
        candidates.extend([["py", version] for version in ("-3.12", "-3.13", "-3.14", "-3")])
    for name in ("python3.12", "python3.13", "python3.14", "python3", "python"):
        if executable := shutil.which(name):
            candidates.append([executable])
    for candidate in candidates:
        if selected := supported_python(candidate):
            return selected
    raise BootstrapError("Нужен Python 3.12+. Установите его или укажите --python <путь>")


def ensure_python(root, explicit=None, development=False):
    environment = root / "tools/.venv"
    python = environment / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    if not supported_python([str(python)]):
        if environment.exists():
            raise BootstrapError(
                "Окружение tools/.venv повреждено. Переместите его и запустите снова"
            )
        selected = find_python(explicit)
        console.write("Python | создание tools/.venv")
        run([str(selected), "-m", "venv", str(environment)])
    dependencies = root / "data/dependencies"
    files = [dependencies / "requirements.txt"]
    if development:
        files.append(dependencies / "requirements-dev.txt")
    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    stamp = environment / "dependencies.json"
    try:
        installed = json.loads(stamp.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        installed = {}
    versions = {}
    for path in files:
        for line in path.read_text(encoding="utf-8").splitlines():
            if "==" in line:
                name, version = line.strip().split("==", 1)
                versions[name] = version
    try:
        probe = subprocess.run(
            [
                str(python),
                "-c",
                "import importlib.metadata as m, json, sys; "
                "print(json.dumps({k:m.version(k) for k in json.loads(sys.argv[1])}))",
                json.dumps(versions),
            ],
            capture_output=True,
            text=True,
            timeout=20,
        )
        matching_versions = probe.returncode == 0 and json.loads(probe.stdout) == versions
    except (OSError, ValueError, subprocess.TimeoutExpired):
        matching_versions = False
    if not matching_versions or any(installed.get(k) != v for k, v in hashes.items()):
        requirement = files[-1]
        console.write(f"Python | установка зависимостей: {requirement.name}")
        run(
            [
                str(python),
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                "-r",
                str(requirement),
            ]
        )
        run([str(python), "-m", "pip", "check"])
        stamp.write_text(json.dumps(installed | hashes, indent=2), encoding="utf-8")
    console.write("Python | Окружение и зависимости готовы", status="+")
    return python


def run_reporter_install(command, reporter, log_path):
    started = last_update = monotonic()

    def update():
        nonlocal last_update
        now = monotonic()
        if now - started >= 600:
            raise BootstrapError(f"Allure: npm ci выполняется дольше 10 минут. Журнал: {log_path}")
        if now - last_update >= 10:
            console.write("Allure | установка зависимостей | выполняется npm ci")
            last_update = now

    try:
        with log_path.open("w", encoding="utf-8") as log:
            with subprocess.Popen(
                command,
                cwd=reporter,
                stdout=log,
                stderr=subprocess.STDOUT,
                **process_options(),
            ) as process:
                try:
                    return follow_process(process, log_path, lambda _: None, on_tick=update)
                except BaseException:
                    terminate_tree(process)
                    raise
    except OSError as error:
        raise BootstrapError(f"Не удалось запустить npm ci: {error}. Журнал: {log_path}") from error


def repair_reporter_cache(npm, reporter, folder):
    cached = run(
        [*npm, "cache", "ls"], cwd=reporter, capture_output=True, text=True, timeout=30
    ).stdout
    packages = json.loads((reporter / "package-lock.json").read_text(encoding="utf-8"))
    for index, (name, package) in enumerate(packages.get("packages", {}).items()):
        url = package.get("resolved", "")
        integrity = package.get("integrity", "")
        if (
            not url.startswith("https://registry.npmjs.org/")
            or url in cached
            or not integrity.startswith("sha512-")
        ):
            continue
        console.write(f"Allure | повторная загрузка: {name.removeprefix('node_modules/')}")
        with urllib.request.urlopen(url, timeout=30) as response:
            data = response.read()
        actual = "sha512-" + base64.b64encode(hashlib.sha512(data).digest()).decode("ascii")
        if actual != integrity:
            raise BootstrapError(f"Контрольная сумма пакета {name} не совпала с package-lock.json")
        folder.mkdir(parents=True, exist_ok=True)
        archive = folder / f"{index}.tgz"
        archive.write_bytes(data)
        run(
            [*npm, "cache", "add", str(archive), "--offline", "--no-audit", "--no-fund"],
            cwd=reporter,
            capture_output=True,
            text=True,
            timeout=30,
        )


def install_reporter(npm, reporter, root):
    logs = root / "data/results/setup" / datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    logs.mkdir(parents=True)
    command = [
        *npm,
        "ci",
        "--no-audit",
        "--no-fund",
        "--include=dev",
        "--prefer-offline",
        "--fetch-retries=3",
        "--maxsockets=4",
        "--fetch-retry-mintimeout=1000",
        "--fetch-retry-maxtimeout=10000",
        "--fetch-timeout=120000",
        "--color=false",
        "--progress=false",
        "--update-notifier=false",
    ]
    retryable = {
        "ECONNRESET",
        "ECONNREFUSED",
        "EAI_AGAIN",
        "ENOTFOUND",
        "ENETUNREACH",
        "EHOSTUNREACH",
        "ETIMEDOUT",
        "ESOCKETTIMEDOUT",
        "E429",
        "E500",
        "E502",
        "E503",
        "E504",
        "EPERM",
        "EBUSY",
        "ENOTEMPTY",
    }
    cache_recovery_attempted = False
    for attempt in range(1, 4):
        console.write(f"Allure | установка зависимостей | попытка: {attempt}/3")
        log_path = logs / f"npm-ci-{attempt}.log"
        code = run_reporter_install(command, reporter, log_path)
        if code == 0:
            return
        output = log_path.read_text(encoding="utf-8", errors="replace")
        errors = re.findall(r"^npm (?:error|ERR!) code (\S+)", output, re.MULTILINE)
        reason = errors[-1] if errors else f"код процесса {code}"
        if reason not in retryable or attempt == 3:
            raise BootstrapError(f"Allure: npm ci не выполнен ({reason}). Журнал: {log_path}")
        if reason not in {"EPERM", "EBUSY", "ENOTEMPTY"} and not cache_recovery_attempted:
            cache_recovery_attempted = True
            try:
                repair_reporter_cache(npm, reporter, logs / "downloads")
            except (BootstrapError, OSError, ValueError, subprocess.TimeoutExpired) as error:
                console.write(
                    f"Allure | повторная загрузка не завершена: {error}", level="Warn", status="!"
                )
        delay = 2 * attempt
        console.write(f"Allure | npm ci: {reason} | повтор через {delay} с", status="!")
        sleep(delay)


def ensure_reporter(root):
    try:
        npm = ensure_node(root)
    except (NodeRuntimeError, OSError, ValueError) as error:
        raise BootstrapError(str(error)) from error
    reporter = root / "tools/reporting"
    cli = reporter / "node_modules/.bin" / ("allure.cmd" if sys.platform == "win32" else "allure")
    lock_hash = hashlib.sha256((reporter / "package-lock.json").read_bytes()).hexdigest()
    stamp = reporter / "node_modules/.lock-sha256"
    if cli.is_file() and stamp.is_file() and stamp.read_text(encoding="utf-8") == lock_hash:
        console.write("Allure | зависимости готовы", status="+")
        return cli
    install_reporter(npm, reporter, root)
    if not cli.is_file():
        raise BootstrapError("npm ci завершён, но исполняемый файл Allure отсутствует")
    try:
        run([str(cli), "--version"], cwd=reporter, capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired as error:
        raise BootstrapError("Allure не ответил на проверку запуска за 30 секунд") from error
    stamp.write_text(lock_hash, encoding="utf-8")
    console.write("Allure | зависимости готовы", status="+")
    return cli
