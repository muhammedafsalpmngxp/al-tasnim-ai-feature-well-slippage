"""Environment-driven configuration.

Every environment-specific value lives in backend/.env. Nothing in this file
carries a business default: thresholds, credentials, model names, hosts and
ports all come from the environment. See backend/.env.example.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[2]
SQL_DIR = BACKEND_DIR / "sql"
ENV_FILE = BACKEND_DIR / ".env"

load_dotenv(ENV_FILE, override=False)


class ConfigurationError(RuntimeError):
    """Raised when a required environment value is missing."""


def _get(*names: str, default: Optional[str] = None) -> Optional[str]:
    """First non-empty value among ``names``.

    Several names are accepted per setting so an existing .env written with
    either the canonical or a legacy key keeps working.
    """
    for name in names:
        value = os.getenv(name)
        if value is not None and value.strip() != "":
            return value.strip().strip('"').strip("'")
    return default


def _get_int(*names: str, default: int) -> int:
    raw = _get(*names)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigurationError(f"{names[0]} must be an integer, got {raw!r}") from exc


def _get_bool(*names: str, default: bool) -> bool:
    raw = _get(*names)
    if raw is None:
        return default
    return raw.lower() in {"1", "true", "yes", "y", "on"}


class Settings:
    """Resolved application settings.

    Instantiating this class never raises for a missing database credential;
    :meth:`require_database` reports that as an operational error instead, so
    the API can start and surface a clean database-error state.
    """

    def __init__(self) -> None:
        # ---- database -----------------------------------------------------
        self.db_driver = _get("DB_DRIVER")
        self.db_server = _get("DB_SERVER", "DB_HOST")
        self.db_port = _get("DB_PORT")
        self.db_database = _get("DB_DATABASE", "DB_NAME")
        self.db_username = _get("DB_USERNAME", "DB_USER", "DB_UID")
        self.db_password = _get("DB_PASSWORD", "DB_PWD")
        self.db_encrypt = _get("DB_ENCRYPT", default="yes")
        self.db_trust_server_certificate = _get(
            "DB_TRUST_SERVER_CERTIFICATE", "DB_TRUST_CERT", default="no"
        )
        self.db_connect_timeout = _get_int("DB_CONNECT_TIMEOUT", default=15)
        self.db_query_timeout = _get_int("DB_QUERY_TIMEOUT", default=60)
        self.db_ansi_codepage = _get("DB_ANSI_CODEPAGE", default="cp1252")

        # ---- api ----------------------------------------------------------
        self.api_host = _get("API_HOST", default="127.0.0.1")
        self.api_port = _get_int("API_PORT", default=8000)
        self.api_log_level = _get("API_LOG_LEVEL", default="INFO")
        self.cors_origins: List[str] = [
            origin.strip()
            for origin in (_get("CORS_ORIGINS", default="") or "").split(",")
            if origin.strip()
        ]

        # ---- presentation / behaviour thresholds --------------------------
        # Number of logical daily tasks at or below which the dashboard shows
        # individual task cards instead of grouped summaries. Configurable so
        # the decision never sits inside React.
        self.detail_view_task_threshold = _get_int(
            "DETAIL_VIEW_TASK_THRESHOLD", default=25
        )
        # Seconds a resolved day dataset stays cached in memory. 0 disables.
        self.daily_cache_ttl_seconds = _get_int("DAILY_CACHE_TTL_SECONDS", default=60)
        # Maximum wells included in the evidence payload sent to the LLM.
        self.explain_max_wells = _get_int("EXPLAIN_MAX_WELLS", default=40)
        # Maximum successful explanations kept in the in-memory cache across
        # all report dates combined, evicted oldest-first once exceeded. Not a
        # correctness knob -- correctness comes from caching by the evidence's
        # own content hash, so changed data is never served a stale answer
        # regardless of this setting. This only bounds memory in a
        # long-running process.
        self.explain_cache_max_entries = _get_int(
            "EXPLAIN_CACHE_MAX_ENTRIES", default=500
        )
        # Where the AI explanation cache persists between process restarts --
        # a dev auto-reload, a redeploy, or just stopping and re-running the
        # app. Without this the cache was only ever in memory, so every
        # restart threw away every explanation generated so far and the very
        # next request for a well already explained minutes earlier paid for
        # a fresh LLM call again. A relative path resolves against
        # BACKEND_DIR. Correctness never depends on this file surviving --
        # content-hashing (see llm_service._evidence_hash) means a stale
        # answer is never served even after arbitrarily many restarts; this
        # setting only decides whether *reusable* answers survive one.
        self.explain_cache_file = _get(
            "EXPLAIN_CACHE_FILE", default=".cache/explain_cache.json"
        )
        # Days ahead of a milestone deadline (pegging / FLAF / rig-on / rig-off)
        # at which a live well starts showing up as an "upcoming" priority
        # alert. Not a business rule -- business_rules.md defines the deadline
        # dates themselves (section 3) but not how far ahead counts as "near",
        # so this stays a configurable presentation threshold.
        self.milestone_priority_window_days = _get_int(
            "MILESTONE_PRIORITY_WINDOW_DAYS", default=7
        )
        # Maximum overdue milestones returned in the capped list (see
        # MilestonesResponse.overdue). overdue_count carries the true total.
        self.milestone_overdue_display_limit = _get_int(
            "MILESTONE_OVERDUE_DISPLAY_LIMIT", default=20
        )

        # ---- llm ----------------------------------------------------------
        self.llm_provider = _get("LLM_PROVIDER", default="groq")
        self.llm_api_key = _get("LLM_API_KEY", "GROQ_API_KEY", "api_key")
        self.llm_model = _get("LLM_MODEL", "GROQ_MODEL")
        self.llm_base_url = _get("LLM_BASE_URL")
        self.llm_timeout_seconds = _get_int("LLM_TIMEOUT_SECONDS", default=45)
        self.llm_max_tokens = _get_int("LLM_MAX_TOKENS", default=900)
        self.llm_temperature = float(_get("LLM_TEMPERATURE", default="0.2"))

        # ---- development only ---------------------------------------------
        # Never enabled by default. When true the API may serve an explicitly
        # labelled development fixture instead of the database.
        self.use_mock_data = _get_bool("USE_MOCK_DATA", default=False)

    # ------------------------------------------------------------------
    @property
    def llm_configured(self) -> bool:
        return bool(self.llm_api_key and self.llm_model)

    def require_database(self) -> None:
        missing = [
            name
            for name, value in (
                ("DB_DRIVER", self.db_driver),
                ("DB_SERVER", self.db_server),
                ("DB_DATABASE", self.db_database),
                ("DB_USERNAME", self.db_username),
                ("DB_PASSWORD", self.db_password),
            )
            if not value
        ]
        if missing:
            raise ConfigurationError(
                "Missing required database configuration in backend/.env: "
                + ", ".join(missing)
            )

    def connection_string(self) -> str:
        """ODBC connection string. Never logged, never returned by the API."""
        self.require_database()
        server = self.db_server
        if self.db_port:
            server = f"{server},{self.db_port}"
        parts = [
            f"DRIVER={{{self.db_driver}}}",
            f"SERVER={server}",
            f"DATABASE={self.db_database}",
            f"UID={self.db_username}",
            f"PWD={self.db_password}",
            f"Encrypt={self.db_encrypt}",
            f"TrustServerCertificate={self.db_trust_server_certificate}",
            f"Connection Timeout={self.db_connect_timeout}",
            # Belt and braces: the feature is read-only by design.
            "ApplicationIntent=ReadOnly",
            "APP=DailyMorningBrief",
        ]
        return ";".join(parts) + ";"

    def safe_dump(self) -> dict:
        """Configuration summary with every secret removed."""
        return {
            "db_server": self.db_server,
            "db_database": self.db_database,
            "db_driver": self.db_driver,
            "api_host": self.api_host,
            "api_port": self.api_port,
            "detail_view_task_threshold": self.detail_view_task_threshold,
            "daily_cache_ttl_seconds": self.daily_cache_ttl_seconds,
            "milestone_priority_window_days": self.milestone_priority_window_days,
            "llm_provider": self.llm_provider,
            "llm_model": self.llm_model,
            "llm_configured": self.llm_configured,
            "use_mock_data": self.use_mock_data,
        }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
