"""LLM-driven extraction of product items from tender documents."""
from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field

from app.core.logging import logger
from app.services.llm import LLMError, get_llm_provider

SYSTEM_PROMPT = """Ты — эксперт по российским закупкам (44-ФЗ, 223-ФЗ). Твоя задача —
извлечь из технического задания (ТЗ) ВСЕ товарные позиции, которые нужно закупить.

КЛЮЧЕВОЕ ПРАВИЛО: если в документе есть таблица со столбцами наподобие
"№ / Наименование / Ед.изм. / Кол-во" или "№ / Наименование товара / Технические
характеристики / Кол-во", это спецификация — извлеки КАЖДУЮ строку этой таблицы
как отдельную позицию. Не пропускай позиции и не объединяй их.

ПРАВИЛА:
1. Извлекай ВСЕ позиции из любых таблиц спецификации, перечня товаров,
   технических характеристик. Каждая строка такой таблицы — отдельная позиция.
2. Если ТЗ описывает составной продукт (модульное здание, комплект мебели),
   извлеки И сам продукт, И его ключевые подкомпоненты
   (окна, двери, светильники, розетки, сантехнику и т.д.).
3. Для каждой позиции укажи: name (наименование), quantity (количество),
   unit (единица измерения), specifications (ключевые характеристики словарём),
   gost (если упомянут ГОСТ/ТУ), okpd2 (код ОКПД2 если есть),
   search_query (короткий поисковый запрос для поиска у поставщика — максимум 8
   слов, с ключевыми параметрами и маркировкой/артикулом если есть).
4. Артикулы и маркировка (например "Т67.19.010М2СБ", "ВДН-8,5Х-1-3000") — это часть
   наименования, оставляй их в name и search_query.
5. Не выдумывай значения. Если поле отсутствует — оставь null или пустую строку.
6. Если в документе классическая 44-ФЗ таблица "наименование показателя / значение",
   собирай характеристики словарём specifications для каждого товара.
7. Игнорируй общие пункты вроде "Требования к упаковке", "Гарантийный срок",
   "Условия поставки", "Итого", служебные строки таблиц — это не товары.
8. Игнорируй пустые строки таблиц (без названия товара) и шапки таблиц.

ФОРМАТ ОТВЕТА — СТРОГО JSON с ключом "items" (массив объектов).
НЕ ИСПОЛЬЗУЙ другие ключи (никаких "tables", "sections", "data" и т.п.).
НЕ ОБОРАЧИВАЙ в markdown. Только чистый JSON:
{
  "items": [
    {
      "name": "Очиститель воздуха ультрафиолетовый",
      "quantity": 40,
      "unit": "шт",
      "gost": null,
      "okpd2": "32.50.50.190",
      "specifications": {
        "Производительность, м3/ч": "≥ 60",
        "Бактерицидная эффективность, %": "≥ 95,0",
        "Вариант исполнения": "Настенный"
      },
      "search_query": "очиститель воздуха ультрафиолетовый настенный 60 м3/ч"
    },
    {
      "name": "Барабан ротора Т67.19.010М2СБ для ЗП-600М2",
      "quantity": 2,
      "unit": "шт",
      "gost": null,
      "okpd2": null,
      "specifications": {},
      "search_query": "барабан ротора Т67.19.010М2СБ ЗП-600М2"
    }
  ]
}

Если в фрагменте товаров нет — верни {"items": []}.
"""


class ExtractedItem(BaseModel):
    name: str
    quantity: float | None = None
    unit: str | None = None
    gost: str | None = None
    okpd2: str | None = None
    specifications: dict[str, Any] = Field(default_factory=dict)
    search_query: str | None = None


class ExtractionResult(BaseModel):
    items: list[ExtractedItem] = Field(default_factory=list)


def _chunk_text(text: str, max_chars: int = 18000) -> list[str]:
    """Split very long documents into chunks at line boundaries."""
    if len(text) <= max_chars:
        return [text]
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for line in text.splitlines(keepends=True):
        if current_len + len(line) > max_chars and current:
            chunks.append("".join(current))
            current = [line]
            current_len = len(line)
        else:
            current.append(line)
            current_len += len(line)
    if current:
        chunks.append("".join(current))
    return chunks


# --- Deterministic table extraction --------------------------------------

