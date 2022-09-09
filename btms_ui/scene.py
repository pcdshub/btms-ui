from __future__ import annotations

import functools
import logging
import math
import pathlib
from typing import Any, ClassVar, Dict, List, Optional, Tuple

import pcdsdevices.lasers.btms_config as config
from pcdsdevices.lasers.btms_config import DestinationPosition, SourcePosition
from pcdsdevices.lasers.btps import BtpsSourceStatus
from pcdsdevices.lasers.btps import BtpsState as BtpsStateDevice
from pcdsdevices.lasers.btps import (DestinationConfig,
                                     SourceToDestinationConfig)
from qtpy import QtCore, QtGui, QtWidgets

from . import config as btms_config
from . import helpers, primitives, util
from .vacuum import EntryGateValve, ExitGateValve, LaserShutter

logger = logging.getLogger(__name__)


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
        self.helper = helpers.PositionHelper(channel_x=channel_x, channel_y=channel_y)
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
        self.helper.position_set.emit(offset_position)


class PyDMRotatedGroup(QtWidgets.QGraphicsItemGroup):
    """
    A graphics item group that gets rotated based on a PyDM channel.

    Radian values are converted to degrees for offset methods.  This is what
    Qt expects.
    """

    def __init__(
        self,
        channel_angle: Optional[str] = None,
        channel_offset: Optional[str] = None,
        offset: float = 0.0,
        source_is_degrees: bool = True,
    ):
        super().__init__()
        self.helper = helpers.AngleHelper(channel_x=channel_angle, channel_y=channel_offset)
        self.helper.angle_updated.connect(self._update_angle)
        self.offset = offset
        self.source_is_degrees = source_is_degrees

    @property
    def channel_angle(self) -> Optional[str]:
        """The angle channel."""
        return self.helper.channel_x

    @channel_angle.setter
    def channel_angle(self, value: Optional[str]):
        self.helper.channel_x = value

    @property
    def channel_offset(self) -> Optional[str]:
        """The offset channel for the angle."""
        return self.helper.channel_y

    @channel_offset.setter
    def channel_offset(self, value: Optional[str]):
        self.helper.channel_y = value

    def get_offset_angle(self, angle: float):
        """Optionally add an angular offset."""
        return angle

    def _update_angle(self, angle: float):
        if not self.source_is_degrees:
            angle = math.degrees(angle)

        offset_angle = self.get_offset_angle(angle)
        self.setRotation(-offset_angle)
        self.helper.angle_set.emit(offset_angle)


