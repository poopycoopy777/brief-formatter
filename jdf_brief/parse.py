"""Parse a plain-text Colorado brief into the block list the builder consumes.

Input is deliberately plain: the user writes in a word processor or a text
editor and the markers are optional.  Explicit markers win; anything left
unmarked is inferred.

Markers
-------
``# Heading``        major numbered section (2., 3., ...)
``## Heading``       centered issue heading
``### A. Heading``   sub-heading with a hanging indent
``> text``           block quote (0.5" left indent, no first-line)
``:: text``          legal/indented paragraph
``[^ n] text``       footnote; the marker is replaced by a real footnote

Anything else is body text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher

# ---------------------------------------------------------------------------
# Block model
# ---------------------------------------------------------------------------

MAJOR = "major"        # "1. Certificate of Compliance"
ISSUE = "issue"        # centered, 14pt regular
SUB = "sub"            # "A. Jurisdiction" / "Standard of Review"
BODY = "body"          # first-line indented, double spaced
QUOTE = "quote"        # 0.5" left indent, no first-line
LEGAL = "legal"        # same as QUOTE but not italic-blocked
LIST = "list"          # numbered/lettered list item


@dataclass
class Block:
    kind: str
    text: str
    letter: str = ""            # "A." for SUB blocks
    footnotes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Recognisers
# ---------------------------------------------------------------------------

# "1. Certificate of Compliance", "2. Table of Content", "3. Table of Authorities"
_NUMBERED = re.compile(r"^\s*(\d{1,2})\s*[.)]\s+(?=\S)(.*)$")

# "A. Jurisdiction", "B. Nature of the Case"
_LETTERED = re.compile(r"^\s*([A-Z])\s*[.)]\s+(?=\S)(.*)$")

# "ISSUE 1: ...", "ISSUE 2 – ..."
_ISSUE_HEAD = re.compile(r"^\s*ISSUE\s*\d+\s*[:.\u2013\u2014-]\s*(.*)$", re.IGNORECASE)

# Known JDF subsection labels, which appear as bare short lines.
_SUB_LABELS = {
    "standard of review",
    "preservation",
    "preservation on appeal",
    "ruled on",
    "discussion",
    "introduction",
    "statement of facts",
    "summary of the argument",
    "certificate of compliance",
    "certificate of service",
    "copies delivered",
    "signature & date",
    "signature and date",
    "jurisdiction",
    "nature of the case",
}

# ALL-CAPS lines that are genuinely major headings.
_MAJOR_CAPS = {
    "ISSUES PRESENTED FOR REVIEW",
    "ISSUE PRESENTED FOR REVIEW",
    "ISSUES ON APPEAL",
    "STATEMENT OF THE CASE",
    "STATEMENT OF FACTS",
    "SUMMARY OF THE ARGUMENT",
    "ARGUMENT SUMMARY",
    "ARGUMENT",
    "CONCLUSION",
    "CERTIFICATE OF COMPLIANCE",
    "CERTIFICATE OF SERVICE",
    "TABLE OF CONTENTS",
    "TABLE OF AUTHORITIES",
    "PRAYER FOR RELIEF",
    "RELIEF REQUESTED",
    "STANDARD OF REVIEW",
}

# Lines that begin a table-of-contents / table-of-authorities block.  The
# heading may itself be numbered ("2. Table of Content") or indented, so the
# leading enumerator is stripped before matching.
_TOC_START = re.compile(r"^\s*table\s+of\s+(?:contents?|content|authorit\w*)", re.IGNORECASE)


def _is_toc_heading(line: str) -> bool:
    """True for "Table of Contents", "3. Table of Authorities", etc."""
    stripped = line.strip()
    if _TOC_START.match(stripped):
        return True
    numbered = _NUMBERED.match(stripped)
    return bool(numbered and _TOC_START.match(numbered.group(2).strip()))

# A caption title such as "APPELLANT'S OPENING BRIEF" or "OPENING BRIEF".
# The leading prefixes must be real words (a word boundary immediately before
# them), otherwise "Content" would match "CONTENT" and the caption would be
# judged to end at the Table of Contents.
_CAPTION_TITLE = re.compile(
    r"(?:(?<![A-Za-z])(?:OPENING|ANSWER|REPLY|AMENDED|SUPPLEMENTAL|COMBINED)\s+)?"
    r"BRIEF(?!\w)",
    re.IGNORECASE,
)

# "Pg. 9", "Pgs. 10 & 12", "P. 9" -- a TOC entry line.
_TOC_ENTRY = re.compile(r"(Pg?s?\.?\s*\d)|(\d+\s*$)")

# Bare category labels that appear inside a Table of Authorities.
_TOC_LABELS = frozenset(
    {
        "cases", "statutes", "statutes and rules", "court rules", "rules",
        "other authorities", "other authorities cited", "constitutional",
        "regulations", "secondary sources", "treatises", "law reviews",
    }
)

# A whole line that is nothing but an authority-category label.
_TOC_LABEL_ONLY = re.compile(
    r"^\s*(?:%s)\s*[:.]?\s*$"
    % "|".join(re.escape(label) for label in sorted(_TOC_LABELS, key=len, reverse=True)),
    re.IGNORECASE,
)


def _is_toc_entry(line: str) -> bool:
    """True for a line that looks like a Table of Contents entry.

    Two shapes qualify: an entry carrying a page reference anywhere in the line
    ("Issue 1 - Finding of Trespass: Pg. 9") and a bare authority-category label
    on its own line ("Cases", "Court Rules").
    """
    stripped = line.strip()
    if not stripped:
        return False
    return bool(_TOC_ENTRY.search(stripped)) or bool(_TOC_LABEL_ONLY.match(stripped))


def _is_caps(line: str) -> bool:
    """True when the line is effectively ALL CAPS and short enough to be a heading."""
    stripped = line.strip()
    if not stripped or len(stripped) > 200:
        return False
    letters = [c for c in stripped if c.isalpha()]
    if len(letters) < 4:
        return False
    upper = sum(1 for c in letters if c.isupper())
    return upper / len(letters) > 0.9


def _is_issue_heading(line: str) -> bool:
    """True for a *specific* issue heading, not the "ISSUES PRESENTED" section.

    An issue heading carries a number -- "ISSUE 1: ..." or "ISSUE 2 - ...".
    The bare section title "ISSUES PRESENTED FOR REVIEW" is a major heading and
    is deliberately excluded.
    """
    stripped = line.strip()
    if not stripped:
        return False
    if _ISSUE_HEAD.match(stripped):
        return True
    return bool(
        re.match(r"(?i)^issues?\s*\d", stripped) and _is_caps(stripped)
    )


def _is_major_caps(line: str) -> bool:
    if not _is_caps(line):
        return False
    norm = re.sub(r"[^A-Z& ]", "", line.upper()).strip()
    norm = re.sub(r"\s+", " ", norm)
    if norm in _MAJOR_CAPS:
        return True
    # "TABLE OF CONTENT" (singular typo) and similar.
    return norm.startswith("TABLE OF ") or norm.startswith("STATEMENT OF ")


def _is_sub_label(line: str) -> bool:
    stripped = line.strip().rstrip(":").strip()
    if not stripped or len(stripped) > 60:
        return False
    if stripped.lower() in _SUB_LABELS:
        return True
    # An ALL-CAPS short label such as "STANDARD OF REVIEW" mid-document.
    words = stripped.split()
    return _is_caps(stripped) and 1 <= len(words) <= 6 and stripped.upper() in {
        w.upper() for w in _SUB_LABELS
    }


def is_explicit_marker(line: str) -> bool:
    s = line.lstrip()
    return s.startswith(("#", ">", "::", "[^"))


# ---------------------------------------------------------------------------
# Marker handling
# ---------------------------------------------------------------------------

def _split_markers(text: str) -> tuple[str, list[str]]:
    """Pull ``[^ ...]`` footnote bodies out of *text*.

    Returns the text with footnote markers removed and the footnote bodies in
    order of appearance.
    """
    notes: list[str] = []
    pattern = re.compile(r"\[\^(.+?)\]", re.DOTALL)

    def take(m: re.Match) -> str:
        notes.append(" ".join(m.group(1).split()))
        return ""

    cleaned = pattern.sub(take, text)
    return re.sub(r"\s{2,}", " ", cleaned).strip(), notes


# ---------------------------------------------------------------------------
# Caption / TOC skipping
# ---------------------------------------------------------------------------

# A line that finishes a sentence.  Used to decide whether the next source
# line continues the same paragraph (hard-wrapped prose) or starts a new one
# (one paragraph per line).  Closing punctuation includes the right quotes and
# brackets that commonly trail a final period.
_ENDS_SENTENCE = re.compile(r"""[.!?]["'\u201d\u2019)\]]*\s*$""")


