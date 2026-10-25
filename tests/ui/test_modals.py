from utils.reporting.scenarios import scenario, scenario_cases


@scenario(
    "MOD-P01",
    "Simple Modal открывается с заголовком и текстом",
    "Открыть Simple Modal и дождаться завершения анимации.",
    "Показаны заголовок Simple Modal и текст Hi, I’m a simple modal.; "
    "Form Modal остаётся закрытой.",
    story="Simple Modal",
)
def test_simple_modal_shows_title_and_text(modals):
    assert modals.heading() == "Modals"
    modals.open_simple()
    assert modals.simple_title() == "Simple Modal"
    assert modals.simple_text() == "Hi, I’m a simple modal."
    assert not modals.form_is_open()


@scenario(
    "MOD-P02",
    "Simple Modal открывается повторно после закрытия",
    "Открыть Simple Modal, закрыть крестиком и открыть снова.",
    "После закрытия окно скрыто; при повторном открытии показывается тот же текст.",
    story="Simple Modal",
)
def test_simple_modal_reopens_after_close(modals):
    modals.open_simple().close()
    modals.open_simple()
    assert modals.simple_text() == "Hi, I’m a simple modal."


@scenario(
    "MOD-P03",
    "Enter на кнопке открывает Simple Modal",
    "Нажать Enter на кнопке Simple Modal.",
    "Окно открыто, показаны заголовок Simple Modal и текст Hi, I’m a simple modal.",
    story="Simple Modal",
)
def test_enter_opens_simple_modal(modals):
    modals.open_simple_with_enter()
    assert modals.simple_title() == "Simple Modal"
    assert modals.simple_text() == "Hi, I’m a simple modal."


@scenario(
    "MOD-P04",
    "После отправки Form Modal показывает введённые данные",
    "Открыть Form Modal; Name=Volga QA, Email=qa@example.com, Message=Hello from UI; Submit.",
    "Сводка содержит введённые Name, Email и Message; окно остаётся открытым.",
    story="Отправка Form Modal",
)
def test_form_modal_shows_submitted_values(modals):
    modals.open_form()
    modals.fill_form("Volga QA", "qa@example.com", "Hello from UI")
    modals.assert_submitted("Volga QA", "qa@example.com", "Hello from UI")


@scenario(
    "MOD-P05",
    "Form Modal отправляется с одним именем",
    "Открыть Form Modal; заполнить только Name=Only Name; Submit.",
    "Отправка успешна; имя сохранено, необязательные Email и Message пусты.",
    story="Отправка Form Modal",
)
def test_form_modal_accepts_name_without_contacts(modals):
    modals.open_form()
    modals.fill_form("Only Name")
    modals.assert_submitted("Only Name")


@scenario(
    "MOD-P06",
    "Escape закрывает Form Modal",
    "Открыть Form Modal и нажать Escape.",
    "Окно полностью закрыто, кнопка открытия снова доступна.",
    story="Закрытие и повторное открытие",
)
def test_escape_closes_form_modal(modals):
    modals.open_form()
    modals.modal.escape()
    modals.modal.wait_closed()
    assert modals.form_trigger_enabled()


@scenario(
    "MOD-P07",
    "Черновик имени сохраняется при закрытии Form Modal",
    "Открыть Form Modal; ввести Name=Draft Name; закрыть крестиком и открыть снова.",
    "Поле Name содержит Draft Name; подтверждения отправки нет.",
    story="Закрытие и повторное открытие",
)
def test_name_draft_survives_form_modal_close(modals):
    modals.open_form()
    modals.fill_form("Draft Name")
    modals.modal.close()
    modals.open_form()
    assert modals.name_value() == "Draft Name"
    assert not modals.form.success_visible()


@scenario(
    "MOD-P08",
    "Back возвращает к форме для новой отправки",
    "Открыть Form Modal; отправить First QA, first@example.com и First message; нажать Back; "
    "заполнить Name=Second QA, "
    "Email=qa@example.com, Message=Second message; Submit.",
    "После Back все три поля пусты; новая сводка содержит только новые значения.",
    story="Закрытие и повторное открытие",
)
def test_back_allows_second_submission(modals):
    modals.open_form()
    modals.fill_form("First QA", "first@example.com", "First message")
    modals.assert_submitted("First QA", "first@example.com", "First message")
    modals.form.back()
    modals.form.assert_values({"name": "", "email": "", "textarea": ""})
    modals.fill_form("Second QA", "qa@example.com", "Second message")
    modals.assert_submitted("Second QA", "qa@example.com", "Second message")


