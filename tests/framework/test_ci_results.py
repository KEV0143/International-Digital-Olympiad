import json

import pytest

from tools.ci import merge_results


def make_run(folder, browser, *, failed=False):
    target = folder / f"ui-{browser}" / "run-one"
    (target / browser).mkdir(parents=True)
    (target / browser / "junit.xml").write_text("<testsuites/>", encoding="utf-8")
    run = {
        "requested_browsers": [browser],
        "browsers": {browser: {"exit_code": int(failed)}},
        "base_url": "https://example.test",
        "headed": False,
        "screenshots": False,
        "ui_timeout": 15,
        "markers": "",
        "workers_per_browser": 2,
        "status": "failed" if failed else "passed",
        "exit_code": int(failed),
        "started_utc": "2026-10-25T10:00:00+00:00",
        "finished_utc": "2026-10-25T10:01:00+00:00",
    }
    path = target / "run.json"
    path.write_text(json.dumps(run), encoding="utf-8")
    return path, run


@pytest.mark.parametrize("condition", ["passed", "failed", "missing"])
def test_matrix_merge_keeps_failure_status_and_available_evidence(tmp_path, condition):
    make_run(tmp_path, "chrome", failed=condition == "failed")
    if condition != "missing":
        make_run(tmp_path, "firefox")
    output = tmp_path / "combined"
    run = merge_results.merge_runs(tmp_path, output)
    assert run["exit_code"] == (0 if condition == "passed" else 1)
    assert run["status"] == ("passed" if condition == "passed" else "failed")
    assert (output / "chrome/junit.xml").is_file()
    assert run["wall_seconds"] == 60
    assert json.loads((output / "run.json").read_text(encoding="utf-8")) == run


@pytest.mark.parametrize("damage", ["parameters", "browser", "duplicate"])
def test_matrix_merge_rejects_incompatible_artifacts(tmp_path, damage):
    make_run(tmp_path, "chrome")
    path, run = make_run(tmp_path, "firefox")
    if damage == "duplicate":
        other = path.parent.parent / "run-two"
        other.mkdir()
        (other / "run.json").write_text(json.dumps(run), encoding="utf-8")
        result = merge_results.merge_runs(tmp_path, tmp_path / "combined")
        assert result["exit_code"] == 1
        assert "firefox" not in result["browsers"]
        return
    if damage == "parameters":
        run["workers_per_browser"] = 4
    else:
        run["requested_browsers"] = ["chrome"]
    path.write_text(json.dumps(run), encoding="utf-8")
    with pytest.raises(ValueError):
        merge_results.merge_runs(tmp_path, tmp_path / "combined")
