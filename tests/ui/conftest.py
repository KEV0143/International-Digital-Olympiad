import pytest

from utils.pages.ads_page import AdsPage
from utils.pages.calendars_page import CalendarsPage
from utils.pages.form_fields_page import FormFieldsPage
from utils.pages.modals_page import ModalsPage


@pytest.fixture
def calendar(driver, page_options):
    return CalendarsPage(driver, **page_options).open()


@pytest.fixture
def modals(driver, page_options):
    return ModalsPage(driver, **page_options).open()


@pytest.fixture
def ads(driver, page_options):
    return AdsPage(driver, **page_options).open()


@pytest.fixture
def fields(driver, page_options):
    return FormFieldsPage(driver, **page_options).open()
