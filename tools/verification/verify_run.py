import argparse
import json
import math
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree

from tools.documentation.generate_scenarios import ROOT, catalog
from utils.reporting.terminal import console
from utils.validation import require_assertions

require_assertions()


def verify_steps(steps):
    for step in steps:
        assert step["status"] == "passed", (step["name"], step["status"])
        verify_steps(step.get("steps", []))


def verify_allure_description(result, descriptions):
    case_id = result["name"].split(".", 1)[0]
    title, steps, expected = descriptions[case_id]
    assert result["name"] == f"{case_id}. {title}", (case_id, "Название Allure не совпадает")
    description = f"Шаги: {steps}\n\nОжидаемый результат: {expected}"
    assert result.get("description") == description, (case_id, "Описание Allure не совпадает")


def verify_metrics(folder, expected):
    cases = json.loads((folder / "collected-scenarios.json").read_text(encoding="utf-8"))
    records = json.loads((folder / "durations.json").read_text(encoding="utf-8"))
    for values in (cases, records):
        ids = [value["id"] for value in values]
        assert len(ids) == len(set(ids)) and set(ids) == expected, "Неполный каталог/метрики"
    phases = ("setup", "call", "teardown")
    for record in records:
        assert set(record["phases"]) == set(phases), (record["id"], record["phases"])
        for phase in record["phases"].values():
            assert phase["outcome"] == "passed", (record["id"], phase)
            assert math.isfinite(phase["seconds"]) and phase["seconds"] >= 0
    return cases, {record["id"]: record for record in records}


def verify_junit(suite, cases, records):
    expected = {}
    for case in cases:
        path, name = case["nodeid"].split("::")
        classname = Path(path).with_suffix("").as_posix().replace("/", ".")
        expected[classname, name] = case["id"]
    actual = [(case.get("classname"), case.get("name")) for case in suite.findall("testcase")]
    assert len(actual) == len(set(actual)) and set(actual) == set(expected), "Неверные тесты JUnit"
    for case in suite.findall("testcase"):
        assert len(case) == 0, "JUnit содержит ошибку, пропуск или неожиданные данные"
        record = records[expected[case.get("classname"), case.get("name")]]
        seconds = sum(phase["seconds"] for phase in record["phases"].values())
        reported = float(case.get("time"))
        assert math.isfinite(reported) and abs(reported - seconds) < 0.005, (record["id"], seconds)


def verify_html_report(folder, total):
    index = folder / "allure-report/index.html"
    assert index.is_file() and index.stat().st_size > 0, "Нет HTML-страницы отчёта"
    summaries = list((folder / "allure-report").rglob("summary.json"))
    assert len(summaries) == 1, "Нет однозначной сводки HTML-отчёта"
    report = json.loads(summaries[0].read_text(encoding="utf-8"))
    assert report["stats"] == {"total": total, "passed": total}, report["stats"]
    assert not report["retryTests"] and not report["flakyTests"]
    return {"total": total, "passed": total, "retries": 0}


