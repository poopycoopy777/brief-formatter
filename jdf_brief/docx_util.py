"""Low-level DOCX helpers: fonts, spacing, indents, footer and footnotes.

python-docx has no footnote API, so the ``footnotes.xml`` part, its content
type, its relationship and the in-document references are all built by hand
here.  Everything is written with *explicit* properties rather than inherited
styles because Google Docs' DOCX import resolves inherited run properties
inconsistently.
"""

from __future__ import annotations

from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.opc.packuri import PackURI
from docx.opc.part import Part
from docx.shared import Inches, Pt

# ---------------------------------------------------------------------------
# Typography, derived from the JDF 1987 sample PDF.
#
# The sample renders Garamond at 0.8614 x the logical size (Cambria's
# ascent+descent+lineGap over em), which recovers the original point sizes:
#   body 13.9 -> 12pt,  major heading 16.1 -> 14pt,  footnote 9.1 -> 10pt
#
# Geometry in PDF points, with a 72pt (1") left margin:
#   major heading number   72   -> 0.0" from margin
#   major heading text    108   -> 0.5"  (tab)
#   body first line       144   -> 0.5"  first-line indent
#   body continuation     108   -> 0.0"
#   sub-heading letter    108   -> 0.5", text 144 -> 1.0" (0.5" hanging)
#   legal/quote indent    144   -> 0.5", no first-line indent
#   footnotes/footer       72   -> 0.0"
# ---------------------------------------------------------------------------

FONT = "Garamond"

# ---------------------------------------------------------------------------
# Type scale
#
# The JDF sample is Garamond 12pt body / 14pt headings / 10pt footnotes.  The
# scale is expressed as a ratio so the whole document can be enlarged from one
# place.  Scaling the body to 14pt keeps every remaining size in the sample's
# proportions: headings 16pt, footnotes 12pt.
# ---------------------------------------------------------------------------

BODY_SIZE_PT = 14.0
BODY_PT = Pt(BODY_SIZE_PT)
# Headings are the same 14pt as the body and are distinguished by weight and
# centring instead of size, so the whole brief is one uniform 14pt.
HEADING_PT = Pt(BODY_SIZE_PT)
FOOTNOTE_PT = Pt(12)     # sample ratio 10/12 -> 11.7pt, rounded to 12pt
FOOTER_PT = Pt(12)

# Exact body line height.  The sample measures 31.4-31.7pt between body
# baselines on every page, which is 12pt Garamond double spaced (2.625x the
# font size).  The same ratio at 14pt is 36.75pt.  Applied as an exact height
# so that every renderer agrees (see set_line_height).
LINE_RATIO = 31.5 / 12.0
BODY_LINE_PT = round(BODY_SIZE_PT * LINE_RATIO, 2)           # 36.75pt

BODY_LEADING = 2.0          # double spaced (used for footnotes/short lines)
MAJOR_TAB = Inches(0.5)     # number at the margin, text at 0.5"
BODY_FIRST_LINE = Inches(0.5)
SUB_LEFT = Inches(0.5)
SUB_TEXT = Inches(1.0)
QUOTE_LEFT = Inches(0.5)
ISSUE_LEFT = Inches(0.5)

FOOTER_LEFT = "JDF 1987  \u2013  Sample Opening Brief"
FOOTER_CENTER = "R: July 12, 2021"
FOOTER_PAGE_LABEL = "Page "

# The JDF sample sets a bold lead-in label on the 0.5" stop with its content
# tabbed to the 1.0" stop, wrapping back to 1.0" (a 0.5" hanging indent).
LABEL_BOLD = True

# Footnote ids are 1-based; 0 and 1 are reserved for the separator entries.
_FOOTNOTE_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/footnotes"
_CONTENT_TYPE_FOOTNOTES = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.footnotes+xml"
)

FOOTNOTES_XML_HEAD = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    '<w:footnotes xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
    'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
    '<w:footnote w:type="separator" w:id="-1"><w:p><w:pPr>'
    '<w:spacing w:after="0" w:line="240" w:lineRule="auto"/>'
    '</w:pPr><w:r><w:separator/></w:r></w:p></w:footnote>'
    '<w:footnote w:type="continuationSeparator" w:id="0"><w:p><w:pPr>'
    '<w:spacing w:after="0" w:line="240" w:lineRule="auto"/>'
    '</w:pPr><w:r><w:continuationSeparator/></w:r></w:p></w:footnote>'
)


def _el(tag: str, **attrs: str):
    """Create a ``w:`` element, quoting every attribute value."""
    parts = []
    for key, value in attrs.items():
        parts.append('%s="%s"' % (key.replace("_", ":"), _esc(value)))
    body = (" " + " ".join(parts)) if parts else ""
    return "<w:%s%s/>" % (tag, body)


