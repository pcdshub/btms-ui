import logging
import signal
import sys
from typing import ClassVar, Optional

import typhos
from qtpy import QtWidgets

from . import util
from .core import DesignerDisplay
from .scene import BtmsStatusView

logger = logging.getLogger(__name__)


class BtmsMain(DesignerDisplay, QtWidgets.QWidget):
    filename: ClassVar[str] = "btms.ui"
    view: BtmsStatusView


def _sigint_handler(signal, frame):
    logger.info("Caught Ctrl-C (SIGINT); exiting.")
    sys.exit(1)


def _configure_stylesheet(path: Optional[str] = None) -> str:
    app = QtWidgets.QApplication.instance()
    typhos.use_stylesheet()

    if not path:
        path = str(util.BTMS_SOURCE_PATH / "stylesheet.qss")

    with open(path, "rt") as fp:
        btms_stylesheet = fp.read()

    full_stylesheet = "\n".join((app.styleSheet(), btms_stylesheet))

    app.setStyleSheet(full_stylesheet)
    return full_stylesheet


def main(prefix: str = "", stylesheet: Optional[str] = None):
    """Launch the ``btms-ui``."""
    signal.signal(signal.SIGINT, _sigint_handler)
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])

    try:
        _configure_stylesheet(stylesheet)
    except Exception:
        logger.exception("Failed to load stylesheet; things may look odd...")

    widget = BtmsMain()
    widget.view.device_prefix = prefix
    widget.show()
    app.exec_()


if __name__ == "__main__":
    main()
