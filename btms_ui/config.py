from __future__ import annotations

import enum
import logging
from typing import Dict

logger = logging.getLogger(__name__)


class Position(str, enum.Enum):
    # Top-bottom sources by where the linear stages are
    ls5 = "ls5"
    ls1 = "ls1"
    ls6 = "ls6"
    ls2 = "ls2"
    ls7 = "ls7"
    ls3 = "ls3"
    ls8 = "ls8"
    ls4 = "ls4"

    # Left-right destination ports (top)
    ld8 = "ld8"
    ld9 = "ld9"
    ld10 = "ld10"
    ld11 = "ld11"
    ld12 = "ld12"
    ld13 = "ld13"
    ld14 = "ld14"

    # Left-right destination ports (bottom)
    ld1 = "ld1"
    ld2 = "ld2"
    ld3 = "ld3"
    ld4 = "ld4"
    ld5 = "ld5"
    ld6 = "ld6"
    ld7 = "ld7"

    @property
    def is_left_source(self) -> bool:
        """Is the laser source coming from the left (as in the diagram)?"""
        return self in (
            Position.ls1,
            Position.ls2,
            Position.ls3,
            Position.ls4,
        )

    @property
    def is_top_port(self) -> bool:
        """Is the laser destination a top port?"""
        return self in (
            Position.ld8,
            Position.ld9,
            Position.ld10,
            Position.ld11,
            Position.ld12,
            Position.ld13,
            Position.ld14,
        )


PORT_SPACING_MM = 215.9  # 8.5 in

# PV source index (bay) to installed LS port
source_to_ls_position: Dict[int, Position] = {
    1: Position.ls1,
    3: Position.ls5,
    4: Position.ls8,
}
# PV destination index (bay) to installed LD port
destination_to_ld_position: Dict[int, Position] = {
    1: Position.ld8,   # TMO IP1
    2: Position.ld10,  # TMO IP2
    3: Position.ld2,   # TMO IP3
    4: Position.ld6,   # RIX QRIXS
    5: Position.ld4,   # RIX ChemRIXS
    6: Position.ld14,  # XPP
    7: Position.ld9,   # Laser Lab
}


IMAGES = {
    "switchbox.png": {
        "pixels_to_mm": 1900. / 855.,
        # width: 970px - 115px = 855px is 78.0in or 1900m
        "origin": (0, 0),  # (144, 94),  # inner chamber top-left position (px)
        "positions": {
            # Sources (left side of rail, centered around axis of rotation)
            Position.ls5: (225, 138),
            Position.ls1: (225, 199),
            Position.ls6: (225, 271),
            Position.ls2: (225, 335),
            Position.ls7: (225, 402),
            Position.ls3: (225, 466),
            Position.ls8: (225, 534),
            Position.ls4: (225, 596),

            # Top destinations (rough bottom centers, inside chamber)
            Position.ld8: (238, 94),
            Position.ld9: (332, 94),
            Position.ld10: (425, 94),
            Position.ld11: (518, 94),
            Position.ld12: (612, 94),
            Position.ld13: (705, 94),
            Position.ld14: (799, 94),

            # Bottom destinations (rough top centers, inside chamber)
            # Position.ld0: (191, 636),
            Position.ld1: (285, 636),
            Position.ld2: (379, 636),
            Position.ld3: (473, 636),
            Position.ld4: (567, 636),
            Position.ld5: (661, 636),
            Position.ld6: (752, 636),
            Position.ld7: (842, 636),
        }
    }
}