class SourceDestinationIndicator(PyDMPositionedGroup):
    pen: ClassVar[QtGui.QPen] = QtGui.QPen(
        QtGui.QColor("mediumblue"),
        10.0,
        QtCore.Qt.SolidLine,
        QtCore.Qt.SquareCap,
        QtCore.Qt.MiterJoin,
    )
    brush: ClassVar[QtGui.QColor] = QtGui.QColor("mediumblue")
    source: SourcePosition
    dest: DestinationPosition

    def __init__(
        self,
        base_item: QtWidgets.QGraphicsRectItem,
        source: SourcePosition,
        dest: DestinationPosition,
        channel_x: Optional[str] = None,
        channel_y: Optional[str] = None,
    ):
        self.base_item = base_item
        self.source = source
        self.dest = dest
        super().__init__(channel_x=channel_x, channel_y=channel_y)
        arrow = primitives.create_scene_arrow(
            width=15,
            height=35,
            direction=(primitives.ArrowDirection.up if dest.is_top else primitives.ArrowDirection.down),
            pen=self.pen,
            brush=self.brush,
        )

        if dest.is_top:
            arrow.setPos(0, -arrow.sceneBoundingRect().height())
        else:
            arrow.setPos(0, arrow.sceneBoundingRect().height())
        self.addToGroup(arrow)

    def get_offset_position(self, x: float, y: float):
        """Optionally add a position offset."""
        base_rect = self.base_item.rect()
        left_center = QtCore.QPointF(
            base_rect.left(),
            base_rect.center().y(),
        )
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
    assemblies: Dict[SourcePosition, MotorizedMirrorAssembly]
    sources: Dict[SourcePosition, LaserSource]
    destinations: Dict[DestinationPosition, Destination]
    beams: Dict[SourcePosition, BeamIndicator]
    current_destinations: Dict[SourcePosition, Optional[DestinationPosition]]
    _subscriptions: List[helpers.OphydCallbackHelper]

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
        self.current_destinations = {}
        self._subscriptions = []

        self._align_items()

    def _create_source(self, source: SourcePosition) -> LaserSource:
        """Create a single LaserSource for LS ``source``."""
        source = LaserSource(ls_position=source)
        return source

    def _create_sources(self) -> Dict[SourcePosition, LaserSource]:
        """Create all laser sources."""
        sources = {}
        for pos in config.valid_sources:
            sources[pos] = self._create_source(pos)
            self.addToGroup(sources[pos])

        return sources

    def _create_destination(self, dest: DestinationPosition) -> Destination:
        """Create a single Destination for LD ``pos``."""
        return Destination(
            ld_position=dest,
        )

    def _create_destinations(self) -> Dict[DestinationPosition, Destination]:
        """Create all laser destinations."""
        destinations = {}
        for pos in config.valid_destinations:
            dest = self._create_destination(pos)
            destinations[pos] = dest
            self.addToGroup(dest)

            pos_x, _ = self.base.positions[pos]
            if pos.is_top:
                pos_y = self.base.sceneBoundingRect().top() - dest.sceneBoundingRect().height()
            else:
                pos_y = self.base.sceneBoundingRect().bottom()

            pos_x -= dest.exit_valve_proxy.sceneBoundingRect().width() / 2.
            dest.setPos(pos_x, pos_y)

        return destinations

    def _create_assembly(self, source: SourcePosition) -> MotorizedMirrorAssembly:
        """Create a single MotorizedMirrorAssembly for LS ``pos``."""
        assembly = MotorizedMirrorAssembly(
            ls_position=source,
        )

        def assembly_moved(_):
            self._update_all_lines()

        assembly.lens.helper.position_set.connect(assembly_moved)

        return assembly

    def _create_assemblies(self) -> Dict[SourcePosition, MotorizedMirrorAssembly]:
        """Create all laser assemblies."""
        assemblies = {}
        for pos in config.valid_sources:
            assembly = self._create_assembly(pos)
            assemblies[pos] = assembly
            self.addToGroup(assemblies[pos])

            pos = self.base.positions[assembly.ls_position]
            assembly.setPos(*pos)

        return assemblies

    def _align_items(self) -> None:
        """Reposition/align graphics items as necessary."""
        for pos, source in self.sources.items():
            assembly = self.assemblies[pos]
            self._align_source_and_assembly(source, assembly)
            self.beams[pos].update_lines()

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
        if source.ls_position.is_left:
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

    def _create_beam_indicator(self, source: SourcePosition) -> BeamIndicator:
        """Create a single BeamIndicator for LS ``pos``."""
        return BeamIndicator(
            source=self.sources[source],
            assembly=self.assemblies[source],
        )

    def _create_beam_indicators(self) -> Dict[SourcePosition, BeamIndicator]:
        """Create all laser beam indicators."""
        indicators = {}
        for pos in config.valid_sources:
            indicators[pos] = self._create_beam_indicator(pos)
            self.addToGroup(indicators[pos])

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

    def get_closest_destination(self, source: SourcePosition, pos: float) -> Optional[Destination]:
        """Get the closest Destination to the given position."""
        zeropos = self.assemblies[source].base.sceneBoundingRect().left()
        distances = {
            abs(dest.sceneBoundingRect().center().x() - zeropos - pos): dest
            for dest in self.destinations.values()
        }
        if min(distances) >= 75.:
            return None

        dest = distances[min(distances)]
        return dest

    def cleanup(self):
        """Clean up any subscriptions."""
        for helper in self._subscriptions:
            try:
                helper.unsubscribe()
            except Exception:
                logger.exception("Failed to unsubscribe")

    def _update_all_lines(self):
        """Update all beam indicator lines as a shutter/valve was opened/closed."""
        device = self._device
        if device is None:
            return

        for source_pos, beam in self.beams.items():
            beam.destination = self.destinations.get(
                self.current_destinations[source_pos], None
            )
            beam.update_lines()

    def _destination_updated(self, source_pos: SourcePosition, info: Dict[str, Any]):
        """Ophyd callback indicating a destination has updated."""
        value = info.get("value", None)
        try:
            dest_pos = DestinationPosition.from_index(value)
        except ValueError:
            dest_pos = None

        self.current_destinations[source_pos] = dest_pos

    @device.setter
    def device(self, device: Optional[BtpsStateDevice]) -> None:
        self._device = device
        if device is None:
            return

        for source, assembly in self.assemblies.items():
            for dest, indicator in assembly.dest_indicators.items():
                source_conf: SourceToDestinationConfig = getattr(
                    device, f"{dest.name}.{source.name}"
                )
                channel = util.channel_from_signal(source_conf.linear.nominal)
                indicator.helper.channel_x = channel

            source_device: BtpsSourceStatus = getattr(device, source.name)

            self.current_destinations[source] = None
            cur_dest = helpers.OphydCallbackHelper(source_device.current_destination)
            self._subscriptions.append(cur_dest)
            cur_dest.updated.connect(
                functools.partial(self._destination_updated, source)
            )
            cur_dest.subscribe()

            source = self.sources[source]
            source.shutter.device = source_device.lss
            source.shutter.channelsPrefix = util.channel_from_device(
                source.shutter.device
            ).rstrip(":")

            source.entry_valve.device = source_device.entry_valve
            source.entry_valve.channelsPrefix = util.channel_from_device(
                source.entry_valve.device
            ).rstrip(":")

            source.shutter.state_update.connect(self._update_all_lines)
            source.entry_valve.state_update.connect(self._update_all_lines)
            assembly.lens.channel_x = util.channel_from_signal(
                source_device.linear.user_readback
            ).rstrip(":")

            assembly.lens.lens.channel_angle = util.channel_from_signal(
                source_device.rotary.user_readback
            ).rstrip(":")

        for dest in self.destinations.values():
            dest_conf: DestinationConfig = getattr(device, f"{dest.ld_position.name}")
            dest.device = dest_conf
            dest.exit_valve.channelsPrefix = util.channel_from_device(dest_conf.exit_valve)
            dest.exit_valve.device = dest_conf.exit_valve
            dest.exit_valve.state_update.connect(self._update_all_lines)


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
    positions: Dict[config.AnyPosition, Tuple[float, float]]

    def __init__(
        self,
        filename: str,
    ):
        info = dict(btms_config.PACKAGED_IMAGES[filename])
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
        if self.source.ls_position.is_left:
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

        source_shutter = self.source.shutter
        entry_valve = self.source.entry_valve

        self.source_to_assembly.setVisible(
            source_shutter.state.lower() == "open" and
            entry_valve.state.lower() == "open"
        )

        if self.source.ls_position.is_left:
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
            self.assembly_to_destination.setVisible(False)
            return

        self.assembly_to_destination.setVisible(
            self.source_to_assembly.isVisible() and
            dest.exit_valve.state.lower() == "open"
        )
        # exit_valve_rect = dest.exit_valve_proxy.sceneBoundingRect()
        if dest.ld_position.is_top:
            dest_y = dest.sceneBoundingRect().bottom()
        else:
            dest_y = dest.sceneBoundingRect().top()

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
    def destination(self, destination: Optional[Destination]):
        self._destination = destination


