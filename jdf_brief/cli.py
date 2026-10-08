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
        "--dry-run", action="store_true",
        help="print the detected block structure without writing a file",
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
        )
        print("skipped caption:", result.skipped_caption)
        print("skipped toc    :", result.skipped_toc)
        print("blocks         :", len(result.blocks))
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
    )
    print("wrote %s" % path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
