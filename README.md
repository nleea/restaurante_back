# Restaurante App

SaaS **multitenant** de gestión de restaurantes. Backend en **FastAPI** + **SQLAlchemy 2.0
async**, arquitectura **hexagonal** (puertos y adaptadores), tenancy **row-level** por
`tenant_id` con resolución del tenant por **subdominio**.

> Alcance funcional y decisiones de producto: ver `docs/Primer Alcance.md` y `CLAUDE.md`.

## Stack

- FastAPI · SQLAlchemy 2.0 (asyncpg) · PostgreSQL · Alembic
- JWT access + refresh (PyJWT) · Argon2 (pwdlib)
- Poetry · pytest · ruff · mypy

## Arquitectura

```
src/restaurante/
├── shared/            # núcleo transversal: config, db, tenancy, security, api
└── modules/
    └── identity/      # módulo de Identidad y Accesos (login)
        ├── domain/         # entidades, value objects, puertos (interfaces)
        ├── application/     # casos de uso + DTOs (orquesta el dominio)
        └── infrastructure/ # adaptadores: ORM, repos, API (router/schemas/deps)
```

Regla de dependencia: `API → application → domain`; `infrastructure` implementa los
puertos del `domain`. El dominio no importa frameworks.

## Puesta en marcha

```bash
cp .env.example .env                 # ajustar JWT_SECRET, etc.
docker compose up -d db              # Postgres local
poetry install
poetry run alembic upgrade head      # crea tablas tenants/branches/users/audit_logs
poetry run python -m scripts.seed    # tenant demo + admin@demo.com / admin1234
poetry run uvicorn restaurante.main:app --reload
# Y, si se usa delivery, el worker que pone los pines (ver más abajo — exactamente uno):
poetry run arq restaurante.modules.delivery.infrastructure.worker.WorkerSettings
```

El tenant se resuelve por subdominio: `Host: <slug>.<BASE_DOMAIN>` (ej. `demo.api.local`).
Para probar localmente basta enviar el header `Host`:

```bash
curl -s http://localhost:8000/auth/login \
  -H "Host: demo.api.local" -H "Content-Type: application/json" \
  -d '{"email":"admin@demo.com","password":"admin1234"}'
```

## El worker de geocodificación (hay que ejecutarlo)

Tomar un pedido guarda la dirección y responde: **nunca espera a un geocodificador**. Quien
pone el pin en el mapa es este worker, y si no corre, las entregas se quedan en
**"sin ubicación"** indefinidamente. No es opcional.

```bash
poetry run arq restaurante.modules.delivery.infrastructure.worker.WorkerSettings
```

> ### EXACTAMENTE UNO. No escalar.
>
> Nominatim y Overpass permiten ~1 petición por segundo y castigan el exceso con un **baneo
> silencioso**, no con un error. Un segundo worker no duplica el rendimiento: **deja a todos
> sin pines**, sin lanzar ninguna excepción, y el síntoma es idéntico a "Overpass va lento".
> Por eso `max_jobs = 1` está fijado en código y verificado por un test, y por eso no existe
> ninguna variable de entorno para la concurrencia. El límite es un techo de todo el sistema:
> aquí no hay nada que escalar horizontalmente, nunca.

Requiere `CACHE_BACKEND=redis` (ver `.env`). El worker es un proceso aparte y se reinicia: con
`memory` la caché se tira en cada arranque y se vuelven a gastar peticiones ya pagadas contra
proveedores de ~1 req/s. Medido: `memory` gasta 2 peticiones por pasada donde `redis` gasta 0
tras la primera.

Dentro del worker corren dos cosas, y la diferencia es todo el diseño:

- **el job `geocode_delivery`** — se anuncia al crear la entrega. Es la *inmediatez*: el pin
  llega en segundos. Se puede perder sin consecuencias.
- **la pasada `sweep_pending_geocodes`** (cron, cada minuto) — lee los registros
  (`latitude IS NULL AND btrim(address_text) <> ''`). Es la *garantía*, y es la autoridad:
  encuentra toda entrega sin pin, se haya anunciado o no. Si Redis está caído al tomar el
  pedido, si el job muere, o si algún camino futuro olvida anunciar, la pasada lo resuelve.

**Rollback** (vuelve al diseño anterior, sigue siendo válido): parar el worker y programar el
script en un timer del sistema. Es el mismo código que llama el cron, así que no cambia nada
más y los pines ya escritos siguen siendo válidos.

```bash
poetry run python -m scripts.geocode_pending [limit]   # drenaje manual y ruta de rollback
```

**Sin resolver: qué supervisa al worker.** Nada, hoy. Este repo no tiene precedente de un
proceso siempre-vivo, y un worker muerto en silencio se ve exactamente igual que un Overpass
lento. La única señal de salud es la línea de log de cada pasada
(`Geocoding sweep: N found, M resolved, K still pending`). Quien despliegue esto tiene que
decidir quién lo reinicia; la respuesta depende de cómo se despliega el backend, que no se ve
desde aquí.

## Imágenes del negocio · Cloudflare R2

La foto/logo del negocio se sube a **Cloudflare R2** (S3-compatible) mediante URLs
**prefirmadas** (SigV4, sin boto3): `POST /media/presign` devuelve una `uploadUrl` a la que el
navegador hace `PUT` del archivo directo al bucket, y la `publicUrl` final que se guarda como
`brand.logoUrl` (lo que lee el storefront). Sin estas variables, `/media/presign` responde un
error claro y la subida queda deshabilitada:

```
R2_ACCOUNT_ID=...            # <account_id> en <account_id>.r2.cloudflarestorage.com
R2_ACCESS_KEY_ID=...         # token de API de R2 (S3)
R2_SECRET_ACCESS_KEY=...
R2_BUCKET=...
R2_PUBLIC_BASE_URL=https://... # URL pública del bucket (r2.dev) o dominio propio
```

Además, en el bucket hay que habilitar **CORS** para `PUT` desde el origen del front (el
navegador sube directo a R2) y lectura pública (o un dominio público) para servir `publicUrl`.

## Comandos de desarrollo

```bash
poetry run pytest                    # tests (unit + integración con sqlite)
poetry run pytest tests/modules/identity/test_login_use_case.py::test_login_ok_emite_par_de_tokens
poetry run ruff check .              # lint
poetry run mypy src                  # tipos
poetry run alembic revision --autogenerate -m "mensaje"   # nueva migración
```
