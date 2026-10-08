"""Italicise case names and reporter citations the way the JDF 1987 sample does.

Plain text carries no italics, so this module re-derives them.  Two span types
are recognised:

* **Case names** -- ``Corder v. Folds``, ``Betterview Investments, LLC v.
  Public Service Co.``  The span starts at the first capitalised party name and
  ends at the comma that introduces the reporter citation.
* **Reporter citations** -- ``292 P.3d 1177``, ``877 P.2d 877``, ``2025 COA
  66``, ``2013 CO 60``, ``2018 CO 3``.

Everything else is left alone.  Book-style authorities (``C.R.S.``,
``C.R.C.P.``, ``CRE``) are *not* italicised because the sample leaves them
roman.
"""

from __future__ import annotations

import re

# A case name is delimited structurally rather than by one clever regex: locate
# the " v. " connector, then walk words outward to the enclosing sentence
# boundary on the left and the reporter comma on the right.  That keeps
# "Ion Media Networks, Inc. v. West", "Finnie v. Jefferson Cnty. Sch. Dist.
# R-1" and "Bristol Bay Prods., LLC v. Lampack" intact where a single pattern
# kept truncating them.
_V_MARKER = re.compile(
    r"(?<=\s)v\.(?=\s)"          # " v. " with spaces both sides
    r"|(?<=\s)vs\.(?=\s)"
    r"|(?<=\s)v(?=\s)"           # bare "v" (some styles)
)

# Tokens that may appear inside a case name, in any capitalisation.
_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9'’\-.]*")

# Lowercase words allowed to continue a case name across a word gap.
_CONNECTORS = frozenset(
    {"of", "the", "and", "re", "ex", "rel.", "rel", "d/b/a", "a/k/a", "on",
     "for", "in", "de", "la", "del", "von", "van", "der", "voor", "In"}
)

# Sentence-initial words that can never begin a case name.
_NOT_A_PARTY = frozenset(
    {
        "The", "This", "That", "These", "Those", "Under", "Where", "When",
        "Because", "Although", "Section", "Rule", "Issue", "Issues",
        "Appellant", "Appellants", "Appellee", "Appellees", "Plaintiff",
        "Defendant", "Colorado", "Court", "Id", "See", "Compare", "First",
        "Second", "Third", "Fourth", "Fifth", "No", "On", "In", "It", "If",
        "And", "But", "Yet", "So", "For", "Here", "There", "Whether",
        "Judgment", "Notice", "Statute", "Statutes", "Argument", "Conclusion",
        "Preservation", "Discussion", "Standard", "However", "Even", "Both",
        "A", "An", "As", "At", "By", "During", "Each", "From", "Had", "He",
        "Her", "His", "I", "Its", "Morgan", "Neither", "Nor", "Now", "Of",
        "Or", "She", "Such", "Than", "Then", "They", "Thus", "To", "Two",
        "Was", "Were", "What", "Which", "While", "Who", "With", "Without",
    }
)

# Reporter abbreviations that begin a citation, longest first.
_REPORTERS = (
    "P.3d", "P.2d", "F. Supp. 3d", "F. Supp. 2d", "F. Supp.", "F.3d", "F.2d",
    "U.S.", "S. Ct.", "L. Ed. 2d", "Cal. Rptr. 3d", "N.E.2d", "N.W.2d",
    "S.E.2d", "S.W.3d", "So. 3d", "A.3d", "B.R.", "Colo.",
)

# "292 P.3d 1177" / "877 P.2d 877" / "409 P.3d 331"
_REPORTER_CITE = re.compile(
    r"""
    (?<![A-Za-z0-9])
    \d{1,4}
    \s+
    (?:%s)
    \s+
    \d{1,5}
    """ % "|".join(re.escape(r) for r in _REPORTERS),
    re.VERBOSE,
)

# "2025 COA 66", "2018 CO 3", "2013 CO 60", "2016 COA 25M", "2024 COA 35"
_YEAR_CITE = re.compile(
    r"(?<![A-Za-z0-9])(?:19|20)\d{2}\s+CO(?:A)?\s+\d+[A-Z]?(?![\w])"
)

