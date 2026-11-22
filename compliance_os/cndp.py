"""Canonical CNDP adequacy list — CNDP deliberation no. 236-2015.

WHY THIS MODULE EXISTS
----------------------
The list previously existed in two places in the codebase: an inline tuple in
`cli.py:cmd_template` that INCLUDED Croatia, and a `_CNDP_STATES` set built
later in the same function that OMITTED it. For a Croatian hosting country the
rendered pack therefore said:

    ON_CNDP_LIST   = "Oui"                                    (first check)
    F118_REQUIRED  = "Oui - autorisation de transfert..."     (second check)

which is a self-contradicting legal document. That is exactly the kind of error
that gets a consultant's work thrown out by a client's legal team, so the list
now lives in ONE place and every consumer imports it.

SCOPE NOTE — READ BEFORE RELYING ON THIS
----------------------------------------
This list is a working transcription of the States treated as adequate under
Moroccan Law 09-08. It is presented as: the EU/EEA member states, plus the
United Kingdom, Switzerland and Canada.

Croatia is an EU member state and is therefore included. An earlier internal
note recorded the list as "32 States"; with Croatia present the count is 33.

**This must be verified against the published deliberation before it is relied
on in a signed client document.** The wallet of States is amended by the CNDP
from time to time, and a stale list produces a wrong transfer-basis statement.
The verification step is written into docs/MOROCCO-RULES.md.
"""

from __future__ import annotations

from typing import Iterable, List

# ---------------------------------------------------------------------------
# The canonical list. One entry per State, in normalised form (lowercase,
# accents stripped, "and" written out). Use `normalise()` before comparing.
# ---------------------------------------------------------------------------
CNDP_ADEQUATE_STATES: List[str] = [
    # --- European Union (27) ---
    "austria",
    "belgium",
    "bulgaria",
    "croatia",
    "cyprus",
    "czech republic",
    "denmark",
    "estonia",
    "finland",
    "france",
    "germany",
    "greece",
    "hungary",
    "ireland",
    "italy",
    "latvia",
    "lithuania",
    "luxembourg",
    "malta",
    "netherlands",
    "poland",
    "portugal",
    "romania",
    "slovakia",
    "slovenia",
    "spain",
    "sweden",
    # --- European Economic Area, non-EU (3) ---
    "iceland",
    "liechtenstein",
    "norway",
    # --- Additional States on the list ---
    "united kingdom",
    "switzerland",
    "canada",
]

# Countries that are frequently typed but are NOT on the list. Kept explicit so
# a reviewer can see we considered them.
CNDP_NOT_ON_LIST: List[str] = [
    "united states",
    "usa",
    "us",
    "india",
    "china",
    "brazil",
    "australia",
    "japan",
    "singapore",
    "united arab emirates",
    "uae",
    "saudi arabia",
    "qatar",
    "turkey",
    "tunisia",
    "egypt",
    "south africa",
    "nigeria",
    "kenya",
    "morocco",
]

_TRANSLITERATE = {
    "\u00e9": "e", "\u00e8": "e", "\u00ea": "e", "\u00eb": "e",
    "\u00e0": "a", "\u00e2": "a", "\u00e4": "a",
    "\u00ee": "i", "\u00ef": "i",
    "\u00f4": "o", "\u00f6": "o",
    "\u00f9": "u", "\u00fb": "u", "\u00fc": "u",
    "\u00e7": "c", "\u00f1": "n",
}


def normalise(country: str) -> str:
    """Normalise a country name for comparison.

    Lowercases, transliterates common accents, collapses whitespace and turns
    hyphens into spaces, so "Czech-Republic", "Czech Republic" and
    "czech republic " all compare equal.
    """
    if not country:
        return ""
    out = country.strip().lower()
    for src, dst in _TRANSLITERATE.items():
        out = out.replace(src, dst)
    out = out.replace("-", " ").replace("_", " ")
    out = " ".join(out.split())
    return out


_CANONICAL = {normalise(s) for s in CNDP_ADEQUATE_STATES}

# Aliases that map onto a canonical entry.
_ALIASES = {
    "uk": "united kingdom",
    "great britain": "united kingdom",
    "england": "united kingdom",
    "holland": "netherlands",
    "the netherlands": "netherlands",
    "republic of ireland": "ireland",
    "czech rep": "czech republic",
    "czechia": "czech republic",
    "czech republic": "czech republic",
}


def is_on_cndp_list(country: str) -> bool:
    """True if `country` is one of the States on the CNDP adequacy list."""
    key = normalise(country)
    if not key:
        return False
    key = _ALIASES.get(key, key)
    return key in _CANONICAL


def explicitly_not_on_list(country: str) -> bool:
    """True if this is a country we know is NOT on the list.

    Distinguishing 'known absent' from 'unrecognised' matters: an unrecognised
    spelling should be flagged for a human, not silently treated as adequate.
    """
    key = normalise(country)
    return key in {normalise(c) for c in CNDP_NOT_ON_LIST}


def transfer_position(country: str) -> dict:
    """Describe the transfer position for a hosting country.

    Returns a dict with `on_list`, `known`, and the two strings that go into a
    client document. Callers use this instead of duplicating the logic.
    """
    key = normalise(country)
    if not key:
        return {
            "on_list": False,
            "known": False,
            "on_list_text": "NON",
            "transfer_basis": "A completer - Etat d hebergement non renseigne",
            "f118_required": "A determiner",
        }

    on_list = is_on_cndp_list(country)
    known = on_list or explicitly_not_on_list(country)

    if on_list:
        return {
            "on_list": True,
            "known": True,
            "on_list_text": "Oui",
            "transfer_basis": (
                "Sans objet - Etat figurant sur la deliberation CNDP n 236-2015"
            ),
            "f118_required": (
                "Non - l Etat de destination figure sur la liste CNDP"
            ),
        }

    if known:
        return {
            "on_list": False,
            "known": True,
            "on_list_text": "NON",
            "transfer_basis": (
                "A definir avec le conseil juridique - Etat NON figurant sur la "
                "deliberation CNDP n 236-2015"
            ),
            "f118_required": (
                "Oui - autorisation de transfert a demander (formulaire F118)"
            ),
        }

    # Unrecognised spelling: do not guess.
    return {
        "on_list": False,
        "known": False,
        "on_list_text": "A VERIFIER",
        "transfer_basis": (
            "A VERIFIER - Etat non reconnu dans la liste de reference; "
            "confirmer le statut aupres du CNDP avant emission"
        ),
        "f118_required": "A determiner apres verification",
    }


def count() -> int:
    """Number of distinct States on the list (deduplicated)."""
    return len(_CANONICAL)


def describe() -> Iterable[str]:
    """Sorted canonical entries, for display and audit."""
    return sorted(_CANONICAL)
