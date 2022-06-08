import functools
import pathlib
from typing import Callable

from qtpy import QtCore

#: The source path of the btms-ui package.
BTMS_SOURCE_PATH = pathlib.Path(__file__).resolve().parent


def run_in_gui_thread(func: Callable, *args, _start_delay_ms: int = 0, **kwargs):
    """Run the provided function in the GUI thread."""
    QtCore.QTimer.singleShot(_start_delay_ms, functools.partial(func, *args, **kwargs))
