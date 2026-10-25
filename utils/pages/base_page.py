from time import monotonic

import allure
from selenium.common.exceptions import (
    ElementClickInterceptedException,
    NoSuchElementException,
    StaleElementReferenceException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


class BasePage:
    path = "/"

    def __init__(self, driver, base_url="https://practice-automation.com", timeout=15.0):
        self.driver = driver
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def wait(self, condition, message="", timeout=None):
        return WebDriverWait(
            self.driver,
            self.timeout if timeout is None else timeout,
            poll_frequency=0.1,
            ignored_exceptions=(NoSuchElementException, StaleElementReferenceException),
        ).until(condition, message)

    @allure.step("Открыть страницу и дождаться загрузки")
    def open(self):
        for attempt in (1, 2):
            try:
                self.driver.get(self.base_url + self.path)
                self.wait_ready()
            except WebDriverException as error:
                dns_error = any(
                    marker in (error.msg or "")
                    for marker in ("about:neterror?e=dnsNotFound", "net::ERR_NAME_NOT_RESOLVED")
                )
                if attempt == 2 or not (isinstance(error, TimeoutException) or dns_error):
                    raise
                allure.attach(
                    f"Первая попытка открытия {self.base_url + self.path}:\n{error}",
                    "Причина повторного открытия страницы",
                    allure.attachment_type.TEXT,
                )
            else:
                return self

    def wait_ready(self):
        self.wait(
            lambda d: d.execute_script(
                "return document.readyState !== 'loading' && !!window.jQuery && jQuery.isReady"
            ),
            "DOM и обработчики страницы ещё не готовы",
        )
        self.visible("h1")

    def heading(self):
        return self.text("h1")

    def press(self, css, *keys):
        self.visible(css).send_keys(*keys)

    def visible(self, css):
        return self.wait(EC.visibility_of_element_located((By.CSS_SELECTOR, css)), css)

    def is_visible(self, css):
        return any(
            element.is_displayed() for element in self.driver.find_elements(By.CSS_SELECTOR, css)
        )

    def value(self, css):
        return self.visible(css).get_property("value")

    def text(self, css):
        return self.visible(css).text.strip()

    def fill(self, css, value):
        self.fill_element(self.visible(css), value)

    def fill_element(self, element, value):
        platform = self.driver.capabilities.get("platformName", "").lower()
        select_all = Keys.COMMAND if "mac" in platform else Keys.CONTROL
        element.send_keys(select_all, "a")
        element.send_keys(Keys.BACKSPACE)
        if value:
            element.send_keys(value)
        element.send_keys(Keys.TAB)

    def click(self, css, *, stable_for=0.0):
        previous, stable_since = None, None

        def click_when_ready(_):
            nonlocal previous, stable_since
            element = self.driver.find_element(By.CSS_SELECTOR, css)
            if not element.is_displayed() or not element.is_enabled():
                previous, stable_since = None, None
                return False
            self.driver.execute_script(
                "arguments[0].scrollIntoView({block:'center',behavior:'instant'});", element
            )
            rectangle = self.driver.execute_script(
                "const e=arguments[0],r=e.getBoundingClientRect();"
                "const hit=document.elementFromPoint(r.x+r.width/2,r.y+r.height/2);"
                "return hit===e||e.contains(hit) ? [r.x,r.y,r.width,r.height] : null;",
                element,
            )
            if not rectangle:
                previous, stable_since = None, None
                return False
            if stable_for:
                geometry = (element.id, *(round(value, 1) for value in rectangle))
                now = monotonic()
                if previous != geometry:
                    previous, stable_since = geometry, now
                    return False
                if now - stable_since < stable_for:
                    return False
            try:
                element.click()
                return True
            except ElementClickInterceptedException:
                previous, stable_since = None, None
                return False

        self.wait(click_when_ready, f"Элемент перекрыт или не готов к клику: {css}")

    @allure.step("Проверить сохранение состояния в течение {seconds} с")
    def assert_for(self, condition, seconds, message):
        deadline = monotonic() + seconds

        def sample(_):
            assert condition(), message
            return monotonic() >= deadline

        self.wait(sample, message, timeout=seconds + self.timeout)
