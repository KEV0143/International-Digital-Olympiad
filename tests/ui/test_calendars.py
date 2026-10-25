from datetime import date

from utils.reporting.scenarios import scenario, scenario_cases


@scenario(
    "CAL-P01",
    "Дата выбирается из текущего месяца и отправляется",
    "Проверить пустое поле, подпись и подсказку формата. Открыть календарь и убедиться, что "
    "показан текущий месяц и выделено сегодня. Выбрать 15-е и отправить форму.",
    "Календарь закрывается, а поле и сводка содержат 15-е число текущего месяца в формате "
    "YYYY-MM-DD.",
    story="Выбор даты",
)
def test_pick_date_in_current_month(calendar):
    today = calendar.browser_today()
    calendar.assert_initial_state()
    calendar.open_picker()
    calendar.assert_current_month(today)
    expected = date(today.year, today.month, 15).isoformat()
    assert calendar.choose_day(15) == expected
    calendar.assert_submitted(expected)


@scenario(
    "CAL-P02",
    "В следующем месяце можно выбрать и отправить дату",
    "Открыть календарь, проверить текущий месяц. Перейти на следующий месяц. "
    "Выбрать 10-е и отправить.",
    "Календарь показывает следующий месяц, а поле и сводка содержат выбранную дату.",
    story="Выбор даты",
)
def test_pick_date_in_next_month(calendar):
    today = calendar.browser_today()
    calendar.open_picker()
    assert calendar.displayed_month() == (today.year, today.month)
    year, month = calendar.shift_month(1)
    expected = date(year, month, 10).isoformat()
    assert calendar.choose_day(10) == expected
    calendar.assert_submitted(expected)


@scenario(
    "CAL-P03",
    "Из января можно вернуться в декабрь",
    "Открыть январь текущего года через меню. Перейти на предыдущий месяц. Выбрать 20-е "
    "и отправить.",
    "Календарь показывает декабрь предыдущего года, а поле и сводка содержат 20 декабря.",
    story="Навигация по месяцам",
)
def test_previous_month_from_january_is_december(calendar):
    current_year = calendar.browser_today().year
    calendar.choose_month(current_year, 1)
    year, month = calendar.shift_month(-1)
    assert (year, month) == (current_year - 1, 12)
    expected = date(year, month, 20).isoformat()
    assert calendar.choose_day(20) == expected
    calendar.assert_submitted(expected)


@scenario(
    "CAL-P04",
    "Из декабря можно перейти в январь",
    "Открыть декабрь текущего года через меню. Перейти на следующий месяц. Выбрать 1-е "
    "и отправить.",
    "Календарь показывает январь следующего года, а поле и сводка содержат 1 января.",
    story="Навигация по месяцам",
)
def test_next_month_from_december_is_january(calendar):
    year = calendar.browser_today().year
    calendar.choose_month(year, 12)
    assert calendar.shift_month(1) == (year + 1, 1)
    expected = date(year + 1, 1, 1).isoformat()
    assert calendar.choose_day(1) == expected
    calendar.assert_submitted(expected)


@scenario(
    "CAL-P05",
    "29 февраля доступно в високосном году",
    "Открыть февраль 2028 года через меню. Выбрать 29-е и отправить.",
    "В календаре есть 29 февраля; поле и сводка равны 2028-02-29.",
    story="Навигация по месяцам",
)
def test_leap_day_is_available_in_2028(calendar):
    calendar.choose_month(2028, 2)
    assert calendar.choose_day(29) == "2028-02-29"
    calendar.assert_submitted("2028-02-29")


@scenario(
    "CAL-P06",
    "Меню переносит календарь на другой год и месяц",
    "Выбрать ноябрь через два года от текущего. Выбрать 17-е и отправить.",
    "Календарь и поле показывают выбранные год и месяц; отправлено 17 ноября.",
    story="Навигация по месяцам",
)
def test_menus_jump_to_another_year_and_month(calendar):
    year = calendar.browser_today().year + 2
    calendar.choose_month(year, 11)
    expected = date(year, 11, 17).isoformat()
    assert calendar.choose_day(17) == expected
    calendar.assert_submitted(expected)


@scenario(
    "CAL-P07",
    "Введённая дата открывается на том же дне",
    "Ввести 2028-07-09. Открыть календарь и проверить месяц и день. Закрыть клавишей "
    "Escape и отправить.",
    "Показан июль 2028 с выделенным 9-м; отправлено 2028-07-09.",
    story="Ручной ввод и клавиатура",
)
def test_typed_date_opens_on_the_same_day(calendar):
    calendar.enter_date("2028-07-09")
    calendar.open_picker()
    assert calendar.displayed_month() == (2028, 7)
    assert calendar.selected_day() == "9"
    calendar.close_picker_with_escape()
    calendar.assert_submitted("2028-07-09")


