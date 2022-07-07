from __future__ import annotations

import enum
import logging
import pathlib
from typing import ClassVar, Dict, Optional, Tuple, Union

import ophyd
import pydm
from pcdsdevices.lasers.btps import BtpsState as BtpsStateDevice
from pcdsdevices.lasers.btps import ShutterSafety, SourceConfig
from qtpy import QtCore, QtGui, QtWidgets

from . import util
from .vacuum import EntryGateValve, ExitGateValve, LaserShutter

logger = logging.getLogger(__name__)


def channel_from_device(device: ophyd.Device) -> str:
    """PyDM-compatible PV name URIs from a given ophyd Device."""
    return f"ca://{device.prefix}"


def channel_from_signal(signal: ophyd.signal.EpicsSignalBase) -> str:
    """PyDM-compatible PV name URIs from a given EpicsSignal."""
    return f"ca://{signal.pvname}"


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


def get_left_center(rect: QtCore.QRectF) -> QtCore.QPointF:
    """
    Get the left-center position of the rectangle.

    Parameters
    ----------
    rect : QtCore.QRectF

    Returns
    -------
    QtCore.QPointF
    """
    return QtCore.QPointF(rect.left(), rect.center().y())


def get_right_center(rect: QtCore.QRectF) -> QtCore.QPointF:
    """
    Get the right-center position of the rectangle.

    Parameters
    ----------
    rect : QtCore.QRectF

    Returns
    -------
    QtCore.QPointF
    """
    return QtCore.QPointF(rect.right(), rect.center().y())


def center_transform_origin(obj: QtWidgets.QGraphicsItem):
    """Put the object's transform origin at its center position."""
    obj.setTransformOriginPoint(obj.rect().center())


def center_transform_top_left(obj: Union[QtWidgets.QGraphicsItem, QtWidgets.QGraphicsItemGroup]):
    """Put the object's transform origin at its top-left position."""
    if isinstance(obj, QtWidgets.QGraphicsItemGroup):
        rect = obj.boundingRect()
    else:
        rect = obj.rect()

    obj.setTransformOriginPoint(rect.topLeft())


def create_scene_rectangle_topleft(
    left: float,
    top: float,
    width: float,
    height: float,
    pen: Optional[Union[QtGui.QColor, QtGui.QPen]] = None,
    brush: Optional[Union[QtGui.QColor, QtGui.QBrush]] = None,
    zvalue: Optional[int] = None,
) -> QtWidgets.QGraphicsRectItem:
    """
    Create a QGraphicsRectItem for a QGraphicsScene.

    The transform origin of the rectangle will be set to its top left.

    Parameters
    ----------
    left : float
        The left X position.
    top : float
        The top Y position.
    width : float
        The width.
    height : float
        The height.
    pen : QColor or QPen, optional
        The pen to draw the rectangle with.
    brush : QColor or QBrush, optional
        The brush to draw the rectangle with.
    zvalue : int, optional
        The z index for the rectangle.

    Returns
    -------
    QtWidgets.QGraphicsRectItem
        The created rectangle.
    """
    item = QtWidgets.QGraphicsRectItem(
        QtCore.QRectF(left, top, width, height)
    )
    center_transform_origin(item)
    if pen is not None:
        item.setPen(pen)
    if brush is not None:
        item.setBrush(brush)
    if zvalue is not None:
        item.setZValue(zvalue)
    return item


def create_scene_rectangle(
    cx: float,
    cy: float,
    width: float,
    height: float,
    pen: Optional[Union[QtGui.QColor, QtGui.QPen]] = None,
    brush: Optional[Union[QtGui.QColor, QtGui.QBrush]] = None,
    zvalue: Optional[int] = None,
) -> QtWidgets.QGraphicsRectItem:
    """
    Create a QGraphicsRectItem for a QGraphicsScene.

    The transform origin of the rectangle will be set to its center.

    Parameters
    ----------
    cx : float
        The center X position.
    cy : float
        The center Y position.
    width : float
        The width.
    height : float
        The height.
    pen : QColor or QPen, optional
        The pen to draw the rectangle with.
    brush : QColor or QBrush, optional
        The brush to draw the rectangle with.
    zvalue : int, optional
        The z index for the rectangle.

    Returns
    -------
    QtWidgets.QGraphicsRectItem
        The created rectangle.
    """
    item = QtWidgets.QGraphicsRectItem(
        QtCore.QRectF(cx - width / 2.0, cy - height / 2.0, width, height)
    )
    center_transform_origin(item)
    if pen is not None:
        item.setPen(pen)
    if brush is not None:
        item.setBrush(brush)
    if zvalue is not None:
        item.setZValue(zvalue)
    return item


