import dataclasses
from btms_ui.scene import SourcePosition, DestinationPosition
from btms_ui.util import get_btps_device
from typing import Optional


def ophyd_cleanup():
    """Clean up ophyd - avoid teardown errors by stopping callbacks."""
    import ophyd
    dispatcher = ophyd.cl.get_dispatcher()
    if dispatcher is not None:
        dispatcher.stop()


@dataclasses.dataclass
class Config:
    linear: Optional[float]
    rotary: Optional[float]
    # goniometer: float


default_rotary_positions = {
    ("left", "up"): 45.6414,
    ("left", "down"): 135.6510,
    ("right", "up"): 315.085,
    ("right", "down"): 225.12,
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
        ),
    },
}


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
            )

            if config.linear is None:
                config.linear = guess_config.linear
            if config.rotary is None:
                config.rotary = guess_config.rotary

            print(source.name_and_desc, dest.name_and_desc, config)
            if not dry_run:
                try:
                    device = btps.destinations[dest].sources[source]
                except KeyError:
                    print("No device for", dest, source)
                    continue
                device.linear.nominal.put(config.linear)
                device.linear.low.put(config.linear - 5.0)
                device.linear.high.put(config.linear + 5.0)
                device.rotary.nominal.put(config.rotary)
                device.rotary.low.put(config.rotary - 5.0)
                device.rotary.high.put(config.rotary + 5.0)
                device.goniometer.nominal.put(0.0)
                device.goniometer.low.put(-5.0)
                device.goniometer.high.put(+5.0)


try:
    dry_run = False
    set_all()
finally:
    ophyd_cleanup()

