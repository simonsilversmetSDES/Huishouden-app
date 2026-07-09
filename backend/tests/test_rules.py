"""Regelengine-tests (spec §5.3, tests-first): matching, seed-regels en apply.

Semantiek: regels per context, geëvalueerd op (priority ASC, id ASC),
first-match-wins; contains/equals case-insensitive, regex met IGNORECASE,
IBAN-matching op genormaliseerd IBAN, None-velden matchen nooit.
"""

from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CategorizationRule, Category, Context, RuleContext, Transaction
from app.models.enums import (
    Categorization,
    CategoryType,
    MatchField,
    MatchType,
)
from app.seed import seed_contexts, seed_rules
from app.services.rules import MatchCandidate, apply_rules, load_rules, match_rule


def _context(db: Session, name: str = "Gemeenschappelijk") -> Context:
    return db.scalars(select(Context).where(Context.name == name)).one()


def _rule_category(db: Session, rule: CategorizationRule) -> Category:
    """Geen relationships op de modellen (conventie) — categorie expliciet ophalen."""
    category = db.get(Category, rule.category_id)
    assert category is not None
    return category


def _category(db: Session, context: Context, name: str) -> Category:
    return db.scalars(
        select(Category).where(Category.context_id == context.id, Category.name == name)
    ).one()


def _rule(
    context: Context,
    category: Category,
    *,
    field: MatchField = MatchField.DESCRIPTION,
    match_type: MatchType = MatchType.CONTAINS,
    value: str,
    priority: int = 100,
) -> CategorizationRule:
    return CategorizationRule(
        context_id=context.id,
        priority=priority,
        match_field=field,
        match_type=match_type,
        match_value=value,
        category_id=category.id,
    )


def _candidate(
    *,
    name: str | None = None,
    iban: str | None = None,
    description: str | None = None,
) -> MatchCandidate:
    return MatchCandidate(counterparty_name=name, counterparty_iban=iban, description=description)


class TestMatchRule:
    def test_contains_case_insensitive(self, seeded_db: Session) -> None:
        ctx = _context(seeded_db)
        cat = _category(seeded_db, ctx, "Boodschappen")
        rules = [_rule(ctx, cat, value="colruyt")]
        assert match_rule(rules, _candidate(description="BETALING 3815 COLRUYT GENT")) is rules[0]
        assert match_rule(rules, _candidate(description="BAKKERIJ")) is None

    def test_equals_case_insensitive(self, seeded_db: Session) -> None:
        ctx = _context(seeded_db)
        cat = _category(seeded_db, ctx, "Katten")
        rules = [
            _rule(
                ctx,
                cat,
                field=MatchField.COUNTERPARTY_NAME,
                match_type=MatchType.EQUALS,
                value="Just Russel",
            )
        ]
        assert match_rule(rules, _candidate(name="JUST RUSSEL")) is rules[0]
        assert match_rule(rules, _candidate(name="JUST RUSSEL BV")) is None

    def test_regex_ignorecase(self, seeded_db: Session) -> None:
        ctx = _context(seeded_db)
        cat = _category(seeded_db, ctx, "Internet")
        rules = [_rule(ctx, cat, match_type=MatchType.REGEX, value=r"mobile\s+vikings")]
        assert match_rule(rules, _candidate(description="SCHULDEISER : MOBILE VIKINGS")) is rules[0]

    def test_ongeldige_regex_wordt_overgeslagen(self, seeded_db: Session) -> None:
        ctx = _context(seeded_db)
        cat = _category(seeded_db, ctx, "Internet")
        kapot = _rule(ctx, cat, match_type=MatchType.REGEX, value=r"[onafgesloten", priority=10)
        vangnet = _rule(ctx, cat, value="TELENET", priority=20)
        assert match_rule([kapot, vangnet], _candidate(description="TELENET FACTUUR")) is vangnet

    def test_none_veld_matcht_nooit(self, seeded_db: Session) -> None:
        ctx = _context(seeded_db)
        cat = _category(seeded_db, ctx, "Boodschappen")
        rules = [_rule(ctx, cat, field=MatchField.COUNTERPARTY_NAME, value="COLRUYT")]
        assert match_rule(rules, _candidate(name=None, description="COLRUYT")) is None

    def test_iban_match_genormaliseerd(self, seeded_db: Session) -> None:
        ctx = _context(seeded_db)
        cat = _category(seeded_db, ctx, "Spaarrekening")
        rules = [
            _rule(
                ctx,
                cat,
                field=MatchField.COUNTERPARTY_IBAN,
                match_type=MatchType.EQUALS,
                value="be55 6666 7777 8888",
            )
        ]
        assert match_rule(rules, _candidate(iban="BE55666677778888")) is rules[0]

    def test_first_match_wins_op_prioriteit(self, seeded_db: Session) -> None:
        """load_rules sorteert op (priority, id); match_rule pakt de eerste hit."""
        ctx = _context(seeded_db)
        boodschappen = _category(seeded_db, ctx, "Boodschappen")
        huis = _category(seeded_db, ctx, "Huis & Wonen")
        laag = _rule(ctx, huis, value="ACTION", priority=50)
        hoog = _rule(ctx, boodschappen, value="ACTION", priority=100)
        seeded_db.add_all([hoog, laag])  # bewust in omgekeerde volgorde toegevoegd
        seeded_db.commit()
        rules = load_rules(seeded_db, ctx.id)
        assert match_rule(rules, _candidate(description="ACTION 2108")) is laag

    def test_load_rules_enkel_eigen_context(self, seeded_db: Session) -> None:
        gem = _context(seeded_db, "Gemeenschappelijk")
        simon = _context(seeded_db, "Simon")
        seeded_db.add(_rule(simon, _category(seeded_db, simon, "Boodschappen"), value="ALDI"))
        seeded_db.commit()
        assert load_rules(seeded_db, gem.id) == []


