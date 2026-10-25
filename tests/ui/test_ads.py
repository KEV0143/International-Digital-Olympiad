from utils.reporting.scenarios import scenario


@scenario(
    "ADS-P01",
    "Реклама появляется после задержки и остаётся открытой",
    "До навигации установить MutationObserver. Открыть Ads, дождаться рекламы и наблюдать "
    "её 7 секунд. Прочитать журнал активаций с начала документа.",
    "До DOMContentLoaded и первые 3,5 секунды после него активаций нет. Первая активация "
    "через 3,5-12 секунд после DOMContentLoaded; следующие 7 секунд "
    "реклама видна, закрытий и повторных активаций нет.",
    story="Появление и содержимое",
)
def test_ad_appears_once_after_delay(ads):
    ads.ready_ad()
    ads.ad.assert_stays_open(7)
    trace = ads.trace()
    assert trace["installed"] <= trace["readyAt"]
    openings = [event for event in trace["transitions"] if event["active"]]
    assert [event["active"] for event in trace["transitions"]] == [True]
    delay = (openings[0]["at"] - trace["readyAt"]) / 1000
    assert 3.5 <= delay <= 12, f"Задержка popup {delay:.3f} с вне допуска 3,5-12 с"


@scenario(
    "ADS-P02",
    "Реклама показывает заголовок, текст и доступную кнопку закрытия",
    "Дождаться рекламы и прочитать заголовок, текст, роль диалога и имя кнопки закрытия.",
    "Заголовок Hi, текст I am an ad., role=dialog; крестик виден, активен и имеет доступное имя.",
    story="Появление и содержимое",
)
def test_ad_content_and_close_control(ads):
    ads.ready_ad()
    assert ads.ad_title() == "Hi"
    assert ads.ad_text() == "I am an ad."
    assert ads.ad_close_is_accessible()
    assert ads.ad_dialog_role() == "dialog"
    assert ads.ad_labelled_title() == "Hi"


@scenario(
    "ADS-P03",
    "После закрытия рекламы ссылка Home работает",
    "Дождаться рекламы, закрыть её крестиком и нажать Home.",
    "Реклама скрыта; ссылка Home переводит на главную страницу того же сайта.",
    story="Закрытие и повторный показ",
)
def test_home_link_works_after_ad_closes(ads):
    ads.ready_ad().close()
    ads.go_home()


@scenario(
    "ADS-P04",
    "Enter на крестике закрывает рекламу",
    "Дождаться рекламы и нажать Enter на кнопке закрытия.",
    "Окно полностью закрыто и больше не активно.",
    story="Закрытие и повторный показ",
)
def test_enter_on_close_button_dismisses_ad(ads):
    ads.ready_ad()
    ads.close_ad_with_enter()
    assert ads.ad_is_closed()


@scenario(
    "ADS-P05",
    "Закрытая реклама не возвращается сама",
    "Дождаться рекламы, закрыть её и наблюдать 7 секунд без перезагрузки.",
    "Весь интервал окно скрыто; зафиксировано ровно одно открытие и одно закрытие.",
    story="Закрытие и повторный показ",
)
def test_closed_ad_does_not_reappear(ads):
    ads.ready_ad().close()
    ads.assert_for(
        lambda: ads.ad_is_closed(),
        7,
        "Реклама снова открылась без перезагрузки",
    )
    assert [event["active"] for event in ads.trace()["transitions"]] == [True, False]


@scenario(
    "ADS-P06",
    "После перезагрузки реклама появляется снова",
    "Дождаться рекламы, закрыть её, перезагрузить страницу и дождаться новой рекламы.",
    "В новом документе снова появляется окно с текстом I am an ad.",
    story="Закрытие и повторный показ",
)
def test_reload_shows_ad_again(ads):
    ads.ready_ad().close()
    ads.reload()
    ads.ready_ad()
    assert ads.ad_text() == "I am an ad."
    assert [event["active"] for event in ads.trace()["transitions"]] == [True]


@scenario(
    "ADS-P07",
    "На странице Ads открыта только реклама",
    "Дождаться рекламы и проверить список активных окон.",
    "Активно только рекламное окно; Simple Modal и Form Modal скрыты.",
    story="Состояние и навигация",
)
def test_ad_is_the_only_open_popup(ads):
    ads.ready_ad()
    assert ads.ad_is_the_only_active_popup()
    assert ads.other_popups_are_hidden()


@scenario(
    "ADS-P08",
    "Реклама помещается в небольшое окно",
    "Установить вьюпорт 800×700, проверить его размер, дождаться рекламы и проверить "
    "границы карточки, текста и крестика.",
    "Все элементы рекламы находятся внутри видимой области; крестик закрывает окно.",
    story="Состояние и навигация",
)
def test_ad_fits_small_viewport(ads):
    ads.set_viewport(800, 700)
    ads.ready_ad()
    assert ads.ad_is_inside_viewport()
    ads.ad.close()


@scenario(
    "ADS-P09",
    "Страница объясняет рекламу и ведёт к видео",
    "Проверить заголовок, текст о задержке, предупреждение об адблокерах и ссылку на видео.",
    "Заголовок Ads; текст обещает появление через 5…4…3…2…1; предупреждение просит "
    "отключить адблокеры; ссылка ведёт на YouTube и имеет target=_blank.",
    story="Состояние и навигация",
)
def test_ad_page_explains_delay_and_links_to_video(ads):
    assert ads.heading() == "Ads"
    assert ads.delay_notice() == "An ad will appear in 5…4…3…2…1"
    assert "ad blockers" in ads.ad_blocker_warning()
    link = ads.tutorial_link()
    assert link["href"] == "https://www.youtube.com/watch?v=FZBGRjv0pqU"
    assert link["target"] == "_blank"


@scenario(
    "ADS-N01",
    "Escape не закрывает рекламу",
    "Дождаться рекламы и нажать Escape; наблюдать 1,2 секунды.",
    "Реклама остаётся активной и видимой.",
    story="Защита от случайного закрытия",
)
def test_escape_leaves_ad_open(ads):
    ads.ready_ad().escape()
    ads.ad.assert_stays_open()


@scenario(
    "ADS-N02",
    "Клик вне карточки не закрывает рекламу",
    "Дождаться рекламы и нажать на затемнённую область вне карточки; наблюдать 1,2 секунды.",
    "Реклама остаётся активной и видимой.",
    story="Защита от случайного закрытия",
)
def test_outside_click_leaves_ad_open(ads):
    ads.ready_ad().click_outside()
    ads.ad.assert_stays_open()


@scenario(
    "ADS-N03",
    "Клик по тексту рекламы не закрывает её",
    "Дождаться рекламы, кликнуть по тексту внутри карточки и наблюдать 1,2 секунды.",
    "Реклама остаётся активной и видимой.",
    story="Защита от случайного закрытия",
)
def test_clicking_ad_text_leaves_ad_open(ads):
    ads.ready_ad()
    ads.click_ad_content()
    ads.ad.assert_stays_open()


@scenario(
    "ADS-N04",
    "Реклама не даёт нажать ссылку под собой",
    "Дождаться рекламы и попробовать нажать ссылку Home, перекрытую окном.",
    "Клик перехватывается оверлеем, URL не меняется, реклама остаётся открытой.",
    story="Перекрытие фона",
)
def test_ad_overlay_blocks_background_link(ads):
    ads.ready_ad()
    ads.assert_home_link_blocked()
    ads.ad.assert_stays_open()
