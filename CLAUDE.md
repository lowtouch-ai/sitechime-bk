# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

SiteChime Backend — a Django 5.1 + Django REST Framework API backend providing JSON data storage with public sharing, an OpenAI-compatible reverse proxy with streaming, JSON/YAML format conversion, and Terms & Conditions tracking. Uses PostgreSQL 14, Redis 7, and Gunicorn.

## Local Dev Prerequisites

PostgreSQL and Redis are provided by external containers from the `agentomatic` stack, not by this project's docker-compose. PostgreSQL runs inside the `agentconnector` container; Redis runs in its own container within that stack. The developer must ensure those containers are running before starting this app. Do not start duplicate db/redis services from this repo.

## Commands

**All commands run inside Docker containers. Do not install dependencies or run Django commands directly on the host VM.**

```bash
docker-compose up --build          # Build and start the web service
docker-compose up                  # Start without rebuilding
docker-compose down                # Stop services
```

### Migrations
```bash
docker-compose exec web python manage.py makemigrations
docker-compose exec web python manage.py migrate
```

### Testing
```bash
docker-compose exec web python manage.py test              # Run all tests
docker-compose exec web python manage.py test api           # Run api app tests
```

### Other management commands
```bash
docker-compose exec web python manage.py createsuperuser
docker-compose exec web python manage.py collectstatic --noinput
```

## Architecture

### Django project: `cloudcontrol_widget_backend/`
Settings, root URL config, WSGI/ASGI entry points. Root URLs mount `/admin/` and `/api/`.

### Main app: `api/`
Single Django app containing all API logic:

- **Models**: `JsonData` (user-scoped JSON storage with UUID-based public sharing) and `TncAcceptance` (IP-based T&C tracking)
- **Views**: `JsonDataViewSet` (CRUD + make_public/make_private actions), `OpenAIProxyView` (rate-limited streaming reverse proxy), `TncAcceptanceViewSet` (admin-only), plus standalone views for public data access and T&C endpoints
- **Serializers**: `JsonDataSerializer`, `PublicJsonDataSerializer`, `TncAcceptanceSerializer`
- **`converters/`**: Sub-module with views for JSON↔YAML conversion via URL fetching with Redis caching (1hr TTL)

### Utilities: `utils/`
- `logger.py`: Pre-configured loggers (`api_logger`, `security_logger`, `db_logger`, `django_logger`) using rotating file handlers
- `converters.py`: `json_to_yaml()` and `yaml_to_json()` conversion functions

### Authentication
Four auth methods configured: JWT (60-min access tokens via simplejwt), Session, Basic, and custom UUID-based auth (via `X-Config-Key` header or `Authorization: Bearer <uuid>`). The OpenAI proxy authenticates requests by looking up a `JsonData` record matching the provided UUID.

### Key patterns
- **User-scoped data**: `JsonDataViewSet.get_queryset()` filters to `request.user` — users only see their own data
- **OpenAI proxy**: `OpenAIProxyView` streams responses from `OPENAI_PROXY_URL` with `OPENWEBUI_API_TOKEN`, forwards `X-LTAI-EXT-*` headers upstream, supports `BENCHMARK_MODE` for static test responses
- **Rate limiting**: django-ratelimit with Redis backend; OpenAI proxy limited to 1 req/min per user on POST
- **CORS**: Allows all origins. `X-LTAI-EXT-*` headers are dynamically allowed via `DynamicExtHeaderCorsMiddleware` (`api/middleware.py`) — any header matching the `x-ltai-ext-*` prefix is automatically permitted in CORS preflight without needing to be listed in `CORS_ALLOW_HEADERS`. This middleware must remain **before** `CorsMiddleware` in the `MIDDLEWARE` stack.
- **Logging**: Separate rotating log files in `logs/` — django.log, security.log, db.log (10MB max, 5 backups)

### URL structure
```
/admin/                              Django admin
/api/json-data/                      JsonData CRUD (authenticated)
/api/json-data/{id}/make_public/     Make data publicly accessible
/api/json-data/{id}/make_private/    Revoke public access
/api/json-data/names/                List unique data names
/api/public/json-data/{uuid}/        Public data access (no auth)
/api/tnc/accept/                     Record T&C acceptance (no auth)
/api/tnc/check/{config_id}/          Check T&C status (no auth)
/api/tnc-records/                    T&C records (admin only)
/api/openai/{path}                   OpenAI proxy (UUID auth)
/api/convert/json-to-yaml/?url=      JSON→YAML converter (no auth)
/api/convert/yaml-to-json/?url=      YAML→JSON converter (no auth)
```

