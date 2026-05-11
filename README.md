# Tender Finder

Веб-приложение для подбора товаров по тендерной документации (44-ФЗ / 223-ФЗ).

Загружаете ТЗ (DOCX / PDF / XLSX) — система извлекает структурированный список позиций с характеристиками, количествами, ГОСТами, и ищет товары на сайтах поставщиков и производителей.

## Возможности

- Загрузка тендерной документации в формате DOCX, PDF, XLSX
- Автоматическое извлечение позиций (наименование, характеристики, кол-во, ед.изм.) при помощи LLM
- Редактирование извлечённых позиций перед поиском
- Поиск товаров по сайтам поставщиков через DuckDuckGo
- Извлечение цен и контактов поставщиков со страниц результатов
- Экспорт итогового подбора в Excel

## Архитектура

- **Backend:** FastAPI (Python 3.11+)
- **Frontend:** React 18 + Vite + TypeScript + Tailwind CSS
- **Database:** SQLite (одного пользователя достаточно)
- **LLM:** адаптер с поддержкой двух провайдеров
  - `ollama` — локальная модель (по умолчанию Qwen2.5)
  - `openrouter` — облачные модели через OpenRouter (есть бесплатный тариф)
- **Парсинг документов:** python-docx, pdfplumber, openpyxl
- **Поиск по поставщикам:** DuckDuckGo HTML + httpx + selectolax/trafilatura

## Быстрый старт

### Требования

- Docker и Docker Compose
- 8 ГБ RAM минимум (для локальной LLM — желательно 16 ГБ)
- Опционально: Ollama (для локальной модели) или ключ OpenRouter

### Запуск через Docker Compose

```bash
cp backend/.env.example backend/.env
# отредактируйте backend/.env — выберите LLM_PROVIDER и укажите ключ при необходимости

docker compose up --build
```

Откройте http://localhost:5173 в браузере.

### Запуск без Docker

См. [backend/README.md](backend/README.md) и [frontend/README.md](frontend/README.md).

## Настройка LLM

### Вариант 1: локальная модель через Ollama (бесплатно, медленно на CPU)

```bash
# установить Ollama: https://ollama.com/download
ollama pull qwen2.5:3b
ollama serve
```

В `backend/.env`:

```ini
LLM_PROVIDER=ollama
OLLAMA_HOST=http://host.docker.internal:11434
OLLAMA_MODEL=qwen2.5:3b
```

### Вариант 2: OpenRouter (бесплатные модели на их тарифе)

1. Зарегистрируйтесь на https://openrouter.ai
2. Создайте ключ
3. В `backend/.env`:

```ini
LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=sk-or-...
OPENROUTER_MODEL=meta-llama/llama-3.3-70b-instruct:free
```

## Структура проекта

```
tender-finder/
├── backend/                  # FastAPI бэкенд
│   ├── app/
│   │   ├── api/              # роутеры REST API
│   │   ├── core/             # настройки, БД, логирование
│   │   ├── models/           # SQLAlchemy модели
│   │   └── services/         # парсинг, LLM, поиск, экспорт
│   ├── tests/
│   ├── pyproject.toml
│   └── Dockerfile
├── frontend/                 # React + Vite + TS
│   ├── src/
│   ├── package.json
│   └── Dockerfile
└── docker-compose.yml
```

## Статус

MVP в разработке. См. [issues](../../issues) для роадмапа.
