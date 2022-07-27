import os

from pcdsdevices.lasers.btms_config import DestinationPosition, SourcePosition

#: The scale for the entire BTMS status view.
VIEW_SCALE = float(os.environ.get("BTMS_VIEW_SCALE", 0.25))
#: The scale for QLabels when shown in the scene.
LABEL_SCALE = float(os.environ.get("BTMS_LABEL_SCALE", 3.0))
#: Images that are packaged with btms-ui.
PACKAGED_IMAGES = {
    "switchbox.png": {
        "pixels_to_mm": 1900. / 855.,
        # width: 970px - 115px = 855px is 78.0in or 1900m
        "origin": (0, 0),  # (144, 94),  # inner chamber top-left position (px)
        "positions": {
            # Sources (left side of rail, centered around axis of rotation)
            SourcePosition.ls5: (225, 138),
            SourcePosition.ls1: (225, 199),
            SourcePosition.ls6: (225, 271),
            SourcePosition.ls2: (225, 335),
            SourcePosition.ls7: (225, 402),
            SourcePosition.ls3: (225, 466),
            SourcePosition.ls8: (225, 534),
            SourcePosition.ls4: (225, 596),

            # Top destinations (rough bottom centers, inside chamber)
            DestinationPosition.ld8: (238, 94),
            DestinationPosition.ld9: (332, 94),
            DestinationPosition.ld10: (425, 94),
            DestinationPosition.ld11: (518, 94),
            DestinationPosition.ld12: (612, 94),
            DestinationPosition.ld13: (705, 94),
            DestinationPosition.ld14: (799, 94),

            # Bottom destinations (rough top centers, inside chamber)
            # Position.ld0: (191, 636),
            DestinationPosition.ld1: (285, 636),
            DestinationPosition.ld2: (379, 636),
            DestinationPosition.ld3: (473, 636),
            DestinationPosition.ld4: (567, 636),
            DestinationPosition.ld5: (661, 636),
            DestinationPosition.ld6: (752, 636),
            DestinationPosition.ld7: (842, 636),
        }
    }
}
