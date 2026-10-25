import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from xml.etree import ElementTree

import pytest

from tools.verification.verify_run import verify_allure_description, verify_junit, verify_metrics
from utils import pytest_plugin as plugin


@pytest.mark.parametrize("damage", [None, "title", "steps", "expected", "missing"])
def test_verifier_matches_allure_title_steps_and_expectation(damage):
    descriptions = {"FF-S01": ("Заполнение Message", "Прочитать список.", "Строка введена.")}
    result = {
        "name": "FF-S01. Заполнение Message",
        "description": "Шаги: Прочитать список.\n\nОжидаемый результат: Строка введена.",
    }
    if damage is None:
        verify_allure_description(result, descriptions)
        return
    if damage == "title":
        result["name"] = "FF-S01. Старое название"
    elif damage == "missing":
        result.pop("description")
    else:
        old = "Прочитать список." if damage == "steps" else "Строка введена."
        result["description"] = result["description"].replace(old, "Чужой сценарий.")
    with pytest.raises(AssertionError, match="Allure не совпадает"):
        verify_allure_description(result, descriptions)


def test_worker_start_cannot_clear_attachments_written_by_another_worker():
    config = SimpleNamespace(workerinput={}, option=SimpleNamespace(clean_alluredir=True))
    plugin.pytest_configure(config)
    assert not config.option.clean_alluredir


def test_worker_results_merge_without_overwriting_other_cases():
    config = SimpleNamespace(stash=pytest.Stash())
    config.stash[plugin.CATALOG] = []
    for case_id in ("FF-P01", "FF-P02"):
        plugin.merge_worker_results(
            config,
            {
                "catalog": [{"id": "FF-P01"}, {"id": "FF-P02"}],
                "environment": {"BrowserVersion": "same"},
                "records": [{"id": case_id}],
            },
        )
    assert config.stash[plugin.RECORDS] == [{"id": "FF-P01"}, {"id": "FF-P02"}]
    assert len(config.stash[plugin.CATALOG]) == 2


@pytest.mark.parametrize("name", ["catalog", "environment"])
def test_inconsistent_workers_are_rejected(name):
    config = SimpleNamespace(stash=pytest.Stash())
    plugin.merge_worker_results(config, {name: {"value": "first"}})
    with pytest.raises(pytest.UsageError, match="Исполнители получили разные"):
        plugin.merge_worker_results(config, {name: {"value": "second"}})


def test_real_parallel_run_keeps_all_cases_and_original_failure(tmp_path):
    source = tmp_path / "test_parallel.py"
    source.write_text(
        "from utils.reporting.scenarios import scenario\n"
        "@scenario('FF-P91', 'first', 'step', 'result')\n"
        "def test_first(): assert True\n"
        "@scenario('FF-P92', 'second', 'step', 'result')\n"
        "def test_second(): assert True\n"
        "@scenario('FF-N91', 'failure', 'step', 'result')\n"
        "def test_failure(): raise AssertionError('ORIGINAL_PARALLEL_FAILURE')\n",
        encoding="utf-8",
    )
    root = Path(__file__).resolve().parents[2]
    results = tmp_path / "allure-results"
    process = subprocess.run(
        [
            sys.executable,
            "-B",
            "-m",
            "pytest",
            "-c",
            str(root / "data/config/pytest.ini"),
            f"--rootdir={tmp_path}",
            str(source),
            "-n",
            "2",
            "--max-worker-restart=0",
            "-q",
            f"--alluredir={results}",
        ],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        env=os.environ
        | {
            "PYTHONPATH": str(root),
            "PYTHONIOENCODING": "utf-8",
            "PYTEST_ADDOPTS": "",
            "PYTHONDONTWRITEBYTECODE": "1",
        },
    )
    assert process.returncode == 1, process.stdout + process.stderr
    assert "ORIGINAL_PARALLEL_FAILURE" in process.stdout
    records = json.loads((tmp_path / "durations.json").read_text(encoding="utf-8"))
    catalog = json.loads((tmp_path / "collected-scenarios.json").read_text(encoding="utf-8"))
    expected = {"FF-P91", "FF-P92", "FF-N91"}
    assert len(records) == len(catalog) == 3
    assert {case["id"] for case in records} == {case["id"] for case in catalog} == expected
    assert all(set(case["phases"]) == {"setup", "call", "teardown"} for case in records)
    failure = next(case for case in records if case["id"] == "FF-N91")
    assert failure["phases"]["call"]["outcome"] == "failed"
    assert len(list(results.glob("*-result.json"))) == 3


@pytest.mark.parametrize("damage", ["missing", "duplicate", "failed", "nan", "negative"])
def test_verifier_rejects_incomplete_or_invalid_timings(tmp_path, damage):
    cases = [{"id": "FF-P01"}, {"id": "FF-P02"}]
    records = [
        {
            "id": case["id"],
            "phases": {
                phase: {"seconds": 0.1, "outcome": "passed"}
                for phase in ("setup", "call", "teardown")
            },
        }
        for case in cases
    ]
    if damage == "missing":
        records.pop()
    elif damage == "duplicate":
        records[1]["id"] = records[0]["id"]
    elif damage == "failed":
        records[0]["phases"]["teardown"]["outcome"] = "failed"
    else:
        records[0]["phases"]["call"]["seconds"] = float("nan") if damage == "nan" else -1
    (tmp_path / "collected-scenarios.json").write_text(json.dumps(cases), encoding="utf-8")
    (tmp_path / "durations.json").write_text(json.dumps(records), encoding="utf-8")
    with pytest.raises(AssertionError):
        verify_metrics(tmp_path, {case["id"] for case in cases})


@pytest.mark.parametrize("damage", ["wrong_name", "wrong_time", "hidden_failure"])
def test_verifier_checks_individual_junit_cases(damage):
    suite = ElementTree.fromstring(
        '<testsuite><testcase classname="tests.ui.test_form_fields" '
        'name="test_first" time="0.3" /></testsuite>'
    )
    cases = [{"id": "FF-P01", "nodeid": "tests/ui/test_form_fields.py::test_first"}]
    records = {
        "FF-P01": {
            "id": "FF-P01",
            "phases": {
                phase: {"seconds": 0.1, "outcome": "passed"}
                for phase in ("setup", "call", "teardown")
            },
        }
    }
    case = suite.find("testcase")
    if damage == "wrong_name":
        case.set("name", "another_test")
    elif damage == "wrong_time":
        case.set("time", "999")
    else:
        ElementTree.SubElement(case, "failure")
    with pytest.raises(AssertionError):
        verify_junit(suite, cases, records)
