import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from threading import Event
from time import monotonic, sleep
from uuid import uuid4

from tools.runner.processes import process_options, terminate_tree, wait_process
from utils.reporting.progress import PytestProgress, scenario_names
from utils.reporting.terminal import console, elapsed_time, follow_process
from utils.validation import positive_number, require_assertions

ROOT = Path(__file__).resolve().parents[2]


def run_browser(browser, folder, args, cancelled):
    if cancelled.is_set():
        return {"exit_code": 130, "interrupted": True}
    target = folder / browser
    target.mkdir()
    command = [
        sys.executable,
        "-u",
        "-B",
        "-m",
        "pytest",
        "-c",
        "data/config/pytest.ini",
        "--rootdir=.",
        "tests/ui",
        "-v",
        "--color=no",
        "--durations=10",
        f"--browser={browser}",
        f"--alluredir={target / 'allure-results'}",
        f"--junitxml={target / 'junit.xml'}",
        f"--base-url={args.base_url}",
        f"--ui-timeout={args.ui_timeout}",
    ]
    if args.headed:
        command.append("--headed")
    if args.no_screenshots:
        command.append("--no-screenshots")
    if args.markers:
        command.extend(["-m", args.markers])
    if args.workers > 1:
        command.extend(["-n", str(args.workers), "--dist=worksteal", "--max-worker-restart=0"])
    progress = PytestProgress(browser, console, scenario_names(ROOT))
    console.write(f"{progress.browser} | запуск | исполнителей: {args.workers}")
    started = monotonic()
    with (target / "pytest.log").open("w", encoding="utf-8") as log:
        with subprocess.Popen(
            command,
            cwd=ROOT,
            stdout=log,
            stderr=subprocess.STDOUT,
            env=os.environ
            | {
                "PYTHONIOENCODING": "utf-8",
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONPATH": str(ROOT),
            },
            **process_options(),
        ) as process:
            (target / "process.json").write_text(
                json.dumps({"pytest_pid": process.pid, "command": command}, indent=2),
                encoding="utf-8",
            )

            def update():
                if cancelled.is_set():
                    terminate_tree(process)
                else:
                    progress.tick()

            try:
                code = follow_process(process, target / "pytest.log", progress.consume, update)
            except BaseException:
                terminate_tree(process)
                raise
    if cancelled.is_set():
        code = 130
    seconds = round(monotonic() - started, 3)
    progress.finish(code)
    if code:
        log_text = (target / "pytest.log").read_text(encoding="utf-8", errors="replace")
        lines = log_text.splitlines()
        failure_start = next(
            (i for i, line in enumerate(lines) if "= FAILURES =" in line or "= ERRORS =" in line),
            max(0, len(lines) - 20),
        )
        console.write("\n".join(lines[failure_start:]), level="Error", status="-")
        console.write(f"{progress.browser} | полный журнал: {target / 'pytest.log'}", status="!")
    return {
        "exit_code": code,
        "wall_seconds": seconds,
        "collected": progress.total,
        "test_counts": dict(Counter(progress.results.values())),
        "interrupted": code == 130,
    }


def show_summary(folder, summary):
    counts = Counter()
    collected = []
    for result in summary["browsers"].values():
        counts.update(result.get("test_counts", {}))
        collected.append(result.get("collected"))
    total = sum(collected) if collected and all(value is not None for value in collected) else "?"
    console.gap()
    console.write(
        f"Статистика | выполнено: {sum(counts.values())}/{total} | "
        f"успешно: {counts['PASSED']} | ошибок: {counts['FAILED'] + counts['ERROR']} | "
        f"пропущено: {counts['SKIPPED']}",
        status="+" if not summary["exit_code"] else "!",
    )
    if counts["XFAIL"] or counts["XPASS"]:
        console.write(
            f"Статистика | XFAIL: {counts['XFAIL']} | XPASS: {counts['XPASS']}", status="!"
        )
    console.write(
        f"Затраченное время: {elapsed_time(summary['wall_seconds'])} "
        f"({summary['wall_seconds']:.1f} с) | код {summary['exit_code']}",
        level="Error" if summary["exit_code"] else "Info",
        status="-" if summary["exit_code"] else "+",
    )
    console.write(f"Результаты: {folder}", status="+" if not summary["exit_code"] else "!")
    report = folder / "allure-report/index.html"
    if summary.get("report_exit_code") == 0 and report.is_file():
        console.write(f"HTML-отчёт: {report}", status="+")
    elif "report_exit_code" in summary:
        console.write(f"HTML-отчёт не создан. Журнал сборки: {folder / 'report.log'}", status="!")
    elif summary.get("status") == "interrupted":
        console.write("Прогон прерван; HTML-отчёт не сформирован.", status="!")
    else:
        console.write("HTML-отчёт отключён; данные Allure сохранены в каталогах браузеров.")