def main():
    parser = argparse.ArgumentParser(
        description="Сверка сценариев, Allure, JUnit и метрик полного прогона"
    )
    parser.add_argument("folder", nargs="?", type=Path)
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--both", action="store_true")
    selection.add_argument("--browser", choices=("chrome", "firefox", "both"))
    args = parser.parse_args()
    folder = args.folder or Path((ROOT / "data/results/last-run.txt").read_text(encoding="utf-8"))
    proof = folder / "verification.json"
    proof.unlink(missing_ok=True)
    run = json.loads((folder / "run.json").read_text(encoding="utf-8"))
    browsers = run["browsers"]
    assert run["exit_code"] == 0, "Запуск завершился с ошибкой"
    assert run.get("status") == "passed", "Нет подтверждения завершения прогона"
    requested = run.get("requested_browsers", [])
    assert requested and len(requested) == len(set(requested)), "Не указаны браузеры прогона"
    assert set(requested) <= {"chrome", "firefox"}, "Неизвестный браузер"
    assert set(browsers) == set(requested), "Результаты получены не для всех браузеров"
    selected = "both" if args.both else args.browser
    if selected:
        expected_browsers = {"chrome", "firefox"} if selected == "both" else {selected}
        assert set(browsers) == expected_browsers, "Отчёт не соответствует выбранному браузеру"
    assert not run.get("markers"), "Для итогового отчёта нужен полный набор без -m"
    expected = {case[0] for case in catalog()}
    descriptions = {case[0]: case[1:] for case in catalog()}
    evidence = {}
    total = 0
    for browser, outcome in browsers.items():
        assert outcome["exit_code"] == 0, (browser, outcome)
        assert not outcome.get("interrupted"), (browser, "Прогон браузера прерван")
        assert outcome.get("collected") == len(expected), (browser, "Неполный набор тестов")
        assert outcome.get("test_counts") == {"PASSED": len(expected)}, (browser, outcome)
        cases, records = verify_metrics(folder / browser, expected)
        for case in cases:
            assert (case["title"], case["steps"], case["expected"]) == descriptions[case["id"]]
        result_dir = folder / browser / "allure-results"
        results = [
            json.loads(p.read_text(encoding="utf-8")) for p in result_dir.glob("*-result.json")
        ]
        ids = [result["name"].split(".", 1)[0] for result in results]
        assert len(ids) == len(set(ids)) and set(ids) == expected, (browser, ids)
        statuses = dict(Counter(result["status"] for result in results))
        assert statuses == {"passed": len(expected)}, (browser, statuses)
        assert all(result.get("steps") for result in results), "Сценарий без Allure-шагов"
        for result in results:
            verify_steps(result["steps"])
            params = {p["name"]: p["value"].strip("'") for p in result.get("parameters", [])}
            assert params.get("browser") == browser
            labels = {
                label["name"].casefold(): label["value"] for label in result.get("labels", [])
            }
            assert labels.get("as_id") == result["name"].split(".", 1)[0]
            verify_allure_description(result, descriptions)
        suite = ElementTree.parse(folder / browser / "junit.xml").getroot().find("testsuite")
        assert math.isfinite(float(suite.attrib["time"])) and float(suite.attrib["time"]) >= 0
        assert int(suite.attrib["tests"]) == len(expected)
        assert all(int(suite.attrib[key]) == 0 for key in ("errors", "failures", "skipped"))
        verify_junit(suite, cases, records)
        evidence[browser] = {
            "statuses": statuses,
            "junit_seconds": float(suite.attrib["time"]),
            "documented_ids_match": True,
            "allure_steps_present": True,
            "allure_descriptions_match": True,
            "metrics_complete": True,
            "junit_cases_match": True,
            "phase_seconds": {
                phase: round(
                    sum(record["phases"][phase]["seconds"] for record in records.values()), 3
                )
                for phase in ("setup", "call", "teardown")
            },
        }
        total += len(results)
    if "report_exit_code" in run:
        assert run["report_exit_code"] == 0
        evidence["html_report"] = verify_html_report(folder, total)
    evidence["wall_seconds"] = run["wall_seconds"]
    evidence["execution"] = run["execution"]
    evidence["workers_per_browser"] = run.get("workers_per_browser", 1)
    evidence["scenario_counts"] = dict(
        Counter(
            case_id.split("-")[0] for case_id in {case[0].split("[", 1)[0] for case in catalog()}
        )
    )
    evidence["execution_counts"] = dict(Counter(case[0].split("-")[0] for case in catalog()))
    proof.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    console.write(
        f"Проверка | вариантов: {len(expected)} × {len(browsers)} браузер(а) = {total}; "
        "Allure, JUnit и каталог сценариев согласованы; пропусков и повторных попыток нет.",
        status="+",
    )


if __name__ == "__main__":
    main()