def _esc(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


# ---------------------------------------------------------------------------
# Runs and paragraphs
# ---------------------------------------------------------------------------

def set_run_font(run, size=BODY_PT, bold=False, italic=False, name=FONT,
                 underline=False) -> None:
    """Apply explicit run properties Word and Google Docs both honour."""
    run.font.name = name
    run.font.size = size
    run.font.bold = bold
    run.font.italic = italic
    # python-docx inserts w:u in its schema-correct position; appending it by
    # hand puts it after w:sz, which the renderer then ignores.
    run.font.underline = bool(underline)
    rpr = run._element.get_or_add_rPr()
    if not underline:
        # False writes nothing, so a run following an underlined one -- the
        # title after the letter of a lettered heading -- would inherit the
        # underline.  Force an explicit "none".
        existing = rpr.find(qn("w:u"))
        if existing is not None:
            rpr.remove(existing)
        run.font.underline = None
        u = OxmlElement("w:u")
        u.set(qn("w:val"), "none")
        rpr.append(u)
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.insert(0, rfonts)
    for attr in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
        rfonts.set(qn(attr), name)


def add_runs(paragraph, segments, size=BODY_PT, bold=False,
             underline=False) -> None:
    """Add ``(text, italic)`` segments as runs."""
    for text, italic in segments:
        if not text:
            continue
        run = paragraph.add_run(text)
        set_run_font(run, size=size, bold=bold, italic=italic,
                     underline=underline)


def set_line_height(paragraph, points: float) -> None:
    """Set an exact line height in points.

    ``lineRule="auto"`` with ``w:line="480"`` looks like double spacing but is
    not: Word multiplies the font's full line box (31.5pt for 12pt Garamond),
    while LibreOffice and Google Docs' DOCX importer multiply only
    ascent+descent, which yields about 27pt. The brief then renders visibly
    tighter than the JDF sample. An exact height of 31.5pt is honoured
    identically by Word, LibreOffice and Google Docs, so the double spacing
    the sample calls for actually survives.
    """
    pf = paragraph.paragraph_format
    pf.line_spacing = Pt(points)
    pf.line_spacing_rule = WD_LINE_SPACING.EXACTLY


def set_spacing(paragraph, *, before=0, after=0, line=None, rule="auto") -> None:
    """Set space before/after, and optionally a multiple line spacing."""
    pf = paragraph.paragraph_format
    pf.space_before = Pt(before)
    pf.space_after = Pt(after)
    if line is not None:
        pf.line_spacing = line
        pf.line_spacing_rule = (
            WD_LINE_SPACING.DOUBLE if line == 2.0 else WD_LINE_SPACING.MULTIPLE
        )


def set_indent(paragraph, *, left=None, first=None, hanging=None) -> None:
    pf = paragraph.paragraph_format
    if left is not None:
        pf.left_indent = left
    if hanging is not None:
        pf.first_line_indent = -hanging
    elif first is not None:
        pf.first_line_indent = first


def add_tab_stop(paragraph, position, alignment="left") -> None:
    from docx.enum.text import WD_TAB_ALIGNMENT

    mapping = {
        "left": WD_TAB_ALIGNMENT.LEFT,
        "center": WD_TAB_ALIGNMENT.CENTER,
        "right": WD_TAB_ALIGNMENT.RIGHT,
    }
    paragraph.paragraph_format.tab_stops.add_tab_stop(
        position, mapping.get(alignment, WD_TAB_ALIGNMENT.LEFT)
    )


def keep_with_next(paragraph) -> None:
    paragraph.paragraph_format.keep_with_next = True


def add_space_before(paragraph, points: float) -> None:
    """Add *points* of space above an already-built paragraph."""
    current = paragraph.paragraph_format.space_before
    existing = current.pt if current is not None else 0.0
    paragraph.paragraph_format.space_before = Pt(existing + points)


def keep_lines_together(paragraph) -> None:
    """Widow/orphan control only.

    Deliberately not ``keep_together``: a double-spaced legal paragraph may
    legitimately flow across a page break, and forcing whole paragraphs onto
    one page inflates the brief's page count considerably.
    """
    paragraph.paragraph_format.widow_control = True


def suppress_auto_hyphenation(paragraph) -> None:
    """Word must not hyphenate quoted legal text into the margin."""
    ppr = paragraph._element.get_or_add_pPr()
    if ppr.find(qn("w:suppressAutoHyphens")) is None:
        ppr.append(OxmlElement("w:suppressAutoHyphens"))


# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------

# The sample's footer ("JDF 1987 - Sample Opening Brief" / "R: July 12, 2021")
# is boilerplate from the court's *sample* form, not part of a real brief, so
# it is not reproduced.  A filing normally carries only a page number; pass
# text to build_footer to add a document identifier of your own.
DEFAULT_FOOTER_LEFT = ""
DEFAULT_FOOTER_CENTER = ""
DEFAULT_FOOTER_RIGHT = "Page {page}"
PAGE_TOKEN = "{page}"


def build_footer(section, *, left: str = DEFAULT_FOOTER_LEFT,
                 center: str = DEFAULT_FOOTER_CENTER,
                 right: str = DEFAULT_FOOTER_RIGHT,
                 page_number: bool = True,
                 text_width=Inches(6.5)) -> None:
    """Build the footer from three cells: left, centre, right.

    ``{page}`` inside *right* is replaced by a live Word ``PAGE`` field.  With
    no left or centre text and *page_number* true, this is just a page number
    in the right margin.
    """
    footer = section.footer
    footer.is_linked_to_previous = False
    paragraph = footer.paragraphs[0] if footer.paragraphs else footer.add_paragraph()
    paragraph.text = ""

    if not (left or center or right or page_number):
        return

    half = int(text_width / 2)
    add_tab_stop(paragraph, half, "center")
    add_tab_stop(paragraph, text_width, "right")

    right_text = right if page_number else right.replace(PAGE_TOKEN, "")
    before, sep, after = right_text.partition(PAGE_TOKEN)

    run = paragraph.add_run(left + "\t" + center + "\t" + before)
    set_run_font(run, size=FOOTER_PT)
    if sep:
        _add_field(paragraph, "PAGE")
    if after:
        tail = paragraph.add_run(after)
        set_run_font(tail, size=FOOTER_PT)
    set_spacing(paragraph, before=0, after=0, line=1.0)


def _add_field(paragraph, instruction: str) -> None:
    """Insert a simple Word field such as ``PAGE``."""
    run = paragraph.add_run()
    set_run_font(run, size=FOOTER_PT)
    r = run._element

    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = " %s " % instruction
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    for node in (begin, instr, end):
        r.append(node)


# ---------------------------------------------------------------------------
# Footnotes
# ---------------------------------------------------------------------------

def _footnote_paragraph_xml(text_runs: list[tuple[str, bool, bool]]) -> str:
    """Build one footnote paragraph from ``(text, bold, italic)`` runs."""
    pieces = [
        '<w:p><w:pPr><w:pStyle w:val="FootnoteText"/>'
        '<w:spacing w:before="0" w:after="0" w:line="240" w:lineRule="auto"/>'
        '<w:ind w:left="0" w:firstLine="0"/></w:pPr>',
        '<w:r><w:rPr><w:rStyle w:val="FootnoteReference"/>'
        '<w:rFonts w:ascii="%s" w:hAnsi="%s"/></w:rPr><w:footnoteRef/></w:r>'
        % (FONT, FONT),
    ]
    for text, bold, italic in text_runs:
        props = '<w:rFonts w:ascii="%s" w:hAnsi="%s" w:cs="%s"/>' % (FONT, FONT, FONT)
        if bold:
            props += "<w:b/>"
        if italic:
            props += "<w:i/>"
        pieces.append(
            '<w:r><w:rPr>%s<w:sz w:val="%d"/><w:szCs w:val="%d"/></w:rPr>'
            '<w:t xml:space="preserve">%s</w:t></w:r>'
            % (props, int(FOOTNOTE_PT.pt * 2), int(FOOTNOTE_PT.pt * 2), _esc(text))
        )
    pieces.append("</w:p>")
    return "".join(pieces)


class FootnoteStore:
    """Collects footnote text and writes the ``footnotes.xml`` part."""

    def __init__(self) -> None:
        self._bodies: list[list[tuple[str, bool, bool]]] = []

    def add(self, runs: list[tuple[str, bool, bool]]) -> int:
        """Register a footnote and return its 1-based id."""
        self._bodies.append(runs)
        return len(self._bodies)

    @property
    def count(self) -> int:
        return len(self._bodies)

    def xml(self) -> str:
        parts = [FOOTNOTES_XML_HEAD]
        for index, runs in enumerate(self._bodies, start=1):
            parts.append('<w:footnote w:id="%d">' % index)
            parts.append(_footnote_paragraph_xml(runs))
            parts.append("</w:footnote>")
        parts.append("</w:footnotes>")
        return "".join(parts).encode("utf-8")

    def attach(self, document) -> None:
        """Register the part and relation so Word resolves the references."""
        if not self._bodies:
            return
        uri = PackURI("/word/footnotes.xml")
        part = Part(uri, _CONTENT_TYPE_FOOTNOTES, self.xml(), document.part.package)
        document.part.relate_to(part, RT.FOOTNOTES)


def add_footnote_reference(paragraph, footnote_id: int) -> None:
    """Append ``w:footnoteReference`` to *paragraph*."""
    run = paragraph.add_run()
    set_run_font(run, size=BODY_PT)
    ref = OxmlElement("w:footnoteReference")
    ref.set(qn("w:id"), str(footnote_id))
    run._element.append(ref)