def _skip_caption(lines: list[str]) -> int:
    """Index of the first line after the caption block, or 0 if not found.

    The caption ends at the document title ("APPELLANT'S OPENING BRIEF"), so
    the first numbered section after that title is where formatting starts.
    """
    title_idx = -1
    for i, line in enumerate(lines[:100]):
        if _CAPTION_TITLE.search(line) and _is_caps(line) and len(line.strip()) < 90:
            title_idx = i

    search_from = title_idx + 1 if title_idx >= 0 else 0
    for i in range(search_from, len(lines)):
        stripped = lines[i].strip()
        if not stripped:
            continue
        if _NUMBERED.match(stripped) or _is_major_caps(stripped) or _is_issue_heading(stripped):
            return i
    return search_from


def _skip_toc(lines: list[str], start: int) -> int:
    """Skip a Table of Contents / Table of Authorities block.

    Walks forward past the heading and its entries, stopping at the next
    numbered major heading, an ALL-CAPS major heading, or an issue heading.
    """
    i = start
    while i < len(lines):
        stripped = lines[i].strip()
        if not stripped:
            i += 1
            continue
        if _is_toc_heading(stripped):
            i += 1
            # Skip entry lines until a real heading appears.
            while i < len(lines):
                entry = lines[i].strip()
                if not entry:
                    i += 1
                    continue
                if _is_toc_heading(entry):
                    i += 1
                    continue
                if _is_toc_entry(entry):
                    i += 1
                    continue
                if _NUMBERED.match(entry):
                    break
                if _is_issue_heading(entry) or _is_major_caps(entry):
                    break
                i += 1
            continue
        break
    return i


