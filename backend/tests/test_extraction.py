"""Tests for deterministic item table extraction."""
from __future__ import annotations

from app.services.extraction import _extract_items_from_tables


def test_simple_item_table() -> None:
    """Each row is one item, columns: №, Наименование, Ед.изм, Кол-во."""
    text = """[Таблица 3]
№ пп || Наимнование || Ед. измерения || Кол-во
1 || Барабан ротора Т67.19.010М2СБ для ЗП-600М2 || шт || 2
2 || Лопатка Т67.01.001М2 || шт || 4
3 || Шкив Т67.01.009 || шт || 2
"""
    items = _extract_items_from_tables(text)
    assert len(items) == 3
    assert items[0].name.startswith("Барабан ротора")
    assert items[0].quantity == 2
    assert items[0].unit == "шт"
    assert items[2].name == "Шкив Т67.01.009"


def test_44fz_pattern_aggregates_specs_per_item() -> None:
    """44-ФЗ pattern: name col repeats; spec_name + spec_value per row."""
    text = """[Таблица 1]
№ п/п || Наименование товара || Наименование показателя || Содержание (значение) || Ед. изм. || Кол-во
1 || 2 || 3 || 4 || 5 || 6
1. || Очиститель воздуха УФ || Производительность, м3/ч || ≥ 60 || шт || 40
1. || Очиститель воздуха УФ || Бактерицидная эффективность, % || ≥ 95,0 || шт || 40
 ||  || Вариант исполнения || Настенный ||  || 
2. || Розетка двойная || Степень защиты || IP44 || шт || 100
 ||  || Цвет || Белый ||  || 
"""
    items = _extract_items_from_tables(text)
    assert len(items) == 2
    assert items[0].name == "Очиститель воздуха УФ"
    assert items[0].quantity == 40
    assert "Производительность, м3/ч" in items[0].specifications
    assert items[0].specifications["Производительность, м3/ч"] == "≥ 60"
    assert "Вариант исполнения" in items[0].specifications
    assert items[1].name == "Розетка двойная"
    assert items[1].quantity == 100
    assert items[1].specifications["Степень защиты"] == "IP44"


def test_rejects_criteria_and_template_tables() -> None:
    """Tables about scoring criteria or empty pricing templates yield no items."""
    text = """[Таблица 2]
Наименование критерия || Документы || Значимость (вес) критерия || Максимальное количество баллов
1. Стоимость предмета закупки || Письмо || 70% || 70
2. Опыт исполнения договоров || Реестр || 30% || 30

[Таблица 6]
№ п.п. || Наименование || Технические характеристики || Ед. изм. || Кол-во
 || Итого стоимость: || Итого стоимость: || Итого стоимость: || Итого стоимость:
"""
    items = _extract_items_from_tables(text)
    assert items == []


def test_skips_pure_enumeration_row() -> None:
    """\"1 || 2 || 3 || 4\" between header and data must not become an item."""
    text = """[Таблица 1]
№ || Наименование || Ед.изм || Кол-во
1 || 2 || 3 || 4
1 || Лампа люминесцентная || шт || 50
"""
    items = _extract_items_from_tables(text)
    assert len(items) == 1
    assert items[0].name == "Лампа люминесцентная"
    assert items[0].quantity == 50


def test_typo_in_header_naimnovanie() -> None:
    """\"Наимнование\" (with a missing letter) is still recognized as a name column."""
    text = """[Таблица 3]
№ пп || Наимнование || Ед. измерения || Кол-во
1 || Ходовая часть на вентилятор ВДН-8,5Х-1-3000 || шт || 1
"""
    items = _extract_items_from_tables(text)
    assert len(items) == 1
    assert "ВДН-8,5Х" in items[0].name


def test_nested_spec_table_associated_with_item() -> None:
    """Item rows that reference a nested ``[Вложенная таблица N.M]`` get its specs."""
    text = """[Таблица 5]
№ || Наименование товара || Характеристика товара || Ед. изм. || Кол-во
1 || Робот Пиранья || [Вложенная таблица 5.1] || шт || 1
2 || Робот КИТ || [Вложенная таблица 5.2] || шт || 3

[Таблица 5.1]
Функциональные, технические характеристики || Требования к показателям
Тип робота || Подводный телеуправляемый
Глубина погружения, м || Не менее 5

[Таблица 5.2]
Тип робота || Подводный программируемый
Источник питания || Внешний от сети
"""
    items = _extract_items_from_tables(text)
    assert len(items) == 2
    piranya = items[0]
    assert piranya.name == "Робот Пиранья"
    assert piranya.quantity == 1
    assert piranya.unit == "шт"
    assert piranya.specifications.get("Тип робота") == "Подводный телеуправляемый"
    assert piranya.specifications.get("Глубина погружения, м") == "Не менее 5"
    assert "Функциональные, технические характеристики" not in piranya.specifications
    kit = items[1]
    assert kit.specifications.get("Источник питания") == "Внешний от сети"


def test_nested_spec_table_without_explicit_header() -> None:
    """Some nested spec tables jump straight to data rows (no header)."""
    text = """[Таблица 2]
№ || Наименование || Характеристика || Ед. || Кол-во
1 || VEX IQ Супер набор || [Вложенная таблица 2.1] || шт || 4

[Таблица 2.1]
Конструктивные элементы из пластика, шт || не менее 99
Зубчатые колеса, шт || не менее 20
"""
    items = _extract_items_from_tables(text)
    assert len(items) == 1
    specs = items[0].specifications
    assert specs.get("Конструктивные элементы из пластика, шт") == "не менее 99"
    assert specs.get("Зубчатые колеса, шт") == "не менее 20"


def test_multirow_header_with_pipe_in_cell() -> None:
    """Header cells with internal pipe separators (multi-paragraph) match prefixes."""
    text = """[Таблица 5]
№ || Наименование товара || Характеристика товара, требуемые показатели качества || Ед. | изм. || Кол-во
1 || Тестовая позиция || Описание || шт || 7
"""
    items = _extract_items_from_tables(text)
    assert len(items) == 1
    assert items[0].unit == "шт"
    assert items[0].quantity == 7
