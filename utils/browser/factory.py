import os

from selenium import webdriver

from utils.browser.transport import command_timeout


def create_browser(name: str, headed: bool):
    options = webdriver.ChromeOptions() if name == "chrome" else webdriver.FirefoxOptions()
    options.unhandled_prompt_behavior = "ignore"
    options.page_load_strategy = "eager"
    if name == "firefox":
        options.enable_bidi = True
    if not headed:
        options.add_argument("--headless=new" if name == "chrome" else "-headless")
    binary = os.getenv(f"{name.upper()}_BINARY")
    if binary:
        options.binary_location = binary
    if name == "chrome":
        options.set_capability("goog:loggingPrefs", {"browser": "ALL"})
    driver = (webdriver.Chrome if name == "chrome" else webdriver.Firefox)(options=options)
    try:
        driver.command_executor.client_config.timeout = 45
        driver.implicitly_wait(0)
        driver.set_page_load_timeout(40)
        driver.set_script_timeout(20)
        driver.set_window_size(1440, 1100)
    except Exception:
        try:
            with command_timeout(driver, 5):
                driver.quit()
        except Exception:
            pass
        raise
    return driver
