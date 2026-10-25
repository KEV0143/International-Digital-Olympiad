from unittest.mock import Mock

import pytest
from selenium.common.exceptions import (
    InvalidSessionIdException,
    TimeoutException,
    WebDriverException,
)

from utils.components import jetpack_form
from utils.components.jetpack_form import JetpackForm
from utils.pages import base_page
from utils.pages.base_page import BasePage


class Field:
    def __init__(self, value):
        self.value = value

    def get_property(self, name):
        assert name == "value"
        return self.value


class Page:
    def __init__(self):
        self.value = ""
        self.fills = 0
        self.waits = 0

    def fill(self, css, value):
        self.fills += 1
        self.value = value

    def visible(self, css):
        return Field(self.value)

    def wait(self, condition, message):
        self.waits += 1
        if self.waits == 1:
            raise TimeoutException(message)
        assert condition(self)


def test_lost_form_input_is_retried_once(monkeypatch):
    attachment = Mock()
    monkeypatch.setattr(jetpack_form.allure, "attach", attachment)
    page = Page()
    JetpackForm(page, "#form").fill("email", "qa@example.com")
    assert page.fills == 2
    assert page.waits == 2
    attachment.assert_called_once()
    message = attachment.call_args.args[0]
    assert "Попытка: 1/2" in message and "Email" in message
    assert "TimeoutException" in message


def test_second_input_timeout_preserves_the_exception(monkeypatch):
    error = TimeoutException("input keeps disappearing")
    page = Page()
    page.wait = Mock(side_effect=error)
    attachment = Mock()
    monkeypatch.setattr(jetpack_form.allure, "attach", attachment)
    with pytest.raises(TimeoutException) as caught:
        JetpackForm(page, "#form").fill("name", "QA")
    assert caught.value is error
    assert page.fills == page.wait.call_count == 2
    attachment.assert_called_once()


@pytest.mark.parametrize(
    "error",
    [
        TimeoutException("navigation timeout"),
        WebDriverException(
            "Reached error page: about:neterror?e=dnsNotFound&u=https://example.test"
        ),
        WebDriverException("unknown error: net::ERR_NAME_NOT_RESOLVED"),
    ],
)
def test_temporary_navigation_failure_is_recorded_before_one_retry(monkeypatch, error):
    driver = Mock()
    driver.get.side_effect = [error, None]
    page = BasePage(driver, base_url="https://example.test")
    monkeypatch.setattr(page, "wait_ready", Mock())
    attachment = Mock()
    monkeypatch.setattr(base_page.allure, "attach", attachment)

    assert page.open() is page
    assert driver.get.call_count == 2
    page.wait_ready.assert_called_once()
    attachment.assert_called_once()
    assert error.msg in attachment.call_args.args[0]
    assert "https://example.test/" in attachment.call_args.args[0]


def test_persistent_dns_failure_stops_after_second_navigation(monkeypatch):
    error = WebDriverException("Reached error page: about:neterror?e=dnsNotFound")
    driver = Mock()
    driver.get.side_effect = error
    page = BasePage(driver)
    monkeypatch.setattr(page, "wait_ready", Mock())

    with pytest.raises(WebDriverException) as caught:
        page.open()
    assert caught.value is error
    assert driver.get.call_count == 2
    page.wait_ready.assert_not_called()


@pytest.mark.parametrize(
    "error",
    [
        InvalidSessionIdException("session closed"),
        WebDriverException("unexpected driver error"),
        WebDriverException(),
    ],
)
def test_other_driver_failures_are_not_retried(monkeypatch, error):
    driver = Mock()
    driver.get.side_effect = error
    page = BasePage(driver)
    monkeypatch.setattr(page, "wait_ready", Mock())

    with pytest.raises(WebDriverException) as caught:
        page.open()
    assert caught.value is error
    driver.get.assert_called_once()


@pytest.mark.parametrize("moving", [False, True])
def test_click_waits_for_stable_target_before_sending_native_click(monkeypatch, moving):
    driver = Mock()
    button = driver.find_element.return_value
    button.id = "submit"
    button.is_displayed.return_value = button.is_enabled.return_value = True
    now = [0.0]
    samples = []
    monkeypatch.setattr(base_page, "monotonic", lambda: now[0])

    def execute(script, element):
        if script.startswith("arguments[0].scrollIntoView"):
            return None
        return [10, 30 if moving and now[0] >= 0.1 else 20, 100, 50]

    driver.execute_script.side_effect = execute
    page = BasePage(driver)

    def wait(condition, message):
        for instant in (0.0, 0.1, 0.21, 0.31):
            now[0] = instant
            if condition(driver):
                samples.append(instant)
                return
            button.click.assert_not_called()
        raise AssertionError(message)

    page.wait = wait
    page.click("button", stable_for=0.2)
    assert samples == ([0.31] if moving else [0.21])
    button.click.assert_called_once()


@pytest.mark.parametrize("visible", [False, True])
def test_submission_error_is_reported_before_its_message_disappears(visible):
    page = Mock()
    error = Mock(text="Request rejected by server")
    error.is_displayed.return_value = visible
    page.driver.find_elements.return_value = [error]
    page.wait.side_effect = lambda condition, message: condition(page.driver)
    form = JetpackForm(page, "#form")
    form.success_visible = lambda: True
    if visible:
        with pytest.raises(AssertionError, match="Request rejected by server"):
            form.summary()
        page.text.assert_not_called()
    else:
        page.text.return_value = "Thank you for your response."
        page.driver.find_elements.side_effect = [[error], [], []]
        assert form.summary() == {}
