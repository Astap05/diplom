# Airport RMS – Backend

FastAPI backend for the Airport Resource Management System.

## Требования

- Python 3.10–3.13 (рекомендуется 3.11 или 3.12; на Windows с Python 3.13 зависимости подобраны под готовые колёса).
- **SQLite (по умолчанию)** — ничего устанавливать не нужно, БД создастся как файл `backend/airport_rms.db`.
- PostgreSQL (опционально, если захотите “как в проде”).

## Установка

1. Создайте виртуальное окружение и активируйте его (рекомендуется Python 3.11 или 3.12, если 3.13 даёт ошибки).
2. Скопируйте `.env.example` в `.env` и при необходимости измените `DATABASE_URL`.
3. Установите зависимости и запустите:

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Используется драйвер **psycopg (v3)** и актуальные версии Pydantic, чтобы установка проходила на Python 3.13 под Windows без сборки из исходников и без `libpq.lib`.

По умолчанию `DATABASE_URL` указывает на SQLite, поэтому PostgreSQL/pgAdmin не требуются.

API docs: http://localhost:8000/docs

## API

- **Flights:** `GET/POST /api/v1/flights`, `GET/PATCH/DELETE /api/v1/flights/{id}`
- **Resources:** `GET/POST /api/v1/resources`, `GET/PATCH/DELETE /api/v1/resources/{id}`
