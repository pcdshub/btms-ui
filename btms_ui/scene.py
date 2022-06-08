from __future__ import annotations

import logging
from typing import ClassVar, Dict, Optional, Union

import ophyd
import pydm
from pcdsdevices.lasers.btps import BtpsState as BtpsStateDevice
from pcdsdevices.lasers.btps import SourceConfig
from qtpy import QtCore, QtGui, QtWidgets

logger = logging.getLogger(__name__)


def channel_from_signal(signal: ophyd.signal.EpicsSignalBase) -> str:
    """PyDM-compatible PV name URIs from a given EpicsSignal."""
    return f"ca://{signal.pvname}"


SOURCES = (1, 2, 3, 4)
DESTINATIONS = (1, 2, 3, 4, 5, 6, 7)
INSTALLED_SOURCES = (1, 3, 4)


def create_scene_rectangle(
    cx: float,
    cy: float,
    width: float,
    height: float,
    pen: Optional[Union[QtGui.QColor, QtGui.QPen]] = None,
    brush: Optional[Union[QtGui.QColor, QtGui.QBrush]] = None,
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

    Returns
    -------
    QtWidgets.QGraphicsRectItem
        The created rectangle.
    """
    item = QtWidgets.QGraphicsRectItem(
        QtCore.QRectF(cx - width / 2.0, cy - height / 2.0, width, height)
    )
    item.setTransformOriginPoint(item.rect().center())
    if pen is not None:
        item.setPen(pen)
    if brush is not None:
        item.setBrush(brush)
    return item


def create_scene_cross(
    cx: float,
    cy: float,
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
    QtWidgets.QGraphicsRectItem
        The created rectangle.
    """
    item = QtWidgets.QGraphicsPolygonItem(
        QtGui.QPolygonF(
            [
                QtCore.QPointF(0.0, 0.0),
                QtCore.QPointF(-width / 2.0, 0.0),
                QtCore.QPointF(width / 2.0, 0.0),
                QtCore.QPointF(0.0, 0.0),
                QtCore.QPointF(0.0, -height / 2.0),
                QtCore.QPointF(0.0, height / 2.0),
            ]
        )

    )
    item.setTransformOriginPoint(QtCore.QPointF(0.0, 0.0))
    if pen is not None:
        item.setPen(pen)
    if brush is not None:
        item.setBrush(brush)
    return item


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
        self.helper = PositionHelper(channel_x, channel_y)
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

    def _update_position(self, x: Optional[float], y: Optional[float]):
        self.setPos(
            self.x() if x is None else x,
            self.y() if y is None else y,
        )


class SourceDestinationIndicator(PyDMPositionedGroup):
    def __init__(
        self,
        channel_x: Optional[str] = None,
        channel_y: Optional[str] = None,
    ):
        super().__init__(channel_x=channel_x, channel_y=channel_y)
        self.addToGroup(create_scene_cross(cx=0, cy=0, width=10, height=10))


class TransportSystem(QtWidgets.QGraphicsItemGroup):
    """
    A graphical representation of the full laser transport system.
    """

    base_width: ClassVar[float] = 400.0
    base_height: ClassVar[float] = 400.0
    base_pen: ClassVar[QtGui.QColor] = QtGui.QColor("black")
    base_brush: ClassVar[QtGui.QColor] = QtGui.QColor(217, 217, 217)

    base: QtWidgets.QGraphicsRectItem
    assemblies: Dict[int, MotorizedMirrorAssembly]
    sources: Dict[int, LaserSource]
    destinations: Dict[int, Destination]

    def __init__(self):
        super().__init__()

        self.base = create_scene_rectangle(
            cx=0,
            cy=0,
            width=self.base_width,
            height=self.base_height,
            pen=self.base_pen,
            brush=self.base_brush,
        )

        self.addToGroup(self.base)
        self.assemblies = {}
        for idx in SOURCES:
            assembly = MotorizedMirrorAssembly(source_index=idx)
            assembly.setPos(
                0.0,
                -self.base_height / 2.0
                + MotorizedMirrorAssembly.base_height * 1.5 * idx,
            )
            self.assemblies[idx] = assembly
            self.addToGroup(assembly)

        for assembly in set(SOURCES) - set(INSTALLED_SOURCES):
            self.assemblies[assembly].lens.setVisible(False)
            for indicator in self.assemblies[assembly].dest_indicators.values():
                indicator.setVisible(False)

        # Just some testing code until we have PyDM channels hooked up:
        self.angle = 0
        self.angle_step = 1
        self.timer = QtCore.QTimer()
        self.timer.setInterval(100)
        self.timer.timeout.connect(self._rotating_test)
        self.timer.start()

    @property
    def device(self) -> Optional[BtpsStateDevice]:
        return self._device

    @device.setter
    def device(self, device: Optional[BtpsStateDevice]) -> None:
        self._device = device
        if device is None:
            return

        for source_idx, assembly in self.assemblies.items():
            for dest_idx, indicator in assembly.dest_indicators.items():
                try:
                    source: SourceConfig = getattr(device, f"dest{dest_idx}.source{source_idx}")
                except AttributeError:
                    if source_idx not in INSTALLED_SOURCES:
                        continue
                    raise
                channel = channel_from_signal(source.linear.nominal)
                indicator.helper.channel_x = channel

    def _rotating_test(self):
        """Testing the rotation mechanism."""
        self.angle += self.angle_step
        direction_swap = False
        for idx, assembly in self.assemblies.items():
            assembly.lens.angle = idx * self.angle
            if abs(assembly.linear_position) >= self.base_width / 3.0:
                if not direction_swap:
                    self.angle_step *= -1
                direction_swap = True
            assembly.linear_position += (-1) ** idx * self.angle_step


class LaserSource(QtWidgets.QGraphicsItemGroup):
    """
    A graphical representation of a laser source.
    """


class Destination(QtWidgets.QGraphicsItemGroup):
    """
    A graphical representation of a destination hutch.
    """


class MotorizedMirrorAssembly(QtWidgets.QGraphicsItemGroup):
    """
    A graphical representation of a single motorized mirror assembly.

    It contains a LensAssembly which has
    """

    base_width: ClassVar[float] = 300.0
    base_height: ClassVar[float] = 40.0
    base_pen: ClassVar[QtGui.QColor] = QtGui.QColor("black")
    base_brush: ClassVar[QtGui.QColor] = QtGui.QColor(239, 239, 239)

    base: QtWidgets.QGraphicsRectItem
    lens: LensAssembly
    source_index: int
    source_device: SourceConfig

    def __init__(self, source_index: int):
        super().__init__()

        self.base = create_scene_rectangle(
            cx=0,
            cy=0,
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
            idx: SourceDestinationIndicator()
            for idx in DESTINATIONS
        }

        for indicator in self.dest_indicators.values():
            self.addToGroup(indicator)
            indicator.setZValue(1)

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

    lens_width: ClassVar[float] = 1.0
    lens_height: ClassVar[float] = 50.0
    lens_pen: ClassVar[QtGui.QColor] = QtGui.QColor("red")
    lens_brush: ClassVar[QtGui.QColor] = QtGui.QColor("red")

    base: QtWidgets.QGraphicsRectItem
    lens: QtWidgets.QGraphicsRectItem

    def __init__(self):
        super().__init__()

        self.base = create_scene_rectangle(
            cx=0,
            cy=0,
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
    system: TransportSystem

    def __init__(
        self,
        parent: Optional[QtWidgets.QWidget] = None,
        scene: Optional[QtWidgets.QGraphicsScene] = None,
    ):
        if scene is None:
            scene = QtWidgets.QGraphicsScene()
        super().__init__(scene, parent=parent)

        self.setMinimumSize(500, 500)
        self.setSceneRect(scene.itemsBoundingRect())

        self.system = TransportSystem()
        self.system.setFlag(QtWidgets.QGraphicsItem.ItemClipsChildrenToShape, True)
        scene.setSceneRect(self.system.boundingRect())
        scene.addItem(self.system)
        self._device_prefix = ""
        self.device = None

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
        # self.system.
        self.system.device = device
        return device
