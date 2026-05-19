"""Characteristics-based product matching.

Workflow:
1. Given an Item (with name + specifications + ГОСТ + ОКПД2), ask the LLM to
   propose 3-4 concrete brand/model hypotheses that should satisfy the ТЗ.
2. For each hypothesis, run a targeted supplier search.
3. For the top result of each hypothesis, ask the LLM to compare the required
   ТЗ specs against what's visible on the supplier page and produce a
   structured match table.

This is separate from the simpler "Найти" flow, which just runs a wide
DuckDuckGo search by item name without spec comparison.
"""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field

from app.core.logging import logger
from app.services.llm import LLMError, get_llm_provider
from app.services.search import SearchResult, search_suppliers


HYPOTHESES_SYSTEM = """Ты — эксперт по российским тендерным закупкам (44-ФЗ, 223-ФЗ)
и по российскому B2B-рынку. Получив позицию из технического задания (ТЗ),
твоя задача — предложить 3-4 конкретных гипотезы о том, какой именно товар
заказчик хочет купить.

ПРАВИЛА:
1. Гипотезы должны быть РАЗНЫМИ — разные марки, разные модели или разные
   типы исполнения, которые тем не менее соответствуют требованиям ТЗ.
2. Используй только РЕАЛЬНЫЕ марки, которые продаются на российском рынке
   (например: для электрики — Schneider Electric, Legrand, ABB, Werkel,
   Эра, EKF; для сантехники — Cersanit, Roca, Vitra, IDDIS, Santek;
   для мебели — IKEA, Hoff, Стандарт, Дятьково; и т.д.).
3. Если ты не уверен в конкретной модели — укажи марку + тип, без точного
   номера модели. НЕ выдумывай несуществующие артикулы.
4. search_query должен помочь найти карточку товара у поставщика — это
   марка + ключевое слово + 1-2 главных параметра, максимум 8 слов.
5. key_features — 3-5 главных параметров ТЗ, которые должен закрывать
   предложенный товар.

ФОРМАТ ОТВЕТА — СТРОГО JSON (без markdown, без пояснений):
{
  "hypotheses": [
    {
      "brand": "Schneider Electric",
      "model_or_type": "Glossa GSL000186",
      "description": "Розетка двойная с заземлением, IP44, белая",
      "key_features": ["IP44", "2 гнезда", "с заземлением", "белая"],
      "search_query": "Schneider Glossa GSL000186 розетка IP44",
      "reasoning": "Schneider Glossa GSL000186 — двойная розетка с заземлением и защитой IP44 в белом цвете, типичная для коммерческих помещений"
    }
  ]
}
"""

EVALUATE_SYSTEM = """Ты — эксперт по проверке соответствия товара требованиям ТЗ
в тендерных закупках. Тебе даны: (а) исходные требования из ТЗ, (б) гипотеза
о подходящем товаре, (в) данные карточки товара с сайта поставщика
(заголовок + сниппет + при наличии — текст страницы).

ТВОЯ ЗАДАЧА:
Для КАЖДОЙ характеристики из ТЗ определи:
- required: что требует ТЗ
- found: что нашлось у этого товара (или "нет данных")
- status: "match" / "mismatch" / "unknown"
- note: краткий комментарий 1 фразой

Затем выведи:
- score: 0-100, общий процент соответствия (важнее всего критичные параметры
  типа размера, материала, ГОСТ — менее критичные типа цвета весят меньше)
- verdict: "high" (>=75% и нет critical mismatch), "medium" (50-75%),
  "low" (<50% или есть critical mismatch), "no_data" (мало данных для оценки)
- summary: 1-2 предложения резюме для покупателя

ВАЖНО:
- НЕ выдумывай совпадения. Если в данных карточки нет упоминания параметра —
  ставь "unknown", а не "match".
- "match" значит: на карточке явно указано значение, которое удовлетворяет ТЗ.
- "mismatch" значит: на карточке явно указано значение, которое НЕ удовлетворяет
  требованию ТЗ (например, ТЗ требует IP44, а на карточке IP20).

ФОРМАТ ОТВЕТА — СТРОГО JSON (без markdown):
{
  "specs": [
    {"name": "IP44", "required": "IP44", "found": "IP44", "status": "match", "note": "явно указано"},
    {"name": "Заземление", "required": "есть", "found": "нет данных", "status": "unknown", "note": "не упомянуто в описании"}
  ],
  "score": 75,
  "verdict": "medium",
  "summary": "По размеру и материалу совпадает; ГОСТ нужно подтвердить у поставщика."
}
"""


class Hypothesis(BaseModel):
    brand: str | None = None
    model_or_type: str | None = None
    description: str = ""
    key_features: list[str] = Field(default_factory=list)
    search_query: str = ""
    reasoning: str = ""


class HypothesesResponse(BaseModel):
    hypotheses: list[Hypothesis] = Field(default_factory=list)


class SpecComparison(BaseModel):
    name: str
    required: str | None = None
    found: str | None = None
    status: str = "unknown"  # match | mismatch | unknown
    note: str | None = None


class MatchEvaluation(BaseModel):
    specs: list[SpecComparison] = Field(default_factory=list)
    score: int = 0
    verdict: str = "no_data"  # high | medium | low | no_data
    summary: str = ""


@dataclass
class MatchOutcome:
    hypothesis: Hypothesis
    search_query: str
    found: SearchResult | None
    evaluation: MatchEvaluation | None


