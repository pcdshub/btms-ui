import logging
import signal
import sys
from typing import ClassVar

from qtpy import QtWidgets

from .core import DesignerDisplay

logger = logging.getLogger(__name__)


class BtmsMain(DesignerDisplay, QtWidgets.QWidget):
    filename: ClassVar[str] = "btms.ui"


def _sigint_handler(signal, frame):
    logger.info("Caught Ctrl-C (SIGINT); exiting.")
    sys.exit(1)


def main():
    """Launch the ``btms-ui``."""
    signal.signal(signal.SIGINT, _sigint_handler)
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])
    widget = BtmsMain()
    widget.show()
    app.exec_()


if __name__ == "__main__":
    main()
