"""Rule-based document_type (spec section 7), investigation_stage (spec section 8),
and legal_basis (spec section 2) classification. Keyword-driven; matches title +
abstract only (no PDF/full-text parsing in this MVP -- spec section 24 is deferred)."""

from __future__ import annotations

import config
from keyword_match import any_keyword

# Ordered rules for spec section 7's 20-type taxonomy. First match wins, so
# more specific phrases are listed before generic ones (e.g. "circumvention"
# before generic "review").
_DOCUMENT_TYPE_RULES: list[tuple[list[str], str]] = [
    (["circumvention", "anti-circumvention", "evasion inquiry"], "Circumvention"),
    (["scope ruling", "scope inquiry"], "Scope ruling"),
    (["preliminary determination", "preliminary affirmative", "preliminary negative", "preliminary results"], "Preliminary determination"),
    (["final determination", "final affirmative", "final results", "final action"], "Final determination"),
    (["antidumping duty order", "countervailing duty order", "safeguard order"], "Order"),
    (["administrative review", "sunset review", "changed circumstances review", "new shipper review"], "Review"),
    (["notice of initiation", "investigation initiated", "initiation of"], "Investigation initiation"),
    (["petition", "complaint"], "Petition / complaint"),
    (["exclusion", "exemption"], "Exclusion / exemption"),
    (["safeguard"], "Safeguard"),
    (["entity list", "export control", "end-use", "end-user", "license requirement"], "Export control"),
    (["forced labor", "withhold release order", "uflpa"], "Forced labor"),
    (["sanction", "sdn", "blocked persons"], "Sanction"),
    (["request for comment", "public comment", "comment period"], "Public comment"),
    (["hearing"], "Hearing"),
    (["tariff modification", "modification of"], "Tariff modification"),
    (["tariff", "duty rate", "surcharge", "reciprocal tariff"], "Tariff action"),
    (["report to congress", "report on"], "Report"),
]


def _text(document: dict) -> str:
    return f"{document.get('title', '')} {document.get('abstract', '')}".lower()


def classify_legal_basis(document: dict) -> list[str]:
    text = _text(document)
    matched = []
    for key, entry in config.legal_basis_categories().items():
        keywords = entry.get("keywords", [])
        if any_keyword(text, keywords):
            matched.append(key)
    return matched


def classify_document_type(document: dict) -> str:
    text = _text(document)
    for keywords, doc_type in _DOCUMENT_TYPE_RULES:
        if any_keyword(text, keywords):
            return doc_type
    if (document.get("document_type") or "").lower() == "presidential document":
        return "Presidential action"
    return "Other"


# Most-advanced-stage-wins tie-break order when a document matches more than
# one stage's phrases -- must match the key order in config/legal_basis.yaml.
STAGE_ORDER = ["Initiation", "Review", "Preliminary", "Final"]


def classify_stage(document: dict) -> str | None:
    text = _text(document)
    phrases = config.stage_phrases()
    matched = [stage for stage in STAGE_ORDER if any_keyword(text, phrases.get(stage, []))]
    if not matched:
        return None
    return max(matched, key=STAGE_ORDER.index)
