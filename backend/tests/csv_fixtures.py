"""Geanonimiseerde CSV-fixtures die de echte bankexport-quirks repliceren.

Bewust bytes-constanten in code en geen .csv-bestanden: git/editor-normalisatie
van regeleindes zou de KBC-\r-rijscheiding en de Fortis-BOM stukmaken. De
IBAN's en namen zijn fictief; de structuur (kolommen, padding, lege
tegenpartij bij kaartbetalingen, statusveld) volgt de echte exports exact.
"""

from __future__ import annotations

FORTIS_ACCOUNT = "BE68539007547034"
KBC_ACCOUNT = "BE71096123456769"

FORTIS_HEADER = (
    "Volgnummer;Uitvoeringsdatum;Valutadatum;Bedrag;Valuta rekening;Rekeningnummer;"
    "Type verrichting;Tegenpartij;Naam van de tegenpartij;Mededeling;Details;Status;"
    "Reden van weigering"
)

KBC_HEADER = (
    "Rekeningnummer;Rubrieknaam;Naam;Munt;Afschriftnummer;Datum;Omschrijving;Valuta;"
    "Bedrag;Saldo;credit;debet;rekeningnummer tegenpartij;BIC tegenpartij;"
    "Naam tegenpartij;Adres tegenpartij;gestructureerde mededeling;Vrije mededeling"
)


def fortis_row(
    *,
    volgnummer: str = "2026-00100",
    datum: str = "15/06/2026",
    valutadatum: str | None = None,
    bedrag: str = "-50,00",
    rekening: str = FORTIS_ACCOUNT,
    verrichting: str = "Overschrijving in euro",
    tegenpartij: str = "BE20914001278412",
    naam: str = "TESTPARTIJ NV",
    mededeling: str = "test mededeling",
    details: str = "OVERSCHRIJVING IN EURO OP REKENING TESTPARTIJ NV",
    status: str = "Geaccepteerd",
    reden: str = "",
) -> str:
    return ";".join(
        [
            volgnummer,
            datum,
            valutadatum or datum,
            bedrag,
            "EUR",
            rekening,
            verrichting,
            tegenpartij,
            naam,
            mededeling,
            details,
            status,
            reden,
        ]
    )


def fortis_card_row(
    *,
    volgnummer: str = "2026-00101",
    datum: str = "26/06/2026",
    bedrag: str = "-5,20",
    merchant: str = "BAKKERIJ DE MIK EKE",
    merchant_datum: str = "26/06/2026",
) -> str:
    """Kaartbetaling: lege tegenpartij/naam/mededeling, merchant in Details."""
    details = (
        f"BETALING MET DEBETKAART NUMMER 4871 04XX XXXX 8258 {merchant} "
        f"{merchant_datum} VISA DEBIT - Google Pay BANKREFERENTIE : 2606271301289954 "
        f"VALUTADATUM : {merchant_datum}"
    )
    return fortis_row(
        volgnummer=volgnummer,
        datum=datum,
        bedrag=bedrag,
        verrichting="Kaartbetaling",
        tegenpartij="",
        naam="",
        mededeling="",
        details=details,
    )


def fortis_csv(rows: list[str], *, bom: bool = True) -> bytes:
    text = "\r\n".join([FORTIS_HEADER, *rows]) + "\r\n"
    return text.encode("utf-8-sig" if bom else "utf-8")


def kbc_row(
    *,
    rekening: str = KBC_ACCOUNT,
    naam: str = "TESTER T. - PARTNER P.",
    afschrift: str = "02026100",
    datum: str = "13/06/2026",
    omschrijving: str = "OVERSCHRIJVING VAN TESTPARTIJ",
    valuta: str = "15/06/2026",
    bedrag: str = "-9,66",
    saldo: str = "544,81",
    tegenpartij_rek: str = "",
    tegenpartij_bic: str = "",
    tegenpartij_naam: str = "",
    gestructureerd: str = "",
    vrij: str = "",
) -> str:
    """Eén KBC-rij mét de padding-spaties uit de echte export."""
    negatief = bedrag.startswith("-")
    velden = [
        rekening,
        " " * 50,  # Rubrieknaam: in de echte export louter spaties
        naam,
        "EUR",
        f"  {afschrift}",
        datum,
        omschrijving,
        valuta,
        bedrag,
        saldo,
        (" " * 14) if negatief else bedrag,  # credit
        bedrag if negatief else (" " * 14),  # debet
        tegenpartij_rek.ljust(34),
        tegenpartij_bic.ljust(11),
        tegenpartij_naam.ljust(71),
        " " * 71,  # Adres tegenpartij
        gestructureerd.ljust(35),
        vrij.ljust(140),
    ]
    return ";".join(velden)


def kbc_card_row(
    *,
    afschrift: str = "02026101",
    datum: str = "26/06/2026",
    valuta: str = "29/06/2026",
    bedrag: str = "-16,00",
    saldo: str = "217,12",
    merchant: str = "SPEELGOEDWINKEL NOORD",
    plaats: str = "BE9070 DESTELBERGEN",
    winkelnummer: str = "",
) -> str:
    """Bancontact-betaling: lege tegenpartijkolommen, merchant in Omschrijving."""
    nummer = f"{winkelnummer} " if winkelnummer else ""
    omschrijving = (
        f"BETALING VIA BANCONTACT              29-06 {datum} OM 18.53 UUR "
        f"{nummer}{merchant} {plaats} MET KBC-DEBETKAART 5127 88XX XXXX 1425 "
        f"KAARTHOUDER: TESTER THOMAS"
    )
    return kbc_row(
        afschrift=afschrift,
        datum=datum,
        omschrijving=omschrijving,
        valuta=valuta,
        bedrag=bedrag,
        saldo=saldo,
    )


def kbc_domiciliering_row(
    *,
    afschrift: str = "02026102",
    datum: str = "19/06/2026",
    bedrag: str = "-23,23",
    schuldeiser: str = "MOBILE VIKINGS",
    tegenpartij_rek: str = "BE99 0000 1111 2222",
) -> str:
    """Europese domiciliëring: IBAN wél, naam alleen in de Omschrijving-tekst."""
    omschrijving = (
        f"EUROPESE DOMICILIERING               19-06 SCHULDEISER     : {schuldeiser} "
        f"REF. SCHULDEISER: 525785625362H-HDBIT MANDAATREFERTE  : 001736898 "
        f"MEDEDELING      : SCOR                   BBA                   525785625362"
    )
    return kbc_row(
        afschrift=afschrift,
        datum=datum,
        omschrijving=omschrijving,
        bedrag=bedrag,
        tegenpartij_rek=tegenpartij_rek,
        tegenpartij_bic="KREDBEBB",
    )


def kbc_csv(rows: list[str]) -> bytes:
    """Rijen gescheiden door \r zónder \n, zoals de echte KBC-export."""
    return "\r".join([KBC_HEADER, *rows]).encode("utf-8")
