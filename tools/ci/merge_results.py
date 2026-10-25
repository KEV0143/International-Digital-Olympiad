import argparse
import json
import shutil
from datetime import datetime
from pathlib import Path

from tools.environment.bootstrap import ensure_reporter
from tools.runner.run_suite import generate_report
from utils.reporting.terminal import console
from utils.validation import require_assertions

ROOT = Path(__file__).resolve().parents[2]


def merge_runs(artifacts, output):
    output.mkdir(parents=True, exist_ok=False)
    summary = {
        "requested_browsers": ["chrome", "firefox"],
        "browsers": {},
        "execution": "ci-matrix",
        "errors": [],
    }
    runs = []
    for browser in summary["requested_browsers"]:
        candidates = list((artifacts / f"ui-{browser}").rglob("run.json"))
        if len(candidates) != 1:
            summary["errors"].append(
                f"{browser}: ожидался один run.json, найдено {len(candidates)}"
            )
            continue
        path = candidates[0]
        run = json.loads(path.read_text(encoding="utf-8"))
        if run["requested_browsers"] != [browser] or set(run["browsers"]) != {browser}:
            raise ValueError(f"{browser}: артефакт содержит другой набор браузеров")
        for key in (
            "base_url",
            "headed",
            "screenshots",
            "ui_timeout",
            "markers",
            "workers_per_browser",
        ):
            if key in summary and summary[key] != run[key]:
                raise ValueError(f"Браузеры запущены с разными параметрами: {key}")
            summary[key] = run[key]
        if run["status"] != "passed" or run["exit_code"]:
            summary["errors"].append(f"{browser}: статус {run['status']}, код {run['exit_code']}")
        source = path.parent / browser
        if not source.is_dir():
            summary["errors"].append(f"{browser}: отсутствует каталог результатов")
            continue
        shutil.copytree(source, output / browser)
        summary["browsers"][browser] = run["browsers"][browser]
        runs.append(run)
    if runs:
        summary["started_utc"] = min(run["started_utc"] for run in runs)
        summary["finished_utc"] = max(run["finished_utc"] for run in runs)
        summary["wall_seconds"] = round(
            (
                datetime.fromisoformat(summary["finished_utc"])
                - datetime.fromisoformat(summary["started_utc"])
            ).total_seconds(),
            3,
        )
    else:
        summary["wall_seconds"] = 0.0
    summary["exit_code"] = 1 if summary["errors"] else 0
    summary["status"] = "failed" if summary["exit_code"] else "passed"
    write_summary(output, summary)
    return summary


def write_summary(output, summary):
    (output / "run.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")


def main():
    require_assertions()
    parser = argparse.ArgumentParser(description="Объединение результатов CI-матрицы")
    parser.add_argument("artifacts", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    summary = merge_runs(args.artifacts, args.output)
    try:
        ensure_reporter(ROOT)
        summary["report_exit_code"] = generate_report(args.output, summary["browsers"])
    except Exception as error:
        summary["report_exit_code"] = 2
        summary["errors"].append(str(error))
    summary["exit_code"] = summary["exit_code"] or summary["report_exit_code"]
    summary["status"] = "failed" if summary["exit_code"] else "passed"
    write_summary(args.output, summary)
    for error in summary["errors"]:
        console.write(error, level="Error", status="-")
    return summary["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
