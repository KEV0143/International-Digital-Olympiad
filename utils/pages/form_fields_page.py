import allure
from selenium.common.exceptions import NoAlertPresentException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select

from utils.pages.base_page import BasePage


class FormFieldsPage(BasePage):
    path = "/form-fields/"
    NAME = "[data-testid='name-input']"
    PASSWORD_LABEL_XPATH = "//label[contains(normalize-space(), 'Password')]/input"
    EMAIL = "[data-testid='email']"
    MESSAGE = "[data-testid='message']"
    AUTOMATION = "#automation"
    SUBMIT = "[data-testid='submit-btn']"
    DRINKS = {
        "Water": "[data-testid='drink1']",
        "Milk": "[data-testid='drink2']",
        "Coffee": "[data-testid='drink3']",
        "Wine": "[data-testid='drink4']",
        "Ctrl-Alt-Delight": "[data-testid='drink5']",
    }
    COLORS = {
        "Red": "[data-testid='color1']",
        "Blue": "[data-testid='color2']",
        "Yellow": "[data-testid='color3']",
        "Green": "[data-testid='color4']",
        "#FFC0CB": "[data-testid='color5']",
    }

    @allure.step("Прочитать список Automation Tools")
    def automation_tools(self):
        elements = self.driver.find_elements(
            By.XPATH,
            "//label[normalize-space()='Automation tools']/following-sibling::ul[1]/li",
        )
        assert elements, "Не найден список Automation tools"
        values = [element.text.strip() for element in elements]
        assert all(values) and len(values) == len(set(values)), (
            "Пустые или повторяющиеся инструменты"
        )
        allure.attach("\n".join(values), "Automation tools из DOM", allure.attachment_type.TEXT)
        return values

    @allure.step("Заполнить Message названиями инструментов через запятую")
    def tools_to_message(self):
        message = ", ".join(self.automation_tools())
        self.fill(self.MESSAGE, message)
        assert self.message_value() == message
        return message

    def name_value(self):
        return self.value(self.NAME)

    def password_field(self):
        return self.wait(
            EC.visibility_of_element_located((By.XPATH, self.PASSWORD_LABEL_XPATH)),
            "Поле Password не найдено по его подписи",
        )

    def password_value(self):
        return self.password_field().get_property("value")

    def password_type(self):
        return self.password_field().get_attribute("type")

    def email_value(self):
        return self.value(self.EMAIL)

    def message_value(self):
        return self.value(self.MESSAGE)

    def form_values(self):
        return {
            "name": self.name_value(),
            "password": self.password_value(),
            "email": self.email_value(),
            "message": self.message_value(),
            "automation": self.value(self.AUTOMATION),
        }

    @allure.step("Ввести имя")
    def fill_name(self, value):
        self.fill(self.NAME, value)

    @allure.step("Ввести пароль")
    def fill_password(self, value):
        self.fill_element(self.password_field(), value)

    @allure.step("Ввести сообщение")
    def fill_message(self, value):
        self.fill(self.MESSAGE, value)

    @allure.step("Выбрать напиток {name}")
    def toggle_drink(self, name):
        self.click(self.DRINKS[name])

    def selected_drinks(self):
        return [name for name, css in self.DRINKS.items() if self.visible(css).is_selected()]

    @allure.step("Выбрать цвет {name}")
    def choose_color(self, name):
        self.click(self.COLORS[name])

    def selected_colors(self):
        return [name for name, css in self.COLORS.items() if self.visible(css).is_selected()]

    @allure.step("Выбрать в списке автоматизации «{text}»")
    def choose_preference(self, text):
        Select(self.visible(self.AUTOMATION)).select_by_visible_text(text)

    def preference_options(self):
        return [option.text for option in Select(self.visible(self.AUTOMATION)).options]

    def preference_value(self):
        return self.value(self.AUTOMATION)

    def preference_text(self):
        return Select(self.visible(self.AUTOMATION)).first_selected_option.text

    @allure.step("Заполнить форму допустимыми данными")
    def fill_valid_form(self, name="Volga QA"):
        self.fill_name(name)
        self.fill_password("Demo-password-42!")
        self.toggle_drink("Water")
        self.toggle_drink("Coffee")
        self.choose_color("Blue")
        self.choose_preference("Yes")
        self.fill(self.EMAIL, "qa@example.com")
        return self.tools_to_message()

    @allure.step("Сверить введённые значения")
    def assert_saved_values(self, expected):
        assert self.form_values() == expected

    @allure.step("Проверить, что после отправки форма очищена")
    def assert_form_reset(self):
        assert self.form_values() == {
            "name": "",
            "password": "",
            "email": "",
            "message": "",
            "automation": "",
        }
        assert self.selected_drinks() == []
        assert self.selected_colors() == []

    @allure.step("Проверить, что браузер требует заполнить Name")
    def assert_name_required_by_browser(self):
        control = self.visible(self.NAME)
        assert control.get_property("validity")["valueMissing"]
        assert control.get_property("validationMessage")

    def alert_is_present(self):
        try:
            _ = self.driver.switch_to.alert
            return True
        except NoAlertPresentException:
            return False

    @allure.step("Убедиться, что форма не отправилась")
    def assert_no_alert(self, seconds=1.2):
        self.assert_for(
            lambda: not self.alert_is_present(),
            seconds,
            "Форма с пустым именем показала успешный alert",
        )

    @allure.step("Отправить форму кнопкой Submit")
    def submit(self):
        self.click(self.SUBMIT)

    @allure.step("Подтвердить alert Message received!")
    def received_alert(self):
        alert = self.wait(EC.alert_is_present(), "Нет подтверждения отправки")
        assert alert.text == "Message received!"
        alert.accept()
