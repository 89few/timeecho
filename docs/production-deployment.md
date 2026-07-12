# Production deployment

TimeEcho production uses both Compose files:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

Create `backend/.env` from `.env.example`, generate unique high-entropy values for every database, Redis, JWT, server-salt and encryption secret, then configure SMTP. Production validation refuses development codes, automatic phone registration, simulation and unsafe default secrets.

PostgreSQL, Redis and the API are only published on loopback. Public HTTPS/WSS traffic reaches `api:8000` through the tunnel container. `postgres_data`, `uploads_data` and `private_media_data` are named volumes and must be included in the host backup policy.

Create the first administrator with the interactive command after migrations:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml run --rm api python scripts/create_admin.py
```

Do not run backend tests against this stack. Tests refuse a database that is neither SQLite nor explicitly suffixed `_test`.

## Verification

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml ps
docker compose -f docker-compose.yml -f docker-compose.prod.yml run --rm migrate alembic current
curl --fail http://127.0.0.1:8000/health
curl --fail https://PUBLIC_HOST/health
```

Cloudflare Quick Tunnel is suitable for temporary acceptance testing, but its hostname can change whenever the tunnel process is recreated. A stable APK endpoint requires a Named Tunnel with a controlled hostname, or another stable HTTPS reverse proxy. No application code can make a changing Quick Tunnel hostname permanent.