def create_scene_polygon(
    polygon: QtGui.QPolygonF,
    pen: Optional[Union[QtGui.QColor, QtGui.QPen]] = None,
    brush: Optional[Union[QtGui.QColor, QtGui.QBrush]] = None,
) -> QtWidgets.QGraphicsPolygonItem:
    """
    Create a QGraphicsPolygonItem in the provided shape for a QGraphicsScene.

    The transform origin of the polygon will be set to its center.

    Parameters
    ----------
    polygon : QPolygonF
        The polygon shape.
    pen : QColor or QPen, optional
        The pen to draw the rectangle with.
    brush : QColor or QBrush, optional
        The brush to draw the rectangle with.

    Returns
    -------
    QtWidgets.QGraphicsPolygonItem
        The created polygon.
    """
    item = QtWidgets.QGraphicsPolygonItem(polygon)
    item.setTransformOriginPoint(QtCore.QPointF(0.0, 0.0))
    if pen is not None:
        item.setPen(pen)
    if brush is not None:
        item.setBrush(brush)
    return item


def create_scene_cross(
    width: float,
    height: float,
    pen: Optional[Union[QtGui.QColor, QtGui.QPen]] = None,
    brush: Optional[Union[QtGui.QColor, QtGui.QBrush]] = None,
) -> QtWidgets.QGraphicsPolygonItem:
    """
    Create a QGraphicsPolygonItem in the shape of a cross for a QGraphicsScene.

    The transform origin of the cross will be set to its center.

    Parameters
    ----------
    cx : float
        The center X position.
    cy : float
        The center Y position.
    width : float
        The width.
    height : float
        The height.
    pen : QColor or QPen, optional
        The pen to draw the rectangle with.
    brush : QColor or QBrush, optional
        The brush to draw the rectangle with.

    Returns
    -------
    QtWidgets.QGraphicsPolygonItem
        The created polygon (cross).
    """
    return create_scene_polygon(
        QtGui.QPolygonF(
            [
                QtCore.QPointF(0.0, 0.0),
                QtCore.QPointF(-width / 2.0, 0.0),
                QtCore.QPointF(width / 2.0, 0.0),
                QtCore.QPointF(0.0, 0.0),
                QtCore.QPointF(0.0, -height / 2.0),
                QtCore.QPointF(0.0, height / 2.0),
            ]
        ),
        brush=brush,
        pen=pen,
    )


def align_vertically(
    align_with: QtWidgets.QGraphicsItem,
    *items: QtWidgets.QGraphicsItem
) -> None:
    """
    Align ``items`` vertically with ``align_with``.

    Parameters
    ----------
    align_with : QtWidgets.QGraphicsItem
        The item to align others with.

    *items : QtWidgets.QGraphicsItem
        The items to align vertically.
    """
    target_center = align_with.sceneBoundingRect().center()
    for item in items:
        item_center = item.sceneBoundingRect().center()
        delta_to_center = target_center - item_center
        item.setPos(item.pos().x(), item.pos().y() + delta_to_center.y())


