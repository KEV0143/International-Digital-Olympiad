import json
import os
import subprocess
import sys
from pathlib import Path

from utils.reporting.progress import scenario_names


def test_parameterized_cases_have_separate_allure_history_metadata_and_timings(tmp_path):
    root = Path(__file__).resolve().parents[2]
    source = tmp_path / "test_variants.py"
    source.write_text(
        "import allure\n"
        "from utils.reporting.scenarios import scenario_cases\n"
        "@scenario_cases([\n"
        " ('MOD-N02[first]', 'First', 'Enter first', 'Rejected', 'one'),\n"
        " ('MOD-N02[second]', 'Second', 'Enter second', 'Rejected', 'two'),\n"
        "])\n"
        "def test_value(case):\n"
        "    with allure.step('Check value'): assert case['value'] in ('one', 'two')\n",
        encoding="utf-8",
    )
    result_dir = tmp_path / "allure-results"
    process = subprocess.run(
        [
            sys.executable,
            "-B",
            "-m",
            "pytest",
            str(source),
            "-c",
            str(root / "data/config/pytest.ini"),
            f"--rootdir={tmp_path}",
            f"--alluredir={result_dir}",
            "-o",
            f"cache_dir={tmp_path / 'cache'}",
            "-q",
        ],
        cwd=root,
        env=os.environ
        | {"PYTHONPATH": str(root), "PYTHONDONTWRITEBYTECODE": "1", "PYTEST_ADDOPTS": ""},
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    assert process.returncode == 0, process.stdout + process.stderr
    results = [
        json.loads(path.read_text(encoding="utf-8")) for path in result_dir.glob("*-result.json")
    ]
    assert len(results) == 2
    assert len({result["historyId"] for result in results}) == 2
    assert {result["name"] for result in results} == {
        "MOD-N02[first]. First",
        "MOD-N02[second]. Second",
    }
    for result in results:
        labels = {label["name"]: label["value"] for label in result["labels"]}
        assert labels["as_id"] == result["name"].split(".", 1)[0]
        assert labels["requirement"] == "MOD-N02"
        assert result["description"].startswith("Шаги: Enter ")
        assert result["steps"][0]["status"] == "passed"
        assert result["parameters"][0]["value"] in ("'one'", "'two'")
    records = json.loads((tmp_path / "durations.json").read_text(encoding="utf-8"))
    assert {record["id"] for record in records} == {"MOD-N02[first]", "MOD-N02[second]"}
    assert all(set(record["phases"]) == {"setup", "call", "teardown"} for record in records)


def test_console_catalog_keeps_parameterized_node_ids():
    names = scenario_names(Path(__file__).resolve().parents[2])
    assert names["tests/ui/test_calendars.py::test_invalid_date_is_rejected[CAL-N04]"].startswith(
        "CAL-N04."
    )
    assert names[
        "tests/ui/test_modals.py::test_invalid_email_blocks_submission[MOD-N02[double_at]]"
    ].startswith("MOD-N02[double_at].")
