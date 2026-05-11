"""Items API: edit items, run supplier search."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.schemas import ItemRead, ItemUpdate, OfferRead, SearchResponse
from app.core.database import get_session
from app.core.logging import logger
from app.models.document import Item, SupplierOffer
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
    await session.refresh(item, attribute_names=["offers"])
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


async def _get_item(session: AsyncSession, item_id: str) -> Item:
    stmt = (
        select(Item).where(Item.id == item_id).options(selectinload(Item.offers))
    )
    item = (await session.execute(stmt)).scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    return item