class PositionHelper(QtCore.QObject):
    """
    A helper for monitoring positions via PyDM channels.

    Emits ``position_updated`` whenever X or Y updates.

    Parameters
    ----------
    x : float, optional
        The starting X position.
    y : float, optional
        The starting Y position.
    channel_x : PyDMChannel, optional
        The PyDM channel for the X position.
    channel_y : PyDMChannel, optional
        The PyDM channel for the Y position.
    """

    #: Emitted on every X or Y update.
    position_updated = QtCore.Signal(object, object)  # Optional[float]

    def __init__(
        self,
        x: float = 0.0,
        y: float = 0.0,
        channel_x: Optional[str] = None,
        channel_y: Optional[str] = None,
    ):
        super().__init__()
        self._channel_x = None
        self._channel_y = None
        self._channels = []
        self.channel_x = channel_x
        self.channel_y = channel_y
        self.x = x
        self.y = y

    def _remove_channel(self, channel: pydm.widgets.PyDMChannel):
        old_connections = [
            ch for ch in self._channels
            if ch.address == channel.address
        ]

        for channel in old_connections:
            channel.disconnect()
            self._channels.remove(channel)

    def _set_channel(
        self,
        old: Optional[pydm.widgets.PyDMChannel],
        new: Optional[str],
    ) -> Optional[pydm.widgets.PyDMChannel]:
        """Update a channel setting."""
        if old is None and new is None:
            return None

        if old is not None:
            self._remove_channel(old)

        if not new:
            return None

        channel = pydm.widgets.PyDMChannel(address=new)
        self._channels.append(channel)
        return channel

    @QtCore.Property(str)
    def channel_x(self) -> Optional[str]:
        """The channel address for the X position."""
        if self._channel_x is None:
            return None
        return self._channel_x.address

    @channel_x.setter
    def channel_x(self, value: Optional[str]):
        self._channel_x = self._set_channel(self._channel_x, value)
        if self._channel_x is None:
            return

        self._channel_x.value_slot = self._set_x
        self._channel_x.connect()

    @QtCore.Slot(int)
    @QtCore.Slot(float)
    def _set_x(self, value: Union[float, int]):
        self._update_position(float(value), None)

    @QtCore.Property(str)
    def channel_y(self) -> Optional[str]:
        """The channel address for the Y position."""
        if self._channel_y is None:
            return None
        return self._channel_y.address

    @channel_y.setter
    def channel_y(self, value: Optional[str]):
        self._channel_y = self._set_channel(self._channel_y, value)
        if self._channel_y is None:
            return

        self._channel_y.value_slot = self._set_y
        self._channel_y.connect()

    @QtCore.Slot(int)
    @QtCore.Slot(float)
    def _set_y(self, value: Union[float, int]):
        self._update_position(None, float(value))

    def _update_position(self, x: Optional[float], y: Optional[float]):
        """
        Hook for when X or Y position updated - signal to be emitted.

        Parameters
        ----------
        x : float, optional
            The new X position.
        y : float, optional
            The new Y position.
        """
        if x is not None:
            self.x = x
        if y is not None:
            self.y = y

        self.position_updated.emit(self.x, self.y)


class PyDMPositionedGroup(QtWidgets.QGraphicsItemGroup):
    """
    A graphics item group that gets positioned based on a PyDM channel.
    """

    def __init__(
        self,
        channel_x: Optional[str] = None,
        channel_y: Optional[str] = None,
    ):
        super().__init__()
        self.helper = PositionHelper(channel_x=channel_x, channel_y=channel_y)
        self.helper.position_updated.connect(self._update_position)

    @property
    def channel_x(self) -> Optional[str]:
        """The X channel for the position."""
        return self.helper.channel_x

    @channel_x.setter
    def channel_x(self, value: Optional[str]):
        self.helper.channel_x = value

    @property
    def channel_y(self) -> Optional[str]:
        """The Y channel for the position."""
        return self.helper.channel_y

    @channel_y.setter
    def channel_y(self, value: Optional[str]):
        self.helper.channel_y = value

    def get_offset_position(self, x: float, y: float):
        """Optionally add a position offset."""
        return QtCore.QPointF(x, y)

    def _update_position(self, x: Optional[float], y: Optional[float]):
        offset_position = self.get_offset_position(
            self.x() if x is None else x,
            self.y() if y is None else y,
        )
        self.setPos(offset_position)