_TABLE_MARKER_RE = re.compile(r"^\[(Таблица|Лист:|Страница)")
_TABLE_ID_RE = re.compile(r"^\[Таблица ([\d.]+)\]")
_NESTED_REF_RE = re.compile(r"\[Вложенная таблица ([\d.]+)\]")
_CELL_SEP_RE = re.compile(r"\s*\|\|\s*")
_NUM_RE = re.compile(r"[-+]?\d+[\d\s.,]*")

# Header prefixes that mark each kind of column
_NAME_PREFIXES = (
    "наим",          # наименование / наимнование (typos accepted)
    "назв",          # название
    "товар",         # товар / товары
    "продукт",      # продукция
    "предмет закуп",
    "запасная часть",
)
# Words that, if found in the name column header, disqualify it as an item-name column
# (signals tables about criteria, contracts, contacts, etc.)
_NAME_NEGATIVE = (
    "критерий",
    "критерия",
    "показателя",
    "документ",
    "заказчик",
    "поставщик",
    "участник",
    "банк",
    "сведения об участнике",
    "пункта проекта",
)
_QTY_PREFIXES = (
    "кол-во",
    "к-во",
    "количеств",
    "число единиц",
    "qty",
    "quantity",
)
_QTY_NEGATIVE = (
    "балл",
    "веса",
    "значимость",
    "оценк",
    "рейтинг",
    "процент",
)
_UNIT_PREFIXES = ("ед. из", "ед.из", "единица", "unit")
_SPEC_PREFIXES = (
    "технические характеристики",
    "характеристик",
    "требования к товару",
    "требования",
    "параметр",
    "спецификация",
)
# 44-ФЗ pattern: separate columns for spec-name and spec-value.
# Keep these prefixes narrow — broad words like "характеристика" also appear in the
# generic header "Функциональные, технические характеристики…" that some
# documents put as a *parent* header above all three (name, value, unit)
# sub-headers — we don't want to claim the first such column as spec_name.
_SPEC_NAME_PREFIXES = (
    "наименование показателя",
    "показатель",
    "показателя",
    "наименование характеристик",
)
_SPEC_VALUE_PREFIXES = (
    "содержание",
    "значение",
    "значения",
    "знчение",  # observed typo in real ТЗ ("Знчение показателя")
)
_SPEC_VALUE_NEGATIVE = (
    "имеет значение",
)
_GOST_PREFIXES = ("гост", "ту ", "норматив")
_OKPD_PREFIXES = ("окпд",)
_COUNTRY_PREFIXES = ("страна происхождения", "страна")
_SKIP_NAME_VALUES = {
    "",
    "итого",
    "итог",
    "всего",
    "итого стоимость:",
    "наименование",
    "наимнование",
    "название",
    "товар",
    "…",
    "...",
    "x",
    "х",
}


def _parse_number(s: str | None) -> float | None:
    if not s:
        return None
    match = _NUM_RE.search(s)
    if not match:
        return None
    raw = match.group(0).replace(" ", "").replace(",", ".")
    # Strip trailing punctuation
    raw = raw.rstrip(".")
    if not raw or raw in {"-", "+"}:
        return None
    try:
        value = float(raw)
    except ValueError:
        return None
    return value if value > 0 else None


def _split_table_blocks(text: str) -> list[list[str]]:
    """Return blocks of lines, one per [Таблица N] / [Лист:] / [Страница N] marker."""
    blocks: list[list[str]] = []
    current: list[str] | None = None
    for line in text.splitlines():
        if _TABLE_MARKER_RE.match(line.strip()):
            if current is not None:
                blocks.append(current)
            current = [line.strip()]
        elif current is not None:
            if line.strip() == "" and len(current) > 1:
                # Blank line ends the table
                blocks.append(current)
                current = None
            else:
                current.append(line.strip())
    if current is not None:
        blocks.append(current)
    return blocks


def _find_column(
    cells: list[str],
    prefixes: tuple[str, ...],
    *,
    negative: tuple[str, ...] = (),
    excluded: set[int] | None = None,
) -> int:
    excluded = excluded or set()
    for i, h in enumerate(cells):
        if i in excluded:
            continue
        h_low = h.lower()
        for kw in prefixes:
            if kw in h_low:
                if any(neg in h_low for neg in negative):
                    continue
                return i
    return -1


