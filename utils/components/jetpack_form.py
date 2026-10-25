import allure
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By


class JetpackForm:
    FIELD_LABELS = {"name": "Name", "email": "Email", "textarea": "Message", "date": "Дата"}

    def __init__(self, page, root):
        self.page, self.root = page, root

    def field(self, kind):
        return f"{self.root} .grunion-field.{kind}"

    def fill(self, kind, value):
        css = self.field(kind)
        label = self.FIELD_LABELS.get(kind, kind)
        with allure.step(f"Заполнить поле {label}"):
            for attempt in (1, 2):
                try:
                    self.page.fill(css, value)
                    self.page.wait(
                        lambda _: self.page.visible(css).get_property("value") == value,
                        f"Форма не сохранила ввод в поле {label}",
                    )
                except TimeoutException as error:
                    if attempt == 2:
                        raise
                    allure.attach(
                        f"Поле: {label}\nПопытка: {attempt}/2\n{type(error).__name__}: {error.msg}",
                        "Причина повторного ввода",
                        allure.attachment_type.TEXT,
                    )
                else:
                    break

    @allure.step("Дождаться готовности формы")
    def wait_editable(self):
        self.page.visible(f"{self.root} form.is-ajax-form:not(.submission-success)")
        self.page.wait(
            lambda _: not self.success_visible(),
            "Форма ещё не вернулась из состояния успешной отправки",
        )
        return self

    def error_id(self, kind):
        described_by = self.page.visible(self.field(kind)).get_attribute("aria-describedby") or ""
        return next(
            (value for value in described_by.split() if value.endswith("error-message")), None
        )

    def error_text(self, kind):
        error_id = self.error_id(kind)
        if not error_id:
            return ""
        elements = self.page.driver.find_elements(By.ID, error_id)
        return elements[0].text.strip() if elements and elements[0].is_displayed() else ""

    def wait_valid(self, kind):
        label = self.FIELD_LABELS.get(kind, kind)
        with allure.step(f"Дождаться снятия ошибки поля {label}"):
            self.page.wait(
                lambda _: (
                    self.page.visible(self.field(kind)).get_attribute("aria-invalid") != "true"
                    and not self.error_text(kind)
                ),
                f"Ошибка поля {label} не исчезла после исправления",
            )

    @allure.step("Отправить форму через кнопку Submit")
    def submit(self):
        self.page.click(f"{self.root} form button[type=submit]", stable_for=0.2)

    def success_visible(self):
        return self.page.is_visible(f"{self.root} .contact-form-submission.submission-success")

    @allure.step("Прочитать сводку отправленной формы")
    def summary(self):
        def submitted(_):
            errors = self.page.driver.find_elements(
                By.CSS_SELECTOR,
                f"{self.root} .contact-form__error[data-wp-text='context.submissionError']",
            )
            messages = [element.text.strip() for element in errors if element.is_displayed()]
            assert not any(messages), f"Сайт отклонил отправку: {'; '.join(messages)}"
            return self.success_visible()

        self.page.wait(submitted, "Нет подтверждения отправки")
        response = f"{self.root} .contact-form-submission.submission-success"
        assert self.page.text(f"{response} h4").startswith("Thank you for your response.")
        names = self.page.driver.find_elements(By.CSS_SELECTOR, f"{response} .field-name")
        values = self.page.driver.find_elements(By.CSS_SELECTOR, f"{response} .field-value")
        assert len(names) == len(values), "Неоднозначная структура сводки отправки"
        return {
            name.text.strip().rstrip(":"): value.text
            for name, value in zip(names, values, strict=True)
        }

    @allure.step("Проверить сообщение «{expected}» и отсутствие отправки")
    def assert_error(self, kind, expected):
        error_id = self.error_id(kind)
        assert error_id, f"У поля {kind} нет ссылки на сообщение об ошибке"
        self.page.wait(
            lambda d: (
                d.find_element(By.ID, error_id).is_displayed()
                and d.find_element(By.ID, error_id).text.strip() == expected
            ),
            f"Нет ожидаемой ошибки {expected!r}",
        )
        assert self.page.visible(self.field(kind)).get_attribute("aria-invalid") == "true"
        assert not self.success_visible(), "При ошибке показано подтверждение отправки"

    @allure.step("Проверить общее сообщение об ошибке формы")
    def assert_form_error(self):
        assert (
            self.page.text(
                f"{self.root} .contact-form__error.show-errors .contact-form__error-message"
            )
            == "Please fill out the form correctly."
        )

    @allure.step("Проверить сохранённые значения полей")
    def assert_values(self, expected):
        self.page.assert_for(
            lambda: {kind: self.page.value(self.field(kind)) for kind in expected} == expected,
            1.2,
            "Значения формы отличаются от ожидаемых",
        )

    @allure.step("Вернуться из сводки к форме")
    def back(self):
        self.page.click(f"{self.root} .contact-form-submission .go-back-message a")
        self.wait_editable()
