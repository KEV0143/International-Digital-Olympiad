import json
from urllib.parse import urlsplit

import allure
from selenium.common.exceptions import ElementClickInterceptedException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC

from utils.components.popup import Popup
from utils.pages.base_page import BasePage


class AdsPage(BasePage):
    path = "/ads/"
    TRACE_JS = (
        "() => {"
        "if (window !== window.top) return;"
        "const trace = {installed: performance.now(), installedState: document.readyState,"
        "readyAt: null, transitions: []};"
        "window.__qaPopupTrace = trace;"
        "document.addEventListener('DOMContentLoaded', () => {"
        "trace.readyAt = performance.now();}, {once:true});"
        "let previous = false;"
        "const record = active => {if (active !== previous) {"
        "trace.transitions.push({active, at:performance.now()}); previous = active;}};"
        "new MutationObserver(records => {"
        "for (let i=0; i<records.length; i++) {"
        "const change = records[i];"
        "if (change.type === 'attributes' && change.target.id === 'pum-1272') {"
        "const next = records.slice(i+1).find(r=>r.type==='attributes' && "
        "r.target===change.target && r.attributeName==='class');"
        "const classes = next ? next.oldValue : change.target.getAttribute('class');"
        "record((classes || '').split(/\\s+/).includes('pum-active'));"
        "}"
        "}"
        "const popup = document.getElementById('pum-1272');"
        "record(!!popup && popup.classList.contains('pum-active'));"
        "}).observe(document, {subtree:true, childList:true, attributes:true,"
        "attributeOldValue:true, attributeFilter:['class']});"
        "}"
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ad = Popup(self, 1272)
        self._trace_registered = False

    def open(self):
        self.install_trace()
        return super().open()

    @allure.step("Установить наблюдатель рекламы до выполнения скриптов страницы")
    def install_trace(self):
        if self._trace_registered:
            return
        if self.driver.capabilities["browserName"] == "firefox":
            self.driver.script.add_preload_script(function_declaration=self.TRACE_JS)
        else:
            self.driver.execute_cdp_cmd(
                "Page.addScriptToEvaluateOnNewDocument", {"source": f"({self.TRACE_JS})()"}
            )
        self._trace_registered = True

    @allure.step("Дождаться появления рекламы")
    def ready_ad(self):
        self.ad.wait_open(timeout=self.timeout * 2)
        return self.ad

    @allure.step("Измерить задержку появления рекламы")
    def trace(self):
        trace = self.driver.execute_script("return window.__qaPopupTrace")
        assert trace and trace["installedState"] == "loading", (
            "Наблюдатель не установлен в начале документа"
        )
        assert trace["readyAt"] is not None, "Не зафиксирован DOMContentLoaded"
        allure.attach(json.dumps(trace, indent=2), "Popup timing", allure.attachment_type.JSON)
        return trace

    def ad_title(self):
        return self.ad.title()

    def ad_text(self):
        return self.ad.content()

    def ad_dialog_role(self):
        return self.ad.dialog_role()

    def ad_labelled_title(self):
        return self.ad.labelled_title()

    def ad_close_is_accessible(self):
        return self.ad.close_button_is_accessible()

    def ad_is_closed(self):
        return self.ad.closed()

    def ad_is_the_only_active_popup(self):
        return self.active_popups() == [self.ad.css.lstrip("#")]

    def other_popups_are_hidden(self):
        return not any(
            self.is_visible(f"#pum-{popup_id} .pum-container") for popup_id in (674, 1318)
        )

    def active_popups(self):
        return self.driver.execute_script(
            "return [...document.querySelectorAll('.pum-active')].map(e=>e.id).sort()"
        )

    @allure.step("Нажать Enter на кнопке закрытия")
    def close_ad_with_enter(self):
        self.ad.close_button().send_keys(Keys.ENTER)
        self.ad.wait_closed()

    @allure.step("Кликнуть по тексту рекламы")
    def click_ad_content(self):
        self.ad.click_content()

    @allure.step("Перейти на главную по ссылке Home")
    def go_home(self):
        self.home_link().click()
        self.wait(lambda d: urlsplit(d.current_url).path == "/")
        assert urlsplit(self.driver.current_url).netloc == urlsplit(self.base_url).netloc

    @allure.step("Проверить, что реклама блокирует ссылку Home")
    def assert_home_link_blocked(self):
        before = self.driver.current_url
        link = self.home_link()
        try:
            link.click()
        except ElementClickInterceptedException:
            blocked_by_ad = self.driver.execute_script(
                "const r=arguments[0].getBoundingClientRect();"
                "const x=(Math.max(0,r.left)+Math.min(innerWidth,r.right))/2;"
                "const y=(Math.max(0,r.top)+Math.min(innerHeight,r.bottom))/2;"
                "const hit=document.elementFromPoint(x,y),ad=document.querySelector(arguments[1]);"
                "return !!(ad&&hit&&ad.contains(hit));",
                link,
                self.ad.css,
            )
            assert blocked_by_ad, "Клик перехвачен элементом вне рекламного окна"
        else:
            raise AssertionError("Ссылка Home открылась под рекламным окном")
        assert self.driver.current_url == before, "URL изменился после перехвата клика рекламой"

    def home_link(self):
        return self.wait(
            EC.visibility_of_element_located((By.LINK_TEXT, "Home")),
            "На странице нет ссылки Home",
        )

    @allure.step("Изменить вьюпорт на {width}×{height}")
    def set_viewport(self, width, height):
        window = self.driver.get_window_size()
        actual = self.driver.execute_script("return [window.innerWidth, window.innerHeight]")
        self.driver.set_window_size(
            window["width"] + width - actual[0], window["height"] + height - actual[1]
        )
        self.wait(
            lambda d: (
                d.execute_script("return [window.innerWidth, window.innerHeight]")
                == [width, height]
            ),
            f"Вьюпорт не получил размер {width}×{height}",
        )

    @allure.step("Проверить, что реклама помещается в окно браузера")
    def ad_is_inside_viewport(self):
        return self.driver.execute_script(
            "const p=document.querySelector(arguments[0]);"
            "return ['.pum-container','.pum-content','.pum-close'].every(s=>{"
            "const e=p.querySelector(s),r=e.getBoundingClientRect();"
            "return r.left>=0&&r.top>=0&&r.right<=innerWidth&&r.bottom<=innerHeight;});",
            self.ad.css,
        )

    @allure.step("Перезагрузить страницу")
    def reload(self):
        self.driver.refresh()
        self.wait_ready()

    @allure.step("Прочитать пояснение о задержке рекламы")
    def delay_notice(self):
        return self.wait(
            EC.visibility_of_element_located(
                (By.XPATH, "//p[contains(normalize-space(.), 'An ad will appear')]")
            ),
            "Нет пояснения о задержке рекламы",
        ).text.strip()

    @allure.step("Прочитать предупреждение об адблокерах")
    def ad_blocker_warning(self):
        return self.wait(
            EC.visibility_of_element_located(
                (By.XPATH, "//p[contains(normalize-space(.), 'ad blockers are turned off')]")
            ),
            "Нет предупреждения об адблокерах",
        ).text.strip()

    @allure.step("Проверить ссылку на обучающее видео")
    def tutorial_link(self):
        link = self.wait(
            EC.visibility_of_element_located(
                (By.LINK_TEXT, "how to handle ads in test automation")
            ),
            "Нет ссылки на обучающее видео",
        )
        return {"href": link.get_attribute("href"), "target": link.get_attribute("target")}
