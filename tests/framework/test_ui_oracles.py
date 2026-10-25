from datetime import date
from unittest.mock import Mock

import pytest
from selenium.common.exceptions import ElementClickInterceptedException

from tests.ui import test_ads, test_calendars, test_form_fields
from utils.pages.ads_page import AdsPage
from utils.pages.calendars_page import CalendarsPage
from utils.pages.form_fields_page import FormFieldsPage


def test_submit_scenario_rejects_missing_drink_selection():
    fields = Mock(spec=FormFieldsPage)
    fields.selected_drinks.return_value = []
    with pytest.raises(AssertionError):
        test_form_fields.test_successful_submit_clears_form(fields)
    fields.submit.assert_not_called()


@pytest.mark.parametrize("cleared", ["password", "automation"])
def test_empty_name_scenario_detects_cleared_optional_values(cleared):
    page = object.__new__(FormFieldsPage)
    page.fill_valid_form = Mock(return_value="tools")
    page.submit = Mock()
    page.assert_name_required_by_browser = Mock()
    page.assert_no_alert = Mock()
    values = {
        "name": "",
        "password": "Demo-password-42!",
        "email": "qa@example.com",
        "message": "tools",
        "automation": "yes",
    }
    values[cleared] = ""
    page.form_values = lambda: values
    with pytest.raises(AssertionError):
        test_form_fields.test_empty_name_stops_submission(page)


def test_ad_delay_scenario_detects_a_later_reopening():
    page = Mock()
    trace = {"installed": 0, "readyAt": 100, "transitions": [{"active": True, "at": 5100}]}
    page.trace.side_effect = lambda: trace

    def reopen(seconds):
        if seconds >= 7:
            trace["transitions"].extend(
                [{"active": False, "at": 7000}, {"active": True, "at": 8000}]
            )

    page.ad.assert_stays_open = Mock(side_effect=reopen)
    with pytest.raises(AssertionError):
        test_ads.test_ad_appears_once_after_delay(page)


@pytest.mark.parametrize("activation_at", [10, 2000])
def test_ad_delay_scenario_rejects_activation_before_lower_bound(activation_at):
    page = Mock()
    page.ad.assert_stays_open = Mock()
    page.trace.return_value = {
        "installed": 0,
        "readyAt": 100,
        "transitions": [{"active": True, "at": activation_at}],
    }
    with pytest.raises(AssertionError, match="вне допуска"):
        test_ads.test_ad_appears_once_after_delay(page)


def test_next_month_scenario_rejects_wrong_initial_month():
    page = Mock()
    page.browser_today.return_value = date(2026, 10, 24)
    page.displayed_month.return_value = (2020, 1)
    with pytest.raises(AssertionError):
        test_calendars.test_pick_date_in_next_month(page)
    page.shift_month.assert_not_called()


def test_today_and_selection_must_be_the_same_calendar_cell():
    page = object.__new__(CalendarsPage)
    page.displayed_month = lambda: (2026, 10)
    page.weekday_headers = lambda: ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]
    page.grid_day_count = lambda: 42
    page.driver = Mock()
    page.driver.find_elements.side_effect = [[Mock(text="24")], [Mock(text="24")]]
    with pytest.raises(AssertionError, match="разные ячейки"):
        page.assert_current_month(date(2026, 10, 24))


def test_readonly_calendar_field_is_not_editable():
    page = object.__new__(CalendarsPage)
    field = Mock()
    field.is_enabled.return_value = True
    field.get_property.return_value = True
    page.visible = lambda _: field
    assert not page.form_is_editable()


@pytest.mark.parametrize("ad_intercepts", [False, True])
def test_background_click_requires_the_ad_to_be_the_interceptor(ad_intercepts):
    page = AdsPage(Mock())
    page.driver.current_url = "https://practice-automation.com/ads/"
    page.driver.execute_script.return_value = ad_intercepts
    link = Mock()
    link.click.side_effect = ElementClickInterceptedException("intercepted")
    page.home_link = lambda: link
    if ad_intercepts:
        page.assert_home_link_blocked()
    else:
        with pytest.raises(AssertionError, match="вне рекламного окна"):
            page.assert_home_link_blocked()


def test_a_smaller_unchanged_viewport_does_not_satisfy_resize():
    page = AdsPage(Mock())
    page.driver.get_window_size.return_value = {"width": 800, "height": 700}
    page.driver.execute_script.return_value = [600, 400]

    def check(condition, message):
        assert condition(page.driver), message

    page.wait = check
    with pytest.raises(AssertionError, match="не получил размер"):
        page.set_viewport(800, 700)
