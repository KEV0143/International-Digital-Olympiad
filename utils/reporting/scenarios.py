import allure
import pytest

FEATURES = {"CAL": "Calendars", "MOD": "Modals", "ADS": "Ads", "FF": "Form Fields"}
MARKERS = {"CAL": "calendars", "MOD": "modals", "ADS": "ads", "FF": "form_fields"}
SEVERITIES = {"positive": "critical", "negative": "normal", "special": "blocker"}
STORIES = {
    "negative": "Негативные проверки",
    "positive": "Основные сценарии",
    "special": "Задание со списком Automation Tools",
}


def metadata(case_id, title, steps, expected, story=""):
    prefix, suffix = case_id.split("-", 1)
    kind = (
        "negative"
        if suffix.startswith("N")
        else "special"
        if suffix.startswith("S")
        else "positive"
    )

    return {
        "id": case_id,
        "requirement_id": case_id.split("[", 1)[0],
        "title": title,
        "steps": steps,
        "expected": expected,
        "kind": kind,
        "feature": FEATURES[prefix],
        "story": story or STORIES[kind],
    }


def scenario(case_id: str, title: str, steps: str, expected: str, story: str = ""):
    data = metadata(case_id, title, steps, expected, story)

    def decorate(function):
        function.scenario = data
        function = getattr(pytest.mark, data["kind"])(function)
        function = getattr(pytest.mark, MARKERS[case_id.split("-", 1)[0]])(function)
        function = allure.id(case_id)(function)
        function = allure.title(f"{case_id}. {title}")(function)
        function = allure.epic("UI-тесты Practice Automation")(function)
        function = allure.feature(data["feature"])(function)
        function = allure.story(data["story"])(function)
        function = allure.severity(SEVERITIES[data["kind"]])(function)
        function = allure.description(f"Шаги: {steps}\n\nОжидаемый результат: {expected}")(function)
        return function

    return decorate


def scenario_cases(records, *, story=""):
    cases = []
    for case_id, title, steps, expected, value in records:
        data = metadata(case_id, title, steps, expected, story)
        cases.append(
            pytest.param(
                {**data, "value": value},
                id=case_id,
                marks=[
                    getattr(pytest.mark, data["kind"]),
                    getattr(pytest.mark, MARKERS[case_id.split("-", 1)[0]]),
                ],
            )
        )

    def decorate(function):
        function.scenario_cases = True
        return pytest.mark.parametrize("case", cases)(function)

    return decorate


def item_metadata(item):
    if getattr(item.obj, "scenario_cases", False):
        return {key: value for key, value in item.callspec.params["case"].items() if key != "value"}
    return getattr(item.obj, "scenario", None)


def report_case(item):
    data = item_metadata(item)
    if not data or not getattr(item.obj, "scenario_cases", False):
        return
    allure.dynamic.id(data["id"])
    allure.dynamic.title(f"{data['id']}. {data['title']}")
    allure.dynamic.epic("UI-тесты Practice Automation")
    allure.dynamic.feature(data["feature"])
    allure.dynamic.story(data["story"])
    allure.dynamic.severity(SEVERITIES[data["kind"]])
    allure.dynamic.description(f"Шаги: {data['steps']}\n\nОжидаемый результат: {data['expected']}")
    allure.dynamic.label("requirement", data["requirement_id"])
    allure.dynamic.parameter("case", item.callspec.params["case"]["value"])
