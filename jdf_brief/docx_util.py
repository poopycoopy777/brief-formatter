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
BODY_PT = Pt(12)
HEADING_PT = Pt(14)
FOOTNOTE_PT = Pt(10)
FOOTER_PT = Pt(10.5)

BODY_LEADING = 2.0          # double spaced
MAJOR_TAB = Inches(0.5)     # number at the margin, text at 0.5"
BODY_FIRST_LINE = Inches(0.5)
SUB_LEFT = Inches(0.5)
SUB_TEXT = Inches(1.0)
QUOTE_LEFT = Inches(0.5)
ISSUE_LEFT = Inches(0.5)

FOOTER_LEFT = "JDF 1987  \u2013  Sample Opening Brief"
FOOTER_CENTER = "R: July 12, 2021"

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

def set_run_font(run, size=BODY_PT, bold=False, italic=False, name=FONT) -> None:
    """Apply explicit run properties Word and Google Docs both honour."""
    run.font.name = name
    run.font.size = size
    run.font.bold = bold
    run.font.italic = italic
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.insert(0, rfonts)
    for attr in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
        rfonts.set(qn(attr), name)


def add_runs(paragraph, segments, size=BODY_PT, bold=False) -> None:
    """Add ``(text, italic)`` segments as runs."""
    for text, italic in segments:
        if not text:
            continue
        run = paragraph.add_run(text)
        set_run_font(run, size=size, bold=bold, italic=italic)


def set_spacing(paragraph, *, before=0, after=0, line=None, rule="auto") -> None:
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

def build_footer(section, text_width=Inches(6.5)) -> None:
    """Three-cell footer: document id | revision | page number."""
    footer = section.footer
    footer.is_linked_to_previous = False
    paragraph = footer.paragraphs[0] if footer.paragraphs else footer.add_paragraph()
    paragraph.text = ""

    half = int(text_width / 2)
    add_tab_stop(paragraph, half, "center")
    add_tab_stop(paragraph, text_width, "right")

    run = paragraph.add_run(FOOTER_LEFT + "\t" + FOOTER_CENTER + "\t")
    set_run_font(run, size=FOOTER_PT)
    _add_field(paragraph, "PAGE")
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
