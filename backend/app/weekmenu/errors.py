"""Nette, frontend-toonbare fouten voor Weekmenu — nooit een kale 500.

De router vertaalt ``WeekmenuError`` naar ``HTTPException`` met
``detail = {"code": ..., "message": ...}`` (NL-boodschap voor de gebruiker).
"""


class WeekmenuError(Exception):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
