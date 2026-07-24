from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Publiek bekende dev-fallback: mag NOOIT buiten development gebruikt worden,
# anders kan iedereen sessie-cookies vervalsen (zie _guard_secret_key).
_DEV_SECRET = "dev-only-change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    secret_key: str = _DEV_SECRET
    tz: str = "Europe/Brussels"

    @model_validator(mode="after")
    def _guard_secret_key(self) -> "Settings":
        """Weiger te starten met een onveilige SECRET_KEY buiten development.

        De app staat publiek bereikbaar (Cloudflare Tunnel); met de bekende
        dev-fallback of een te korte sleutel kan iedereen sessie-cookies smeden.
        RuntimeError (geen ValueError) zodat pydantic hem rauw laat doorbubbelen
        en de app hard crasht in plaats van door te starten.
        """
        if self.app_env == "development":
            return self
        if self.secret_key == _DEV_SECRET or len(self.secret_key) < 32:
            raise RuntimeError(
                "Onveilige SECRET_KEY: zet in .env een lange random waarde "
                "(min. 32 tekens, bv. `openssl rand -hex 32`). De app weigert "
                f"te starten met app_env={self.app_env!r} zonder veilige sleutel."
            )
        return self

    database_url: str = "sqlite:///./data/db/huishouden.db"

    simon_email: str = ""
    simon_password_hash: str = ""
    jozefien_email: str = ""
    jozefien_password_hash: str = ""

    # Eigen rekening-IBAN's (nooit in de repo): CSV-rekeningkoppeling en
    # detectie van interne overschrijvingen. Leeg = rekening zonder IBAN.
    account_iban_kbc_zicht: str = ""
    account_iban_kbc_spaar: str = ""
    account_iban_fortis_zicht: str = ""
    account_iban_fortis_spaar: str = ""
    account_iban_jozefien_zicht: str = ""

    session_cookie_name: str = "huishouden_session"
    # 7 dagen: kort genoeg voor een publiek bereikbare app met financiële data;
    # geldt voor de cookie (max_age) én de servercheck (sessions.parse_session_value).
    session_max_age_days: int = 7
    session_cookie_secure: bool = True

    # Rate limiting op de login: vanaf `max_attempts` mislukte pogingen wordt
    # het IP/account geblokkeerd met oplopende wachttijd (base × 2^extra, gecapt).
    login_max_attempts: int = 5
    login_block_base_seconds: int = 30
    login_block_max_seconds: int = 900

    price_fetch_enabled: bool = True
    price_fetch_hour: int = 18

    # Weekmenu: Claude API voor recept-parsing (URL-fallback + vision).
    # Lege key = AI-parsing uitgeschakeld (parse-endpoint geeft dan 503 voor die paden).
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-haiku-4-5"

    # Financiën-import: AI-fallback voor categorisatie. Rijen die noch door een regel
    # noch door de historiek herkend worden, gaan (tegenpartij + omschrijving) naar de
    # Claude API voor een suggestie. Uitschakelbaar — dan blijven regels + historiek over,
    # zonder enige externe call. Een lege anthropic_api_key schakelt de laag sowieso uit.
    import_ai_categorization_enabled: bool = True

    # Weekmenu: map voor receptfoto's. Leeg = dev-fallback (backend/data/recipe_photos);
    # in Docker overschreven naar /data/recipe_photos (het gemounte volume, zie
    # docker-compose.yml), anders verdwijnen foto's bij een container-rebuild.
    weekmenu_photos_dir: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