class LaserSource(QtWidgets.QGraphicsItemGroup):
    """
    A graphical representation of a laser source.
    """

    shutter_proxy: QtWidgets.QGraphicsProxyWidget
    shutter: LaserShutter
    entry_valve_proxy: QtWidgets.QGraphicsProxyWidget
    entry_valve: EntryGateValve
    icon_size: ClassVar[int] = 128
    ls_position: SourcePosition

    def __init__(self, ls_position: SourcePosition):
        super().__init__()

        self.ls_position = ls_position

        self.entry_valve = EntryGateValve()
        self.entry_valve.controlsLocation = self.entry_valve.ContentLocation.Hidden
        self.entry_valve.iconSize = self.icon_size
        self.entry_valve.setFixedSize(self.entry_valve.minimumSizeHint())
        self.entry_valve_proxy = QtWidgets.QGraphicsProxyWidget()
        self.entry_valve_proxy.setWidget(self.entry_valve)
        self.addToGroup(self.entry_valve_proxy)
        primitives.center_transform_origin(self.entry_valve_proxy)

        self.shutter = LaserShutter()
        self.shutter.controlsLocation = self.shutter.ContentLocation.Hidden
        self.shutter.iconSize = self.icon_size
        self.shutter.setFixedSize(self.shutter.minimumSizeHint())
        self.shutter_proxy = QtWidgets.QGraphicsProxyWidget()
        self.shutter_proxy.setWidget(self.shutter)
        self.addToGroup(self.shutter_proxy)
        primitives.center_transform_origin(self.shutter_proxy)

        self.name_label = QtWidgets.QLabel(
            f"{self.ls_position}:\n{self.ls_position.description}"
        )
        self.name_label.setObjectName("NameLabel")

        self.name_label_proxy = QtWidgets.QGraphicsProxyWidget()
        self.name_label_proxy.setWidget(self.name_label)
        self.name_label_proxy.setScale(btms_config.LABEL_SCALE)
        self.addToGroup(self.name_label_proxy)

        if ls_position.is_left:
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

        self.name_label_proxy.setPos(
            self.entry_valve_proxy.sceneBoundingRect().bottomLeft()
        )

        self.setTransformOriginPoint(self.boundingRect().center())