@scenario(
    "CAL-P08",
    "Стрелка переносит выбор с 31 января на 1 февраля",
    "Ввести 2028-01-31. Открыть календарь, нажать ArrowRight и Space. Отправить.",
    "Выбрано 2028-02-01, календарь закрыт.",
    story="Ручной ввод и клавиатура",
)
def test_arrow_key_moves_selection_to_next_month(calendar):
    calendar.enter_date("2028-01-31")
    calendar.open_picker()
    calendar.choose_next_day_with_keyboard()
    calendar.wait_field_value("2028-02-01")
    calendar.assert_submitted("2028-02-01")


@scenario(
    "CAL-P09",
    "Закрытие календаря не сбрасывает выбранную дату",
    "Выбрать 2028-05-10. Открыть календарь, сменить месяц и закрыть через Escape. Снова "
    "открыть и кликнуть вне окна. Выбрать 22-е и отправить.",
    "Escape и клик вне окна не меняют 2028-05-10; после нового выбора отправлено 2028-05-22.",
    story="Повторный выбор и исправление",
)
def test_closing_picker_keeps_selected_date(calendar):
    calendar.choose_month(2028, 5)
    calendar.choose_day(10)
    calendar.open_picker()
    calendar.shift_month(1)
    calendar.close_picker_with_escape()
    assert calendar.field_value() == "2028-05-10"
    calendar.open_picker()
    calendar.close_picker_outside()
    assert calendar.field_value() == "2028-05-10"
    calendar.open_picker()
    assert calendar.displayed_month() == (2028, 5)
    calendar.choose_day(22)
    calendar.assert_submitted("2028-05-22")


@scenario(
    "CAL-P10",
    "Некорректную дату можно исправить и отправить",
    "Ввести 2028-02-30 и отправить. Проверить ошибку. Исправить на 2028-02-29 и снова "
    "отправить. Нажать Back.",
    "Сообщение ошибки даты отсутствует; aria-invalid отличается от true. Сводка содержит "
    "2028-02-29. После Back поле даты доступно для ввода, readOnly=false; сводка скрыта.",
    story="Повторный выбор и исправление",
)
def test_correcting_impossible_date_allows_submit(calendar):
    calendar.assert_invalid("2028-02-30")
    calendar.enter_date("2028-02-29")
    calendar.wait_until_valid()
    calendar.assert_submitted("2028-02-29")
    calendar.form.back()
    assert calendar.form_is_editable()
    assert not calendar.form.success_visible()


@scenario_cases(
    [
        (
            "CAL-N01",
            "Текст вместо даты отклоняется",
            "Ввести not-a-date и отправить.",
            "Сообщение ошибки: Please enter a valid date. Поле имеет aria-invalid=true; "
            "значение not-a-date сохранено. Сводка успешной отправки отсутствует.",
            "not-a-date",
        ),
        (
            "CAL-N02",
            "Дата через косую черту отклоняется",
            "Ввести 01/10/2026 вместо формата YYYY-MM-DD и отправить.",
            "Сообщение ошибки: Please enter a valid date. Поле имеет aria-invalid=true; "
            "значение 01/10/2026 сохранено. Сводка успешной отправки отсутствует.",
            "01/10/2026",
        ),
        (
            "CAL-N03",
            "31 апреля отклоняется",
            "Ввести 2028-04-31 и отправить.",
            "Сообщение ошибки: Please enter a valid date. Поле имеет aria-invalid=true; "
            "значение 2028-04-31 сохранено. Сводка успешной отправки отсутствует.",
            "2028-04-31",
        ),
        (
            "CAL-N04",
            "29 февраля невисокосного года отклоняется",
            "Ввести 2027-02-29 и отправить.",
            "Сообщение ошибки: Please enter a valid date. Поле имеет aria-invalid=true; "
            "значение 2027-02-29 сохранено. Сводка успешной отправки отсутствует.",
            "2027-02-29",
        ),
        (
            "CAL-N05",
            "Месяц 13 отклоняется",
            "Ввести 2028-13-01 и отправить.",
            "Сообщение ошибки: Please enter a valid date. Поле имеет aria-invalid=true; "
            "значение 2028-13-01 сохранено. Сводка успешной отправки отсутствует.",
            "2028-13-01",
        ),
    ],
    story="Некорректные даты",
)
def test_invalid_date_is_rejected(calendar, case):
    calendar.assert_invalid(case["value"])
