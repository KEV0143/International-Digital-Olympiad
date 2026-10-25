import allure
from selenium.webdriver import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys


class Popup:
    def __init__(self, page, popup_id):
        self.page, self.css = page, f"#pum-{popup_id}"

    def active(self):
        return self.page.driver.execute_script(
            "const p=document.querySelector(arguments[0]);"
            "return !!p && p.classList.contains('pum-active');",
            self.css,
        )

    def closed(self):
        return not self.active() and not self.page.is_visible(f"{self.css} .pum-container")

    def title(self):
        return self.page.text(f"{self.css} .pum-title")

    def content(self):
        return self.page.text(f"{self.css} .pum-content")

    def dialog_role(self):
        return self.page.visible(self.css).get_attribute("role")

    def labelled_title(self):
        title_id = self.page.visible(self.css).get_attribute("aria-labelledby")
        return self.page.text(f"[id='{title_id}']") if title_id else None

    def close_button(self):
        return self.page.visible(f"{self.css} button.pum-close")

    def close_button_is_accessible(self):
        button = self.close_button()
        return button.is_enabled() and bool(button.accessible_name)

    @allure.step("Дождаться открытия окна")
    def wait_open(self, timeout=None):
        self.page.wait(lambda _: self.active(), f"Окно {self.css} не открылось", timeout=timeout)
        self.page.wait(
            lambda d: d.execute_script(
                "const p=document.querySelector(arguments[0]);"
                "if(!p)return false;"
                "const c=p.querySelector('.pum-container');"
                "if(!c)return false;"
                "const r=c.getBoundingClientRect();"
                "return getComputedStyle(p).opacity==='1' && getComputedStyle(c).opacity==='1'"
                "&&r.x>=0&&r.y>=0&&r.right<=innerWidth&&r.top<innerHeight;",
                self.css,
            ),
            "Анимация окна не завершилась",
            timeout=timeout,
        )
        self.page.visible(f"{self.css} .pum-content")
        return self

    def wait_closed(self):
        self.page.wait(
            lambda d: d.execute_script(
                "const p=document.querySelector(arguments[0]);"
                "return !!p && !p.classList.contains('pum-active')"
                "&& getComputedStyle(p).display==='none';",
                self.css,
            ),
            "Overlay ещё перехватывает клики после скрытия карточки",
        )
        assert not self.page.is_visible(f"{self.css} .pum-container")

    @allure.step("Закрыть окно крестиком")
    def close(self):
        self.page.click(f"{self.css} button.pum-close")
        self.wait_closed()

    @allure.step("Нажать Escape")
    def escape(self):
        ActionChains(self.page.driver).send_keys(Keys.ESCAPE).perform()

    @allure.step("Нажать на затемнённую область вне окна")
    def click_outside(self):
        overlay = self.page.driver.find_element(By.CSS_SELECTOR, self.css)
        geometry = self.page.driver.execute_script(
            "const p=arguments[0],c=p.querySelector('.pum-container');"
            "if(!c)return null;"
            "const r=p.getBoundingClientRect(),cr=c.getBoundingClientRect();"
            "const points=[[8,8],[innerWidth-8,8],[8,innerHeight-8],"
            "[innerWidth-8,innerHeight-8],[cr.left-8,cr.top+cr.height/2],"
            "[cr.right+8,cr.top+cr.height/2]];"
            "for(const [x,y] of points){"
            "if(x<0||y<0||x>=innerWidth||y>=innerHeight)continue;"
            "const hit=document.elementFromPoint(x,y);"
            "if(hit&&(hit===p||p.contains(hit))&&!c.contains(hit))"
            "return {x:x-(r.left+r.width/2),y:y-(r.top+r.height/2),point:[x,y]};}"
            "return null;",
            overlay,
        )
        assert geometry, "Не найдена свободная точка подложки вне окна"
        ActionChains(self.page.driver).move_to_element_with_offset(
            overlay, round(geometry["x"]), round(geometry["y"])
        ).click().perform()

    @allure.step("Кликнуть по тексту окна")
    def click_content(self):
        self.page.click(f"{self.css} .pum-content")

    def assert_stays_open(self, seconds=1.2):
        self.page.assert_for(
            lambda: self.active() and self.page.is_visible(f"{self.css} .pum-content"),
            seconds,
            f"Окно {self.css} неожиданно закрылось",
        )
