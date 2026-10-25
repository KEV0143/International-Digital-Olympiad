from utils.reporting.scenarios import scenario


@scenario(
    "FF-S01",
    "Список Automation Tools переносится в Message",
    "Прочитать элементы Automation Tools через Selenium, проверить состав и порядок, "
    "соединить названия через запятую и ввести строку в Message.",
    "Список содержит Selenium, Playwright, Cypress, Appium, Katalon Studio в этом порядке; "
    "Message равен строке из прочитанных названий.",
    story="Задание со списком Automation Tools",
)
def test_automation_tools_are_pasted_into_message(fields):
    assert fields.heading() == "Form Fields"
    tools = fields.automation_tools()
    assert tools == ["Selenium", "Playwright", "Cypress", "Appium", "Katalon Studio"]
    assert fields.tools_to_message() == ", ".join(tools)


@scenario(
    "FF-P01",
    "После успешной отправки форма очищается",
    "Заполнить Name, Password, Email, Message; выбрать Water, Coffee, Blue и Yes; отправить.",
    "Показан alert Message received!; после OK текстовые поля, флажки и радиокнопки очищены, "
    "а список автоматизации снова показывает пустой вариант.",
    story="Отправка формы",
)
def test_successful_submit_clears_form(fields):
    message = fields.fill_valid_form()
    fields.assert_saved_values(
        {
            "name": "Volga QA",
            "password": "Demo-password-42!",
            "email": "qa@example.com",
            "message": message,
            "automation": "yes",
        }
    )
    assert fields.selected_drinks() == ["Water", "Coffee"]
    assert fields.selected_colors() == ["Blue"]
    fields.submit()
    fields.received_alert()
    fields.assert_form_reset()


@scenario(
    "FF-N01",
    "Пустое имя останавливает отправку",
    "Заполнить остальные поля и Message, оставить Name пустым и нажать Submit.",
    "У Name validity.valueMissing=true; validationMessage непусто. Alert отсутствует "
    "в течение 1,2 с. Введённые значения и выбор напитков, цвета и Automation сохранены.",
    story="Обязательные поля",
)
def test_empty_name_stops_submission(fields):
    message = fields.fill_valid_form(name="")
    fields.submit()
    fields.assert_name_required_by_browser()
    fields.assert_no_alert()
    fields.assert_saved_values(
        {
            "name": "",
            "password": "Demo-password-42!",
            "email": "qa@example.com",
            "message": message,
            "automation": "yes",
        }
    )
    assert fields.selected_drinks() == ["Water", "Coffee"]
    assert fields.selected_colors() == ["Blue"]


@scenario(
    "FF-N02",
    "Полностью пустая форма требует Name",
    "Не заполнять поля и нажать Submit.",
    "У Name validity.valueMissing=true; validationMessage непусто. Alert отсутствует "
    "в течение 1,2 с. Текстовые поля пусты; Automation=default; напитки и цвет не выбраны.",
    story="Обязательные поля",
)
def test_empty_form_requires_name(fields):
    fields.submit()
    fields.assert_name_required_by_browser()
    fields.assert_no_alert()
    fields.assert_saved_values(
        {"name": "", "password": "", "email": "", "message": "", "automation": "default"}
    )
    assert fields.selected_drinks() == []
    assert fields.selected_colors() == []


@scenario(
    "FF-P07",
    "Для отправки достаточно одного Name",
    "Заполнить только Name=Only Name, проверить остальные поля и нажать Submit.",
    "Пустые необязательные поля не препятствуют отправке; alert равен Message received!; "
    "после OK форма очищена.",
    story="Отправка формы",
)
def test_name_alone_allows_submission(fields):
    fields.fill_name("Only Name")
    fields.assert_saved_values(
        {"name": "Only Name", "password": "", "email": "", "message": "", "automation": "default"}
    )
    assert fields.selected_drinks() == []
    assert fields.selected_colors() == []
    fields.submit()
    fields.received_alert()
    fields.assert_form_reset()


@scenario(
    "FF-P02",
    "Пароль скрывается при вводе",
    "Ввести Demo-secret-42! в Password, снять фокус и проверить тип и значение поля.",
    "Поле имеет type=password и сохраняет введённое значение.",
    story="Контролы формы",
)
def test_password_is_masked(fields):
    fields.fill_password("Demo-secret-42!")
    assert fields.password_type() == "password"
    assert fields.password_value() == "Demo-secret-42!"


@scenario(
    "FF-P03",
    "Напитки выбираются независимо друг от друга",
    "Отметить Water, Wine и Ctrl-Alt-Delight, затем снять Wine.",
    "Сначала выбраны три напитка; после снятия Wine остаются Water и Ctrl-Alt-Delight.",
    story="Контролы формы",
)
def test_drinks_are_selected_independently(fields):
    assert fields.selected_drinks() == []
    for name in ("Water", "Wine", "Ctrl-Alt-Delight"):
        fields.toggle_drink(name)
    assert fields.selected_drinks() == ["Water", "Wine", "Ctrl-Alt-Delight"]
    fields.toggle_drink("Wine")
    assert fields.selected_drinks() == ["Water", "Ctrl-Alt-Delight"]


@scenario(
    "FF-P04",
    "В группе цветов остаётся один выбор",
    "Последовательно выбрать Red, Blue, Yellow, Green и #FFC0CB.",
    "После каждого клика выбран ровно текущий цвет; предыдущий снимается.",
    story="Контролы формы",
)
def test_only_one_color_stays_selected(fields):
    assert fields.selected_colors() == []
    for name in ("Red", "Blue", "Yellow", "Green", "#FFC0CB"):
        fields.choose_color(name)
        assert fields.selected_colors() == [name]


@scenario(
    "FF-P05",
    "Список автоматизации переключается между вариантами",
    "Проверить пустой вариант и список Yes, No, Undecided; выбрать No, Undecided, Yes, затем "
    "вернуться к пустому варианту.",
    "Отображаемый текст и value соответствуют выбору; возврат к пустому варианту работает.",
    story="Контролы формы",
)
def test_automation_dropdown_switches_options(fields):
    assert fields.preference_options() == ["", "Yes", "No", "Undecided"]
    assert fields.preference_value() == "default"
    for text, value in (("No", "no"), ("Undecided", "undecided"), ("Yes", "yes"), ("", "default")):
        fields.choose_preference(text)
        assert fields.preference_value() == value
        assert fields.preference_text() == text


@scenario(
    "FF-P06",
    "Отправка формы с кириллицей и переносом строки",
    "Ввести Name=Климкин Егор Владимирович и две строки Message с кириллицей, <>& и №42; "
    "отправить.",
    "До отправки значения Name и Message сохранены без искажений. Необязательные поля "
    "оставлены пустыми. После подтверждения отправки поля Name и Message очищены.",
    story="Текстовые поля",
)
def test_cyrillic_and_multiline_message_survive_submit(fields):
    message = "Первая строка: Ёжик <>&\nВторая строка: тест №42"
    fields.fill_name("Климкин Егор Владимирович")
    fields.fill_message(message)
    assert fields.name_value() == "Климкин Егор Владимирович"
    assert fields.message_value() == message
    assert fields.email_value() == ""
    assert fields.password_value() == ""
    assert fields.selected_drinks() == []
    assert fields.selected_colors() == []
    fields.submit()
    fields.received_alert()
    assert fields.name_value() == ""
    assert fields.message_value() == ""