class SourceDestinationIndicator(PyDMPositionedGroup):
    pen: ClassVar[QtGui.QPen] = QtGui.QPen(QtGui.QColor("red"), 10.0)
    brush: ClassVar[QtGui.QColor] = QtGui.QColor("black")

    def __init__(
        self,
        base_item: QtWidgets.QGraphicsRectItem,
        channel_x: Optional[str] = None,
        channel_y: Optional[str] = None,
    ):
        self.base_item = base_item
        super().__init__(channel_x=channel_x, channel_y=channel_y)
        self.addToGroup(
            create_scene_cross(width=50, height=50, pen=self.pen, brush=self.brush)
        )

    def get_offset_position(self, x: float, y: float):
        """Optionally add a position offset."""
        base_rect = self.base_item.rect()
        left_center = QtCore.QPointF(base_rect.left(), base_rect.center().y())
        return left_center + QtCore.QPointF(x, y)


class SwitchBox(QtWidgets.QGraphicsItemGroup):
    """
    A graphical representation of the full laser transport system switch box.
    """

    base_padding_multiplier: ClassVar[float] = 1.1
    base_pen: ClassVar[QtGui.QColor] = QtGui.QColor("black")
    base_brush: ClassVar[QtGui.QColor] = QtGui.QColor(217, 217, 217)
    source_margin: ClassVar[float] = 10.0

    base: PackagedPixmap
    assemblies: Dict[int, MotorizedMirrorAssembly]
    sources: Dict[int, LaserSource]
    destinations: Dict[int, Destination]

    def __init__(self):
        super().__init__()

        self.base = PackagedPixmap("switchbox.png")
        self.base.setPos(0, 0)
        self.base.setZValue(-1)

        self.assemblies = self._create_assemblies()
        self.addToGroup(self.base)

        self.sources = self._create_sources()
        self.destinations = self._create_destinations()
        self.beams = self._create_beam_indicators()

        self._align_items()

        # Just some testing code until we have PyDM channels hooked up:
        self.angle = {idx: 0 for idx in source_to_ls_position}
        self.angle_step = {idx: 1 for idx in source_to_ls_position}
        self.timer = QtCore.QTimer()
        self.timer.setInterval(100)
        self.timer.timeout.connect(self._rotating_test)
        self.timer.start()

    def _create_source(self, idx: int) -> LaserSource:
        """Create a single LaserSource for index ``idx``."""
        ls_position = source_to_ls_position[idx]
        source = LaserSource(source_index=idx, ls_position=ls_position)
        return source

    def _create_sources(self) -> Dict[int, LaserSource]:
        """Create all laser sources."""
        sources = {}
        for idx in source_to_ls_position:
            sources[idx] = self._create_source(idx)
            self.addToGroup(sources[idx])

        return sources

    def _create_destination(self, idx: int) -> Destination:
        """Create a single Destination for index ``idx``."""
        return Destination(
            destination_index=idx,
            ld_position=destination_to_ld_position[idx]
        )

    def _create_destinations(self) -> Dict[int, Destination]:
        """Create all laser destinations."""
        destinations = {}
        for idx in destination_to_ld_position:
            dest = self._create_destination(idx)
            destinations[idx] = dest
            self.addToGroup(dest)

            pos = QtCore.QPointF(*self.base.positions[dest.ld_position])
            multiplier = -1.6 if dest.ld_position.is_top_port else 1.1
            pos += QtCore.QPointF(
                -dest.boundingRect().width() / 2.,
                multiplier * dest.boundingRect().height()
            )
            dest.setPos(pos)

        return destinations

    def _create_assembly(self, idx: int) -> MotorizedMirrorAssembly:
        """Create a single MotorizedMirrorAssembly for index ``idx``."""
        assembly = MotorizedMirrorAssembly(
            source_index=idx,
            ls_position=source_to_ls_position[idx],
        )
        return assembly

    def _create_assemblies(self) -> Dict[int, MotorizedMirrorAssembly]:
        """Create all laser assemblies."""
        assemblies = {}
        for idx in source_to_ls_position:
            assembly = self._create_assembly(idx)
            assemblies[idx] = assembly
            self.addToGroup(assemblies[idx])

            pos = self.base.positions[assembly.ls_position]
            assembly.setPos(*pos)

        return assemblies

    def _align_items(self) -> None:
        """Reposition/align graphics items as necessary."""
        for idx, source in self.sources.items():
            assembly = self.assemblies[idx]
            self._align_source_and_assembly(source, assembly)
            self.beams[idx].update_lines()

    def _align_source_and_assembly(
        self, source: LaserSource, assembly: MotorizedMirrorAssembly
    ) -> None:
        """
        Align the source and assembly in the diagram

        Parameters
        ----------
        source : LaserSource
            The source.
        assembly : MotorizedMirrorAssembly
            The assembly.
        """
        if source.ls_position.is_left_source:
            source.setPos(
                assembly.boundingRect().x()
                - (source.boundingRect().width() + self.source_margin),
                0.0,
            )
        else:
            source.setPos(
                self.base.sceneBoundingRect().right() + self.source_margin * 2,
                0.0,
            )

        align_vertically(assembly, source)

    def _create_beam_indicator(self, idx: int) -> BeamIndicator:
        """Create a single BeamIndicator for index ``idx``."""
        return BeamIndicator(
            source=self.sources[idx],
            assembly=self.assemblies[idx],
        )

    def _create_beam_indicators(self) -> Dict[int, BeamIndicator]:
        """Create all laser beam indicators."""
        indicators = {}
        for idx in source_to_ls_position:
            indicators[idx] = self._create_beam_indicator(idx)
            self.addToGroup(indicators[idx])

        return indicators

    @property
    def device(self) -> Optional[BtpsStateDevice]:
        """
        The ophyd device - BtpsStateDevice - associated with the SwitchBox.

        Returns
        -------
        BtpsStateDevice or None
        """
        return self._device

    def get_closest_destination(self, pos: float) -> Optional[Destination]:
        """Get the closest Destination to the given position."""
        distances = {
            abs(dest.pos().x() - pos): dest
            for dest in self.destinations.values()
        }
        if min(distances) >= 100.:
            return None

        dest = distances[min(distances)]
        return dest

    @device.setter
    def device(self, device: Optional[BtpsStateDevice]) -> None:
        self._device = device
        if device is None:
            return

        for source_idx, assembly in self.assemblies.items():
            for dest_idx, indicator in assembly.dest_indicators.items():
                source_conf: SourceConfig = getattr(
                    device, f"dest{dest_idx}.source{source_idx}"
                )
                channel = channel_from_signal(source_conf.linear.nominal)
                indicator.helper.channel_x = channel

            shutter_safety: ShutterSafety = getattr(device, f"shutter{source_idx}")
            source = self.sources[source_idx]
            source.shutter.channelsPrefix = channel_from_device(shutter_safety.lss).rstrip(":")

    def _rotating_test(self):
        """Testing the rotation mechanism."""
        for idx, assembly in self.assemblies.items():
            self.angle[idx] += 1
            assembly.lens.angle = self.angle[idx]
            if assembly.linear_position < 0 or assembly.linear_position >= 1400:
                self.angle_step[idx] *= -1
            assembly.linear_position += (-1) ** idx * (10 * self.angle_step[idx])
            self.beams[idx].destination = self.get_closest_destination(
                assembly.linear_position
            )
            self.beams[idx].update_lines()


