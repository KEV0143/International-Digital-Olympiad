import allure
from selenium.webdriver.common.keys import Keys

from utils.components.jetpack_form import JetpackForm
from utils.components.popup import Popup
from utils.pages.base_page import BasePage


class ModalsPage(BasePage):
    path = "/modals/"
    NAME_ERROR = "This field is required."
    EMAIL_ERROR = "Please enter a valid email address"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.simple = Popup(self, 1318)
        self.modal = Popup(self, 674)
        self.form = JetpackForm(self, "#pum-674 [data-test='contact-form']")

    @allure.step("Открыть Simple Modal")
    def open_simple(self):
        self.click("#simpleModal")
        self.simple.wait_open()
        return self.simple

    @allure.step("Открыть Simple Modal клавишей Enter")
    def open_simple_with_enter(self):
        self.press("#simpleModal", Keys.ENTER)
        self.simple.wait_open()

    @allure.step("Открыть Form Modal")
    def open_form(self):
        self.click("#formModal")
        self.modal.wait_open()
        self.form.wait_editable()
        return self.form

    def simple_title(self):
        return self.simple.title()

    def simple_text(self):
        return self.simple.content()

    def simple_is_open(self):
        return self.simple.active()

    def form_title(self):
        return self.modal.title()

    def form_is_open(self):
        return self.modal.active()

    def form_trigger_enabled(self):
        return self.visible("#formModal").is_enabled()

    def name_is_required(self):
        return self.visible(self.form.field("name")).get_attribute("aria-required") == "true"

    def name_is_enabled(self):
        return self.visible(self.form.field("name")).is_enabled()

    def name_value(self):
        return self.value(self.form.field("name"))

    @allure.step("Заполнить поля Name, Email и Message")
    def fill_form(self, name, email="", message=""):
        self.form.fill("name", name)
        self.form.fill("email", email)
        self.form.fill("textarea", message)

    @allure.step("Отправить форму и сверить сводку")
    def assert_submitted(self, name, email="", message=""):
        self.form.submit()
        assert self.form.summary() == {"Name": name, "Email": email, "Message": message}
        assert self.modal.active(), "Форма не должна автоматически закрывать окно"

    @allure.step("Отправить форму без имени и проверить ошибку")
    def assert_name_missing(self):
        self.form.submit()
        self.form.assert_error("name", self.NAME_ERROR)
        self.form.assert_form_error()

    @allure.step("Отправить форму с неверным email и проверить ошибку")
    def assert_email_invalid(self):
        self.form.submit()
        self.form.assert_error("email", self.EMAIL_ERROR)
        self.form.assert_form_error()
        assert self.visible(self.form.field("email")).get_property("validity")["typeMismatch"]
