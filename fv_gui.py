#!/usr/bin/env python3
"""flowviewer GUI entry point: ``python fv_gui.py``."""

import sys


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    from fv import __version__

    if argv in (["--version"], ["-V"]):
        print(f"flowviewer {__version__}")
        return 0
    if argv in (["--help"], ["-h"]):
        print("usage: python fv_gui.py")
        return 0

    from fv.gui.main import run_gui

    return run_gui(None)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))