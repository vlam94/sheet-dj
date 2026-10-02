"""Entry point of the packaged program: the same function the `sheet-dj` script runs."""

import sys

from sheet_dj.launcher import main

if __name__ == "__main__":
    sys.exit(main())