def _strip_toc_blocks(lines: list[str]) -> list[str]:
    """Remove every Table of Contents / Table of Authorities run in *lines*.

    Unlike :func:`_skip_toc` this works anywhere in the document, because the
    TOC frequently appears after the Certificate of Compliance.  A run begins
    at the TOC heading and ends at the first line that is a genuine heading:
    a non-TOC numbered section, an ALL-CAPS major heading, or a numbered issue
    heading.  TOC entry lines are recognised by their page references and by
    the bare category labels ("Cases", "Statutes", "Court Rules").
    """
    out: list[str] = []
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        if stripped and _is_toc_heading(stripped):
            i += 1
            while i < len(lines):
                entry = lines[i].strip()
                if not entry:
                    i += 1
                    continue
                if _is_toc_heading(entry):
                    i += 1
                    continue          # "3. Table of Authorities" is still TOC
                if _is_toc_entry(entry):
                    i += 1
                    continue          # "Issue 1 - ...: Pg. 9", "Cases", ...
                if _NUMBERED.match(entry):
                    break
                if _is_major_caps(entry) or _is_issue_heading(entry):
                    break
                i += 1
            continue
        out.append(lines[i])
        i += 1
    return out


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

@dataclass
class ParseResult:
    blocks: list[Block]
    skipped_caption: bool
    skipped_toc: bool
    removed_duplicates: int = 0


# ---------------------------------------------------------------------------
# Near-duplicate paragraphs
# ---------------------------------------------------------------------------

# Editing passes routinely leave two copies of a paragraph that differ only in
# punctuation (an em-dash version and a hyphen version).  Comparison therefore
# normalises dashes and all other punctuation away before measuring similarity.
_DUPE_MIN_CHARS = 160
_DUPE_MIN_WORDS = 25
_DUPE_THRESHOLD = 0.90


def _normalise_for_compare(text: str) -> str:
    lowered = text.lower()
    for dash in ("\u2014", "\u2013", "\u2212"):
        lowered = lowered.replace(dash, "-")
    lowered = re.sub(r"[^a-z0-9 ]+", " ", lowered)
    return re.sub(r"\s+", " ", lowered).strip()


def _is_duplicate_pair(first: str, second: str) -> bool:
    """True when *second* is a near-copy of the paragraph *first*."""
    if len(first) < _DUPE_MIN_CHARS or len(second) < _DUPE_MIN_CHARS:
        return False
    a = _normalise_for_compare(first)
    b = _normalise_for_compare(second)
    if len(a.split()) < _DUPE_MIN_WORDS or len(b.split()) < _DUPE_MIN_WORDS:
        return False
    if a == b:
        return True
    return SequenceMatcher(None, a, b).ratio() >= _DUPE_THRESHOLD


def collapse_duplicate_paragraphs(blocks: list[Block]) -> tuple[list[Block], int]:
    """Drop a body paragraph that repeats the one immediately before it.

    Only consecutive ``BODY`` blocks are compared, so a sentence legitimately
    repeated in a different part of the brief ("the Integrity Act commands
    release of ..." appears in both the summary and the argument) is kept.
    The longer of the two copies is retained.
    """
    out: list[Block] = []
    removed = 0

    for block in blocks:
        if (
            out
            and block.kind == BODY
            and out[-1].kind == BODY
            and _is_duplicate_pair(out[-1].text, block.text)
        ):
            if len(block.text) > len(out[-1].text):
                out[-1] = block
            removed += 1
            continue
        out.append(block)

    return out, removed