class TestSeedRules:
    def test_seed_regels_aangemaakt_per_context(self, seeded_db: Session) -> None:
        contexts = seed_contexts(seeded_db)
        seed_rules(seeded_db, contexts)
        seeded_db.commit()
        gem = contexts["Gemeenschappelijk"]
        rules = load_rules(seeded_db, gem.id)
        assert rules  # niet leeg
        by_value = {r.match_value: r for r in rules}
        assert _rule_category(seeded_db, by_value["COLRUYT"]).name == "Boodschappen"
        assert _rule_category(seeded_db, by_value["AUTOMATISCH SPAREN"]).type == CategoryType.SPAREN
        assert by_value["MONIZZE"].match_field == MatchField.COUNTERPARTY_NAME
        assert all(not r.created_from_correction for r in rules)

    def test_loon_regel_enkel_waar_categorie_bestaat(self, seeded_db: Session) -> None:
        """'Loon' is geseed voor Simon/Jozefien; Gemeenschappelijk heeft geen LOON-regel."""
        contexts = seed_contexts(seeded_db)
        seed_rules(seeded_db, contexts)
        seeded_db.commit()
        gem_values = {
            r.match_value for r in load_rules(seeded_db, contexts["Gemeenschappelijk"].id)
        }
        simon_rules = load_rules(seeded_db, contexts["Simon"].id)
        simon_loon = [r for r in simon_rules if r.match_value == "LOON"]
        assert "LOON" not in gem_values
        assert len(simon_loon) == 1
        loon_cat = _rule_category(seeded_db, simon_loon[0])
        assert loon_cat.name == "Loon"
        assert loon_cat.type == CategoryType.INKOMEN

    def test_seed_rules_idempotent(self, seeded_db: Session) -> None:
        contexts = seed_contexts(seeded_db)
        seed_rules(seeded_db, contexts)
        seeded_db.commit()
        eerste = seeded_db.scalars(select(CategorizationRule)).all()
        seed_rules(seeded_db, contexts)
        seeded_db.commit()
        tweede = seeded_db.scalars(select(CategorizationRule)).all()
        assert len(eerste) == len(tweede)

    def test_seed_regels_matchen_echte_omschrijvingen(self, seeded_db: Session) -> None:
        """Rooktest op teksten zoals ze uit de parsers komen."""
        contexts = seed_contexts(seeded_db)
        seed_rules(seeded_db, contexts)
        seeded_db.commit()
        rules = load_rules(seeded_db, contexts["Gemeenschappelijk"].id)
        gevallen = {
            "BETALING VIA BANCONTACT 29-06 OM 18.53 UUR 3815 COLRUYT SINT-AMAN": "Boodschappen",
            "EUROPESE DOMICILIERING SCHULDEISER : MOBILE VIKINGS": "Internet",
            "TERUGBETALING 05-06 WONINGKREDIET REFERENTIE 420-1234567-89": "Lening",
            "AUTOMATISCH SPAREN 02-06 NAAR BE55 6666 7777 8888 SPAARACTIE": "Spaarrekening",
            "EIGEN OMSCHR. : WONINGPOLIS VOOR DE EIGENAAR": "Verzekeringen / Belastingen",
        }
        for tekst, verwacht in gevallen.items():
            rule = match_rule(rules, _candidate(description=tekst))
            assert rule is not None, tekst
            assert _rule_category(seeded_db, rule).name == verwacht