# A publisher-neutral citation may be followed by ", ¶ 36" -- the paragraph
# pin is part of the citation in Colorado practice.
_PIN = re.compile(r"^\s*,\s*¶+\s*[\d,\s\-–]+")

# Explicit inline italics: *text* or _text_.  Underscores are only treated as
# markup when they wrap a whole word, so file-style names are left alone.
_EXPLICIT_ITALIC = re.compile(
    r"\*([^*\n]+)\*"
    r"|(?<![A-Za-z0-9])_([^_\n]+)_(?![A-Za-z0-9])"
)

# Words that start a case name but are capitalised mid-sentence for other
# reasons; never treat these as the head of a party name.
_NOT_A_PARTY = frozenset(
    {
        "The", "This", "That", "These", "Those", "Under", "Where", "When",
        "Because", "Although", "Section", "Rule", "Issue", "Appellant",
        "Appellees", "Appellee", "Plaintiff", "Defendant", "Colorado",
        "Court", "Id", "See", "Compare", "First", "Second", "Third", "Fourth",
        "No", "On", "In", "It", "If", "And", "But", "Yet", "So", "For",
        "Here", "There", "Whether", "Appellants", "Judgment", "Notice",
        "Statute", "Statutes", "Argument", "Conclusion", "Preservation",
        "Discussion", "Standard",
    }
)


def _token_span(text: str, pos: int) -> tuple[int, int, str] | None:
    """Return the whole token ending at or containing *pos*.

    ``pos`` frequently lands on the trailing period of ``Inc.`` or the hyphen
    of ``R-1``, so punctuation is stepped over before the token is read.
    """
    if pos < 0 or pos >= len(text):
        return None
    start = pos
    while start >= 0 and not text[start].isalnum():
        start -= 1
    if start < 0:
        return None
    while start > 0 and text[start - 1].isalnum():
        start -= 1
    m = _WORD_RE.match(text, start)
    if m is None or m.start() > pos:
        return None
    return m.start(), m.end(), m.group(0)


def _looks_proper(value: str) -> bool:
    """True when a token can belong to a case name."""
    return value[:1].isupper() or value.strip(",.").lower() in _CONNECTORS


def _cont_name_token(value: str) -> bool:
    """True when *value* may continue a case name across a word gap."""
    return value not in _NOT_A_PARTY and _looks_proper(value)


# "Party Name v. Other Party" -- the connector that anchors a case name.
_V_MARKER = re.compile(r"(?<=\s)v\.(?=\s)|(?<=\s)vs\.(?=\s)|(?<=\s)v(?=\s)")

# Tokens inside a case name.  The leading character is a letter; the tail may
# carry digits and punctuation so "R-1", "Inc." and "Ass'n" stay whole.
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9'’\-.]*")
_SUFFIX_RE = re.compile(r"\s*,\s*([A-Za-z][A-Za-z0-9.'’\-]*)")
_NEXT_WORD_RE = re.compile(r"\s*([A-Za-z][A-Za-z0-9'’\-.]*)")


# Corporate designators that may sit after a comma inside a party name.
_SUFFIX_WORDS = frozenset(
    {
        "Inc", "LLC", "Ltd", "Co", "Corp", "Prods", "Assn", "Dep't", "Cnty",
        "Dist", "Sch", "Bd", "Comm'n", "PLLC", "LLP", "LP", "PC", "PA",
    }
)


