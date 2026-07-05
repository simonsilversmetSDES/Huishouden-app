from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.config import Settings

_SALT = "huishouden-session"


def _serializer(settings: Settings) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.secret_key, salt=_SALT)


def create_session_value(user_id: int, settings: Settings) -> str:
    return _serializer(settings).dumps({"uid": user_id})


def parse_session_value(
    value: str, settings: Settings, max_age_seconds: int | None = None
) -> int | None:
    if max_age_seconds is None:
        max_age_seconds = settings.session_max_age_days * 86400
    try:
        data = _serializer(settings).loads(value, max_age=max_age_seconds)
    except (BadSignature, SignatureExpired):
        return None
    uid = data.get("uid") if isinstance(data, dict) else None
    return uid if isinstance(uid, int) else None
