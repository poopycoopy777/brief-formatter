"""Assemble a JDF 1987-shaped DOCX from parsed brief blocks.

``python-docx`` is imported lazily inside the functions that need it, so this
module (and therefore the whole package) imports cleanly in an environment
that only has the parsing and citation dependencies.  That keeps the
repository's broader test suite collectable everywhere.
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path

from .citations import italic_segments
from .parse import BODY, ISSUE, LEGAL, LIST, MAJOR, QUOTE, SUB, Block, parse


def _docx_util():
    """Import :mod:`jdf_brief.docx_util` on demand.

    That module needs python-docx, which the parsing and citation code does
    not, so deferring the import keeps the package importable everywhere.
    """
    from . import docx_util

    return docx_util


def _inch(value: float):
    """Return *value* inches as a python-docx length.

    python-docx is imported on demand so this module stays importable in an
    environment that only has the parsing and citation dependencies.
    """
    from docx.shared import Inches

    return Inches(value)


# Numeric inch values, safe to use as import-time default arguments.
_BODY_FIRST_LINE = 0.5
_QUOTE_LEFT = 0.5
_SUB_LEFT = 0.5
_SUB_TEXT = 1.0
_MAJOR_TAB = 0.5
_ISSUE_LEFT = 0.5

# The sample's body text begins 1.5" from the top of the page on every page,
# not 1" (its first body baseline sits at y=107.5-108.1 on a 792pt page).
_TOP_MARGIN = 1.5

_ROMAN = (
    "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X",
    "XI", "XII", "XIII", "XIV", "XV", "XVI", "XVII", "XVIII", "XIX", "XX",
)


def _roman(number: int) -> str:
    return _ROMAN[number - 1] if 1 <= number <= len(_ROMAN) else str(number)


# ---------------------------------------------------------------------------
# Paragraph builders
# ---------------------------------------------------------------------------

def _emit_chunks(adder, chunks: list[str], footnotes: list[str]) -> None:
    """Send each chunk to *adder*, giving the footnotes to the last one only.

    Splitting a paragraph on a lead-in label produces several paragraphs; the
    ``[^ ...]`` markers sat at the end of the original text, so they belong to
    the final chunk.
    """
    for index, chunk in enumerate(chunks):
        is_last = index == len(chunks) - 1
        adder(chunk, footnotes if is_last else [])


def _add_labeled_body(doc, label: str, text: str, notes, footnotes: list[str]):
    """A "Word Limits:" style paragraph: bold label, content on the 1.0" stop.

    Matches the sample, which sets the label bold at 0.5" and tabs the content
    to 1.0", wrapping back to 1.0" (a 0.5" hanging indent).
    """
    du = _docx_util()
    from docx.enum.text import WD_TAB_ALIGNMENT

    paragraph = doc.add_paragraph()
    du.set_line_height(paragraph, du.BODY_LINE_PT)
    du.set_indent(paragraph, left=_inch(_SUB_LEFT), first=_inch(0))
    du.keep_lines_together(paragraph)
    paragraph.paragraph_format.tab_stops.add_tab_stop(
        _inch(_SUB_TEXT), WD_TAB_ALIGNMENT.LEFT
    )

    label_run = paragraph.add_run(label + "\t")
    du.set_run_font(label_run, size=du.BODY_PT, bold=du.LABEL_BOLD)
    du.add_runs(paragraph, italic_segments(text))
    for note_text in footnotes:
        note_id = notes.add([(note_text, False, False)])
        du.add_footnote_reference(paragraph, note_id)
    return paragraph


# A whole paragraph that is nothing but a lead-in label: "Word Limits:",
# "Standard of Review:", "Preservation:".  The JDF sample sets these bold on
# the 0.5" stop with the content tabbed to 1.0" on the same line.
_LABEL_ONLY = re.compile(r"^[A-Z][A-Za-z' \-]{2,34}:$")


def _is_label_only(text: str) -> bool:
    return bool(_LABEL_ONLY.match(text.strip()))


def _join_label_pairs(blocks: list) -> list[tuple[str, object, object]]:
    """Flatten body text into paragraphs, pairing labels with their content.

    A lead-in label is often not its own block: the source runs
    "... Including: Word Limits: My brief has ..." onto one line, and
    :func:`_split_label` separates them.  Splitting therefore happens here,
    before pairing, so a bare "Word Limits:" is matched with the paragraph
    that follows it and the two render on one line.

    Yields ``(kind, first, second)``; ``second`` is None unless the first is a
    label that owns the following paragraph.
    """
    flat: list = []
    for block in blocks:
        if block.kind == BODY and not block.letter:
            for chunk in _split_label(block.text):
                flat.append(Block(BODY, chunk, footnotes=block.footnotes))
        else:
            flat.append(block)

    out: list[tuple[str, object, object]] = []
    index = 0
    while index < len(flat):
        block = flat[index]
        nxt = flat[index + 1] if index + 1 < len(flat) else None
        if (
            block.kind == BODY
            and nxt is not None
            and nxt.kind == BODY
            and _is_label_only(block.text)
        ):
            out.append(("labeled", block, nxt))
            index += 2
            continue
        out.append((block.kind, block, None))
        index += 1
    return out


def _add_placeholder_heading(doc, title: str, number: int):
    """A reserved section such as "2. Table of Contents".

    The heading is numbered like any other section.  The entries themselves
    are not generated -- pagination is only known once the brief is laid out
    -- so a blank paragraph is left beneath it for the writer to fill in.
    """
    paragraph = _add_major_heading(doc, title, number)
    spacer = doc.add_paragraph()
    _docx_util().set_line_height(spacer, _docx_util().BODY_LINE_PT)
    return paragraph


def _add_body(doc, text: str, notes, footnotes: list[str], *,
              first_line: float = _BODY_FIRST_LINE, left=None, italic=False):
    """Add one body paragraph, attaching any footnotes it carries.

    Footnote markers are re-attached at the end of the paragraph, which is
    where a ``[^ ...]`` marker sits once the text has been joined back up.
    """
    du = _docx_util()
    paragraph = doc.add_paragraph()
    du.set_line_height(paragraph, du.BODY_LINE_PT)
    du.keep_lines_together(paragraph)
    if left is not None:
        du.set_indent(paragraph, left=left, first=_inch(0))
    elif first_line:
        du.set_indent(paragraph, first=_inch(first_line))
    else:
        du.set_indent(paragraph, first=_inch(0))
    segments = italic_segments(text)
    if italic:
        segments = [(chunk, True) for chunk, _ in segments]
    du.add_runs(paragraph, segments)
    for note_text in footnotes:
        note_id = notes.add([(note_text, False, False)])
        _docx_util().add_footnote_reference(paragraph, note_id)
    return paragraph


def _add_major_heading(doc, text: str, number: int):
    paragraph = doc.add_paragraph()
    _docx_util().set_spacing(paragraph, before=12, after=0)
    _docx_util().set_line_height(paragraph, _docx_util().BODY_LINE_PT)
    # No left indent: the number sits on the left margin and the section text
    # is tabbed to 0.5", matching the sample.
    _docx_util().set_indent(paragraph, left=_inch(0), first=_inch(0))
    _docx_util().add_tab_stop(paragraph, _inch(_MAJOR_TAB), "left")
    _docx_util().add_runs(paragraph, [(f"{number}.\t{text}", False)],
                size=_docx_util().HEADING_PT, bold=True)
    _docx_util().keep_with_next(paragraph)
    return paragraph


def _add_issue_heading(doc, text: str):
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    paragraph = doc.add_paragraph()
    _docx_util().set_spacing(paragraph, before=12, after=0)
    _docx_util().set_line_height(paragraph, _docx_util().BODY_LINE_PT)
    _docx_util().set_indent(paragraph, left=_inch(_ISSUE_LEFT), first=_inch(0))
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _docx_util().add_runs(paragraph, italic_segments(text), size=_docx_util().HEADING_PT)
    _docx_util().keep_with_next(paragraph)
    return paragraph


def _add_sub_heading(doc, text: str, letter: str = ""):
    paragraph = doc.add_paragraph()
    _docx_util().set_spacing(paragraph, before=0, after=0)
    _docx_util().set_line_height(paragraph, _docx_util().BODY_LINE_PT)
    _docx_util().set_indent(paragraph, left=_inch(_SUB_LEFT), first=_inch(0))
    if letter:
        # Letter on the 0.5" stop, text on the 1.0" stop: a 0.5" hanging
        # indent, so the label aligns with the body's first line.
        _docx_util().add_tab_stop(paragraph, _inch(_SUB_TEXT), "left")
        label = f"{letter}\t{text}"
    else:
        label = text
    _docx_util().add_runs(paragraph, [(label, False)])
    _docx_util().keep_with_next(paragraph)
    return paragraph


def _add_lettered_body(doc, letter: str, text: str):
    """A lettered paragraph: letter on the 0.5" stop, text hanging at 1.0"."""
    chunks = _split_label(text)
    paragraphs = []
    for index, chunk in enumerate(chunks):
        paragraph = doc.add_paragraph()
        _docx_util().set_line_height(paragraph, _docx_util().BODY_LINE_PT)
        if index == 0:
            _docx_util().set_indent(paragraph, left=_inch(_SUB_LEFT), first=_inch(0))
            _docx_util().add_tab_stop(paragraph, _inch(_SUB_TEXT), "left")
            _docx_util().add_runs(paragraph, [(f"{letter}\t", False)])
        else:
            _docx_util().set_indent(paragraph, left=_inch(_SUB_LEFT), first=_inch(0))
            _docx_util().add_tab_stop(paragraph, _inch(_SUB_TEXT), "left")
            paragraph.add_run("\t")
        _docx_util().add_runs(paragraph, italic_segments(chunk))
        paragraphs.append(paragraph)
    return paragraphs


def _add_list_item(doc, text: str):
    """A numbered list item such as "1. Whether the district court erred...".

    The item is a hanging indent, not a plain left indent: the number sits on
    the 0.5" stop and every following line -- including the wrapped lines of the
    item's own text -- aligns on the 1.0" stop.  With a plain 0.5" left indent
    the wrapped lines fall back under the number, which is what the JDF sample
    avoids.
    """
    paragraph = doc.add_paragraph()
    _docx_util().set_line_height(paragraph, _docx_util().BODY_LINE_PT)
    _docx_util().set_indent(
        paragraph,
        left=_inch(_SUB_TEXT),                    # body column at 1.0"
        hanging=_inch(_SUB_TEXT - _SUB_LEFT),     # number hangs out at 0.5"
    )
    _docx_util().add_tab_stop(paragraph, _inch(_SUB_TEXT), "left")
    _docx_util().add_runs(paragraph, italic_segments(text))
    return paragraph


_LEADING_NUMBER = re.compile(r"^\s*\d{1,2}\s*[.)]\s+")

# A short lead-in label such as "Word Limits:" or "Standard of Review:" that
# begins its own paragraph.  The label is matched at a sentence boundary; a
# non-overlapping scan would only ever see the first one ("Including:"), so
# every boundary is examined and the longest label wins.
# A lead-in label must start the paragraph or follow sentence-ending
# punctuation (or another label's colon, as in "Including: Word Limits:").
# Matching the whitespace run without consuming it lets every site be tested,
# which a consuming pattern cannot do.
_LABEL_SITE = re.compile(r"(?:(?<=^)|(?<=[.?!:]))(\s+)(?=[A-Z])")
_LABEL_AT = re.compile(
    r"^(?P<label>[A-Z][A-Za-z' \-]{2,34}:)(?P<rest>(?:\s+\S.*)?)", re.DOTALL
)

# JDF section labels that always stand on their own line.
_SECTION_LABELS = frozenset(
    {
        "word limits",
        "standard of review",
        "preservation",
        "ruled on",
        "discussion",
        "introduction",
        "jurisdiction",
        "nature of the case",
        "statement of the case",
        "statement of facts",
        "summary of the argument",
        "argument summary",
        "conclusion",
        "certificate of compliance",
        "certificate of service",
    }
)

# Lead-in words that introduce a list or clause rather than a section.
_NOT_A_LABEL = frozenset(
    {"note", "see", "cf", "id", "e.g", "i.e", "but", "and", "including", "or"}
)


def _label_candidates(text: str) -> list[tuple[int, str, str]]:
    """Return every ``(start, label, rest)`` label candidate in *text*.

    A candidate must begin the paragraph or follow sentence-ending punctuation,
    so a colon inside a sentence ("rests on the CCJRA: ...") is never treated
    as a label, while a real lead-in that was flattened into the paragraph
    ("... 28 and 32. Including: Word Limits: My brief has ...") is found.
    """
    found: list[tuple[int, str, str]] = []
    sites = [0]
    sites.extend(
        m.end(1) for m in _LABEL_SITE.finditer(text) if m.group(1)
    )

    for start in sites:
        label_match = _LABEL_AT.match(text[start:])
        if label_match is None:
            continue
        label = label_match.group("label").strip()
        name = label.rstrip(":").lower()
        if name in _NOT_A_LABEL:
            continue
        found.append(
            (start, label, (label_match.group("rest") or "").strip())
        )

    return found


def _split_label(text: str) -> list[str]:
    """Break a paragraph before any lead-in label it contains.

    "I certify ... 28 and 32. Including: Word Limits: My brief has ..."
    becomes: the certification sentence, the "Word Limits:" label, and the
    content that follows.
    """
    out: list[str] = []
    tail = text.strip()
    seen: set[tuple[int, str]] = set()

    while tail:
        candidates = _label_candidates(tail)
        # Prefer a known JDF section label, then the longest label, then the
        # one furthest left so earlier sentences stay intact.
        candidates = [
            c for c in candidates if (c[0], c[1]) not in seen
        ]
        if not candidates:
            out.append(tail)
            break

        def rank(item):
            start, label, _rest = item
            name = label.rstrip(":").lower()
            return (name in _SECTION_LABELS, len(label), -start)

        start, label, rest = max(candidates, key=rank)
        seen.add((start, label))

        prefix = tail[:start].strip()
        if prefix:
            out.append(prefix)
        if label.rstrip(":").lower() in _SECTION_LABELS:
            out.append(label)
            tail = rest
        else:
            tail = "%s %s" % (label, rest)

    return out or [text]
    """Return every ``(start, label, rest)`` label candidate in *text*.

    Walks the text forward, testing each sentence boundary.  Rejected lead-ins
    ("Including:") are stepped over so a real label hiding behind them
    ("Word Limits:") is still found.
    """
    found: list[tuple[int, str, str]] = []

    starts = [0]
    starts.extend(m.end() for m in _SENTENCE_END.finditer(text))

    for start in starts:
        tail = text[start:]
        match = _LABEL_AT.match(tail)
        if match is None:
            continue
        name = match.group("label").rstrip(":").lower()
        if name in _NOT_A_LABEL:
            continue
        found.append((start, match.group("label"), match.group("rest").strip()))

    return found


def _strip_existing_number(text: str) -> str:
    return _LEADING_NUMBER.sub("", text, count=1).strip()


# ---------------------------------------------------------------------------
# Rejoined-line repair
# ---------------------------------------------------------------------------

def _looks_like_heading_fragment(line: str) -> bool:
    stripped = line.strip()
    if not stripped or len(stripped) > 60:
        return False
    letters = [c for c in stripped if c.isalpha()]
    if len(letters) < 4:
        return False
    if sum(1 for c in letters if c.isupper()) / len(letters) > 0.85:
        return True
    if stripped.endswith(":") and len(stripped.split()) <= 8:
        return True
    return False


# ---------------------------------------------------------------------------
# Styles
# ---------------------------------------------------------------------------

def _configure_styles(document) -> None:
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Pt

    normal = document.styles["Normal"]
    normal.font.name = _docx_util().FONT
    normal.font.size = _docx_util().BODY_PT
    rpr = normal.element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.insert(0, rfonts)
    for attr in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
        rfonts.set(qn(attr), _docx_util().FONT)
    normal.paragraph_format.space_before = Pt(0)
    normal.paragraph_format.space_after = Pt(0)

    try:
        footnote = document.styles["Footnote Text"]
        footnote.font.name = _docx_util().FONT
        footnote.font.size = _docx_util().FOOTNOTE_PT
    except KeyError:
        pass


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

def build_brief(text: str, output: str | Path, *,
                skip_caption: bool = True,
                skip_toc: bool = True,
                collapse_duplicates: bool = True,
                footer_left: str | None = None,
                footer_center: str | None = None,
                footer_right: str | None = None,
                footer_page_number: bool = True) -> Path:
    """Format *text* as a JDF 1987 brief and write it to *output*.

    The footer defaults to a bare page number.  The JDF sample's own footer
    text ("JDF 1987 - Sample Opening Brief" / "R: July 12, 2021") belongs to
    the court's sample form, so it is not reproduced on a real filing; pass
    *footer_left* / *footer_center* to add your own identifier.
    """
    from docx import Document

    result = parse(text, skip_caption=skip_caption, skip_toc=skip_toc,
                   collapse_duplicates=collapse_duplicates)

    document = Document()
    _configure_styles(document)

    section = document.sections[0]
    # The sample's body starts at y=107.5-108.1 on every page, i.e. 1.5" down
    # (not 1"), while its footer sits just inside a 1" bottom margin.
    section.top_margin = _inch(_TOP_MARGIN)
    for attr in ("left_margin", "right_margin", "bottom_margin"):
        setattr(section, attr, _inch(1))
    util = _docx_util()
    util.build_footer(
        section,
        left=util.DEFAULT_FOOTER_LEFT if footer_left is None else footer_left,
        center=(util.DEFAULT_FOOTER_CENTER if footer_center is None
                else footer_center),
        right=(util.DEFAULT_FOOTER_RIGHT if footer_right is None
               else footer_right),
        page_number=footer_page_number,
    )

    notes = _docx_util().FootnoteStore()
    major_number = 0
    major_to_insert = -1
    reserved = list(result.reserved)

    if reserved:
        # The TOC/TOA content is not generated, so the author's own numbering
        # cannot be relied on: sections are renumbered in sequence, with the
        # reserved TOC/TOA slots inserted at the end of the Certificate of
        # Compliance (which the form numbers 1).
        major_number = 0
        major_to_insert = 1

    def add_reserved() -> None:
        """Emit the reserved TOC/TOA sections at their fixed numbers.

        These carry the numbers the author gave them, so the running counter is
        left alone; the following sections continue from the last reserved
        number.
        """
        nonlocal major_to_insert, major_number
        for section in reserved:
            _add_placeholder_heading(
                document, _strip_existing_number(section.text), int(section.number)
            )
            major_number = int(section.number)
        major_to_insert = 0         # done: never insert again

    for kind, block, partner in _join_label_pairs(result.blocks):
        if kind == "labeled":
            _add_labeled_body(
                document, block.text, partner.text, notes, partner.footnotes
            )
        elif kind == MAJOR:
            if major_to_insert == 2:
                # The TOC/TOA slots go at the end of the first section, after
                # the Certificate of Compliance's own text and signature line.
                add_reserved()
            major_number += 1
            heading = _strip_existing_number(block.text)
            _add_major_heading(document, heading, major_number)
            if major_to_insert == 1:
                major_to_insert = 2
        elif kind == ISSUE:
            _add_issue_heading(document, _strip_existing_number(block.text))
        elif kind == SUB:
            _add_sub_heading(document, block.text, block.letter)
        elif kind == LIST:
            _add_list_item(document, block.text)
        elif kind in (QUOTE, LEGAL):
            # Both sit at a half inch with no first-line indent; a quoted
            # passage is additionally italicised.
            italic = kind == QUOTE and not block.text.endswith(":")
            _add_body(document, block.text, notes, block.footnotes,
                      first_line=_inch(0), left=_inch(_QUOTE_LEFT),
                      italic=italic)
        else:
            if block.letter:
                _add_lettered_body(document, block.letter, block.text)
            else:
                _add_body(document, block.text, notes, block.footnotes)

    if major_to_insert in (1, 2):
        add_reserved()

    notes.attach(document)

    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    document.save(str(output))
    if notes.count:
        _register_content_type(output)
    return output


def _register_content_type(path: Path) -> None:
    """Add the footnotes content-type override to the saved package.

    ``Part`` writes the part and the relationship but python-docx offers no
    hook for ``[Content_Types].xml``, so the override is injected afterwards.
    """
    import shutil
    import tempfile

    target = str(path)
    tmp = target + ".tmp"
    with zipfile.ZipFile(target, "r") as src:
        names = src.namelist()
        payload = {name: src.read(name) for name in names}

    ct_name = "[Content_Types].xml"
    xml = payload[ct_name].decode("utf-8")
    override = (
        '<Override PartName="/word/footnotes.xml" '
        'ContentType="%s"/>' % _docx_util()._CONTENT_TYPE_FOOTNOTES
    )
    if override not in xml:
        xml = xml.replace("</Types>", override + "</Types>")

    payload[ct_name] = xml.encode("utf-8")

    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as dst:
        for name in names:
            dst.writestr(name, payload[name])
    shutil.move(tmp, target)