def _find_case_names(text: str) -> list[tuple[int, int]]:
    """Locate case names by expanding outward from each ``v.`` connector.

    Walks left and right over capitalized words / corporate suffixes / the
    small lowercase connectors that occur inside party names, stopping at the
    sentence boundary on the left and the reporter comma on the right.
    """
    out: list[tuple[int, int]] = []

    for v in _V_MARKER.finditer(text):
        # ---- walk left: the first party ----
        chain: list[tuple[int, int, str]] = []
        cursor = v.start()
        while True:
            stripped = text[:cursor].rstrip()
            if not stripped:
                break
            tok = _token_span(text, len(stripped) - 1)
            if tok is None:
                break
            start, end, value = tok
            # A comma inside a party name is legal only when the token to its
            # right is a corporate designator: "Networks, Inc." stays together
            # while "... said, Ion Media" does not.  chain[-1] is the token
            # immediately right of the gap.
            comma = re.fullmatch(r"(\s*),(\s*)", text[end:cursor])
            if comma is not None and chain[-1][2].rstrip(".") not in _SUFFIX_WORDS:
                break
            if not _cont_name_token(value):
                break
            chain.append((start, end, value))
            cursor = start
        chain.reverse()

        # Drop a sentence-initial word that slipped in at the far left;
        # "See Dunlap v. Colo. Springs Cablevision" must start at "Dunlap".
        while len(chain) > 1 and chain[0][2] in _NOT_A_PARTY:
            chain.pop(0)
        if not chain:
            continue

        # ---- walk right: the second party ----
        right: list[tuple[int, int, str]] = []
        cursor = v.end()
        while True:
            m = _SUFFIX_RE.match(text, cursor)
            if m is not None:
                if m.group(1).rstrip(".") not in _SUFFIX_WORDS:
                    break
                right.append((m.start(1), m.end(1), m.group(1)))
                cursor = m.end(1)
                continue
            m = _NEXT_WORD_RE.match(text, cursor)
            if m is None:
                break
            if not _cont_name_token(m.group(1)):
                break
            right.append((m.start(1), m.end(1), m.group(1)))
            cursor = m.end(1)

        if not right:
            continue

        # chain was reversed above, so chain[0] is the leftmost token of the
        # first party and right[-1] is the rightmost token of the second.
        start = chain[0][0]
        end = right[-1][1]
        name = text[start:end].rstrip().rstrip(",")
        end = start + len(name)
        if len(name.split()) < 3:
            continue
        out.append((start, end))

    return out


def _spans(text: str) -> list[tuple[int, int]]:
    """Return non-overlapping (start, end) spans that should be italic."""
    found: list[tuple[int, int]] = list(_find_case_names(text))

    for rx in (_REPORTER_CITE, _YEAR_CITE):
        for m in rx.finditer(text):
            start, end = m.start(), m.end()
            # Absorb a trailing ", ¶ 36" pin cite.
            pin = _PIN.match(text[end:])
            if pin:
                end += pin.end()
            found.append((start, end))

    if not found:
        return []

    # Merge overlaps, then sort.
    found.sort()
    merged: list[tuple[int, int]] = [found[0]]
    for start, end in found[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end:
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))
    return merged


def italic_segments(text: str) -> list[tuple[str, bool]]:
    """Split *text* into ``(chunk, is_italic)`` pairs covering the whole string.

    Explicit ``*...*`` or ``_..._`` markup is honoured first, so a writer can
    force italics anywhere; the automatic case-name and reporter detection then
    runs only on the remaining roman text.
    """
    out: list[tuple[str, bool]] = []
    cursor = 0

    for match in _EXPLICIT_ITALIC.finditer(text):
        if match.start() > cursor:
            out.extend(_auto_segments(text[cursor:match.start()]))
        inner = match.group(1) or match.group(2)
        out.append((inner, True))
        cursor = match.end()

    if cursor < len(text):
        out.extend(_auto_segments(text[cursor:]))

    return [seg for seg in out if seg[0]]


def _auto_segments(text: str) -> list[tuple[str, bool]]:
    """Apply automatic citation italics to a roman chunk of text."""
    spans = _spans(text)
    if not spans:
        return [(text, False)] if text else []

    out: list[tuple[str, bool]] = []
    cursor = 0
    for start, end in spans:
        if start > cursor:
            out.append((text[cursor:start], False))
        out.append((text[start:end], True))
        cursor = end
    if cursor < len(text):
        out.append((text[cursor:], False))
    return [seg for seg in out if seg[0]]
