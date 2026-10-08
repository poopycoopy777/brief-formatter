# JDF 1987 brief formatter

Standalone tool. Formats a plain-text Colorado appellate brief so it matches
the **JDF 1987 Sample Opening Brief** that the Colorado Court of Appeals
publishes. The output is a `.docx` you upload to Google Drive and open as a
Google Doc, then export to PDF with **File → Download → PDF Document**.

The caption and the table of contents / table of authorities are **skipped by
default** — you already have those, and they are laid out by hand.

It lives at `D:\Brief Formatter` and is independent of the `legal-app`,
`The Verifyer` and `complete-legal-document-extractor` repositories.

---

## Setup

The parser and citation code use the standard library only, so `--dry-run`
works with no installation. Building a document needs `python-docx`:

```sh
pip install -r requirements.txt
```

## Quick start

Run from this folder:

```sh
# Write the formatted docx next to the input
python -m jdf_brief.cli "Cooper v Ingo Opening Brief V1.txt"

# Choose the output path
python -m jdf_brief.cli brief.txt -o "Cooper_v_Ingo_Opening_Brief_JDF.docx"

# Inspect what the parser detected, without writing anything
python -m jdf_brief.cli brief.txt --dry-run
```

Then:

1. Open <https://drive.google.com> and upload the `.docx`.
2. Right-click it → **Open with → Google Docs**. Uploading rather than pasting
   is what preserves the fonts, indents and the footer.
3. **File → Download → PDF Document (.pdf)**.
4. Paste your caption ahead of section 1 in Google Docs if you want it in the
   same file, or keep it as its own document.

### Options

| Flag | Effect |
| --- | --- |
| `--include-caption` | keep the caption block instead of starting at section 1 |
| `--include-toc` | keep the Table of Contents / Table of Authorities blocks |
| `--dry-run` | print the detected structure and stop |

---

## What it produces

Every measurement below was taken from the sample PDF and is applied exactly.

| Element | Format |
| --- | --- |
| Font | Garamond 12pt, double-spaced (31.5pt leading) |
| Margins | 1" all round, US Letter |
| Major headings (`1. Certificate of Compliance`) | 14pt **bold**; number on the left margin, text tabbed to 0.5" |
| Issue headings (`ISSUE 1: ...`) | 14pt regular, centred, 0.5" indent |
| Sub-headings (`A. Jurisdiction`, `Standard of Review`) | letter on the 0.5" stop, text hanging at 1.0" |
| Body paragraph | 0.5" first-line indent, 0" continuation |
| Block quote / indented legal paragraph | 0.5" left indent, **no** first-line indent |
| Footnotes | 10pt, auto-numbered, real Word footnotes |
| Case names and reporter citations | *italicised automatically* |
| Footer (every page) | `JDF 1987 – Sample Opening Brief` ‖ `R: July 12, 2021` ‖ live page number |

Sections are renumbered sequentially from the order they appear, so a stray
`3.` before a table of authorities cannot leak into the finished brief.

---

## How the input is read

You do not have to mark anything up. The parser recognises what is already
there:

| You wrote | It becomes |
| --- | --- |
| `1. Certificate of Compliance` | major heading 1 |
| `STATEMENT OF THE CASE` | next major heading |
| `A. Jurisdiction` | sub-heading with the letter preserved |
| `Standard of Review` on its own line | sub-heading |
| `ISSUE 1: THE COURT ERRED...` | centred issue heading |
| `1. Whether the district court erred...` under an Issues heading | numbered list item |

Markers are available when you want certainty. If **any** explicit marker
appears in the document, detection is disabled and only the markers are used.

| Marker | Meaning |
| --- | --- |
| `# Heading` | major numbered section |
| `## Heading` | centred issue heading |
| `### A. Heading` | sub-heading |
| `> text` | italic block quote at 0.5" |
| `:: text` | roman indented paragraph at 0.5" |
| `[^ note text]` | a real footnote at that point |
| `*text*` or `_text_` | force italics |

### Italics

Case names and reporter citations are italicised without any markup, because
plain text carries no italics and Colorado practice italicises both:

> The court relied on *Ion Media Networks, Inc. v. West*, 2025 COA 66, ¶ 36.

`C.R.S.`, `C.R.C.P.` and `CRE` are deliberately left roman, matching the
sample. Use `*...*` when you want to override the automatic result.

---

## Layout of the package

```
D:\Brief Formatter\
  README.md            this file
  requirements.txt     python-docx
  run_tests.py         runs the suite without needing pytest
  jdf_brief\
    cli.py             command line entry point
    parse.py           plain text -> block list (headings, body, quotes, footnotes)
    citations.py       case-name / reporter italicisation and inline markup
    build.py           block list -> DOCX
    docx_util.py       fonts, spacing, indents, footer, and the footnote part
  tests\
    test_jdf_brief.py
```

`python-docx` is imported lazily, so `parse` and `italic_segments` work in any
environment; only building the document needs the DOCX stack.

## Notes and limits

* **Footnotes** are real Word footnotes. python-docx has no API for them, so
  `docx_util.py` writes `word/footnotes.xml`, its content-type override and its
  relationship directly. Word, LibreOffice and Google Docs all resolve them.
* **No pagination.** The source line breaks are not retained, because the true
  page numbers depend on the final font metrics and Google Docs re-flows the
  text anyway. The footer page number is a live field. If a court requires line
  numbers, turn them on in Google Docs (Format → Line numbers) after import;
  they are intentionally absent here because the JDF sample has none.
* **Garamond must be installed** to render exactly as the sample does. Google
  Docs supplies it; a machine without it substitutes a serif face and the text
  re-flows.
* The caption and the two tables are skipped by design. Use
  `--include-caption` / `--include-toc` if you want them formatted too.

## Tests

```sh
python run_tests.py -v
```

The DOCX tests skip themselves automatically when `python-docx` is not
installed in the running interpreter, so the suite is safe to run anywhere.
