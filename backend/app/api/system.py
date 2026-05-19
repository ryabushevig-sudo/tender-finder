"""System API: health checks and provider info."""
from __future__ import annotations

from fastapi import APIRouter

from app.api.schemas import ProviderHealth
from app.core.config import settings
from app.services.llm import get_llm_provider

router = APIRouter(prefix="/api/system", tags=["system"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/llm", response_model=ProviderHealth)
async def llm_health() -> ProviderHealth:
    provider_name = settings.llm_provider
    if provider_name == "ollama":
        model = settings.ollama_model
    elif provider_name == "openrouter":
        model = settings.openrouter_model
    else:
        model = "unknown"
    try:
        provider = get_llm_provider()
        healthy = await provider.health()
    except Exception:
        healthy = False
    return ProviderHealth(provider=provider_name, model=model, healthy=healthy)