@scenario(
    "MOD-P09",
    "Form Modal открывается после Simple Modal",
    "Открыть Simple Modal, закрыть его и открыть Form Modal.",
    "Simple Modal не активна; показана Form Modal с обязательным полем Name.",
    story="Переключение и исправление",
)
def test_form_modal_opens_after_simple(modals):
    modals.open_simple().close()
    modals.open_form()
    assert not modals.simple_is_open()
    assert modals.form_title() == "Modal Containing A Form"
    assert modals.name_is_required()


@scenario(
    "MOD-P10",
    "Исправленный email разблокирует отправку",
    "Открыть Form Modal; заполнить Name=Volga QA, Email=broken-address, Message=Recovery; "
    "отправить; проверить ошибку; заменить email на qa@example.com и отправить снова.",
    "Ошибка email исчезает; сводка содержит Volga QA, qa@example.com и Recovery.",
    story="Переключение и исправление",
)
def test_fixed_email_unblocks_submission(modals):
    modals.open_form()
    modals.fill_form("Volga QA", "broken-address", "Recovery")
    modals.assert_email_invalid()
    modals.form.fill("email", "qa@example.com")
    modals.form.wait_valid("email")
    modals.assert_submitted("Volga QA", "qa@example.com", "Recovery")


@scenario(
    "MOD-N01",
    "Пустое имя не пропускает отправку",
    "Открыть Form Modal; оставить Name пустым; ввести Email=qa@example.com; Submit.",
    "Ошибка Name: This field is required. Атрибут aria-invalid=true. Общее сообщение: "
    "Please fill out the form correctly. Сводка успешной отправки отсутствует.",
    story="Валидация формы",
)
def test_empty_name_blocks_submission(modals):
    modals.open_form()
    modals.fill_form("", "qa@example.com")
    modals.assert_name_missing()


@scenario_cases(
    [
        (
            "MOD-N02[missing_at]",
            "Email без @ отклоняется",
            "Открыть Form Modal; ввести Name=Volga QA, Email=not-an-email, Message=Keep message; "
            "Submit.",
            "Показаны точные ошибки email и формы, aria-invalid=true и typeMismatch=true; "
            "отправки нет; "
            "все значения сохранены.",
            "not-an-email",
        ),
        (
            "MOD-N02[double_at]",
            "Email с двумя @ отклоняется",
            "Открыть Form Modal; ввести Name=Volga QA, Email=qa@@example.com, "
            "Message=Keep message; "
            "Submit.",
            "Показаны точные ошибки email и формы, aria-invalid=true и typeMismatch=true; "
            "отправки нет; "
            "все значения сохранены.",
            "qa@@example.com",
        ),
        (
            "MOD-N02[missing_domain]",
            "Email без домена отклоняется",
            "Открыть Form Modal; ввести Name=Volga QA, Email=qa@, Message=Keep message; Submit.",
            "Показаны точные ошибки email и формы, aria-invalid=true и typeMismatch=true; "
            "отправки нет; "
            "все значения сохранены.",
            "qa@",
        ),
    ],
    story="Валидация формы",
)
def test_invalid_email_blocks_submission(modals, case):
    modals.open_form()
    modals.fill_form("Volga QA", case["value"], "Keep message")
    modals.assert_email_invalid()
    modals.form.assert_values(
        {"name": "Volga QA", "email": case["value"], "textarea": "Keep message"}
    )


@scenario(
    "MOD-N03",
    "Escape не закрывает Simple Modal",
    "Открыть Simple Modal и нажать Escape; наблюдать 1,2 секунды.",
    "Окно остаётся активным и видимым весь интервал.",
    story="Защита от случайного закрытия",
)
def test_escape_leaves_simple_modal_open(modals):
    modals.open_simple().escape()
    modals.simple.assert_stays_open()


@scenario(
    "MOD-N04",
    "Клик вне Simple Modal не закрывает его",
    "Открыть Simple Modal и нажать на затемнённую область вне окна; наблюдать 1,2 секунды.",
    "Окно остаётся активным и видимым весь интервал.",
    story="Защита от случайного закрытия",
)
def test_outside_click_leaves_simple_modal_open(modals):
    modals.open_simple().click_outside()
    modals.simple.assert_stays_open()


@scenario(
    "MOD-N05",
    "Клик вне Form Modal не закрывает его",
    "Открыть Form Modal и нажать на затемнённую область вне окна; наблюдать 1,2 секунды.",
    "Окно и поле Name остаются видимыми; подтверждения отправки нет.",
    story="Защита от случайного закрытия",
)
def test_outside_click_leaves_form_modal_open(modals):
    modals.open_form()
    modals.modal.click_outside()
    modals.modal.assert_stays_open()
    assert modals.name_is_enabled()
    assert not modals.form.success_visible()
