# Лабораторна робота 1 — CRUD-сервіс /lab-results

Варіант 4: результат лабораторного аналізу. Сервіс на Python 3.12 + FastAPI, база PostgreSQL 16, балансувальник nginx, усе в Docker Compose.

## Запуск

Потрібен Docker Desktop.

```
copy .env.example .env
docker compose up -d --build
```


Стенд піднімається на http://localhost:8000. Схема бази накочується автоматично з `db/schema.sql`.

Перевірка:

- http://localhost:8000/healthz — відповідь 200, якщо база доступна (503, якщо ні);
- http://localhost:8000/docs — документація API;
- `docker compose ps` — db і web у стані healthy.

## Два вебінстанси

```
docker compose up -d --scale web=2
docker compose up -d --force-recreate --no-deps lb
```

Друга команда перестворює балансувальник, щоб він отримав адреси обох інстансів.

## Навантаження

```
python loadgen\loadgen.py seed
python loadgen\loadgen.py check
python loadgen\loadgen.py series --instances 1
```

Сирі результати прогонів лежать у `results/raw`.

## Зупинка

```
docker compose down     
docker compose down -v 
```

## Структура

- `app/` — код сервісу (`main.py`) і скрипт healthcheck (`healthcheck.py`)
- `db/schema.sql` — схема таблиці
- `lb/nginx.conf` — конфігурація балансувальника
- `loadgen/` — генератор навантаження
- `scripts/` — допоміжні скрипти (перевірка циклу CRUD, розбір затримки)
- `results/` — результати вимірювань
- `Dockerfile`, `.dockerignore`, `docker-compose.yml`, `.env.example`

Звіт: [report.md](report.md)
