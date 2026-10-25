from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from utils import pytest_plugin as conftest
from utils.browser.transport import command_timeout
from utils.reporting.evidence import redact_html, snapshot


@pytest.mark.parametrize(
    "markup",
    [
        '<input value="private-token" type="hidden">',
        "<INPUT TYPE='HIDDEN' value='private-token' />",
        "<input value=private-token disabled type=hidden>",
        '<input\n value="private-token" data-note="a > b" type="password">',
        '<input value="private-token" type="password" value="second-token">',
    ],
)
def test_sensitive_input_values_masked_without_losing_public_html(markup):
    public = '<label>Public <b>text</b></label><input type="text" value="public-value">'
    result = redact_html(public + markup)
    assert result.startswith(public)
    assert "private-token" not in result and "second-token" not in result
    assert "[redacted]" in result


def test_browser_launch_failure_is_saved_for_allure(monkeypatch):
    options = {"--browser": "chrome", "--headed": False}
    request = SimpleNamespace(
        config=SimpleNamespace(getoption=lambda key: options[key]),
        node=SimpleNamespace(stash=pytest.Stash()),
    )
    monkeypatch.setattr(
        conftest, "create_browser", Mock(side_effect=RuntimeError("Chrome недоступен"))
    )
    fixture = conftest.driver.__wrapped__(request)
    with pytest.raises(RuntimeError, match="Chrome недоступен"):
        next(fixture)
    assert request.node.stash[conftest.LAST_STATE] == {
        "browser-launch-error": "RuntimeError: Chrome недоступен"
    }


def test_metadata_setup_error_still_quits_browser(monkeypatch, tmp_path):
    occupied = tmp_path / "not-a-directory"
    occupied.write_text("occupied", encoding="utf-8")
    browser = Mock(capabilities={"browserName": "chrome", "browserVersion": "test"})
    browser.command_executor.client_config.timeout = 45
    options = {
        "--browser": "chrome",
        "--headed": False,
        "allure_report_dir": str(occupied),
        "--no-screenshots": False,
    }
    request = SimpleNamespace(
        config=SimpleNamespace(getoption=lambda key: options[key]),
        node=SimpleNamespace(stash=pytest.Stash()),
    )
    monkeypatch.setattr(conftest, "create_browser", lambda *_: browser)
    monkeypatch.setattr(conftest, "snapshot", lambda _, **kwargs: {})
    monkeypatch.setattr(conftest.allure.dynamic, "parameter", lambda *_args, **_kwargs: None)
    fixture = conftest.driver.__wrapped__(request)
    with pytest.raises(FileExistsError):
        next(fixture)
    browser.quit.assert_called_once()
    assert request.node.stash[conftest.DRIVER] is None


def test_diagnostic_timeout_restored_even_after_failure():
    driver = SimpleNamespace(
        command_executor=SimpleNamespace(client_config=SimpleNamespace(timeout=45))
    )
    with pytest.raises(RuntimeError, match="original failure"):
        with command_timeout(driver, 2):
            assert driver.command_executor.client_config.timeout == 2
            raise RuntimeError("original failure")
    assert driver.command_executor.client_config.timeout == 45


def test_disabled_screenshot_keeps_text_evidence():
    browser = Mock(
        capabilities={"browserName": "chrome"},
        current_url="https://example.test/",
        page_source='<input type="password" value="secret">',
    )
    browser.command_executor.client_config.timeout = 45
    browser.get_log.return_value = []
    evidence = snapshot(browser, screenshots=False)
    browser.get_screenshot_as_png.assert_not_called()
    assert set(evidence) == {"url", "html", "capabilities", "console"}
    assert "secret" not in evidence["html"]
    assert browser.command_executor.client_config.timeout == 45
