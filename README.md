# Tender Finder

Веб-приложение для подбора товаров по тендерной документации (44-ФЗ / 223-ФЗ).

Загружаете ТЗ (DOCX / PDF / XLSX) — система извлекает структурированный список позиций с характеристиками, количествами, ГОСТами, и ищет товары на сайтах поставщиков и производителей.

---

## 🚀 Быстрый старт на Windows (рекомендуется)

1. **Установите Docker Desktop**, если ещё нет:
   👉 https://www.docker.com/products/docker-desktop/
   После установки запустите Docker Desktop и подождите 30–60 секунд, пока он стартует (иконка в трее перестанет вращаться)

2. **Скачайте этот репозиторий**: на странице GitHub нажмите зелёную кнопку **Code → Download ZIP**, распакуйте архив в любую папку (например, `C:\tender-finder`)

3. **Дважды кликните `start.bat`** — он проверит Docker, поднимет все контейнеры и сам откроет браузер на http://localhost:5173

   ⏳ **Первый запуск займёт 5–15 минут** — нужно подкачать модель `qwen2.5:3b` (~2 ГБ). Последующие запуски — 10–20 секунд.

4. **Чтобы остановить** — дважды кликните `stop.bat` (данные документов и модель сохранятся).

> **Важно про железо:** при 8 ГБ RAM на время извлечения позиций лучше закрыть тяжёлые приложения (браузер можно оставить с одной вкладкой). Если будет тяжело — переключите LLM на бесплатный OpenRouter (см. ниже).

---

## Возможности

- Загрузка тендерной документации в формате DOCX, PDF, XLSX
- Автоматическое извлечение позиций (наименование, характеристики, кол-во, ед.изм.) при помощи LLM
- Редактирование извлечённых позиций перед поиском
- Поиск товаров по сайтам поставщиков через DuckDuckGo (маркетплейсы отфильтрованы)
- Извлечение цен и контактов поставщиков со страниц результатов
- Экспорт итогового подбора в Excel (два листа: Позиции + Предложения)

## Архитектура

- **Backend:** FastAPI (Python 3.11+)
- **Frontend:** React + Vite + TypeScript + Tailwind CSS (раздаётся nginx, который проксирует `/api` в backend)
- **Database:** SQLite на персистентном томе
- **LLM:** адаптер с двумя провайдерами
  - `ollama` — локальная модель (по умолчанию `qwen2.5:3b`, поднимается в Docker)
  - `openrouter` — облачные модели (есть бесплатный тариф)
- **Парсинг:** python-docx, pdfplumber, openpyxl
- **Поиск:** DuckDuckGo HTML + httpx + selectolax

## macOS / Linux

```bash
git clone https://github.com/ryabushevig-sudo/tender-finder.git
cd tender-finder
docker compose up -d --build
# дождитесь, пока model-puller подкачает модель (первый запуск 5–15 мин)
open http://localhost:5173        # macOS
xdg-open http://localhost:5173    # Linux
```

Остановить: `docker compose down`. Удалить вместе с моделью: `docker compose down -v`.

## Переключение на OpenRouter (если локальная модель медленная)

Если 3B-модель на CPU слишком медленная / слабая, переключитесь на бесплатные облачные модели OpenRouter (Llama 3.3 70B, Qwen 72B):

1. Зарегистрируйтесь на https://openrouter.ai и создайте API-ключ
2. Создайте файл `.env` в корне проекта:
   ```ini
   LLM_PROVIDER=openrouter
   OPENROUTER_API_KEY=sk-or-v1-...
   OPENROUTER_MODEL=meta-llama/llama-3.3-70b-instruct:free
   ```
3. В `docker-compose.yml` для сервиса `backend` добавьте `env_file: - .env`
4. Перезапустите: `docker compose down && docker compose up -d`

После этого можно убрать сервисы `ollama` и `model-puller` из compose, чтобы освободить ~3 ГБ RAM.

## Запуск без Docker

См. [backend/README.md](backend/README.md) и [frontend/README.md](frontend/README.md).

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
│   ├── nginx.conf            # прокси /api → backend в проде
│   └── Dockerfile
├── docker-compose.yml        # backend + frontend + ollama + model-puller
├── start.bat                 # Windows: запуск
└── stop.bat                  # Windows: остановка
```

## Статус

MVP. См. PR #1 и [issues](../../issues) для роадмапа.