### Infrastructure
- **Docker services**: This repo only runs the `web` service (Django/Gunicorn, port 8001). PostgreSQL (in the `agentconnector` container) and Redis are external containers from the `agentomatic` stack and must already be running.
- **Networking**: The web container uses host networking (`network_mode: "host"`). It reaches PostgreSQL and Redis via `localhost` through their host port mappings (PostgreSQL on 5432, Redis on 6379). Gunicorn binds to port 8001 (port 8000 is taken by `agentconnector`).
- **entrypoint.sh**: Waits for PostgreSQL, runs migrations, collectstatic, creates superuser if env vars set, then starts Gunicorn with 4 workers
- **PostgreSQL compatibility**: Django is pinned to `>=5.1.6,<5.2` because the `agentconnector` container runs PostgreSQL 13 (Django 5.2+ requires PostgreSQL 14).

## Reverse Proxy Session Token Validation

The Django `OpenAIProxyView` validates the host application's OIDC session token before forwarding any request to the AI backend. This is the security choke point — all widget chat requests pass through here.

### How it works

The host application extracts its OIDC access token from `sessionStorage` and passes it as `X-LTAI-EXT-API-TOKEN` on every request. The proxy validates that token before forwarding:

```
Host App → X-LTAI-EXT-API-TOKEN header → Django proxy → validate → AI backend
```

### Key files

- **`api/token_validator.py`** — core validation module. Two strategies:
  - `jwt_local` — verifies JWT signature offline using JWKS public keys (cached 15 min). No per-request network call.
  - `oidc_introspect` — calls RFC 7662 introspection endpoint per request. Detects revoked tokens.
  - `none` — always passes (local dev without an OIDC provider).
- **`api/views.py`** — `OpenAIProxyView.dispatch()` calls the validator after benchmark mode check, before UUID auth.

### Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `PROXY_TOKEN_VALIDATION_ENABLED` | `0` | Master switch — set to `1` to enable |
| `PROXY_TOKEN_VALIDATION_STRATEGY` | `jwt_local` | `jwt_local`, `oidc_introspect`, or `none` |
| `PROXY_TOKEN_VALIDATION_FAILURE_MODE` | `closed` | `closed` = reject on validator error; `open` = allow |
| `OIDC_JWKS_URI` | — | Auth provider's JWKS public key endpoint |
| `OIDC_JWT_ISSUER` | — | Expected `iss` claim in the token |
| `OIDC_JWT_AUDIENCE` | — | Expected `aud` claim (optional) |
| `OIDC_INTROSPECTION_ENDPOINT` | — | For `oidc_introspect` strategy only |

### Example config (OIDC provider)

```
PROXY_TOKEN_VALIDATION_ENABLED=1
PROXY_TOKEN_VALIDATION_STRATEGY=jwt_local
OIDC_JWKS_URI=https://<your-auth-provider>/.well-known/jwks.json
OIDC_JWT_ISSUER=https://<your-auth-provider>/
```

The JWKS URI can be discovered from the provider's OpenID Connect discovery document at `<issuer>/.well-known/openid-configuration`. Ensure the token signing algorithm matches a key in the JWKS (e.g. RS256).

### Testing

1. Obtain a valid access token from the host application's session storage
2. `curl -s -w "\nHTTP %{http_code}" -X POST http://127.0.0.1:8001/api/openai/api/chat/completions -H "X-LTAI-EXT-API-TOKEN: <token>" -H "X-Config-Key: test" -H "Content-Type: application/json" -d '{"model":"test","messages":[{"role":"user","content":"hi"}]}'`
3. Check `docker exec sitechime-bk-web-1 tail -10 /app/logs/security.log` for results

### No-break guarantee

- `PROXY_TOKEN_VALIDATION_ENABLED` defaults to `0` — existing deployments unaffected until opted in
- Benchmark mode short-circuits before the validation gate
- Strategy `none` available for local dev
