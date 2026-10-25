import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize("working_directory", [".", "tests/ui"])
def test_pytest_resolves_ui_fixtures_with_project_config(tmp_path, working_directory):
    root = Path(__file__).resolve().parents[2]
    environment = os.environ | {
        "PYTEST_ADDOPTS": "",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONIOENCODING": "utf-8",
    }
    environment.pop("PYTHONPATH", None)
    process = subprocess.run(
        [
            sys.executable,
            "-B",
            "-m",
            "pytest",
            "-c",
            str(root / "data/config/pytest.ini"),
            f"--rootdir={root}",
            "--setup-plan",
            "-q",
            "--browser=firefox",
            f"--alluredir={tmp_path / 'allure-results'}",
            "-o",
            f"cache_dir={tmp_path / 'cache'}",
        ],
        cwd=root / working_directory,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    output = process.stdout + process.stderr
    assert process.returncode == 0, output
    assert re.search(r"\bSETUP\s+F driver\b", output), output
    catalog = json.loads((tmp_path / "collected-scenarios.json").read_text(encoding="utf-8"))
    assert len(catalog) == 55
    assert len({case["id"] for case in catalog}) == 55
    assert all(case["nodeid"].startswith("tests/ui/") for case in catalog)


def test_page_assertion_displays_actual_and_expected_values(tmp_path):
    root = Path(__file__).resolve().parents[2]
    probe = tmp_path / "test_page_assertion.py"
    probe.write_text(
        "from utils.pages.form_fields_page import FormFieldsPage\n"
        "def test_saved_values():\n"
        "    page = object.__new__(FormFieldsPage)\n"
        "    page.form_values = lambda: {'name': 'ACTUAL_NAME'}\n"
        "    page.assert_saved_values({'name': 'EXPECTED_NAME'})\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            "-m",
            "pytest",
            str(probe),
            "-v",
            "--tb=short",
            "-c",
            str(root / "data/config/pytest.ini"),
            f"--rootdir={tmp_path}",
            f"--alluredir={tmp_path / 'allure-results'}",
            "-o",
            f"cache_dir={tmp_path / 'cache'}",
        ],
        cwd=root,
        env=os.environ | {"PYTEST_ADDOPTS": "", "PYTHONIOENCODING": "utf-8"},
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    assert result.returncode == 1, result.stdout + result.stderr
    assert "{'name': 'ACTUAL_NAME'} == {'name': 'EXPECTED_NAME'}" in result.stdout