def _format_item_for_prompt(
    *,
    name: str,
    quantity: float | None,
    unit: str | None,
    gost: str | None,
    okpd2: str | None,
    specifications: dict[str, Any] | None,
) -> str:
    parts = [f"Наименование: {name}"]
    if quantity is not None:
        parts.append(f"Количество: {quantity} {unit or ''}".strip())
    if gost:
        parts.append(f"ГОСТ: {gost}")
    if okpd2:
        parts.append(f"ОКПД2: {okpd2}")
    if specifications:
        parts.append("Характеристики:")
        for k, v in specifications.items():
            parts.append(f"  - {k}: {v}")
    return "\n".join(parts)


async def propose_hypotheses(
    *,
    name: str,
    quantity: float | None = None,
    unit: str | None = None,
    gost: str | None = None,
    okpd2: str | None = None,
    specifications: dict[str, Any] | None = None,
    max_hypotheses: int = 4,
) -> list[Hypothesis]:
    provider = get_llm_provider()
    item_block = _format_item_for_prompt(
        name=name,
        quantity=quantity,
        unit=unit,
        gost=gost,
        okpd2=okpd2,
        specifications=specifications,
    )
    user_prompt = (
        f"Позиция из ТЗ:\n\n{item_block}\n\n"
        f"Предложи {max_hypotheses} различных гипотез — какие именно реальные товары "
        "на российском B2B-рынке подходят под эти требования."
    )
    try:
        raw = await provider.chat_json(HYPOTHESES_SYSTEM, user_prompt)
    except LLMError as exc:
        logger.error("Hypotheses generation failed: {}", exc)
        return []
    try:
        parsed = HypothesesResponse.model_validate(raw)
    except Exception as exc:
        logger.error("Invalid hypotheses payload: {}; raw={}", exc, raw)
        return []
    return parsed.hypotheses[:max_hypotheses]


async def evaluate_match(
    *,
    item_block: str,
    hypothesis: Hypothesis,
    search_result: SearchResult,
) -> MatchEvaluation:
    provider = get_llm_provider()
    found_block = (
        f"Заголовок: {search_result.title}\n"
        f"URL: {search_result.url}\n"
        f"Домен: {search_result.domain}\n"
        f"Сниппет: {search_result.snippet}\n"
    )
    if search_result.price:
        found_block += f"Цена: {search_result.price}\n"
    if search_result.raw_extract:
        # raw_extract may contain a 'page_text' or similar field — include if present
        for key, value in search_result.raw_extract.items():
            if isinstance(value, str) and value.strip():
                found_block += f"{key}: {value[:1500]}\n"

    hypothesis_block = (
        f"Марка: {hypothesis.brand or '—'}\n"
        f"Модель/тип: {hypothesis.model_or_type or '—'}\n"
        f"Описание: {hypothesis.description}\n"
        f"Ключевые особенности: {', '.join(hypothesis.key_features) or '—'}"
    )

    user_prompt = (
        f"ТРЕБОВАНИЯ ИЗ ТЗ:\n{item_block}\n\n"
        f"ГИПОТЕЗА (предположение, какой товар нужен):\n{hypothesis_block}\n\n"
        f"НАЙДЕНО У ПОСТАВЩИКА:\n{found_block}\n"
        "Сравни требования ТЗ с тем, что видно у этого товара. Если данных мало — "
        "ставь 'unknown', а не выдумывай совпадения."
    )
    try:
        raw = await provider.chat_json(EVALUATE_SYSTEM, user_prompt)
    except LLMError as exc:
        logger.warning("Match evaluation failed: {}", exc)
        return MatchEvaluation(verdict="no_data", summary=f"Не удалось оценить: {exc}")
    try:
        return MatchEvaluation.model_validate(raw)
    except Exception as exc:
        logger.warning("Invalid match payload: {}; raw={}", exc, json.dumps(raw)[:500])
        return MatchEvaluation(
            verdict="no_data",
            summary="Не удалось разобрать ответ LLM по сопоставлению характеристик",
        )


async def match_item_to_products(
    *,
    name: str,
    quantity: float | None = None,
    unit: str | None = None,
    gost: str | None = None,
    okpd2: str | None = None,
    specifications: dict[str, Any] | None = None,
    max_hypotheses: int = 4,
    results_per_hypothesis: int = 3,
) -> list[MatchOutcome]:
    """Top-level orchestration:
    1. Propose hypotheses
    2. Search for each
    3. Evaluate top result
    """
    hypotheses = await propose_hypotheses(
        name=name,
        quantity=quantity,
        unit=unit,
        gost=gost,
        okpd2=okpd2,
        specifications=specifications,
        max_hypotheses=max_hypotheses,
    )
    if not hypotheses:
        return []

    item_block = _format_item_for_prompt(
        name=name,
        quantity=quantity,
        unit=unit,
        gost=gost,
        okpd2=okpd2,
        specifications=specifications,
    )

    async def process_one(hyp: Hypothesis) -> MatchOutcome:
        query = (hyp.search_query or hyp.description or name).strip()
        try:
            results = await search_suppliers(query, max_results=results_per_hypothesis)
        except Exception as exc:
            logger.warning("Search failed for hypothesis {}: {}", hyp.search_query, exc)
            return MatchOutcome(
                hypothesis=hyp, search_query=query, found=None, evaluation=None
            )
        if not results:
            return MatchOutcome(
                hypothesis=hyp, search_query=query, found=None, evaluation=None
            )
        top = results[0]
        evaluation = await evaluate_match(
            item_block=item_block, hypothesis=hyp, search_result=top
        )
        return MatchOutcome(
            hypothesis=hyp, search_query=query, found=top, evaluation=evaluation
        )

    outcomes = await asyncio.gather(*(process_one(h) for h in hypotheses))
    return list(outcomes)