class ScaledPixmapItem(QtWidgets.QGraphicsPixmapItem):
    """
    A pixmap that represents a to-scale drawing or physical object.

    Parameters
    ----------
    filename : str

    pixels_to_mm : float, optional

    origin : Tuple[float, float], optional

    """
    filename: pathlib.Path
    pixels_to_mm: float
    origin: Tuple[float, float]

    def __init__(
        self,
        filename: str,
        pixels_to_mm: float = 1.0,
        origin: Optional[Tuple[float, float]] = None,
    ):
        self.filename = util.BTMS_SOURCE_PATH / "ui" / filename
        self.pixels_to_mm = pixels_to_mm
        super().__init__(QtGui.QPixmap(str(self.filename.resolve())))

        self.origin = origin or (0, 0)
        self.setScale(pixels_to_mm)
        self.setTransformOriginPoint(self.boundingRect().topLeft())

    def position_from_pixels(
        self, pixel_pos: Tuple[float, float]
    ) -> Tuple[float, float]:
        """
        Get an item position from the provided pixel position.

        Parameters
        ----------
        pixel_pos : Tuple[float, float]


        Returns
        -------
        Tuple[float, float]

        """
        px, py = pixel_pos
        return (px * self.pixels_to_mm, py * self.pixels_to_mm)


