"""Format a Colorado opening brief to match the JDF 1987 sample.

The public entry point is :func:`jdf_brief.build.build_brief`.  ``parse`` and
``italic_segments`` work without python-docx, so the package imports cleanly in
any environment; only :func:`build_brief` needs the DOCX stack.
"""

from .build import build_brief
from .citations import italic_segments
from .parse import parse

__all__ = ["build_brief", "parse", "italic_segments"]
__version__ = "1.0.0"
