import argparse
import os
import subprocess
import sys
from pathlib import Path

from tools.environment.bootstrap import BootstrapError, ensure_python, ensure_reporter
from tools.runner.processes import interrupt_and_wait, process_options, terminate_tree, wait_process
from utils.reporting.terminal import console
from utils.validation import positive_number, require_assertions

ROOT = Path(__file__).resolve().parent


def finish_run(code, no_pause=False):
    if not no_pause and sys.stdin.isatty() and sys.stdout.isatty():
        console.gap()
        console.write("Тестирование завершено, нажмите Enter для закрытия программы.")
        try:
            input()
        except (EOFError, KeyboardInterrupt):
            pass
    return code


def run_command(command):
    process = None
    try:
        process = subprocess.Popen(command, **process_options())
        try:
            return wait_process(process)
        except KeyboardInterrupt:
            console.write("Остановка тестирования", status="!")
            return interrupt_and_wait(process)
    except OSError as error:
        if process is not None:
            terminate_tree(process)
        console.write(f"Не удалось запустить тестирование: {error}", level="Error", status="-")
        return 2


def main():
    require_assertions()
    parser = argparse.ArgumentParser(description="Selenium UI: запуск и проверка проекта")
    parser.add_argument(
        "action",
        nargs="?",
        default="run",
        choices=("run", "check", "verify"),
        help="run: UI и HTML; check: код; verify: отчёт",
    )
    parser.add_argument("--browser", choices=("chrome", "firefox", "both"))
    parser.add_argument(
        "--workers",
        type=int,
        choices=range(1, 13),
        default=4,
        help="Число исполнителей на браузер (1-12, по умолчанию 4)",
    )
    parser.add_argument("--headed", action="store_true", help="Показать тестовый браузер")
    parser.add_argument("--sequential", action="store_true", help="Запускать браузеры по очереди")
    parser.add_argument("--no-report", action="store_true", help="Сохранить Allure JSON без HTML")
    parser.add_argument("--no-screenshots", action="store_true", help="Не снимать PNG страницы")
    parser.add_argument(
        "--no-pause", action="store_true", help="Завершить запуск без ожидания Enter"
    )
    parser.add_argument("--base-url", default="https://practice-automation.com")
    parser.add_argument("--ui-timeout", type=positive_number, default=15.0)
    parser.add_argument("-m", "--markers", default="", help="Например: calendars или negative")
    parser.add_argument("--python", type=Path, help="Python 3.12+ для создания окружения")
    parser.add_argument("--folder", type=Path, help="Каталог результатов для verify")
    args = parser.parse_args()
    if args.python:
        args.python = args.python.resolve()
    if args.folder:
        args.folder = args.folder.resolve()
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    os.environ["PYTHONIOENCODING"] = "utf-8"
    os.environ["PYTHONPATH"] = str(ROOT)
    os.environ["RUFF_CACHE_DIR"] = str(ROOT / "data/.cache/ruff")
    os.chdir(ROOT)
    console.gap()
    console.write(f"Klimkin EV AutoTest | {args.action}")
    if args.action == "verify":
        command = [sys.executable, "-B", "-m", "tools.verification.verify_run"]
        if args.folder:
            command.append(str(args.folder.resolve()))
        if args.browser:
            command.extend(["--browser", args.browser])
        return subprocess.call(command)
    args.browser = args.browser or "chrome"
    try:
        python = ensure_python(ROOT, args.python, development=args.action == "check")
        if args.action == "run" and not args.no_report:
            ensure_reporter(ROOT)
    except BootstrapError as error:
        console.write(f"Ошибка подготовки: {error}", level="Error", status="-")
        return finish_run(2, args.no_pause) if args.action == "run" else 2
    if args.action == "check":
        common = [str(python), "-B", "-m"]
        config = "data/config/pyproject.toml"
        commands = [
            common + ["ruff", "check", "--config", config, "app.py", "utils", "tests", "tools"],
            common
            + [
                "ruff",
                "format",
                "--check",
                "--config",
                config,
                "app.py",
                "utils",
                "tests",
                "tools",
            ],
            common + ["tools.documentation.generate_scenarios", "--check"],
            common
            + [
                "pytest",
                "-c",
                "data/config/pytest.ini",
                "--rootdir=.",
                "tests/framework",
                "-q",
                "--alluredir=data/results/check/allure-results",
            ],
        ]
        labels = ("Ruff", "Форматирование", "Каталог сценариев", "Проверки инфраструктуры")
        for label, command in zip(labels, commands, strict=True):
            console.write(f"Проверка | {label}")
            code = subprocess.call(command)
            if code:
                console.write(f"{label} | код {code}", level="Error", status="-")
                return code
            console.write(f"{label} | готово", status="+")
        return 0
    command = [
        str(python),
        "-B",
        "-m",
        "tools.runner.run_suite",
        "--browser",
        args.browser,
        "--workers",
        str(args.workers),
        "--base-url",
        args.base_url,
        "--ui-timeout",
        str(args.ui_timeout),
    ]
    for flag, enabled in (
        ("--headed", args.headed),
        ("--sequential", args.sequential),
        ("--report", not args.no_report),
        ("--no-screenshots", args.no_screenshots),
    ):
        if enabled:
            command.append(flag)
    if args.markers:
        command.extend(["-m", args.markers])
    return finish_run(run_command(command), args.no_pause)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
