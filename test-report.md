# Tender Finder — Cloud E2E Test Report

**Date:** 2026-05-13
**Branch:** `devin/1778510677-mvp-init`
**Frontend:** https://dist-mppqrfou.devinapps.com
**Backend:** https://tender-finder-api.onrender.com
**LLM:** OpenRouter `openai/gpt-oss-120b:free`

## Summary

All 3 user-facing flows pass end-to-end on the cloud-hosted stack. The frontend (devinapps static SPA) talks to the FastAPI backend (Render Docker web service) over CORS `*`, the LLM (OpenRouter free-tier `gpt-oss-120b`) extracts 19 structured items from a real Russian-language ТЗ, supplier search returns 6 ranked offers with price/email metadata, and Excel export downloads with two populated sheets.

## Environment

| Layer | URL | Stack |
|---|---|---|
| Frontend | https://dist-mppqrfou.devinapps.com | React + Vite + TS, devinapps static |
| Backend | https://tender-finder-api.onrender.com | FastAPI + SQLite, Render Docker free plan, Oregon region |
| LLM | https://openrouter.ai/api/v1 | OpenRouter free-tier, `openai/gpt-oss-120b:free` |
| Search | DuckDuckGo HTML | No key required |

## Test 1: It should show the previously uploaded ТЗ with 19 extracted items

**Result:** PASSED

Header confirms LLM connectivity (`openrouter / openai/gpt-oss-120b:free (online)`). Document list shows the uploaded ТЗ with 19 extracted items. Table renders each item with ОКПД2, GOST (where applicable) and an auto-derived search query.

![Frontend loaded, document and items visible](https://app.devin.ai/attachments/0407bd43-5ad9-4dea-9ec9-c7dd3875b40b/screenshot_58245d049b09491e922644687204e2ac.png)

## Test 2: It should find suppliers for "Розетка двойная" via DuckDuckGo

**Result:** PASSED

Clicking *Найти* on item 9 expands the row with 6 supplier offers from `vseinstrumenti.ru`, `220.ru`, `lemanapro.ru`, and `lu.ru`. The 220.ru offer carries a parsed price (230,95 ₽) and email `sales@220.ru`. Marketplaces (WB, Ozon, Yandex.Market, Avito) are filtered out by the domain blocklist.

![Suppliers expanded under Розетка двойная](https://app.devin.ai/attachments/2bbf7f18-09b6-4f03-b853-aaadc56e3b25/screenshot_2d8a8517ca0840ab8e82c27c2ffc3fbf.png)

## Test 3: It should export all items + offers to Excel

**Result:** PASSED

Clicking *Экспорт в Excel* downloads `++++_подбор.xlsx` (11 KB) immediately. Server-side verification via `openpyxl.load_workbook` confirms two sheets: «Позиции» with 20 rows × 7 cols (1 header + 19 items) and «Предложения» with 9 rows × 9 cols (1 header + 8 offers from the supplier search).

![Excel file downloaded](https://app.devin.ai/attachments/dc41e559-76d9-490b-8719-1f2d3448d50d/screenshot_03e5dc07165c4192af15a7d74fb59b2f.png)

## Notes & known characteristics of the free-tier stack

- **Cold start:** Render free plan spins the container down after ~15 min of inactivity. The first request after a cold start takes 30–60 s; subsequent requests are fast.
- **Ephemeral storage:** Free Render plan has no persistent disk. SQLite (`./data/tender_finder.db`) and uploaded files (`./data/uploads/`) live on the container filesystem and reset on each redeploy / scale-down. Documents uploaded earlier survive within a session window but should not be relied on as long-term storage. (Switch to Neon Postgres + object store if persistence becomes a requirement.)
- **LLM throughput:** OpenRouter free `openai/gpt-oss-120b:free` extraction of a ~5 KB ТЗ took ~6 minutes on Render's 0.1 CPU container (the cloud LLM itself is fast; the bottleneck is parsing the ~3 KB JSON response on a small CPU + DuckDuckGo HTML fetches afterward). For a paid Render instance or a stronger plan this drops to seconds.
- **Truncation salvage:** With Russian text + `max_tokens=4096`, the LLM was clipping mid-JSON. Fixed by raising the default to 16000 *and* adding a tolerant parser that strips markdown fences and closes balanced prefixes when the response is truncated — so users still get partial results from a clipped response instead of a hard error.

## Reproducing

```bash
# Health checks
curl https://tender-finder-api.onrender.com/api/system/health
curl https://tender-finder-api.onrender.com/api/system/llm

# Upload a ТЗ
curl -X POST -F "file=@/path/to/tz.docx" \
  https://tender-finder-api.onrender.com/api/documents

# Extract items (may take a few minutes on free tier)
curl -X POST https://tender-finder-api.onrender.com/api/documents/{id}/extract

# Search for an item
curl -X POST https://tender-finder-api.onrender.com/api/items/{item_id}/search

# Export to Excel
curl -o tender.xlsx https://tender-finder-api.onrender.com/api/documents/{id}/export
```
