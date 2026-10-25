import json
import platform
import sys
from pathlib import Path

import allure
import pytest

from utils.browser.factory import create_browser
from utils.browser.transport import command_timeout
from utils.reporting.evidence import attach, snapshot
from utils.reporting.redaction import redact_text
from utils.reporting.scenarios import item_metadata, report_case
from utils.validation import positive_number, require_assertions

pytest.register_assert_rewrite("utils.pages", "utils.components")

DRIVER = pytest.StashKey()
LAST_STATE = pytest.StashKey()
PHASES = pytest.StashKey()
REPORTS = pytest.StashKey()
CATALOG = pytest.StashKey()
RECORDS = pytest.StashKey()
ENVIRONMENT = pytest.StashKey()


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config):
    try:
        require_assertions()
    except RuntimeError as error:
        raise pytest.UsageError(str(error)) from error
    if hasattr(config, "workerinput"):
        config.option.clean_alluredir = False


def pytest_addoption(parser):
    group = parser.getgroup("ui")
    group.addoption("--browser", choices=("chrome", "firefox"), default="chrome")
    group.addoption("--headed", action="store_true", help="Показать тестовый браузер")
    group.addoption("--base-url", default="https://practice-automation.com")
    group.addoption("--ui-timeout", type=positive_number, default=15.0)
    group.addoption("--no-screenshots", action="store_true", help="Не снимать PNG страницы")


@pytest.fixture
def driver(request):
    for attempt in (1, 2):
        try:
            browser = create_browser(
                request.config.getoption("--browser"), request.config.getoption("--headed")
            )
        except Exception as error:
            if attempt == 2:
                request.node.stash[LAST_STATE] = {
                    "browser-launch-error": redact_text(f"{type(error).__name__}: {error}")
                }
                raise
        else:
            break
    request.node.stash[DRIVER] = browser
    try:
        allure.dynamic.parameter("browser", browser.capabilities["browserName"])
        allure.dynamic.parameter(
            "browser_version", browser.capabilities["browserVersion"], excluded=True
        )
        result_dir = request.config.getoption("allure_report_dir")
        if result_dir:
            folder = Path(result_dir)
            folder.mkdir(parents=True, exist_ok=True)
            environment = {
                "Python": platform.python_version(),
                "OS": platform.platform(),
                "Browser": browser.capabilities["browserName"],
                "BrowserVersion": browser.capabilities["browserVersion"],
                "BaseURL": request.config.getoption("--base-url"),
                "Headless": str(not request.config.getoption("--headed")),
                "InitialWindow": "1440x1100",
            }
            previous = request.config.stash.setdefault(ENVIRONMENT, environment)
            if previous != environment:
                raise pytest.UsageError("Параметры окружения изменились между тестами")
        yield browser
    finally:
        cleanup_browser(
            request.node, browser, screenshots=not request.config.getoption("--no-screenshots")
        )


def cleanup_browser(node, browser, *, screenshots):
    failures = []
    evidence = node.stash.get(LAST_STATE, {})
    try:
        try:
            evidence = snapshot(browser, screenshots=screenshots)
        except Exception as error:
            failures.append(error)
    finally:
        try:
            with command_timeout(browser, 5):
                browser.quit()
        except Exception as error:
            failures.append(error)
        finally:
            node.stash[DRIVER] = None
    node.stash[LAST_STATE] = evidence
    if not failures:
        return
    details = "\n".join(redact_text(f"{type(error).__name__}: {error}") for error in failures)
    evidence["cleanup-errors"] = details
    attach({"cleanup-errors": details}, "teardown")
    primary = sys.exception()
    if primary is not None:
        primary.add_note(f"Ошибки при завершении браузера:\n{details}")
        return
    failed_reports = [r for r in node.stash.get(REPORTS, {}).values() if r.failed]
    if failed_reports:
        for report in failed_reports:
            report.sections.append(("Browser cleanup", details))
        return
    raise ExceptionGroup("Ошибка завершения браузера", failures)


@pytest.fixture
def page_options(request):
    return {
        "base_url": request.config.getoption("--base-url"),
        "timeout": request.config.getoption("--ui-timeout"),
    }


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    item.stash.setdefault(REPORTS, {})[report.when] = report
    phases = item.stash.setdefault(PHASES, {})
    phases[report.when] = {"seconds": round(report.duration, 6), "outcome": report.outcome}
    if report.failed:
        browser = item.stash.get(DRIVER, None)
        evidence = item.stash.get(LAST_STATE, {})
        if browser:
            try:
                evidence = snapshot(
                    browser, screenshots=not item.config.getoption("--no-screenshots")
                )
            except Exception as error:
                evidence = {"snapshot-error": f"{type(error).__name__}: {error}"}
        attach(evidence, report.when if browser else f"{report.when}: last live page")


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_setup(item):
    yield
    report_case(item)


def pytest_sessionfinish(session):
    result_dir = session.config.getoption("allure_report_dir")
    if not result_dir or session.config.option.collectonly:
        return
    records = session.config.stash.get(RECORDS, [])
    for item in session.items:
        phases = item.stash.get(PHASES, {})
        if phases:
            metadata = item_metadata(item) or {}
            records.append({"id": metadata.get("id", item.nodeid), "phases": phases})
    cases = session.config.stash.get(CATALOG, [])
    environment = session.config.stash.get(ENVIRONMENT, {})
    if hasattr(session.config, "workerinput"):
        session.config.workeroutput["ui_results"] = {
            "records": records,
            "catalog": cases,
            "environment": environment,
        }
        return
    folder = Path(result_dir).parent
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "durations.json").write_text(
        json.dumps(sorted(records, key=lambda r: r["id"]), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (folder / "collected-scenarios.json").write_text(
        json.dumps(cases, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if environment:
        (Path(result_dir) / "environment.properties").write_text(
            "\n".join(f"{key}={value}" for key, value in environment.items()) + "\n",
            encoding="utf-8",
        )


def merge_worker_results(config, payload):
    for key, name in ((CATALOG, "catalog"), (ENVIRONMENT, "environment")):
        value = payload.get(name)
        if value:
            previous = config.stash.get(key, None)
            if previous and previous != value:
                raise pytest.UsageError(f"Исполнители получили разные {name}")
            config.stash[key] = value
    config.stash.setdefault(RECORDS, []).extend(payload.get("records", []))


@pytest.hookimpl(optionalhook=True)
def pytest_testnodedown(node, error):
    merge_worker_results(node.config, node.workeroutput.get("ui_results", {}))


def pytest_collection_finish(session):
    cases = []
    seen = set()
    for item in session.items:
        data = item_metadata(item)
        if data:
            if data["id"] in seen:
                raise pytest.UsageError(f"Duplicate scenario ID: {data['id']}")
            seen.add(data["id"])
            cases.append({**data, "nodeid": item.nodeid, "line": item.location[1] + 1})
        elif "tests/ui/" in item.nodeid.split("::", 1)[0].replace("\\", "/"):
            raise pytest.UsageError(f"UI scenario metadata missing: {item.nodeid}")
    session.config.stash[CATALOG] = cases
    if session.config.option.collectonly and not hasattr(session.config, "workerinput"):
        result_dir = session.config.getoption("allure_report_dir")
        folder = Path(result_dir).parent if result_dir else Path("data/results/collection")
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "collected-scenarios.json").write_text(
            json.dumps(cases, ensure_ascii=False, indent=2), encoding="utf-8"
        )