class TestApplyRules:
    def _tx(
        self,
        context: Context,
        *,
        amount: str,
        description: str | None = None,
        name: str | None = None,
        internal: bool = False,
        categorization: Categorization = Categorization.UNCATEGORIZED,
    ) -> Transaction:
        bedrag = Decimal(amount)
        return Transaction(
            context_id=context.id,
            date=date(2026, 6, 15),
            amount=bedrag,
            type=CategoryType.INKOMEN if bedrag > 0 else CategoryType.UITGAVEN,
            description=description,
            counterparty_name=name,
            categorization=categorization,
            is_internal_transfer=internal,
        )

    def test_apply_zet_categorie_type_en_auto(self, seeded_db: Session) -> None:
        contexts = seed_contexts(seeded_db)
        seed_rules(seeded_db, contexts)
        gem = contexts["Gemeenschappelijk"]
        tx = self._tx(gem, amount="-100.00", description="AUTOMATISCH SPAREN NAAR SPAARACTIE")
        seeded_db.add(tx)
        seeded_db.commit()

        aantal = apply_rules(seeded_db, gem.id)
        seeded_db.commit()

        assert aantal == 1
        assert tx.category_id is not None
        category = seeded_db.get(Category, tx.category_id)
        assert category is not None and category.name == "Spaarrekening"
        assert tx.type == CategoryType.SPAREN  # type volgt de categorie
        assert tx.categorization == Categorization.AUTO

    def test_apply_slaat_interne_en_gecategoriseerde_over(self, seeded_db: Session) -> None:
        contexts = seed_contexts(seeded_db)
        seed_rules(seeded_db, contexts)
        gem = contexts["Gemeenschappelijk"]
        intern = self._tx(gem, amount="-50.00", description="COLRUYT", internal=True)
        al_manueel = self._tx(
            gem, amount="-20.00", description="COLRUYT", categorization=Categorization.MANUAL
        )
        geen_match = self._tx(gem, amount="-10.00", description="ONBEKENDE WINKEL")
        seeded_db.add_all([intern, al_manueel, geen_match])
        seeded_db.commit()

        assert apply_rules(seeded_db, gem.id) == 0
        assert intern.category_id is None
        assert al_manueel.categorization == Categorization.MANUAL
        assert geen_match.categorization == Categorization.UNCATEGORIZED

    def test_apply_met_rule_id_gebruikt_enkel_die_regel(self, seeded_db: Session) -> None:
        contexts = seed_contexts(seeded_db)
        gem = contexts["Gemeenschappelijk"]
        boodschappen = _category(seeded_db, gem, "Boodschappen")
        katten = _category(seeded_db, gem, "Katten")
        regel_a = _rule(gem, boodschappen, value="COLRUYT")
        regel_b = _rule(gem, katten, value="JUST RUSSEL")
        seeded_db.add_all(
            [
                regel_a,
                regel_b,
                self._tx(gem, amount="-30.00", description="COLRUYT GENT"),
                self._tx(gem, amount="-25.00", description="JUST RUSSEL DRONGEN"),
            ]
        )
        seeded_db.commit()

        assert apply_rules(seeded_db, gem.id, rule_id=regel_b.id) == 1
        txs = seeded_db.scalars(select(Transaction)).all()
        by_descr = {t.description: t for t in txs}
        assert by_descr["COLRUYT GENT"].category_id is None
        assert by_descr["JUST RUSSEL DRONGEN"].category_id == katten.id


