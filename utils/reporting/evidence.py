import json
from html import escape
from html.parser import HTMLParser

import allure

from utils.browser.transport import command_timeout
from utils.reporting.redaction import private_key, redact, redact_text, redact_url


def redact_html(source):
    offsets = [0]
    for line in source.split("\n"):
        offsets.append(offsets[-1] + len(line) + 1)

    class Redactor(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=False)
            self.replacements = []
            self.private_text_start = None

        def handle_starttag(self, tag, attrs):
            if self.private_text_start is not None:
                return
            properties = dict(attrs)
            sensitive = (properties.get("type") or "").lower() in ("hidden", "password") or any(
                private_key(properties.get(key) or "") for key in ("name", "id", "autocomplete")
            )
            if tag not in ("input", "textarea") or not sensitive:
                return
            raw = self.get_starttag_text()
            row, column = self.getpos()
            start = offsets[row - 1] + column
            if tag == "textarea":
                self.private_text_start = start + len(raw)
            if "value" not in properties:
                return
            attributes = []
            for key, value in attrs:
                value = "[redacted]" if key == "value" else value
                attributes.append(key if value is None else f'{key}="{escape(value, quote=True)}"')
            ending = " />" if raw.rstrip().endswith("/>") else ">"
            self.replacements.append(
                (start, start + len(raw), "<" + tag + " " + " ".join(attributes) + ending)
            )

        def handle_endtag(self, tag):
            if tag == "textarea" and self.private_text_start is not None:
                row, column = self.getpos()
                self.replacements.append(
                    (self.private_text_start, offsets[row - 1] + column, "[redacted]")
                )
                self.private_text_start = None

        def handle_startendtag(self, tag, attrs):
            self.handle_starttag(tag, attrs)
            if tag == "textarea":
                self.private_text_start = None

    parser = Redactor()
    parser.feed(source)
    parser.close()
    if parser.private_text_start is not None:
        parser.replacements.append((parser.private_text_start, len(source), "[redacted]"))
    for start, end, replacement in reversed(parser.replacements):
        source = source[:start] + replacement + source[end:]
    return source


def snapshot(driver, *, screenshots=True):
    with command_timeout(driver, 2):
        return _snapshot(driver, screenshots=screenshots)


def _snapshot(driver, *, screenshots=True):
    evidence = {}
    actions = {
        "url": lambda: redact_url(driver.current_url),
        "html": lambda: redact_html(driver.page_source),
        "capabilities": lambda: json.dumps(
            redact(driver.capabilities), ensure_ascii=False, indent=2
        ),
    }
    if screenshots:
        actions = {"screenshot": driver.get_screenshot_as_png, **actions}
    for name, action in actions.items():
        try:
            evidence[name] = action()
        except Exception as error:
            evidence[f"{name}-unavailable"] = type(error).__name__
    if driver.capabilities.get("browserName") == "chrome":
        try:
            evidence["console"] = json.dumps(
                redact(driver.get_log("browser")), ensure_ascii=False, indent=2
            )
        except Exception as error:
            evidence["console-unavailable"] = type(error).__name__
    return evidence


def attach(evidence, phase):
    types = {
        "screenshot": allure.attachment_type.PNG,
        "html": allure.attachment_type.HTML,
        "capabilities": allure.attachment_type.JSON,
        "console": allure.attachment_type.JSON,
    }
    for name, value in evidence.items():
        try:
            if name.endswith(("-error", "-errors")):
                value = redact_text(value)
            allure.attach(value, f"{phase}: {name}", types.get(name, allure.attachment_type.TEXT))
        except Exception:
            pass