def _parse_nested_spec_table(block: list[str]) -> dict[str, str]:
    """Parse a nested 2-column spec table into a dict.

    Nested tables in real ТЗ docs are inconsistent: some have a header row
    (e.g. "Функциональные характеристики... || Требования к показателям") and
    others jump straight to data. We treat the first row as a header only
    when its first cell matches one of the spec-header keywords; otherwise
    we use all rows as data.
    """
    specs: dict[str, str] = {}
    if len(block) < 2:
        return specs
    start = 1
    first_row = _CELL_SEP_RE.split(block[1])
    if len(first_row) >= 2:
        h0_low = first_row[0].lower()
        h1_low = first_row[1].lower()
        # Recognise an explicit header row: the second column reads like
        # a "value/requirement" column header.
        header_value_markers = (
            "требования к показател",
            "требование",
            "требуемые показател",
            "значение показател",
            "значение",
            "содержание",
        )
        header_name_hint = (
            "характеристик" in h0_low
            or "показател" in h0_low
            or "наименован" in h0_low
        )
        if header_name_hint and any(m in h1_low for m in header_value_markers):
            start = 2
    for row in block[start:]:
        cells = _CELL_SEP_RE.split(row)
        if len(cells) < 2:
            continue
        name = _clean_cell(cells[0])
        value = _clean_cell(cells[1])
        if len(cells) > 2:
            extras = [_clean_cell(c) for c in cells[2:] if _clean_cell(c)]
            if extras:
                value = (value + " " + " ".join(extras)).strip() if value else " ".join(extras)
        if not name or name.lower() in _SKIP_NAME_VALUES:
            continue
        # Avoid clobbering when the same key appears multiple times (e.g. several
        # "Наличие" requirements with different name lines)
        if name in specs and specs[name] != value:
            # Append distinct values
            specs[name] = f"{specs[name]}; {value}" if value else specs[name]
        else:
            specs[name] = value
    return specs


def _collect_nested_specs(blocks: list[list[str]]) -> dict[str, dict[str, str]]:
    """Find nested-table blocks (hierarchical IDs like 5.1) and parse each."""
    nested: dict[str, dict[str, str]] = {}
    for block in blocks:
        if not block:
            continue
        m = _TABLE_ID_RE.match(block[0])
        if not m:
            continue
        tid = m.group(1)
        if "." not in tid:
            continue
        specs = _parse_nested_spec_table(block)
        if specs:
            nested[tid] = specs
    return nested


