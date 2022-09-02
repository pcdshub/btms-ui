import functools
import pathlib
import subprocess
import sys
from typing import Callable, List

import ophyd
from pcdsdevices.lasers import btms_config
from pcdsdevices.lasers.btps import BtpsState as BtpsStateDevice
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


def open_typhos_in_subprocess(*devices: str) -> subprocess.Popen:
    return subprocess.Popen(
        args=[sys.executable, "-m", "typhos", *devices],
    )


def prune_expert_issues(issues: List[btms_config.MoveError]) -> List[btms_config.MoveError]:
    """
    Remove issues that experts can safely ignore.

    Parameters
    ----------
    issues : List[MoveError]
        The list of issues to be resolved prior to moving.

    Returns
    -------
    List[MoveError]
        A pruned list of issues.
    """
    return [
        issue
        for issue in issues
        if not isinstance(
            issue,
            (btms_config.PositionInvalidError, btms_config.MaintenanceModeActiveError)
        )
    ]


_btps_device_by_prefix = {}


def get_btps_device(prefix: str = "") -> BtpsStateDevice:
    """
    Get the BtpsState singleton.

    Parameters
    ----------
    prefix : str, optional
        Custom prefix to use.
    """
    if _btps_device_by_prefix.get(prefix, None) is None:
        _btps_device_by_prefix[prefix] = BtpsStateDevice(prefix, name="las_btps")

    return _btps_device_by_prefix[prefix]
