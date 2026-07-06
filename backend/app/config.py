from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    secret_key: str = "dev-only-change-me"
    tz: str = "Europe/Brussels"

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
    session_max_age_days: int = 30
    session_cookie_secure: bool = True

    price_fetch_enabled: bool = True
    price_fetch_hour: int = 18


@lru_cache
def get_settings() -> Settings:
    return Settings()
