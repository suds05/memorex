######################################################################
#
# Module entrypoint for running the memoir CLI with `python -m memoir`.
#
# This module delegates execution to the CLI main function when the
# package is invoked as a Python module.
#
# Author: Sudhakar Narayanamurthy.
#

from .cli import main


if __name__ == "__main__":
    raise SystemExit(main())
