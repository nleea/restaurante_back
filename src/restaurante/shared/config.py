"""Configuración de la aplicación, cargada desde variables de entorno / .env."""

from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Secreto JWT por defecto: NUNCA debe usarse fuera de `debug`/desarrollo.
_INSECURE_DEFAULT_SECRET = "3d9bada11447945502abc576afa73f8b4523c1ee61d80c9e82f60775239b4eae"
# Longitud mínima para HS256 (RFC 7518 §3.2: >= 32 bytes).
_MIN_JWT_SECRET_LENGTH = 32


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Aplicación
    app_name: str = "Restaurante API"
    debug: bool = False
    # Dominio base para resolver el tenant: <slug>.<base_domain>
    base_domain: str = "api.local"

    # CORS: el navegador exige que la API autorice el origen del front. El front corre en
    # <slug>.<base_domain>:<port> (un subdominio por tenant), por lo que un patrón (regex)
    # cubre todos los subdominios de tenant. El valor por defecto habilita cualquier
    # *.localhost en cualquier puerto (desarrollo); en producción defina
    # CORS_ALLOW_ORIGIN_REGEX con el/los dominio(s) reales del front.
    cors_allow_origin_regex: str = r"https?://([a-z0-9-]+\.)?localhost(:\d+)?"

    # Base de datos (SQLAlchemy async)
    database_url: str = (
        "postgresql+asyncpg://restaurante:restaurante@localhost:5432/restaurante"
    )

    # JWT
    jwt_secret: str = _INSECURE_DEFAULT_SECRET
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    # Cache: backend "memory" (per process, dev/tests) or "redis" (distributed).
    #
    # The geocoder needs "redis" wherever it really runs, and this is not a preference. Its
    # resolver is a separate, restarted process, so a per-process cache is thrown away on
    # every run: measured, "memory" re-spends 2 provider requests every pass where "redis"
    # spends 0 after the first. With "memory" the branch-city lookup costs one request per
    # run instead of one per branch, and an address that matches nothing is re-queried
    # forever against providers that allow ~1 req/s. "memory" is for tests and for a dev box
    # with no Redis — it is not an optimisation.
    cache_backend: str = "memory"
    redis_url: str = "redis://localhost:6379/0"
    cache_ttl_seconds: int = 300

    # Geocoding: turn a delivery address into an approximate map pin. Provider is swappable
    # ("nominatim" today, e.g. self-hosted "photon" later; "none" disables geocoding). The
    # public Nominatim policy requires a valid User-Agent identifying the app + a contact.
    geocoder_provider: str = "nominatim"
    nominatim_url: str = "https://nominatim.openstreetmap.org"
    nominatim_user_agent: str = "restaurante-app/1.0 (contacto: admin@example.com)"
    geocode_cache_ttl_seconds: int = 60 * 60 * 24 * 30  # 30 days; streets don't move

    # Overpass answers what Nominatim cannot: the node two named streets share, i.e. the
    # corner a Colombian address is measured from. Worth 555 m of accuracy on a real address.
    # The public instance is free, has no SLA, and shed 1 probe request in 3 — self-hosting
    # the Colombia extract is the answer if delivery ever depends on this. Set to "" to skip
    # corner lookups and keep the street-level pin.
    overpass_url: str = "https://overpass-api.de"
    overpass_cache_ttl_seconds: int = 60 * 60 * 24 * 30  # 30 days; corners don't move either

    # The pin resolver's periodic pass: how many records it takes, and how often it runs. It
    # is the guarantee — every pin-less record with an address is found here eventually, with
    # or without a queued job. The bound keeps a pass finishing; the cadence is a floor on how
    # long a lost announcement can leave a record pin-less.
    #
    # There is deliberately NO concurrency setting. The providers allow ~1 req/s and punish a
    # breach with a silent ban rather than an error, so one-at-a-time is a property of the
    # design (`max_jobs = 1`, exactly one worker), not something a deployment may tune.
    geocode_sweep_limit: int = 50
    geocode_sweep_minute_step: int = 1

    # Cloudflare R2 (S3-compatible) object storage for business images (logos). Empty by
    # default → uploads disabled (the /media/presign endpoint returns a clear error). Set all
    # of these in production. `r2_public_base_url` is the bucket's public base — its r2.dev URL
    # or a custom domain — used to build the object's public URL after upload.
    
    storage: str = "r2"
    r2_account_id: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_bucket: str = ""
    r2_public_base_url: str = ""
    # Optional explicit S3 endpoint (e.g. a jurisdiction-specific R2 host). When empty the
    # standard `<account_id>.r2.cloudflarestorage.com` is used. Whatever host is used here is
    # both signed and where the browser PUTs, so they always match.
    r2_endpoint_url: str = ""

    # WhatsApp bridge (unofficial). `whatsapp_bridge_base_url` empty → outbound disabled;
    # the gateway says so instead of failing obscurely.
    #
    # OPERATIONAL WARNING: the bridge — not this service — owns the pairing credentials for
    # every branch's number. That state MUST persist outside the pod (a volume or an external
    # store). If it lives in the container filesystem, a redeploy unpairs every tenant at
    # once and every branch has to rescan its QR before it can receive a message again. We
    # deliberately store no auth material here: only the instance reference and a status.
    whatsapp_bridge_base_url: str = ""
    whatsapp_bridge_api_key: str = ""
    whatsapp_bridge_timeout_seconds: float = 10.0
    # Shared secret the bridge presents on the inbound webhook. Empty → the webhook rejects
    # everything, which is the safe default for an endpoint with no user authentication.
    whatsapp_webhook_secret: str = ""
    # Silence after which a new inbound message opens a fresh conversation instead of
    # joining the old one. 24h matches how people think about a WhatsApp chat.
    whatsapp_conversation_idle_hours: int = 24
    # Cómo nos ve el puente DESDE FUERA. Evolution corre en otra máquina, así que un
    # `localhost` aquí significa que sus webhooks se los manda a sí mismo y ningún mensaje
    # entra nunca — sin error visible en ningún lado.
    whatsapp_public_base_url: str = ""
    # Dominio público donde se sirve la CARTA, SIN el subdominio del tenant: el slug de
    # cada tenant se antepone al construir el enlace.
    #
    #     STOREFRONT_BASE_URL=https://wsquote.uk  →  https://demo.wsquote.uk/store/centro
    #     STOREFRONT_BASE_URL=http://localhost:5173  →  http://demo.localhost:5173/store/…
    #
    # NO puede ser una URL fija con tenant incluido: el enlace es un dato POR TENANT, y una
    # sola URL global mandaría a los clientes de un negocio a la carta de otro. El front
    # deduce el tenant del subdominio del navegador (`lib/http.ts`), así que el subdominio
    # correcto no es cosmético — es lo único que identifica de quién es la carta.
    storefront_base_url: str = ""

    # La zona horaria del negocio. Los horarios de atención se guardan como minutos desde
    # medianoche EN HORA LOCAL de la sede, así que responder "¿está abierto ahora?" exige
    # saber qué hora es allí. Sin esto se comparaban contra UTC, y en Colombia (UTC-5) eso
    # significa que a las 3 de la tarde el sistema creía que eran las 20:00 —cerrado— y a
    # partir de las 7 de la tarde hasta el DÍA de la semana estaba corrido.
    #
    # Es un ajuste de despliegue y no un campo por tenant a propósito: hoy todos los
    # negocios están en Colombia. El día que uno no lo esté, esto se muda al Perfil del
    # negocio y este valor pasa a ser el de por defecto.
    timezone: str = "America/Bogota"

    # --- Asistente (LLM) -----------------------------------------------------------------
    # La credencial es NUESTRA, no del tenant: compramos los tokens al por mayor y los
    # revendemos, así que el que arde en un bucle es nuestro dinero. Vacía → no se puede
    # llamar a ningún modelo, que es el estado correcto mientras nadie esté habilitado.
    assistant_api_key: str = ""
    # El INTERRUPTOR GLOBAL. Se evalúa antes que ninguna otra comprobación y no distingue
    # tenants: existe para una sola frase, "para todo ahora mismo", y por eso no se puede
    # tocar desde ninguna pantalla del producto.
    assistant_kill_switch: bool = False
    # Llamadas por minuto y tenant. Es DEFENSIVO, no comercial: contesta a "¿hay algo en
    # bucle?", no a "¿ha comprado esto?". Una cuota mensual no impide gastarse el mes en
    # cuatro minutos, y este límite no impide gastar más de lo comprado: son tres preguntas
    # distintas y hacen falta tres mecanismos.
    assistant_rate_limit_per_minute: int = 10
    # Cuántos turnos previos se mandan. Es el principal motor del coste de entrada, así que
    # es una ventana fija y pequeña, no "toda la conversación".
    assistant_history_turns: int = 6

    @model_validator(mode="after")
    def _validate_jwt_secret(self) -> "Settings":
        """Fail-closed: en producción el secreto JWT debe ser fuerte y propio.

        En un SaaS multi-tenant, un secreto débil o por defecto permite forjar
        tokens y cruzar la frontera entre tenants. Sólo se permite relajar esta
        regla con `debug=True` (desarrollo/pruebas).
        """
        if self.debug:
            return self
        if self.jwt_secret == _INSECURE_DEFAULT_SECRET:
            raise ValueError(
                "JWT_SECRET no puede usar el valor por defecto en producción. "
                "Defina un secreto propio (>= 32 bytes)."
            )
        if len(self.jwt_secret.encode("utf-8")) < _MIN_JWT_SECRET_LENGTH:
            raise ValueError(
                "JWT_SECRET es demasiado corto: se requieren al menos "
                f"{_MIN_JWT_SECRET_LENGTH} bytes para HS256 (RFC 7518)."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    """Devuelve la configuración como singleton cacheado."""
    return Settings()
