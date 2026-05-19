"""Pydantic schemas for API request/response bodies."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class OfferRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    position: int
    title: str
    url: str
    supplier_domain: str | None
    snippet: str | None
    price: str | None
    contact_phone: str | None
    contact_email: str | None


class SpecComparisonRead(BaseModel):
    name: str
    required: str | None = None
    found: str | None = None
    status: str = "unknown"
    note: str | None = None


class ProductMatchRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    position: int
    hypothesis_brand: str | None
    hypothesis_model: str | None
    hypothesis_description: str | None
    hypothesis_reasoning: str | None
    search_query: str | None
    found_title: str | None
    found_url: str | None
    found_domain: str | None
    found_snippet: str | None
    found_price: str | None
    specs_compared: list[SpecComparisonRead] | None = None
    match_score: int | None
    verdict: str | None
    summary: str | None


class MatchResponse(BaseModel):
    item_id: str
    matches: list[ProductMatchRead]


class ItemBase(BaseModel):
    name: str
    quantity: float | None = None
    unit: str | None = None
    gost: str | None = None
    okpd2: str | None = None
    specifications: dict[str, Any] | None = None
    notes: str | None = None
    search_query: str | None = None


class ItemRead(ItemBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    document_id: str
    position: int
    offers: list[OfferRead] = Field(default_factory=list)
    matches: list[ProductMatchRead] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class ItemUpdate(BaseModel):
    name: str | None = None
    quantity: float | None = None
    unit: str | None = None
    gost: str | None = None
    okpd2: str | None = None
    specifications: dict[str, Any] | None = None
    notes: str | None = None
    search_query: str | None = None


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    filename: str
    mime_type: str | None
    size_bytes: int
    status: str
    error: str | None
    created_at: datetime
    updated_at: datetime
    items: list[ItemRead] = Field(default_factory=list)


class DocumentSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    filename: str
    status: str
    size_bytes: int
    created_at: datetime
    updated_at: datetime
    items_count: int = 0


class ExtractionResponse(BaseModel):
    items: list[ItemRead]


class SearchResponse(BaseModel):
    item_id: str
    offers: list[OfferRead]


class ProviderHealth(BaseModel):
    provider: str
    model: str
    healthy: bool