def _extract_items_from_tables(text: str) -> list[ExtractedItem]:
    """Find spec-list tables in the parsed text and extract rows deterministically.

    Handles two common patterns:

    A. Simple item list — each row is one item:
       № | Наименование | Ед.изм | Кол-во

    B. 44-ФЗ spec table — each row is one *spec* of an item; the product name
       repeats (or is blank, carrying forward) across many rows:
       № | Наименование товара | Наименование показателя | Значение | Ед | Кол-во

    Also supports nested-table pattern — each row of the item table has a
    reference like ``[Вложенная таблица 5.1]`` in its spec cell; the
    referenced child table holds the actual characteristics.
    """
    items: list[ExtractedItem] = []
    blocks = _split_table_blocks(text)
    nested_specs = _collect_nested_specs(blocks)
    for block in blocks:
        if len(block) < 3:
            continue
        # Skip nested-id blocks — they're consumed via references in parent tables.
        first_marker = _TABLE_ID_RE.match(block[0])
        if first_marker and "." in first_marker.group(1):
            continue
        header_idx, header_cells = _find_header_row(block)
        if header_idx == -1:
            continue

        # Claim columns in priority order so that, e.g., "Наименование показателя, ед.изм"
        # ends up tagged as spec_name (not unit and not item-name).
        claimed: set[int] = set()

        def claim(prefixes: tuple[str, ...], negative: tuple[str, ...] = ()) -> int:
            col = _find_column(
                header_cells,
                prefixes,
                negative=negative,
                excluded=claimed,
            )
            if col != -1:
                claimed.add(col)
            return col

        spec_name_col = claim(_SPEC_NAME_PREFIXES)
        spec_value_col = claim(_SPEC_VALUE_PREFIXES, _SPEC_VALUE_NEGATIVE)
        name_col = claim(_NAME_PREFIXES, _NAME_NEGATIVE)
        qty_col = claim(_QTY_PREFIXES, _QTY_NEGATIVE)
        unit_col = claim(_UNIT_PREFIXES)
        specs_col = claim(_SPEC_PREFIXES)
        gost_col = claim(_GOST_PREFIXES)
        okpd_col = claim(_OKPD_PREFIXES)
        country_col = claim(_COUNTRY_PREFIXES)

        if name_col == -1 or qty_col == -1:
            continue

        is_44fz = spec_name_col != -1 and spec_value_col != -1
        logger.info(
            "Item table detected ({}); pattern={} cols name={} qty={} unit={} "
            "specs={} spec_name={} spec_val={}",
            block[0],
            "44-ФЗ" if is_44fz else "simple",
            name_col,
            qty_col,
            unit_col,
            specs_col,
            spec_name_col,
            spec_value_col,
        )

        current_item: ExtractedItem | None = None
        last_name: str = ""

        for row_line in block[header_idx + 1 :]:
            cells = _CELL_SEP_RE.split(row_line)
            if len(cells) <= max(name_col, qty_col):
                continue
            # Skip 44-ФЗ enumeration row "1 || 2 || 3 || ..." (every cell is a small int)
            if _is_enumeration_row(cells):
                continue

            raw_name = _clean_cell(cells[name_col])
            name_low = raw_name.lower()
            # Skip totals
            if name_low.startswith("итого") or name_low.startswith("всего"):
                if current_item is not None:
                    items.append(current_item)
                    current_item = None
                continue

            # If the name cell is empty and we're in 44-ФЗ mode, carry forward
            if not raw_name and is_44fz and current_item is not None:
                name = current_item.name
            elif raw_name in ("", "…", "..."):
                continue
            else:
                if name_low in _SKIP_NAME_VALUES:
                    continue
                name = raw_name

            qty = _parse_number(cells[qty_col]) if qty_col < len(cells) else None
            unit = (
                _clean_cell(cells[unit_col])
                if unit_col != -1 and unit_col < len(cells)
                else None
            )
            unit = unit or None
            if unit and unit.lower() in _SKIP_NAME_VALUES:
                unit = None

            # Collect references to nested spec tables anywhere in this row.
            nested_refs: list[str] = []
            for c in cells:
                nested_refs.extend(_NESTED_REF_RE.findall(c))

            spec_kv: dict[str, Any] = {}
            if is_44fz:
                spec_name = (
                    _clean_cell(cells[spec_name_col])
                    if spec_name_col < len(cells)
                    else ""
                )
                spec_value = (
                    _clean_cell(cells[spec_value_col])
                    if spec_value_col < len(cells)
                    else ""
                )
                if spec_name and spec_value:
                    spec_kv[spec_name] = spec_value
                elif spec_name and not spec_value:
                    spec_kv[spec_name] = ""
            else:
                if specs_col != -1 and specs_col < len(cells):
                    specs_text = _clean_cell(cells[specs_col])
                    # Strip any nested-table reference markers — they were
                    # already collected separately and the literal placeholder
                    # is not a useful characteristic value.
                    specs_text_clean = _NESTED_REF_RE.sub("", specs_text).strip()
                    if (
                        specs_text_clean
                        and specs_text_clean.lower() not in _SKIP_NAME_VALUES
                    ):
                        spec_kv["Технические характеристики"] = specs_text_clean

            # Merge in characteristics from any nested spec tables referenced
            # by this row.
            for ref_id in nested_refs:
                nested = nested_specs.get(ref_id)
                if not nested:
                    continue
                for k, v in nested.items():
                    if k and k not in spec_kv:
                        spec_kv[k] = v

            gost = None
            if gost_col != -1 and gost_col < len(cells):
                gost_text = _clean_cell(cells[gost_col])
                if gost_text and gost_text.lower() not in _SKIP_NAME_VALUES:
                    gost = gost_text
            okpd = None
            if okpd_col != -1 and okpd_col < len(cells):
                okpd_text = _clean_cell(cells[okpd_col])
                if okpd_text and okpd_text.lower() not in _SKIP_NAME_VALUES:
                    okpd = okpd_text
            country = None
            if country_col != -1 and country_col < len(cells):
                ctext = _clean_cell(cells[country_col])
                if ctext and ctext.lower() not in _SKIP_NAME_VALUES:
                    country = ctext

            if is_44fz:
                # If this row starts a new product name (different from current_item.name),
                # flush the previous item.
                if raw_name and name != last_name:
                    if current_item is not None:
                        items.append(current_item)
                    current_item = ExtractedItem(
                        name=name,
                        quantity=qty,
                        unit=unit,
                        gost=gost,
                        okpd2=okpd,
                        specifications=dict(spec_kv),
                        search_query=name,
                    )
                    if country:
                        current_item.specifications[
                            "Страна происхождения"
                        ] = country
                    last_name = name
                else:
                    # Continuation row — merge specs into the current item
                    if current_item is None:
                        current_item = ExtractedItem(
                            name=name,
                            quantity=qty,
                            unit=unit,
                            gost=gost,
                            okpd2=okpd,
                            specifications=dict(spec_kv),
                            search_query=name,
                        )
                        last_name = name
                    else:
                        if qty and not current_item.quantity:
                            current_item.quantity = qty
                        if unit and not current_item.unit:
                            current_item.unit = unit
                        if gost and not current_item.gost:
                            current_item.gost = gost
                        if okpd and not current_item.okpd2:
                            current_item.okpd2 = okpd
                        if country and "Страна происхождения" not in current_item.specifications:
                            current_item.specifications[
                                "Страна происхождения"
                            ] = country
                        for k, v in spec_kv.items():
                            if k and k not in current_item.specifications:
                                current_item.specifications[k] = v
            else:
                # Simple table: one row = one item
                if current_item is not None:
                    items.append(current_item)
                    current_item = None
                non_empty = {c.strip() for c in cells if c.strip()}
                if len(non_empty) <= 1:
                    continue
                # Total / boilerplate rows like "Начальная (максимальная) цена
                # договора" repeat the same text across many cells — skip.
                if cells.count(cells[name_col]) >= 3:
                    continue
                if name_low.startswith("начальная") or \
                   name_low.startswith("максимальная") or \
                   "цена договора" in name_low or \
                   "цены договоров" in name_low or \
                   name_low.startswith("нмцд") or \
                   name_low.startswith("нмцк"):
                    continue
                # In a simple-pattern table qty is a required signal; rows
                # without a parseable qty are headers/notes/totals.
                if qty is None:
                    continue
                item = ExtractedItem(
                    name=name,
                    quantity=qty,
                    unit=unit,
                    gost=gost,
                    okpd2=okpd,
                    specifications=dict(spec_kv),
                    search_query=name,
                )
                if country:
                    item.specifications["Страна происхождения"] = country
                items.append(item)

        if current_item is not None:
            items.append(current_item)
    return items


