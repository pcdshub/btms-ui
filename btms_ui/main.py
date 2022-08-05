import logging
import signal
import sys
from typing import List, Optional

import typhos
from qtpy import QtWidgets

from . import util
from .widgets import BtmsMain

logger = logging.getLogger(__name__)


def _sigint_handler(signal, frame):
    logger.info("Caught Ctrl-C (SIGINT); exiting.")
    sys.exit(1)


def _configure_stylesheet(paths: Optional[List[str]] = None) -> str:
    """
    Configure stylesheets for btms-ui.

    Parameters
    ----------
    paths : List[str], optional
        A list of paths to stylesheets to load.
        Defaults to those packaged in btms-ui.

    Returns
    -------
    str
        The full stylesheet.
    """
    app = QtWidgets.QApplication.instance()
    typhos.use_stylesheet()

    if paths is None:
        paths = [
            str(util.BTMS_SOURCE_PATH / "stylesheet.qss"),
            str(util.BTMS_SOURCE_PATH / "pydm.qss"),
        ]

    stylesheets = [app.styleSheet()]

    for path in paths:
        with open(path, "rt") as fp:
            stylesheets.append(fp.read())

    full_stylesheet = "\n\n".join(stylesheets)

    app.setStyleSheet(full_stylesheet)
    return full_stylesheet


def main(prefix: str = "", stylesheet: Optional[str] = None):
    """Launch the ``btms-ui``."""
    signal.signal(signal.SIGINT, _sigint_handler)
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])

    try:
        _configure_stylesheet(paths=[stylesheet] if stylesheet else None)
    except Exception:
        logger.exception("Failed to load stylesheet; things may look odd...")

    widget = BtmsMain()
    widget.prefix = prefix
    widget.show()
    app.exec_()


if __name__ == "__main__":
    main()
