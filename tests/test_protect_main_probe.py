"""Одноразовая проверка защиты main: тест падает намеренно, PR не должен сливаться."""


def test_protect_main_probe_fails_on_purpose() -> None:
    raise AssertionError("намеренно красный тест проверки защиты main")