class PackagedPixmap(ScaledPixmapItem):
    """
    A scaled pixmap packaged with btms-ui.

    Parameters
    ----------
    filename : str
        The packaged pixmap filename (in ``ui/``).
    """
    filename: pathlib.Path
    positions: Dict[Position, Tuple[float, float]]

    def __init__(
        self,
        filename: str,
    ):
        info = dict(IMAGES[filename])
        self.positions = dict(info.pop("positions", {}))
        super().__init__(filename=filename, **info)

        for key, pos in list(self.positions.items()):
            # Scale all positions into millimeters
            self.positions[key] = self.position_from_pixels(pos)


class BeamIndicator(QtWidgets.QGraphicsItemGroup):
    """Active laser beam indicator."""
    source: LaserSource
    assembly: MotorizedMirrorAssembly
    _destination: Optional[Destination]
    source_to_assembly: QtWidgets.QGraphicsLineItem
    assembly_to_destination: QtWidgets.QGraphicsLineItem
    lines: Tuple[QtWidgets.QGraphicsLineItem, ...]

    pen_width: ClassVar[int] = 10
    pen: ClassVar[QtGui.QPen] = QtGui.QPen(QtGui.QColor("green"), pen_width)

    def __init__(self, source: LaserSource, assembly: MotorizedMirrorAssembly):
        super().__init__()
        self.source = source
        self.assembly = assembly
        self._destination = None

        self.source_to_assembly = QtWidgets.QGraphicsLineItem(0, 0, 0, 0)
        self.assembly_to_destination = QtWidgets.QGraphicsLineItem(0, 0, 0, 0)
        self.lines = (self.source_to_assembly, self.assembly_to_destination)

        for line in self.lines:
            self.addToGroup(line)
            line.setPen(self.pen)

    def update_lines(self):
        """
        Update the source-assembly and assembly-destination lines based on
        the updated positions of the other widgets.
        """
        entry_valve_rect = self.source.entry_valve_proxy.sceneBoundingRect()
        lens_center = self.assembly.lens.sceneBoundingRect().center()
        if self.source.ls_position.is_left_source:
            source_pos = get_right_center(entry_valve_rect)
        else:
            source_pos = get_left_center(entry_valve_rect)

        source_to_assembly_y = (source_pos.y() + lens_center.y()) / 2.
        self.source_to_assembly.setLine(
            source_pos.x(),
            source_to_assembly_y,
            lens_center.x(),
            source_to_assembly_y,
        )

        if self.source.ls_position.is_left_source:
            source_pos = get_right_center(entry_valve_rect)
        else:
            source_pos = get_left_center(entry_valve_rect)

        self.source_to_assembly.setLine(
            source_pos.x(),
            lens_center.y(),
            lens_center.x(),
            lens_center.y(),
        )

        dest = self._destination
        if dest is None:
            return

        exit_valve_rect = dest.exit_valve_proxy.sceneBoundingRect()
        dest_y = exit_valve_rect.center().y()

        self.assembly_to_destination.setLine(
            lens_center.x(),
            lens_center.y(),
            lens_center.x(),
            dest_y,
        )

    @property
    def destination(self) -> Optional[Destination]:
        """The destination hutch."""
        return self._destination

    @destination.setter
    def destination(self, destination: Destination):
        self._destination = destination
        self.assembly_to_destination.setVisible(destination is not None)