def _find_header_row(block: list[str]) -> tuple[int, list[str]]:
    """Find the header row(s) in a [Таблица] block.

    Many 44-ФЗ tables have multi-line headers (e.g. main header + sub-header)
    before the first data row. We:
      1) skip the [Таблица] marker and any pure-enumeration row,
      2) collect consecutive non-data rows as header candidates,
      3) merge them cell-by-cell with ' / ' so all useful keywords show up
         in one logical header row.
    A row is treated as data if its first non-empty cell is a small integer
    (typical position number).
    """
    candidates: list[list[str]] = []
    last_idx = -1
    for i in range(1, min(len(block), 8)):
        row = _CELL_SEP_RE.split(block[i])
        if len(row) < 3:
            continue
        non_empty = [c.strip() for c in row if c.strip()]
        if not non_empty:
            continue
        if all(_is_small_int(c) for c in non_empty):
            # pure enumeration row — ignore
            continue
        if _is_small_int(non_empty[0]):
            # "1 || Наименование ..." — looks like the first data row
            break
        # Caption rows: only one cell has content but the row has several
        # columns (e.g. "ОПИСАНИЕ ОБЪЕКТА ЗАКУПКИ-ТОВАРЫ ||  ||  || ...").
        # These are titles, not real headers, and including them confuses
        # prefix matching (e.g. "ТОВАРЫ" matching the name-column prefix).
        if len(non_empty) == 1 and len(row) >= 3:
            continue
        candidates.append(row)
        last_idx = i
    if not candidates:
        return -1, []
    def _norm(cell: str) -> str:
        # Header cells in our parser may contain in-cell paragraph separators
        # ('|' between paragraphs). Normalise those so prefix matching works
        # on cells like "Ед. | изм." (-> "Ед. изм.").
        cell = re.sub(r"\s*\|\s*", " ", cell)
        return re.sub(r"\s+", " ", cell).strip()

    if len(candidates) == 1:
        return last_idx, [_norm(c) for c in candidates[0]]
    # Merge cells across the candidate rows, padding short rows.
    width = max(len(r) for r in candidates)
    merged: list[str] = []
    for col in range(width):
        parts: list[str] = []
        for row in candidates:
            if col < len(row):
                v = _norm(row[col])
                if v and v not in parts:
                    parts.append(v)
        merged.append(" / ".join(parts))
    return last_idx, merged


