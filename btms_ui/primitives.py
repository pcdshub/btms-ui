from __future__ import annotations

from enum import Enum
from typing import Optional, Union

from qtpy import QtCore, QtGui, QtWidgets


class ArrowDirection(str, Enum):
    up = "up"
    down = "down"
    left = "left"
    right = "right"


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


def create_scene_arrow(
    width: float,
    height: float,
    direction: ArrowDirection,
    pen: Optional[Union[QtGui.QColor, QtGui.QPen]] = None,
    brush: Optional[Union[QtGui.QColor, QtGui.QBrush]] = None,
    head_percent: float = 0.75,
) -> QtWidgets.QGraphicsPolygonItem:
    """
    Create a QGraphicsPolygonItem in the shape of an arrow for a QGraphicsScene.

    The transform origin of the shape will be set to its center.

    Parameters
    ----------
    width : float
        The width.
    height : float
        The height.
    direction : ArrowDirection
        Direction of the arrow.
    pen : QColor or QPen, optional
        The pen to draw the rectangle with.
    brush : QColor or QBrush, optional
        The brush to draw the rectangle with.
    head_percent : float, optional
        Normalized factor to be applied to the height to determine where the
        head of the arrow should be drawn.

    Returns
    -------
    QtWidgets.QGraphicsPolygonItem
        The created polygon (arrow).
    """
    half_width = width / 2.0
    half_height = height / 2.0
    head_base = head_percent * half_height
    polygon = create_scene_polygon(
        QtGui.QPolygonF(
            [
                QtCore.QPointF(0.0, -half_height),
                QtCore.QPointF(0.0, head_base),
                QtCore.QPointF(-half_width, head_base),
                QtCore.QPointF(0.0, half_height),
                QtCore.QPointF(half_width, head_base),
                QtCore.QPointF(0.0, head_base),
            ]
        ),
        brush=brush,
        pen=pen,
    )
    if direction == ArrowDirection.up:
        polygon.setRotation(180)
    # elif direction == ArrowDirection.left:
    #     polygon.setRotation(90)
    # elif direction == ArrowDirection.right:
    #     polygon.setRotation(270)
    return polygon
