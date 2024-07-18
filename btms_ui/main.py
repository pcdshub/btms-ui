import logging
import signal
import sys
from typing import Optional

import typhos
from pydm.exception import install as install_exception_handler
from qtpy import QtWidgets

from . import util
from .widgets import BtmsMain, HutchOverviewDisplay

logger = logging.getLogger(__name__)


def _sigint_handler(signal, frame):
    logger.info("Caught Ctrl-C (SIGINT); exiting.")
    sys.exit(1)


def _configure_stylesheet(paths: Optional[list[str]] = None) -> str:
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
        with open(path) as fp:
            stylesheets.append(fp.read())

    full_stylesheet = "\n\n".join(stylesheets)

    app.setStyleSheet(full_stylesheet)
    return full_stylesheet


def configure_ophyd():
    """Configure ophyd defaults."""
    from ophyd.signal import EpicsSignalBase
    EpicsSignalBase.set_defaults(
        timeout=10.0,
        connection_timeout=10.0,
        auto_monitor=True,
    )


def main(
    screen: str = "overview",
    prefix: str = "",
    stylesheet: Optional[str] = None
) -> None:
    """Launch the ``btms-ui``."""
    signal.signal(signal.SIGINT, _sigint_handler)
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])

    install_exception_handler()
    configure_ophyd()

    try:
        _configure_stylesheet(paths=[stylesheet] if stylesheet else None)
    except Exception:
        logger.exception("Failed to load stylesheet; things may look odd...")

    try:
        if screen == "hutch":
            widget = HutchOverviewDisplay()
        elif screen == "overview":
            widget = BtmsMain()
            widget.prefix = prefix
        elif screen == "btps":
            # Convenience (?) method: typhos las_btps
            widget = typhos.suite.TyphosSuite.from_device(
                util.get_btps_device(prefix=prefix)
            )
        else:
            raise ValueError(f"Unexpected screen type: {screen}")
        widget.show()
    except Exception:
        logger.exception("Failed to load BtmsMain user interface")
        raise
    app.exec_()


if __name__ == "__main__":
    main()
