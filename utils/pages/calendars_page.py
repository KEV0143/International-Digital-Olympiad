from datetime import date
from time import monotonic

import allure
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

from utils.components.jetpack_form import JetpackForm
from utils.pages.base_page import BasePage

MONTHS = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)


class CalendarsPage(BasePage):
    path = "/calendars/"
    input = ".entry-content input.date"
    invalid_date = "Please enter a valid date."

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.form = JetpackForm(self, ".entry-content [data-test='contact-form']")

    def open(self):
        super().open()
        self.form.wait_editable()
        return self

    def browser_today(self):
        parts = self.driver.execute_script(
            "const d=new Date();return [d.getFullYear(),d.getMonth()+1,d.getDate()]"
        )
        return date(*parts)

    def field_value(self):
        return self.value(self.input)

    @allure.step("Дождаться значения поля {value}")
    def wait_field_value(self, value):
        self.wait(lambda _: self.field_value() == value, f"Поле не получило значение {value}")

    def field_type(self):
        return self.visible(self.input).get_attribute("type")

    def field_label(self):
        field_id = self.visible(self.input).get_attribute("id")
        return self.text(f"label[for='{field_id}']")

    def format_hint(self):
        described_by = self.visible(self.input).get_attribute("aria-describedby") or ""
        hint_id = next(
            (reference for reference in described_by.split() if reference.endswith("-text-format")),
            None,
        )
        assert hint_id, "У поля даты нет ссылки на подсказку формата"
        return self.text(f"[id='{hint_id}']")

    def picker_is_open(self):
        return self.is_visible(".dp-cal")

    def displayed_month(self):
        return int(self.text(".dp-cal-year")), MONTHS.index(self.text(".dp-cal-month")) + 1

    def weekday_headers(self):
        return [
            element.text.upper()
            for element in self.driver.find_elements(By.CSS_SELECTOR, ".dp-col-header")
        ]

    def grid_day_count(self):
        return len(self.driver.find_elements(By.CSS_SELECTOR, ".dp-day"))

    def selected_day(self):
        return self.text(".dp-day.dp-selected")

    @allure.step("Проверить исходное состояние поля даты")
    def assert_initial_state(self):
        assert self.heading() == "Calendars"
        assert self.field_value() == ""
        assert self.field_type() == "text"
        assert not self.picker_is_open()
        assert self.field_label() == "Select or enter a date"
        assert self.format_hint() == "YYYY-MM-DD"

    @allure.step("Проверить текущий месяц, сетку и выделение сегодня")
    def assert_current_month(self, today):
        assert self.displayed_month() == (today.year, today.month)
        assert self.weekday_headers() == ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]
        assert self.grid_day_count() == 42
        today_cells = self.driver.find_elements(
            By.CSS_SELECTOR, ".dp-cal .dp-day-today:not(.dp-edge-day)"
        )
        selected_cells = self.driver.find_elements(
            By.CSS_SELECTOR, ".dp-cal .dp-day.dp-selected:not(.dp-edge-day)"
        )
        assert len(today_cells) == len(selected_cells) == 1
        assert today_cells[0] == selected_cells[0], "Сегодня и выбранная дата – разные ячейки"
        assert today_cells[0].text == str(today.day)

    @allure.step("Открыть календарь")
    def open_picker(self):
        self.click(self.input)
        stable_since = None

        def opened(_):
            nonlocal stable_since
            if not self.picker_is_open():
                stable_since = None
                self.press(self.input, Keys.ARROW_DOWN)
                return False
            stable_since = stable_since or monotonic()
            return monotonic() - stable_since >= 0.15

        self.wait(opened, "Календарь не завершил открытие после смены фокуса")

    @allure.step("Выбрать год {year} и месяц {month} через меню календаря")
    def choose_month(self, year, month):
        if not self.picker_is_open():
            self.open_picker()
        self.click(".dp-cal-year")
        self.click(f'.dp-year[data-year="{year}"]')
        self.click(".dp-cal-month")
        self.click(f'.dp-month[data-month="{month - 1}"]')
        self.wait(lambda _: self.displayed_month() == (year, month))

    @allure.step("Перейти на {direction} месяц")
    def shift_month(self, direction):
        assert direction in (-1, 1)
        year, month = self.displayed_month()
        serial = year * 12 + month - 1 + direction
        expected = (serial // 12, serial % 12 + 1)
        self.click(".dp-next" if direction == 1 else ".dp-prev")
        self.wait(lambda _: self.displayed_month() == expected)
        return expected

    @allure.step("Выбрать день {day} в отображаемом месяце")
    def choose_day(self, day):
        year, month = self.displayed_month()
        expected = date(year, month, day).isoformat()
        cells = self.driver.find_elements(By.CSS_SELECTOR, ".dp-day:not(.dp-edge-day)")
        target = next((cell for cell in cells if cell.text == str(day)), None)
        assert target is not None, f"День {day} отсутствует в сетке {year}-{month}"
        target.click()
        self.wait(lambda _: self.field_value() == expected)
        self.wait(lambda _: not self.picker_is_open())
        return expected

    @allure.step("Перейти к следующему дню стрелкой и подтвердить выбор")
    def choose_next_day_with_keyboard(self):
        self.press(".dp-cal", Keys.ARROW_RIGHT, Keys.SPACE)
        self.wait(lambda _: not self.picker_is_open())

    @allure.step("Ввести дату {value} в поле")
    def enter_date(self, value):
        self.fill(self.input, value)

    @allure.step("Закрыть календарь клавишей Escape")
    def close_picker_with_escape(self):
        self.press(".dp-cal", Keys.ESCAPE)
        self.wait(lambda _: not self.picker_is_open())

    @allure.step("Закрыть календарь кликом вне окна")
    def close_picker_outside(self):
        self.click("h1")
        self.wait(lambda _: not self.picker_is_open())

    def wait_until_valid(self):
        self.form.wait_valid("date")

    def form_is_editable(self):
        control = self.visible(self.input)
        return control.is_enabled() and not control.get_property("readOnly")

    @allure.step("Отправить дату и сверить сводку")
    def assert_submitted(self, expected):
        self.form.submit()
        assert self.form.summary() == {"Select or enter a date": expected}

    @allure.step("Отправить дату {value} и проверить ошибку")
    def assert_invalid(self, value):
        self.enter_date(value)
        self.form.submit()
        self.form.assert_error("date", self.invalid_date)
        assert self.field_value() == value