class TestMultiEntiteit:
    """Regel geldt voor meerdere entiteiten (#9): categorie per entiteit op naam gematcht."""

    def _tx(self, context: Context, description: str) -> Transaction:
        return Transaction(
            context_id=context.id,
            date=date(2026, 6, 15),
            amount=Decimal("-10.00"),
            type=CategoryType.UITGAVEN,
            description=description,
            categorization=Categorization.UNCATEGORIZED,
        )

    def _link(self, db: Session, rule: CategorizationRule, *contexts: Context) -> None:
        db.flush()
        db.add_all(RuleContext(rule_id=rule.id, context_id=c.id) for c in contexts)

    def test_regel_geldt_voor_andere_entiteit(self, seeded_db: Session) -> None:
        gem = _context(seeded_db, "Gemeenschappelijk")
        simon = _context(seeded_db, "Simon")
        rule = _rule(gem, _category(seeded_db, gem, "Boodschappen"), value="COLRUYT")
        seeded_db.add(rule)
        self._link(seeded_db, rule, gem, simon)
        tx = self._tx(simon, "Betaling COLRUYT Gent")
        seeded_db.add(tx)
        seeded_db.commit()

        # De Gemeenschappelijk-regel wordt geladen én toegepast voor Simon,
        # met Simon's eigen 'Boodschappen'-categorie.
        assert any(r.id == rule.id for r in load_rules(seeded_db, simon.id))
        assert apply_rules(seeded_db, simon.id) == 1
        seeded_db.commit()
        assert tx.category_id == _category(seeded_db, simon, "Boodschappen").id
        assert tx.categorization == Categorization.AUTO

    def test_ontbrekende_categorie_wordt_overgeslagen(self, seeded_db: Session) -> None:
        simon = _context(seeded_db, "Simon")
        gem = _context(seeded_db, "Gemeenschappelijk")
        # 'Loon' bestaat bij Simon, niet bij Gemeenschappelijk (seed).
        rule = _rule(simon, _category(seeded_db, simon, "Loon"), value="WEDDE")
        seeded_db.add(rule)
        self._link(seeded_db, rule, gem)  # enkel aan Gemeenschappelijk gekoppeld
        tx = self._tx(gem, "WEDDE juni")
        seeded_db.add(tx)
        seeded_db.commit()

        # Regel matcht, maar 'Loon' ontbreekt bij Gemeenschappelijk → overgeslagen.
        assert apply_rules(seeded_db, gem.id) == 0
        assert tx.categorization == Categorization.UNCATEGORIZED

    def test_opslaan_filtert_niet_toepasbare_entiteiten(
        self, logged_in, seeded_db: Session
    ) -> None:
        """'Geldt voor' mag enkel entiteiten bevatten waar de categorie(naam) bestaat:
        'Loon' bestaat bij Simon/Jozefien maar niet bij Gemeenschappelijk (seed)."""
        gem = _context(seeded_db, "Gemeenschappelijk")
        simon = _context(seeded_db, "Simon")
        jozefien = _context(seeded_db, "Jozefien")
        loon = _category(seeded_db, simon, "Loon")
        resp = logged_in.post(
            "/api/rules",
            json={
                "context_id": simon.id,
                "match_field": "description",
                "match_type": "contains",
                "match_value": "WEDDE",
                "category_id": loon.id,
                "priority": 100,
                "context_ids": [gem.id, simon.id, jozefien.id],
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        # Gemeenschappelijk heeft geen 'Loon' → eruit gefilterd bij het opslaan.
        assert sorted(data["context_ids"]) == sorted([simon.id, jozefien.id])
        assert sorted(data["applicable_context_ids"]) == sorted([simon.id, jozefien.id])

    def test_lijst_geeft_toepasbaarheid_per_regel(self, logged_in, seeded_db: Session) -> None:
        gem = _context(seeded_db, "Gemeenschappelijk")
        simon = _context(seeded_db, "Simon")
        jozefien = _context(seeded_db, "Jozefien")
        rule = _rule(simon, _category(seeded_db, simon, "Loon"), value="WEDDE")
        seeded_db.add(rule)
        self._link(seeded_db, rule, simon)
        seeded_db.commit()

        listed = logged_in.get("/api/rules", params={"context_id": simon.id}).json()
        out = next(r for r in listed if r["match_value"] == "WEDDE")
        assert sorted(out["applicable_context_ids"]) == sorted([simon.id, jozefien.id])
        assert gem.id not in out["applicable_context_ids"]

    def test_inactieve_categorie_telt_niet_als_toepasbaar(
        self, logged_in, seeded_db: Session
    ) -> None:
        """'Bestaat niet' = geen ACTIEVE categorie met die naam: een gedeactiveerde
        categorie (bv. 'Boodschappen' bij Simon/Jozefien) maakt de regel daar
        niet-toepasbaar."""
        simon = _context(seeded_db, "Simon")
        jozefien = _context(seeded_db, "Jozefien")
        _category(seeded_db, jozefien, "Loon").active = False
        rule = _rule(simon, _category(seeded_db, simon, "Loon"), value="WEDDE")
        seeded_db.add(rule)
        self._link(seeded_db, rule, simon)
        seeded_db.commit()

        listed = logged_in.get("/api/rules", params={"context_id": simon.id}).json()
        out = next(r for r in listed if r["match_value"] == "WEDDE")
        assert out["applicable_context_ids"] == [simon.id]

    def test_engine_slaat_inactieve_categorie_over(self, seeded_db: Session) -> None:
        """De regelengine categoriseert nooit in een gedeactiveerde categorie."""
        simon = _context(seeded_db, "Simon")
        loon = _category(seeded_db, simon, "Loon")
        loon.active = False
        rule = _rule(simon, loon, value="WEDDE")
        seeded_db.add(rule)
        self._link(seeded_db, rule, simon)
        tx = self._tx(simon, "WEDDE juni")
        seeded_db.add(tx)
        seeded_db.commit()

        assert apply_rules(seeded_db, simon.id) == 0
        assert tx.categorization == Categorization.UNCATEGORIZED

    def test_route_maakt_regel_voor_meerdere_entiteiten(
        self, logged_in, seeded_db: Session
    ) -> None:
        gem = _context(seeded_db, "Gemeenschappelijk")
        simon = _context(seeded_db, "Simon")
        cat = _category(seeded_db, gem, "Boodschappen")
        resp = logged_in.post(
            "/api/rules",
            json={
                "context_id": gem.id,
                "match_field": "description",
                "match_type": "contains",
                "match_value": "COLRUYT",
                "category_id": cat.id,
                "priority": 100,
                "context_ids": [gem.id, simon.id],
            },
        )
        assert resp.status_code == 201
        assert sorted(resp.json()["context_ids"]) == sorted([gem.id, simon.id])
        # De regel duikt op in de lijst van Simon (andere entiteit).
        listed = logged_in.get("/api/rules", params={"context_id": simon.id}).json()
        assert any(r["match_value"] == "COLRUYT" for r in listed)
