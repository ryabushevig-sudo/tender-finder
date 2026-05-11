"""LLM-driven extraction of product items from tender documents."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.core.logging import logger
from app.services.llm import LLMError, get_llm_provider

SYSTEM_PROMPT = """Ты — эксперт по российским закупкам (44-ФЗ, 223-ФЗ). Твоя задача —
извлечь из технического задания (ТЗ) структурированный список товаров для закупки.

ПРАВИЛА:
1. Извлекай каждую отдельную товарную позицию. Если ТЗ описывает составной продукт
   (например, модульное здание или комплект мебели), извлеки И сам продукт целиком,
   И его ключевые подкомпоненты, которые имеет смысл искать у поставщиков
   (окна, двери, светильники, розетки, сантехнику и т.д.).
2. Для каждой позиции укажи: name (наименование), quantity (количество),
   unit (единица измерения), specifications (ключевые характеристики словарём),
   gost (если упомянут ГОСТ/ТУ), okpd2 (код ОКПД2 если есть),
   search_query (короткий поисковый запрос для поиска у поставщика — максимум 8 слов,
   без избыточных характеристик, но с ключевыми параметрами для уникальности).
3. Не выдумывай значения. Если поле отсутствует — оставь null или пустую строку.
4. Если в документе классическая 44-ФЗ таблица "наименование показателя / значение",
   собирай характеристики словарём specifications для каждого товара.
5. Игнорируй общие пункты вроде "Требования к упаковке", "Гарантийный срок",
   "Условия поставки" — это не товары.

ФОРМАТ ОТВЕТА — СТРОГО JSON следующего вида (без markdown, без пояснений):
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
    }
  ]
}
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


async def extract_items(document_text: str) -> ExtractionResult:
    """Run the LLM to extract a list of items from the parsed document text."""
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
        try:
            parsed = ExtractionResult.model_validate(raw)
        except Exception as exc:
            logger.error("Failed to validate extraction response: {}; raw={}", exc, raw)
            continue
        all_items.extend(parsed.items)

    deduped = _dedupe(all_items)
    return ExtractionResult(items=deduped)


def _dedupe(items: list[ExtractedItem]) -> list[ExtractedItem]:
    """Drop items with the same lowercased name + unit + quantity."""
    seen: set[tuple[str, str, float | None]] = set()
    result: list[ExtractedItem] = []
    for item in items:
        key = (
            item.name.strip().lower(),
            (item.unit or "").strip().lower(),
            item.quantity,
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result
