"""Console entry point shared by the onedir and onefile Windows bundles."""

import sys

from netaudit.cli import main


if __name__ == "__main__":
    # A frozen interpreter does not necessarily honor PYTHONUTF8. Windows pipes
    # otherwise use the host code page, which may not encode Chinese reports.
    # Native console streams keep Python's Unicode-aware console behavior.
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and not stream.isatty() and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    raise SystemExit(main())
