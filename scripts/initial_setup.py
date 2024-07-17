import dataclasses
from typing import Optional

from ophyd import EpicsSignal
from pcdsdevices.lasers.btps import RangeComparison

from btms_ui.scene import DestinationPosition, SourcePosition
from btms_ui.util import get_btps_device


def ophyd_cleanup():
    """Clean up ophyd - avoid teardown errors by stopping callbacks."""
    import ophyd
    dispatcher = ophyd.cl.get_dispatcher()
    if dispatcher is not None:
        dispatcher.stop()


@dataclasses.dataclass
class Config:
    linear: Optional[float] = None
    rotary: Optional[float] = None
    goniometer: Optional[float] = None


default_rotary_positions = {
    ("left", "up"): 45.6414,
    ("left", "down"): 135.6510,
    ("right", "up"): 315.085,
    ("right", "down"): 225.12,
}

default_goniometer_positions = {
    ("left", "up"): -0.4666,
    ("left", "down"): -0.4276,
    ("right", "up"): -0.28,
    ("right", "down"): -0.3219,
}


# Bottom destinations (rough top centers, inside chamber)
BOTTOM_PORTS = [
    1,
    2,
    3,
    4,
    5,
    6,
    7,
]
TOP_PORTS = [
    8,
    9,
    10,
    11,
    12,
    13,
    14,
]


def guess_position_for_port(source: SourcePosition, dest: DestinationPosition) -> float:
    """
    Make a guess at a linear stage position given the destination port number.

    Parameters
    ----------
    dest : int
        The destination port number.

    Returns
    -------
    float
        Linear stage position guess.
    """
    # 8.5" spacing per side
    # 215.9 mm port-to-port
    port_spacing_mm = 215.9
    # TMO IP1 is always known:
    if source.is_left:
        top_start = full_config[SourcePosition.ls1][DestinationPosition.ld8].linear
    else:
        top_start = full_config[SourcePosition.ls8][DestinationPosition.ld8].linear

    assert top_start is not None
    bottom_start = top_start + port_spacing_mm / 2

    dest_index = dest.index
    if dest_index in TOP_PORTS:
        port_index = TOP_PORTS.index(dest_index)
        start = top_start
    else:
        port_index = BOTTOM_PORTS.index(dest_index)
        start = bottom_start

    return start + port_index * port_spacing_mm


full_config = {
    # LS1 - bay 1
    SourcePosition.ls1: {
        DestinationPosition.ld2: Config(
            # "TMO IP3",
            linear=None,
            rotary=None,
        ),
        DestinationPosition.ld4: Config(
            # "RIX ChemRIXS",
            linear=787.9045,
            rotary=135.6510,
            goniometer=-0.4276,
        ),
        DestinationPosition.ld6: Config(
            # "RIX QRIXS",
            linear=None,
            rotary=None,
        ),
        DestinationPosition.ld8: Config(
            # "TMO IP1",
            linear=46.4244,
            rotary=45.6414,
            goniometer=-0.4666,
        ),
        DestinationPosition.ld9: Config(
            # "Laser Lab",
            linear=None,
            rotary=None,
        ),
        DestinationPosition.ld10: Config(
            # "TMO IP2",
            linear=None,
            rotary=None,
        ),
        DestinationPosition.ld14: Config(
            # "XPP",
            linear=1339.5865,
            rotary=45.6566,
            goniometer=-0.4394,
        ),
    },
    # LS5 - bay 3
    SourcePosition.ls8: {
        DestinationPosition.ld9: Config(
            # "Laser Lab",
            linear=252.860,
            rotary=315.085,
        ),
    },
    # LS8 - bay 4
    SourcePosition.ls8: {
        DestinationPosition.ld2: Config(
            # "TMO IP3",
            linear=None,
            rotary=None,
        ),
        DestinationPosition.ld4: Config(
            # "RIX ChemRIXS",
            linear=782.60952,
            rotary=225.12,
            goniometer=-0.3219,
        ),
        DestinationPosition.ld6: Config(
            # "RIX QRIXS",
            linear=None,
            rotary=None,
        ),
        DestinationPosition.ld8: Config(
            # "TMO IP1",
            linear=31.95952,
            rotary=315.085,
            goniometer=-0.28,
        ),
        DestinationPosition.ld9: Config(
            # "Laser Lab",
            linear=None,
            rotary=None,
        ),
        DestinationPosition.ld10: Config(
            # "TMO IP2",
            linear=None,
            rotary=None,
        ),
        DestinationPosition.ld14: Config(
            # "XPP",
            linear=1329.95952,
            rotary=315.107,
            goniometer=-0.338,
        ),
    },
}


def _put(signal: EpicsSignal, value: float):
    current = signal.get()
    if abs(current - value) > 1e-6:
        print(f"-> Changing {signal.pvname} to {value}")
        if not dry_run:
            signal.put(value)


def _update(device: RangeComparison, value: float, delta: float):
    _put(device.nominal, value)
    _put(device.low, value - delta)
    _put(device.high, value + delta)


def set_all():
    btps = get_btps_device()

    for source in SourcePosition:
        for dest in DestinationPosition:
            try:
                config = full_config[source][dest]
            except KeyError:
                config = Config(linear=None, rotary=None)

            left_text = "left" if source.is_left else "right"
            up_text = "up" if dest.is_top else "down"
            key = (left_text, up_text)
            guess_config = Config(
                linear=guess_position_for_port(source, dest),
                rotary=default_rotary_positions[key],
                goniometer=default_goniometer_positions[key],
            )

            if config.linear is None:
                config.linear = guess_config.linear
            if config.rotary is None:
                config.rotary = guess_config.rotary
            if config.goniometer is None:
                config.goniometer = guess_config.goniometer

            print(source.name_and_desc, dest.name_and_desc, config)
            if not dry_run:
                try:
                    device = btps.destinations[dest].sources[source]
                except KeyError:
                    print("No device for", dest, source)
                    continue

                _update(device.linear, config.linear, delta=5.0)
                _update(device.rotary, config.rotary, delta=5.0)
                _update(device.goniometer, config.goniometer, delta=5.0)


try:
    dry_run = False
    set_all()
finally:
    ophyd_cleanup()