def generate_report(folder, browsers):
    cli = (
        ROOT
        / "tools/reporting/node_modules/.bin"
        / ("allure.cmd" if sys.platform == "win32" else "allure")
    )
    if not cli.is_file():
        console.write("Allure не установлен. Запустите python app.py", level="Error", status="-")
        return 2
    merged = folder / "allure-results"
    merged.mkdir()
    environments = []
    for browser in browsers:
        result_dir = folder / browser / "allure-results"
        if not result_dir.is_dir():
            continue
        for source in result_dir.iterdir():
            if source.name != "environment.properties":
                target = merged / source.name
                if target.exists():
                    raise RuntimeError(f"Повторяющееся имя Allure: {source.name}")
                shutil.copy2(source, target)
        env_file = result_dir / "environment.properties"
        if env_file.is_file():
            environments.append(
                dict(
                    line.split("=", 1)
                    for line in env_file.read_text(encoding="utf-8").splitlines()
                    if "=" in line
                )
            )
    if environments:
        shared = {
            key: environments[0][key]
            for key in environments[0]
            if key not in ("Browser", "BrowserVersion")
            and all(env.get(key) == environments[0][key] for env in environments)
        }
        shared["Browsers"] = "; ".join(
            f"{env['Browser']} {env['BrowserVersion']}" for env in environments
        )
        (merged / "environment.properties").write_text(
            "\n".join(f"{key}={value}" for key, value in shared.items()) + "\n", encoding="utf-8"
        )
    console.write("Allure | сборка HTML-отчёта")
    with (folder / "report.log").open("w", encoding="utf-8") as log:
        with subprocess.Popen(
            [
                str(cli),
                "generate",
                str(merged),
                "--output",
                str(folder / "allure-report"),
                "--config",
                str(ROOT / "data/config/allurerc.json"),
            ],
            cwd=ROOT,
            stdout=log,
            stderr=subprocess.STDOUT,
            **process_options(),
        ) as process:
            try:
                code = wait_process(process)
            except BaseException:
                terminate_tree(process)
                raise
    if code:
        console.write(
            (folder / "report.log").read_text(encoding="utf-8", errors="replace"),
            level="Error",
            status="-",
        )
    else:
        console.write(f"Allure | отчёт готов: {folder / 'allure-report/index.html'}", status="+")
    return code


def main():
    require_assertions()
    parser = argparse.ArgumentParser(description="Запуск UI-сценариев и сборка Allure")
    parser.add_argument("--browser", choices=("chrome", "firefox", "both"), default="chrome")
    parser.add_argument("--workers", type=int, choices=range(1, 13), default=4)
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--sequential", action="store_true")
    parser.add_argument("--report", action="store_true")
    parser.add_argument("--base-url", default="https://practice-automation.com")
    parser.add_argument("--ui-timeout", type=positive_number, default=15.0)
    parser.add_argument("--no-screenshots", action="store_true")
    parser.add_argument("-m", "--markers", default="")
    args = parser.parse_args()
    folder = ROOT / "data/results" / f"run-{datetime.now(UTC):%Y%m%dT%H%M%S%fZ}-{uuid4().hex[:8]}"
    folder.mkdir(parents=True)
    browsers = ("chrome", "firefox") if args.browser == "both" else (args.browser,)
    summary = {
        "started_utc": datetime.now(UTC).isoformat(),
        "browsers": {},
        "requested_browsers": list(browsers),
        "status": "running",
        "base_url": args.base_url,
        "headed": args.headed,
        "screenshots": not args.no_screenshots,
        "ui_timeout": args.ui_timeout,
        "markers": args.markers,
        "workers_per_browser": args.workers,
        "execution": "sequential" if args.sequential or len(browsers) == 1 else "concurrent",
    }
    started = monotonic()
    exit_code = 0
    cancelled = Event()
    futures = {}
    console.gap()
    console.write("Selenium UI | " + ", ".join(browser.capitalize() for browser in browsers))
    console.write(f"Исполнителей на браузер: {args.workers} | сайт: {args.base_url}")
    if args.markers:
        console.write(f"Выбор тестов: {args.markers}")
    try:
        with ThreadPoolExecutor(max_workers=1 if args.sequential else len(browsers)) as pool:
            futures = {
                browser: pool.submit(run_browser, browser, folder, args, cancelled)
                for browser in browsers
            }
            try:
                for browser, future in futures.items():
                    try:
                        while not future.done():
                            sleep(0.1)
                        summary["browsers"][browser] = future.result()
                    except Exception as error:
                        summary["browsers"][browser] = {"exit_code": 2, "error": str(error)}
                        console.finish(browser.capitalize())
                        console.write(f"{browser}: {error}", level="Error", status="-")
                    exit_code = exit_code or summary["browsers"][browser]["exit_code"]
            except BaseException:
                cancelled.set()
                raise
        if args.report:
            try:
                summary["report_exit_code"] = generate_report(folder, browsers)
            except Exception as error:
                summary["report_exit_code"] = 2
                summary["report_error"] = str(error)
                console.write(f"Ошибка отчёта: {error}", level="Error", status="-")
            exit_code = exit_code or summary["report_exit_code"]
        summary["status"] = "passed" if exit_code == 0 else "failed"
    except KeyboardInterrupt:
        exit_code = 130
        summary["status"] = "interrupted"
        for browser, future in futures.items():
            if browser not in summary["browsers"]:
                try:
                    summary["browsers"][browser] = future.result()
                except (KeyboardInterrupt, Exception):
                    summary["browsers"][browser] = {"exit_code": 130, "interrupted": True}
        console.write("Тестирование прервано пользователем", status="!")
    except Exception as error:
        exit_code = exit_code or 2
        summary["status"] = "failed"
        summary["error"] = str(error)
        console.write(f"Ошибка запуска: {error}", level="Error", status="-")
    finally:
        if summary["status"] == "running":
            summary["status"] = "failed"
            exit_code = exit_code or 2
        summary["finished_utc"] = datetime.now(UTC).isoformat()
        summary["wall_seconds"] = round(monotonic() - started, 3)
        summary["exit_code"] = exit_code
        (folder / "run.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        (ROOT / "data/results/last-run.txt").write_text(str(folder), encoding="utf-8")
        show_summary(folder, summary)
    return exit_code


if __name__ == "__main__":
    if sys.platform == "win32":
        signal.signal(signal.SIGBREAK, signal.default_int_handler)
    raise SystemExit(main())