class LaserSource(QtWidgets.QGraphicsItemGroup):
    """
    A graphical representation of a laser source.
    """

    shutter_proxy: QtWidgets.QGraphicsProxyWidget
    shutter: LaserShutter
    entry_valve_proxy: QtWidgets.QGraphicsProxyWidget
    entry_valve: EntryGateValve
    icon_size: ClassVar[int] = 128
    ls_position: Position

    def __init__(self, source_index: int, ls_position: Position):
        super().__init__()

        self.source_index = source_index
        self.ls_position = ls_position

        self.entry_valve = EntryGateValve()
        self.entry_valve.controlsLocation = self.entry_valve.ContentLocation.Hidden
        self.entry_valve.iconSize = self.icon_size
        self.entry_valve.setFixedSize(self.entry_valve.minimumSizeHint())
        self.entry_valve_proxy = QtWidgets.QGraphicsProxyWidget()
        self.entry_valve_proxy.setWidget(self.entry_valve)
        self.addToGroup(self.entry_valve_proxy)
        center_transform_origin(self.entry_valve_proxy)

        self.shutter = LaserShutter()
        self.shutter.controlsLocation = self.shutter.ContentLocation.Hidden
        self.shutter.iconSize = self.icon_size
        self.shutter.setFixedSize(self.shutter.minimumSizeHint())
        self.shutter_proxy = QtWidgets.QGraphicsProxyWidget()
        self.shutter_proxy.setWidget(self.shutter)
        self.addToGroup(self.shutter_proxy)
        center_transform_origin(self.shutter_proxy)

        if ls_position.is_left_source:
            # (Shutter) (Valve)
            shutter_pos = self.entry_valve_proxy.pos() - QtCore.QPointF(
                2. * self.shutter_proxy.boundingRect().width(),
                0.0
            )
        else:
            # (Valve) (Shutter)
            shutter_pos = self.entry_valve_proxy.pos() + QtCore.QPointF(
                self.entry_valve_proxy.boundingRect().width() * 1.1,
                0.0
            )

        self.shutter_proxy.setPos(shutter_pos)
        align_vertically(self.shutter_proxy, self.entry_valve_proxy)

        self.setTransformOriginPoint(self.boundingRect().center())


class Destination(QtWidgets.QGraphicsItemGroup):
    """
    A graphical representation of a destination hutch (LDx).
    """

    exit_valve_proxy: QtWidgets.QGraphicsProxyWidget
    exit_valve: EntryGateValve
    icon_size: ClassVar[int] = 128
    ld_position: Position
    destination_index: int

    def __init__(self, destination_index: int, ld_position: Position):
        super().__init__()

        self.destination_index = destination_index
        self.ld_position = ld_position

        self.exit_valve = ExitGateValve()
        self.exit_valve.controlsLocation = self.exit_valve.ContentLocation.Hidden
        self.exit_valve.iconSize = self.icon_size
        self.exit_valve.setFixedSize(self.exit_valve.minimumSizeHint())
        self.exit_valve_proxy = QtWidgets.QGraphicsProxyWidget()
        self.exit_valve_proxy.setWidget(self.exit_valve)
        self.addToGroup(self.exit_valve_proxy)
        center_transform_origin(self.exit_valve_proxy)

        self.exit_valve_proxy.setRotation(90.)


class MotorizedMirrorAssembly(QtWidgets.QGraphicsItemGroup):
    """
    A graphical representation of a single motorized mirror assembly.

    It contains a LensAssembly which has
    """

    base_width: ClassVar[float] = 1450.0
    base_height: ClassVar[float] = 50.0
    base_pen: ClassVar[QtGui.QColor] = QtGui.QColor("green")
    base_brush: ClassVar[QtGui.QColor] = QtGui.QColor("transparent")

    base: QtWidgets.QGraphicsRectItem
    lens: LensAssembly
    source_index: int
    source_device: SourceConfig

    def __init__(self, source_index: int, ls_position: Position):
        super().__init__()

        self.source_index = source_index
        self.ls_position = ls_position

        self.base = create_scene_rectangle_topleft(
            left=0,
            top=-self.base_height / 2.0,
            width=self.base_width,
            height=self.base_height,
            pen=self.base_pen,
            brush=self.base_brush,
        )
        self.base.setZValue(0)
        self.addToGroup(self.base)

        self.lens = LensAssembly()
        self.addToGroup(self.lens)

        self.lens.setZValue(2)
        self.dest_indicators = {
            idx: SourceDestinationIndicator(self.base)
            for idx in destination_to_ld_position
        }

        for indicator in self.dest_indicators.values():
            self.addToGroup(indicator)
            indicator.setZValue(1)

        self.setTransformOriginPoint(get_left_center(self.base.rect()))

    @property
    def linear_position(self) -> float:
        """The position of the lens assembly on the linear stage."""
        return self.lens.pos().x()

    @linear_position.setter
    def linear_position(self, pos: float) -> None:
        self.lens.setPos(QtCore.QPointF(pos, 0.0))