def _is_small_int(s: str) -> bool:
    s = s.strip(" |.№")
    if not s:
        return False
    if len(s) > 4:
        return False
    return s.isdigit()


def _clean_cell(value: str) -> str:
    """Normalize a parsed cell: collapse the within-cell '|' newline marker."""
    value = value.strip(" |")
    # Convert the parser's internal paragraph separator " | " into a single space
    value = re.sub(r"\s*\|\s*", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def _is_enumeration_row(cells: list[str]) -> bool:
    """True if every non-empty cell is a small integer (1, 2, 3, ...)."""
    non_empty = [c.strip() for c in cells if c.strip()]
    if not non_empty or len(non_empty) < 3:
        return False
    return all(_is_small_int(c) for c in non_empty)


async def extract_items(document_text: str) -> ExtractionResult:
    """Extract items from a parsed document.

    Strategy:
      1) Run a fast deterministic extractor over tables whose header looks
         like a specification list (Наименование + Кол-во, optionally with
         Наименование показателя / Значение for 44-ФЗ docs).
      2) If we found items that way, return them — the LLM would only add
         noise from the surrounding procedural boilerplate.
      3) Otherwise fall back to LLM-based chunked extraction.
    """
    table_items = _extract_items_from_tables(document_text)
    if table_items:
        logger.info(
            "Deterministic table extractor found {} items — skipping LLM",
            len(table_items),
        )
        return ExtractionResult(items=_dedupe(table_items))

    provider = get_llm_provider()
    chunks = _chunk_text(document_text)
    all_items: list[ExtractedItem] = []
    for i, chunk in enumerate(chunks):
        logger.info(
            "LLM extraction chunk {}/{}, length={} chars", i + 1, len(chunks), len(chunk)
        )
        user_prompt = (
            f"Извлеки список товаров из следующего фрагмента ТЗ "
            f"(фрагмент {i + 1} из {len(chunks)}):\n\n{chunk}"
        )
        try:
            raw = await provider.chat_json(SYSTEM_PROMPT, user_prompt)
        except LLMError as exc:
            logger.error("Extraction failed on chunk {}: {}", i + 1, exc)
            continue
        # Tolerate models that wrap items under unexpected keys.
        if isinstance(raw, dict) and "items" not in raw:
            for key in ("products", "goods", "positions", "list", "data"):
                value = raw.get(key)
                if isinstance(value, list):
                    raw = {"items": value}
                    break
        try:
            parsed = ExtractionResult.model_validate(raw)
        except Exception as exc:
            logger.error("Failed to validate extraction response: {}; raw={}", exc, raw)
            continue
        if parsed.items:
            logger.info(
                "LLM chunk {} returned {} items", i + 1, len(parsed.items)
            )
        all_items.extend(parsed.items)

    deduped = _dedupe(all_items)
    logger.info(
        "Extraction summary (LLM): {} raw -> {} deduped",
        len(all_items),
        len(deduped),
    )
    return ExtractionResult(items=deduped)


def _dedupe(items: list[ExtractedItem]) -> list[ExtractedItem]:
    """Collapse items with the same normalized name.

    When the same product appears in multiple tables (e.g. spec table +
    price table), merge them: keep the longest spec dict and fill in any
    missing unit / GOST / ОКПД2 / qty from the alternative.
    """
    by_name: dict[str, ExtractedItem] = {}
    order: list[str] = []
    for item in items:
        name_key = _normalize_name(item.name)
        if not name_key:
            continue
        existing = by_name.get(name_key)
        if existing is None:
            by_name[name_key] = item
            order.append(name_key)
            continue
        # Merge — prefer the one with more specs as the base
        if len(item.specifications) > len(existing.specifications):
            base, extra = item, existing
            by_name[name_key] = base
        else:
            base, extra = existing, item
        if not base.quantity and extra.quantity:
            base.quantity = extra.quantity
        if not base.unit and extra.unit:
            base.unit = extra.unit
        if not base.gost and extra.gost:
            base.gost = extra.gost
        if not base.okpd2 and extra.okpd2:
            base.okpd2 = extra.okpd2
        for k, v in extra.specifications.items():
            if k and k not in base.specifications:
                base.specifications[k] = v
    return [by_name[k] for k in order]


def _normalize_name(name: str) -> str:
    """Lowercase, collapse whitespace and punctuation for dedup matching."""
    s = name.lower().strip()
    s = re.sub(r"[\s,;.()/\\\-]+", " ", s)
    return s.strip()
