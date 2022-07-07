import functools
import pathlib
from typing import Callable

import ophyd
from qtpy import QtCore

#: The source path of the btms-ui package.
BTMS_SOURCE_PATH = pathlib.Path(__file__).resolve().parent


def run_in_gui_thread(func: Callable, *args, _start_delay_ms: int = 0, **kwargs):
    """Run the provided function in the GUI thread."""
    QtCore.QTimer.singleShot(_start_delay_ms, functools.partial(func, *args, **kwargs))


def channel_from_device(device: ophyd.Device) -> str:
    """PyDM-compatible PV name URIs from a given ophyd Device."""
    return f"ca://{device.prefix}"


def channel_from_signal(signal: ophyd.signal.EpicsSignalBase) -> str:
    """PyDM-compatible PV name URIs from a given EpicsSignal."""
    return f"ca://{signal.pvname}"