class Destination(QtWidgets.QGraphicsItemGroup):
    """
    A graphical representation of a destination hutch (LDx).
    """

    name_label_proxy: QtWidgets.QGraphicsProxyWidget
    name_label: QtWidgets.QLabel
    exit_valve_proxy: QtWidgets.QGraphicsProxyWidget
    exit_valve: ExitGateValve
    icon_size: ClassVar[int] = 128
    ld_position: config.DestinationPosition

    def __init__(self, ld_position: config.DestinationPosition):
        super().__init__()

        self.ld_position = ld_position

        self.exit_valve = ExitGateValve()
        self.exit_valve.controlsLocation = self.exit_valve.ContentLocation.Hidden
        self.exit_valve.iconSize = self.icon_size
        self.exit_valve.setFixedSize(self.exit_valve.minimumSizeHint())
        self.exit_valve_proxy = QtWidgets.QGraphicsProxyWidget()
        self.exit_valve_proxy.setWidget(self.exit_valve)
        self.addToGroup(self.exit_valve_proxy)
        primitives.center_transform_origin(self.exit_valve_proxy)

        self.exit_valve_proxy.setRotation(90.)

        self.name_label = QtWidgets.QLabel(
            f"{self.ld_position}:\n{self.ld_position.description}"
        )
        self.name_label.setObjectName("NameLabel")

        self.name_label_proxy = QtWidgets.QGraphicsProxyWidget()
        self.name_label_proxy.setWidget(self.name_label)
        self.name_label_proxy.setScale(btms_config.LABEL_SCALE)
        self.addToGroup(self.name_label_proxy)

        if self.ld_position.is_top:
            self.exit_valve_proxy.setPos(
                self.name_label_proxy.sceneBoundingRect().bottomLeft()
            )
        else:
            self.name_label_proxy.setPos(
                self.exit_valve_proxy.sceneBoundingRect().bottomLeft()
            )


