"""Documents API: upload, list, extract items, export."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.schemas import (
    DocumentRead,
    DocumentSummary,
    ExtractionResponse,
    ItemRead,
)
from app.core.config import settings
from app.core.database import get_session
from app.core.logging import logger
from app.models.document import Document, Item
from app.services.export import build_xlsx
from app.services.extraction import extract_items
from app.services.parsing import parse_bytes

router = APIRouter(prefix="/api/documents", tags=["documents"])

ALLOWED_SUFFIXES = {".docx", ".pdf", ".xlsx", ".xlsm", ".txt"}


@router.post("", response_model=DocumentSummary, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile,
    session: AsyncSession = Depends(get_session),
) -> DocumentSummary:
    filename = file.filename or "upload"
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type {suffix}. Supported: {sorted(ALLOWED_SUFFIXES)}",
        )

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")

    try:
        text = parse_bytes(filename, data)
    except Exception as exc:
        logger.exception("Failed to parse upload {}", filename)
        raise HTTPException(status_code=422, detail=f"Parsing failed: {exc}") from exc

    document = Document(
        filename=filename,
        stored_path="",
        mime_type=file.content_type,
        size_bytes=len(data),
        extracted_text=text,
        status="parsed",
    )
    session.add(document)
    await session.flush()

    upload_path = settings.upload_path / f"{document.id}_{filename}"
    upload_path.write_bytes(data)
    document.stored_path = str(upload_path)

    await session.commit()
    await session.refresh(document)

    return DocumentSummary(
        id=document.id,
        filename=document.filename,
        status=document.status,
        size_bytes=document.size_bytes,
        created_at=document.created_at,
        updated_at=document.updated_at,
        items_count=0,
    )


@router.get("", response_model=list[DocumentSummary])
async def list_documents(session: AsyncSession = Depends(get_session)) -> list[DocumentSummary]:
    stmt = (
        select(
            Document,
            func.count(Item.id).label("items_count"),
        )
        .outerjoin(Item, Item.document_id == Document.id)
        .group_by(Document.id)
        .order_by(Document.created_at.desc())
    )
    result = await session.execute(stmt)
    rows = result.all()
    return [
        DocumentSummary(
            id=doc.id,
            filename=doc.filename,
            status=doc.status,
            size_bytes=doc.size_bytes,
            created_at=doc.created_at,
            updated_at=doc.updated_at,
            items_count=int(items_count or 0),
        )
        for doc, items_count in rows
    ]


@router.get("/{document_id}", response_model=DocumentRead)
async def get_document(
    document_id: str,
    session: AsyncSession = Depends(get_session),
) -> DocumentRead:
    stmt = (
        select(Document)
        .where(Document.id == document_id)
        .options(selectinload(Document.items).selectinload(Item.offers))
    )
    document = (await session.execute(stmt)).scalar_one_or_none()
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return DocumentRead.model_validate(document)


@router.get("/{document_id}/text")
async def get_document_text(
    document_id: str,
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    document = (
        await session.execute(select(Document).where(Document.id == document_id))
    ).scalar_one_or_none()
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"id": document.id, "text": document.extracted_text or ""}


@router.delete("/{document_id}", status_code=204)
async def delete_document(
    document_id: str,
    session: AsyncSession = Depends(get_session),
) -> None:
    document = (
        await session.execute(select(Document).where(Document.id == document_id))
    ).scalar_one_or_none()
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    if document.stored_path:
        Path(document.stored_path).unlink(missing_ok=True)
    await session.delete(document)
    await session.commit()


@router.post("/{document_id}/extract", response_model=ExtractionResponse)
async def extract_document_items(
    document_id: str,
    session: AsyncSession = Depends(get_session),
) -> ExtractionResponse:
    stmt = (
        select(Document)
        .where(Document.id == document_id)
        .options(selectinload(Document.items).selectinload(Item.offers))
    )
    document = (await session.execute(stmt)).scalar_one_or_none()
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    if not document.extracted_text:
        raise HTTPException(status_code=422, detail="Document has no extracted text")

    document.status = "extracting"
    await session.commit()

    try:
        result = await extract_items(document.extracted_text)
    except Exception as exc:
        document.status = "error"
        document.error = str(exc)
        document.updated_at = datetime.utcnow()
        await session.commit()
        logger.exception("Extraction failed for {}", document.id)
        raise HTTPException(status_code=502, detail=f"Extraction failed: {exc}") from exc

    # Replace previous items
    for old in list(document.items):
        await session.delete(old)
    await session.flush()

    new_items: list[Item] = []
    for idx, extracted in enumerate(result.items, start=1):
        item = Item(
            document_id=document.id,
            position=idx,
            name=extracted.name,
            quantity=extracted.quantity,
            unit=extracted.unit,
            gost=extracted.gost,
            okpd2=extracted.okpd2,
            specifications=extracted.specifications or None,
            search_query=extracted.search_query,
        )
        session.add(item)
        new_items.append(item)

    document.status = "ready"
    document.error = None
    document.updated_at = datetime.utcnow()
    await session.commit()

    for item in new_items:
        await session.refresh(item, attribute_names=["offers"])

    return ExtractionResponse(items=[ItemRead.model_validate(i) for i in new_items])


@router.get("/{document_id}/export")
async def export_document(
    document_id: str,
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    stmt = (
        select(Document)
        .where(Document.id == document_id)
        .options(selectinload(Document.items).selectinload(Item.offers))
    )
    document = (await session.execute(stmt)).scalar_one_or_none()
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")

    data = build_xlsx(document, list(document.items))
    from io import BytesIO

    return StreamingResponse(
        BytesIO(data),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": (
                f'attachment; filename="tender_{document.id}.xlsx"'
            )
        },
    )
