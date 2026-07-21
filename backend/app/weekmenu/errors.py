"""Nette, frontend-toonbare fouten voor Weekmenu — nooit een kale 500.

De routers vertalen ``WeekmenuError`` via ``to_http`` naar ``HTTPException`` met
``detail = {"code": ..., "message": ...}`` (NL-boodschap voor de gebruiker).
"""

from fastapi import HTTPException


class WeekmenuError(Exception):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


def to_http(exc: WeekmenuError) -> HTTPException:
    return HTTPException(
        status_code=exc.status_code, detail={"code": exc.code, "message": exc.message}
    )
