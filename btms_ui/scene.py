from __future__ import annotations

from typing import ClassVar, Dict, Optional, Union

from qtpy import QtCore, QtGui, QtWidgets


def create_scene_rectangle(
    cx: float,
    cy: float,
    width: float,
    height: float,
    pen: Optional[Union[QtGui.QColor, QtGui.QPen]] = None,
    brush: Optional[Union[QtGui.QColor, QtGui.QBrush]] = None,
) -> QtWidgets.QGraphicsRectItem:
    """
    Create a QGraphicsRectItem for a a QGraphicsScene.

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
        for idx in range(1, 5):
            assembly = MotorizedMirrorAssembly()
            assembly.setPos(
                0.0,
                -self.base_height / 2.0
                + MotorizedMirrorAssembly.base_height * 1.5 * idx,
            )
            self.assemblies[idx] = assembly
            self.addToGroup(assembly)

        self.assemblies[2].lens.setVisible(False)

        self.angle = 0
        self.angle_step = 1
        self.timer = QtCore.QTimer()
        self.timer.setInterval(100)
        self.timer.timeout.connect(self._rotate)
        self.timer.start()

    def _rotate(self):
        self.angle += self.angle_step
        direction_swap = False
        for idx, assembly in self.assemblies.items():
            assembly.lens.lens_angle = idx * self.angle
            if abs(assembly.lens.linear_position) >= self.base_width / 3.0:
                if not direction_swap:
                    self.angle_step *= -1
                direction_swap = True
            assembly.lens.linear_position += (-1) ** idx * self.angle_step


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
    """

    base_width: ClassVar[float] = 300.0
    base_height: ClassVar[float] = 40.0
    base_pen: ClassVar[QtGui.QColor] = QtGui.QColor("black")
    base_brush: ClassVar[QtGui.QColor] = QtGui.QColor(239, 239, 239)

    base: QtWidgets.QGraphicsRectItem
    lens: LensAssembly

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

        self.lens = LensAssembly()
        self.addToGroup(self.lens)


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
    def lens_angle(self) -> float:
        return self.lens.rotation()

    @lens_angle.setter
    def lens_angle(self, angle: float) -> None:
        self.lens.setRotation(angle)

    @property
    def linear_position(self) -> float:
        return self.pos().x()

    @linear_position.setter
    def linear_position(self, pos: float) -> None:
        self.setPos(QtCore.QPointF(pos, 0.0))


def test():
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])
    scene = QtWidgets.QGraphicsScene()
    view = QtWidgets.QGraphicsView(scene)

    view.setMinimumSize(500, 500)
    view.setSceneRect(scene.itemsBoundingRect())

    system = TransportSystem()
    system.setFlag(QtWidgets.QGraphicsItem.ItemClipsChildrenToShape, True)
    scene.setSceneRect(system.boundingRect())
    scene.addItem(system)

    view.show()
    app.exec_()


if __name__ == "__main__":
    test()
