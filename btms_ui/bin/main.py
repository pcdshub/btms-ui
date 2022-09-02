"""
`btms_ui` is the top-level command for accessing various subcommands.

Try:

"""

import argparse
import logging
import sys

import btms_ui

from ..main import main as start_gui

DESCRIPTION = __doc__


def main(args=None):
    top_parser = argparse.ArgumentParser(
        prog='btms-ui',
        description=DESCRIPTION,
        formatter_class=argparse.RawTextHelpFormatter
    )

    top_parser.add_argument(
        "screen",
        default="overview",
        choices=("overview", "hutch", "btps"),
        help="Specify the screen to launch",
    )

    top_parser.add_argument(
        "--version",
        "-V",
        action="version",
        version=btms_ui.__version__,
        help="Show the btms-ui version number and exit.",
    )

    top_parser.add_argument(
        "--prefix",
        type=str,
        default="",
        help="Set the device prefix manually (for debugging)",
    )

    top_parser.add_argument(
        "--log",
        "-l",
        dest="log_level",
        default="INFO",
        type=str,
        help="Python logging level (e.g. DEBUG, INFO, WARNING)",
    )

    args = top_parser.parse_args(args=args)
    kwargs = vars(args)
    log_level = kwargs.pop('log_level')

    logger = logging.getLogger('btms_ui')
    logger.setLevel(log_level)
    logging.basicConfig()

    start_gui(screen=kwargs.pop("screen"), prefix=kwargs["prefix"])


def hutch_screen():
    """Entrypoint for starting the hutch screen."""
    return main(args=["hutch", *sys.argv[1:]])


def overview_screen():
    """Entrypoint for starting the top-level overview screen."""
    return main(args=["overview", *sys.argv[1:]])


def btps_screen():
    """Entrypoint for starting the top-level BTPS screen."""
    return main(args=["btps", *sys.argv[1:]])


if __name__ == '__main__':
    main()