class LensAssembly(QtWidgets.QGraphicsItemGroup):
    """
    A graphical representation of a single lens assembly.
    """

    base_width: ClassVar[float] = 50.0
    base_height: ClassVar[float] = 50.0
    base_pen: ClassVar[QtGui.QColor] = QtGui.QColor("black")
    base_brush: ClassVar[QtGui.QColor] = QtGui.QColor(217, 217, 217)

    lens_width: ClassVar[float] = 8.0
    lens_height: ClassVar[float] = 50.0
    lens_pen: ClassVar[QtGui.QColor] = QtGui.QColor("red")
    lens_brush: ClassVar[QtGui.QColor] = QtGui.QColor("red")

    base: QtWidgets.QGraphicsRectItem
    lens: QtWidgets.QGraphicsRectItem

    def __init__(self):
        super().__init__()

        self.base = create_scene_rectangle(
            cx=0.0,
            cy=0.0,
            width=self.base_width,
            height=self.base_height,
            pen=self.base_pen,
            brush=self.base_brush,
        )
        base_center = self.base.rect().center()
        self.addToGroup(self.base)

        self.lens = create_scene_rectangle(
            cx=base_center.x(),
            cy=base_center.y(),
            width=self.lens_width,
            height=self.lens_height,
            pen=self.lens_pen,
            brush=self.lens_brush,
        )

        self.addToGroup(self.lens)

    @property
    def angle(self) -> float:
        """The rotation angle in degrees of the lens assembly."""
        return self.lens.rotation()

    @angle.setter
    def angle(self, angle: float) -> None:
        self.lens.setRotation(angle)


class BtmsStatusView(QtWidgets.QGraphicsView):
    _qt_designer_ = {
        "group": "Laser Transport System",
    }
    device: Optional[BtpsStateDevice]
    switch_box: SwitchBox

    def __init__(
        self,
        parent: Optional[QtWidgets.QWidget] = None,
        scene: Optional[QtWidgets.QGraphicsScene] = None,
    ):
        if scene is None:
            scene = QtWidgets.QGraphicsScene()
        super().__init__(scene, parent=parent)

        self.setMinimumSize(750, 500)
        self.scale(0.25, 0.25)

        self.switch_box = SwitchBox()
        # self.switch_box.setFlag(QtWidgets.QGraphicsItem.ItemClipsChildrenToShape, True)
        # scene.setSceneRect(self.switch_box.boundingRect())
        scene.addItem(self.switch_box)

        self.recenter()

        self._device_prefix = ""
        self.device = None

    def recenter(self) -> None:
        """"Recenter the view on the scene contents."""
        scene = self.scene()
        margin = QtCore.QMarginsF(10, 10, 10, 10)
        self.setSceneRect(
            scene.itemsBoundingRect().marginsAdded(margin)
        )
        self.centerOn(scene.itemsBoundingRect().center())

    @QtCore.Property(str)
    def device_prefix(self) -> str:
        """The prefix for the ophyd Device ``BtpsStateDevice``."""
        return self._device_prefix

    @device_prefix.setter
    def device_prefix(self, prefix: str) -> None:
        self._device_prefix = prefix

        if not prefix:
            return

        if self.device is not None:
            self.device.destroy()
            self.device = None

        self.device = self._create_device(prefix)

    def _create_device(self, prefix: str) -> BtpsStateDevice:
        """
        Create the BTPS State device given its prefix.
        """
        device = BtpsStateDevice(
            prefix,
            name="las_btps"
        )
        self.switch_box.device = device
        return device
