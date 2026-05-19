"""Items API: edit items, run supplier search, run characteristics-based match."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.schemas import (
    ItemRead,
    ItemUpdate,
    MatchResponse,
    OfferRead,
    ProductMatchRead,
    SearchResponse,
)
from app.core.database import get_session
from app.core.logging import logger
from app.models.document import Item, ProductMatch, SupplierOffer
from app.services.matching import match_item_to_products
from app.services.search import search_suppliers

router = APIRouter(prefix="/api/items", tags=["items"])


@router.get("/{item_id}", response_model=ItemRead)
async def get_item(
    item_id: str,
    session: AsyncSession = Depends(get_session),
) -> ItemRead:
    item = await _get_item(session, item_id)
    return ItemRead.model_validate(item)


@router.patch("/{item_id}", response_model=ItemRead)
async def update_item(
    item_id: str,
    body: ItemUpdate,
    session: AsyncSession = Depends(get_session),
) -> ItemRead:
    item = await _get_item(session, item_id)
    for field_name, value in body.model_dump(exclude_unset=True).items():
        setattr(item, field_name, value)
    item.updated_at = datetime.utcnow()
    await session.commit()
    await session.refresh(item, attribute_names=["offers", "matches"])
    return ItemRead.model_validate(item)


@router.delete("/{item_id}", status_code=204)
async def delete_item(
    item_id: str,
    session: AsyncSession = Depends(get_session),
) -> None:
    item = await _get_item(session, item_id)
    await session.delete(item)
    await session.commit()


@router.post("/{item_id}/search", response_model=SearchResponse)
async def search_for_item(
    item_id: str,
    session: AsyncSession = Depends(get_session),
) -> SearchResponse:
    item = await _get_item(session, item_id)
    query = (item.search_query or item.name).strip()
    if not query:
        raise HTTPException(status_code=422, detail="Item has no search query or name")

    logger.info("Searching suppliers for item {}: {}", item.id, query)
    try:
        results = await search_suppliers(query)
    except Exception as exc:
        logger.exception("Supplier search failed for item {}", item.id)
        raise HTTPException(status_code=502, detail=f"Search failed: {exc}") from exc

    # Replace previous offers
    for existing in list(item.offers):
        await session.delete(existing)
    await session.flush()

    new_offers: list[SupplierOffer] = []
    for idx, r in enumerate(results, start=1):
        offer = SupplierOffer(
            item_id=item.id,
            position=idx,
            title=r.title or r.url,
            url=r.url,
            supplier_domain=r.domain,
            snippet=r.snippet,
            price=r.price,
            contact_phone=r.contact_phone,
            contact_email=r.contact_email,
            raw_extract=r.raw_extract or None,
        )
        session.add(offer)
        new_offers.append(offer)
    await session.commit()
    for offer in new_offers:
        await session.refresh(offer)

    return SearchResponse(
        item_id=item.id,
        offers=[OfferRead.model_validate(o) for o in new_offers],
    )


@router.post("/{item_id}/match", response_model=MatchResponse)
async def match_for_item(
    item_id: str,
    session: AsyncSession = Depends(get_session),
) -> MatchResponse:
    """Run the 'Подбор по характеристикам' workflow:
    LLM proposes hypotheses → search → LLM compares specs → save matches.
    """
    item = await _get_item(session, item_id)

    logger.info("Running characteristics match for item {}: {}", item.id, item.name)
    try:
        outcomes = await match_item_to_products(
            name=item.name,
            quantity=item.quantity,
            unit=item.unit,
            gost=item.gost,
            okpd2=item.okpd2,
            specifications=item.specifications,
        )
    except Exception as exc:
        logger.exception("Match failed for item {}", item.id)
        raise HTTPException(status_code=502, detail=f"Match failed: {exc}") from exc

    # Replace previous matches
    for existing in list(item.matches):
        await session.delete(existing)
    await session.flush()

    new_matches: list[ProductMatch] = []
    for idx, outcome in enumerate(outcomes, start=1):
        specs_list = (
            [s.model_dump() for s in outcome.evaluation.specs]
            if outcome.evaluation
            else None
        )
        pm = ProductMatch(
            item_id=item.id,
            position=idx,
            hypothesis_brand=outcome.hypothesis.brand,
            hypothesis_model=outcome.hypothesis.model_or_type,
            hypothesis_description=outcome.hypothesis.description,
            hypothesis_reasoning=outcome.hypothesis.reasoning,
            search_query=outcome.search_query,
            found_title=outcome.found.title if outcome.found else None,
            found_url=outcome.found.url if outcome.found else None,
            found_domain=outcome.found.domain if outcome.found else None,
            found_snippet=outcome.found.snippet if outcome.found else None,
            found_price=outcome.found.price if outcome.found else None,
            specs_compared=specs_list,
            match_score=outcome.evaluation.score if outcome.evaluation else None,
            verdict=outcome.evaluation.verdict if outcome.evaluation else "no_data",
            summary=outcome.evaluation.summary if outcome.evaluation else None,
        )
        session.add(pm)
        new_matches.append(pm)

    await session.commit()
    for pm in new_matches:
        await session.refresh(pm)

    return MatchResponse(
        item_id=item.id,
        matches=[ProductMatchRead.model_validate(m) for m in new_matches],
    )


async def _get_item(session: AsyncSession, item_id: str) -> Item:
    stmt = (
        select(Item)
        .where(Item.id == item_id)
        .options(selectinload(Item.offers), selectinload(Item.matches))
    )
    item = (await session.execute(stmt)).scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    return item
