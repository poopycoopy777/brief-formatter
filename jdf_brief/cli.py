"""Command line entry point: format a plain-text brief as a JDF 1987 DOCX."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .build import build_brief
from .parse import parse


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="jdf-brief",
        description="Format a plain-text Colorado brief to match JDF 1987.",
    )
    parser.add_argument("input", type=Path, help="plain-text brief")
    parser.add_argument(
        "-o", "--output", type=Path, default=None,
        help="output .docx (default: alongside the input)",
    )
    parser.add_argument(
        "--include-caption", action="store_true",
        help="keep the caption block instead of starting at section 1",
    )
    parser.add_argument(
        "--include-toc", action="store_true",
        help="keep the Table of Contents / Table of Authorities blocks",
    )
    parser.add_argument(
        "--keep-duplicates", action="store_true",
        help="keep a paragraph that repeats the one before it (by default a "
             "near-identical consecutive paragraph is dropped)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="print the detected block structure without writing a file",
    )
    parser.add_argument(
        "--footer-left", default=None, metavar="TEXT",
        help="left footer cell (default: empty — the sample's own footer text "
             "belongs to the court's sample form, not to your brief)",
    )
    parser.add_argument(
        "--footer-center", default=None, metavar="TEXT",
        help="centre footer cell (default: empty)",
    )
    parser.add_argument(
        "--footer-right", default=None, metavar="TEXT",
        help="right footer cell; {page} becomes a live page number "
             "(default: 'Page {page}')",
    )
    parser.add_argument(
        "--no-page-numbers", action="store_true",
        help="omit the page number from the footer",
    )
    args = parser.parse_args(argv)

    if not args.input.is_file():
        print("error: not a file: %s" % args.input, file=sys.stderr)
        return 2

    text = args.input.read_text(encoding="utf-8", errors="replace")

    if args.dry_run:
        result = parse(
            text,
            skip_caption=not args.include_caption,
            skip_toc=not args.include_toc,
            collapse_duplicates=not args.keep_duplicates,
        )
        print("skipped caption :", result.skipped_caption)
        print("skipped toc     :", result.skipped_toc)
        print("removed dupes   :", result.removed_duplicates)
        print("blocks          :", len(result.blocks))
        print("-" * 72)
        for block in result.blocks:
            label = block.kind.upper()
            if block.letter:
                label += "(%s)" % block.letter
            preview = block.text if len(block.text) <= 78 else block.text[:75] + "..."
            print("%-10s %s" % (label, preview))
        return 0

    output = args.output or args.input.with_suffix(".docx")
    path = build_brief(
        text,
        output,
        skip_caption=not args.include_caption,
        skip_toc=not args.include_toc,
        collapse_duplicates=not args.keep_duplicates,
        footer_left=args.footer_left,
        footer_center=args.footer_center,
        footer_right=args.footer_right,
        footer_page_number=not args.no_page_numbers,
    )
    print("wrote %s" % path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