class MotorizedMirrorAssembly(QtWidgets.QGraphicsItemGroup):
    """
    A graphical representation of a single motorized mirror assembly.

    It contains:
    * One LensAssembly (the moving assembly with lens and goniometer installed)
    * One Base: an outline of the rail on which the lens assembly moves
    * One SourceDestinationIndicator per destination - a marker where
      destination nominal positions are
    """

    base_width: ClassVar[float] = 1450.0
    base_height: ClassVar[float] = 50.0
    base_pen: ClassVar[QtGui.QColor] = QtGui.QColor("green")
    base_brush: ClassVar[QtGui.QColor] = QtGui.QColor("transparent")

    base: QtWidgets.QGraphicsRectItem
    lens: LensAssembly
    source_device: SourceToDestinationConfig

    def __init__(self, ls_position: SourcePosition):
        super().__init__()

        self.ls_position = ls_position

        self.base = primitives.create_scene_rectangle_topleft(
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
            dest: SourceDestinationIndicator(self.base, ls_position, dest)
            for dest in config.valid_destinations
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


class LensAssembly(PyDMPositionedGroup):
    """
    A graphical representation of a single lens assembly.
    """

    base_width: ClassVar[float] = 50.0
    base_height: ClassVar[float] = 50.0
    base_pen: ClassVar[QtGui.QColor] = QtGui.QPen(
        QtGui.QColor("black"),
        2.5
    )
    base_brush: ClassVar[QtGui.QColor] = QtGui.QColor("white")

    lens_width: ClassVar[float] = 50.0
    lens_height: ClassVar[float] = 8.0
    lens_pen: ClassVar[QtGui.QColor] = QtGui.QColor("red")
    lens_brush: ClassVar[QtGui.QColor] = QtGui.QColor("red")

    base: QtWidgets.QGraphicsRectItem
    lens: PyDMRotatedGroup

    def __init__(self):
        super().__init__()

        self.base = primitives.create_scene_rectangle(
            cx=0.0,
            cy=0.0,
            width=self.base_width,
            height=self.base_height,
            pen=self.base_pen,
            brush=self.base_brush,
        )
        base_center = self.base.rect().center()
        self.addToGroup(self.base)

        self.lens = PyDMRotatedGroup()
        self.lens.addToGroup(
            primitives.create_scene_rectangle(
                cx=base_center.x(),
                cy=base_center.y(),
                width=self.lens_width,
                height=self.lens_height,
                pen=self.lens_pen,
                brush=self.lens_brush,
            )
        )

        self.lens.addToGroup(
            primitives.create_scene_rectangle(
                cx=base_center.x(),
                cy=base_center.y() - self.lens_height,
                width=self.lens_width / 2.0,
                height=self.lens_height,
                pen=self.lens_pen,
                brush=self.lens_brush,
            )
        )
        self.addToGroup(self.lens)

    @property
    def angle(self) -> float:
        """The rotation angle in degrees of the lens assembly."""
        return self.lens.rotation()

    @angle.setter
    def angle(self, angle: float) -> None:
        self.lens.setRotation(angle)

    def get_offset_position(self, x: float, y: float):
        """Optionally add a position offset."""
        return QtCore.QPointF(x, y)


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

        self.scale(btms_config.VIEW_SCALE, btms_config.VIEW_SCALE)

        self.switch_box = SwitchBox()
        # self.switch_box.setFlag(QtWidgets.QGraphicsItem.ItemClipsChildrenToShape, True)
        # scene.setSceneRect(self.switch_box.boundingRect())
        scene.addItem(self.switch_box)

        self.recenter()

        self._device_prefix = ""
        self.device = None

    def __dtor__(self):
        try:
            self.switch_box.cleanup()
        except Exception:
            logger.exception("Teardown error")

    def resizeEvent(self, event: QtGui.QResizeEvent):
        try:
            self.fitInView(self.scene().sceneRect(), QtCore.Qt.KeepAspectRatio)
            self.recenter()
        except Exception:
            logger.exception("Failed to resize view")
        return super().resizeEvent(event)

    def move_request(self, source: SourcePosition, dest: DestinationPosition):
        device = self.device
        if device is None:
            return

        self._move_status = device.set_source_to_destination(source, dest)

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        item = self.itemAt(event.pos())
        if item is not None:
            group = item.group()
            if isinstance(group, SourceDestinationIndicator):
                # NOTE: Disabling move with clicking of the SourceDestinationIndicator
                # I expect it would not be desirable.  Uncomment the following
                # to re-enable it:
                # self.move_request(group.source, group.dest)
                ...
        if isinstance(item, QtWidgets.QGraphicsProxyWidget):
            # Forward mouse events to proxy widgets
            # TODO: I feel like this shouldn't be necessary and I messed something
            # up; but it works for now...
            event.accept()
            widget = item.widget()
            widget.mousePressEvent(event)
            return
        return super().mousePressEvent(event)

    def recenter(self) -> None:
        """"Recenter the view on the scene contents."""
        scene = self.scene()
        margin = QtCore.QMarginsF(10, 10, 10, 10)
        self.setSceneRect(
            scene.itemsBoundingRect().marginsAdded(margin)
        )
        self.centerOn(scene.itemsBoundingRect().center())

    @QtCore.Property(str)
    def device_prefix(self) -> str:   # pyright: ignore
        """The prefix for the ophyd Device ``BtpsStateDevice``."""
        return self._device_prefix

    @device_prefix.setter
    def device_prefix(self, prefix: str) -> None:
        if prefix is None:
            return

        if self.device is not None:
            if prefix == self._device_prefix:
                return
            self.device.destroy()
            self.device = None

        self._device_prefix = prefix
        self.device = self._create_device(prefix)

    def _create_device(self, prefix: str) -> BtpsStateDevice:
        """
        Create the BTPS State device given its prefix.
        """
        device = util.get_btps_device(prefix)
        self.switch_box.device = device
        return device
