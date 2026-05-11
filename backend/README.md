# Tender Finder Backend

FastAPI бэкенд для парсинга ТЗ и поиска по поставщикам.

## Локальный запуск

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

cp .env.example .env
# отредактируйте .env

uvicorn app.main:app --reload --port 8000
```

API доступно на http://localhost:8000, документация (Swagger) на http://localhost:8000/docs.

## Тесты

```bash
pytest
```

## Линт

```bash
ruff check .
ruff format .
```
