# Airport RMS — Диспетчерский дашборд

Интерактивный дашборд для системы управления ресурсами аэропорта (Next.js 14, App Router, Tailwind CSS, TypeScript).

## Возможности

- **Шапка:** время аэропорта, выбор даты, кнопки «Загрузить XML-расписание» и «Запустить авто-распределение».
- **Сайдбар:** список неразмещённых рейсов и конфликтов (из ответа POST /allocate).
- **Таймлайн (Gantt):** ось Y — ресурсы по типам (стойки регистрации, выходы на посадку, ленты багажа), ось X — время за выбранный день, zoom/pan. Цвет блоков: синий — норма, оранжевый — задержка, красный — конфликт.
- **Тултип:** при наведении на блок — номер рейса, авиакомпания, ВС, плановое время, EAT при задержке, codeshares.
- **Ручное изменение:** клик по блоку открывает модальное окно смены ресурса (сохранение — заглушка под будущий PATCH API).

## Запуск

```bash
cd frontend
npm install
npm run dev
```

Откройте [http://localhost:3000](http://localhost:3000).

## Данные

- По умолчанию используются **моковые данные** (см. `src/lib/mockData.ts`), чтобы проверить UI без backend.
- Чтобы подключаться к API: в корне `frontend` создайте `.env.local`:
  ```
  NEXT_PUBLIC_API_URL=http://localhost:8000
  NEXT_PUBLIC_USE_MOCK=false
  ```
  Запустите backend (`cd ../backend && uvicorn app.main:app --reload`), затем обновите страницу дашборда.

## Маппинг backend → таймлайн

- **Groups (ось Y):** из `GET /api/v1/resources` — каждая запись становится строкой; порядок по `resource_type` (check-in → gate → baggage_carousel), затем по имени.
- **Items (блоки):** из `GET /api/v1/allocations?date=...` — поля `start_time`, `end_time` → интервал блока, `resource_id` → привязка к группе, `flight_number` → подпись, `is_delayed` и флаг конфликта → цвет (оранжевый/красный).
- **Конфликты:** из `POST /api/v1/allocate` в ответе `conflicts` отображаются в сайдбаре.

## Структура

- `src/app/page.tsx` — страница дашборда, состояние и загрузка данных.
- `src/components/Header.tsx` — шапка с временем, датой и кнопками.
- `src/components/ConflictSidebar.tsx` — сайдбар неразмещённых/конфликтных рейсов.
- `src/components/ResourceTimeline.tsx` — таймлайн (vis-timeline): группы = ресурсы, элементы = аллокации.
- `src/components/ManualOverrideModal.tsx` — модальное окно ручного изменения аллокации.
- `src/lib/types.ts` — типы, совместимые с API backend.
- `src/lib/api.ts` — клиент запросов к FastAPI.
- `src/lib/mockData.ts` — моковые ресурсы, аллокации и конфликты для тестов.