def parse(text: str, *, skip_caption: bool = True, skip_toc: bool = True,
          collapse_duplicates: bool = True) -> ParseResult:
    """Turn brief text into a list of :class:`Block`."""
    raw_lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    lines = raw_lines

    start = _skip_caption(lines) if skip_caption else 0
    skipped_caption = start > 0
    if skip_toc:
        trimmed = _strip_toc_blocks(lines[start:])
        skipped_toc = len(trimmed) < len(lines[start:])
        lines = lines[:start] + trimmed
    else:
        skipped_toc = False

    blocks: list[Block] = []
    paragraph_buf: list[str] = []
    in_issues = False

    def flush() -> None:
        if not paragraph_buf:
            return
        joined = " ".join(paragraph_buf)
        paragraph_buf.clear()
        joined = re.sub(r"\s{2,}", " ", joined).strip()
        if not joined:
            return
        body, notes = _split_markers(joined)
        if not body:
            return
        blocks.append(Block(BODY, body, footnotes=notes))

    explicit = any(is_explicit_marker(ln) for ln in lines[start:])

    for raw in lines[start:]:
        line = raw.strip()

        if not line:
            flush()
            continue

        # ---- explicit markers always win ----
        if explicit:
            if line.startswith("###"):
                flush()
                label = line[3:].strip()
                letter, rest = _label_and_text(label)
                blocks.append(Block(SUB, rest, letter=letter))
                continue
            if line.startswith("##"):
                flush()
                blocks.append(Block(ISSUE, line[2:].strip()))
                continue
            if line.startswith("#"):
                flush()
                blocks.append(Block(MAJOR, line[1:].strip()))
                continue
            if line.startswith("::"):
                flush()
                blocks.append(Block(LEGAL, line[2:].strip()))
                continue
            if line.startswith(">"):
                flush()
                blocks.append(Block(QUOTE, line[1:].strip()))
                continue

        # ---- structural detection ----
        # A numbered line is a list item while we are inside an Issues section
        # (those items are full sentences and often end with a period); it is
        # a major heading otherwise.  This runs before the issue test so that
        # the section title "2. ISSUES PRESENTED FOR REVIEW" is not read as an
        # issue heading.
        m = _NUMBERED.match(line)
        if m:
            rest = m.group(2).strip()
            if _is_toc_heading(line):
                continue
            if in_issues and not _is_major_caps(rest):
                # A numbered item inside an Issues list, even though the
                # sentence may run long and end with a period.  An unmistakable
                # section name ("3. CONCLUSION") breaks the list instead.
                flush()
                blocks.append(Block(LIST, f"{m.group(1)}. {rest}"))
                continue
            if not line.rstrip().endswith(".") and len(line) < 120:
                flush()
                blocks.append(Block(MAJOR, rest))
                in_issues = "issue" in rest.lower() or "argument" in rest.lower()
                continue

        if _is_issue_heading(line):
            flush()
            m = _ISSUE_HEAD.match(line)
            blocks.append(Block(ISSUE, m.group(1).strip() if m else line))
            in_issues = False
            continue

        if _is_major_caps(line):
            flush()
            blocks.append(Block(MAJOR, line))
            norm = line.lower()
            # Only an Issues section turns following numbered lines into list
            # items; any other major heading ends that context.
            in_issues = "issue" in norm or "argument" in norm
            continue

        if _is_sub_label(line):
            flush()
            blocks.append(Block(SUB, line.rstrip(":").strip()))
            continue

        m = _LETTERED.match(line)
        if m and not re.match(r"(?i)^issue\b", line):
            flush()
            letter = f"{m.group(1)}."
            rest = m.group(2).strip()
            if len(rest) > 60 or rest.endswith("."):
                # A full sentence that happens to be lettered: keep it as a
                # paragraph, but hang the letter so the outline stays aligned.
                blocks.append(Block(BODY, rest, letter=letter))
            else:
                blocks.append(Block(SUB, rest, letter=letter))
            continue

        paragraph_buf.append(line)

        # A source line that ends a sentence ends the paragraph.  Without this
        # two unrelated paragraphs joined by a hard line break would be merged
        # into one, which is what happens when a brief is written with one
        # paragraph per line rather than hard-wrapped.
        if _ENDS_SENTENCE.search(line):
            flush()

    flush()

    removed = 0
    if collapse_duplicates:
        blocks, removed = collapse_duplicate_paragraphs(blocks)

    return ParseResult(blocks, skipped_caption, skipped_toc, removed)


def _label_and_text(label: str) -> tuple[str, str]:
    """Split "A. Jurisdiction" into ("A.", "Jurisdiction")."""
    m = _LETTERED.match(label)
    if m:
        return f"{m.group(1)}.", m.group(2).strip()
    return "", label
