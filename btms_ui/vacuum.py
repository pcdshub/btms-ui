from __future__ import annotations

import logging
import textwrap
from typing import Optional

import ophyd
from pcdsdevices.lasers.btps import VGC, LssShutterStatus
from pcdswidgets.icons.valves import BaseSymbolIcon
from pcdswidgets.vacuum.base import PCDSSymbolBase
from pcdswidgets.vacuum.mixins import InterlockMixin, OpenCloseStateMixin
from pcdswidgets.vacuum.valves import PneumaticValve
from qtpy import QtCore, QtGui, QtWidgets

logger = logging.getLogger(__name__)


class LaserShutterIcon(BaseSymbolIcon):
    """A symbol for the laser shutter."""

    def __init__(self, parent=None, **kwargs):
        super().__init__(parent, **kwargs)
        self._interlock_brush = QtGui.QBrush(
            QtGui.QColor(0, 255, 0), QtCore.Qt.SolidPattern
        )
        self._shutter_brush = QtGui.QBrush(
            QtGui.QColor(0, 255, 0), QtCore.Qt.SolidPattern
        )

    @QtCore.Property(QtGui.QBrush)
    def interlockBrush(self) -> QtGui.QBrush:
        return self._interlock_brush

    @interlockBrush.setter
    def interlockBrush(self, new_brush: QtGui.QBrush):
        if new_brush != self._interlock_brush:
            self._interlock_brush = new_brush
            self.update()

    @QtCore.Property(QtGui.QBrush)
    def shutterBrush(self) -> QtGui.QBrush:
        return self._shutter_brush

    @shutterBrush.setter
    def shutterBrush(self, new_brush: QtGui.QBrush):
        if new_brush != self._shutter_brush:
            self._shutter_brush = new_brush
            self.update()

    def draw_icon(self, painter: QtGui.QPainter):
        # The rectangle at the top indicates the shutter status:
        painter.setBrush(self._shutter_brush)
        painter.drawRect(QtCore.QRectF(0.0, 0, 0.2, 0.8))
        painter.setBrush(self._interlock_brush)
        # The little triangle at the bottom indicates interlock status:
        painter.drawPolygon(
            QtGui.QPolygonF(
                (
                    QtCore.QPointF(0.0, 1.0),
                    QtCore.QPointF(0.2, 1.0),
                    QtCore.QPointF(0.1, 0.8),
                )
            )
        )


class TyphosDeviceMixin:
    """
    Mixin for symbols: re-uses provided ophyd Device instance for typhos.

    Handles mousePressEvent specifically for forwarded events from a
    QGraphicsView.
    """
    device: Optional[ophyd.Device]

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.type() == QtCore.QEvent.MouseButtonPress:
            if event.button() == QtCore.Qt.LeftButton:
                self._handle_icon_click()

    def _cleanup_expert_display(self):
        return super()._cleanup_expert_display()

    def _handle_icon_click(self):
        """When the icon is clicked, open up typhos."""
        if self.device is None:
            return

        if self._expert_display is not None:
            self._expert_display.show()
            self._expert_display.raise_()
            return

        try:
            import typhos
        except ImportError:
            logger.error('Typhos not installed. Cannot create display.')
            return

        display = typhos.TyphosDeviceDisplay.from_device(self.device)
        self._expert_display = display
        display.destroyed.connect(self._cleanup_expert_display)

        if display:
            display.show()


class LaserShutter(TyphosDeviceMixin, InterlockMixin, OpenCloseStateMixin, PCDSSymbolBase):
    """
    A Symbol Widget representing with the proper icon and
    controls.

    Parameters
    ----------
    parent : QWidget
        The parent widget for the symbol

    Notes
    -----
    This widget allow for high customization through the Qt Stylesheets
    mechanism.
    As this widget is composed by internal widgets, their names can be used as
    selectors when writing your stylesheet to be used with this widget.
    Properties are also available to offer wider customization possibilities.
    """

    _interlock_suffix = ":LSS_RBV"
    _open_suffix = ":OPN_RBV"
    _close_suffix = ":CLS_RBV"
    _command_suffix = ":REQ_RBV"

    NAME = "Laser Shutter"
    EXPERT_OPHYD_CLASS = "pcdsdevices.lasers.btps.LssShutterStatus"
    device: Optional[LssShutterStatus]

    def __init__(
        self,
        device: Optional[LssShutterStatus] = None,
        parent: Optional[QtWidgets.QWidget] = None,
        **kwargs
    ):
        self.device = device
        super().__init__(
            parent=parent,
            interlock_suffix=self._interlock_suffix,
            open_suffix=self._open_suffix,
            close_suffix=self._close_suffix,
            command_suffix=self._command_suffix,
            **kwargs
        )
        self.icon = LaserShutterIcon(parent=self)
        self.icon.clicked.connect(self._handle_icon_click)
        self.setAutoFillBackground(False)
        self.setAttribute(QtCore.Qt.WA_NoSystemBackground)

        self.setStyleSheet(
            textwrap.dedent(
                """\
                LaserShutter[interlocked="true"] #interlock {
                    border: 1px solid red;
                }
                LaserShutter[interlocked="false"] #interlock {
                    border: 0px;
                }
                LaserShutter[interlocked="true"] #icon {
                    qproperty-interlockBrush: #FF0000;
                }
                LaserShutter[interlocked="false"] #icon {
                    qproperty-interlockBrush: #00FF00;
                }
                LaserShutter[state="Close"] #icon {
                    qproperty-penColor: black;
                    qproperty-brush: black;
                }
                LaserShutter[state="Open"] #icon {
                    qproperty-penColor: black;
                    qproperty-brush: #00FF00;
                }
                LaserShutter[connected="false"] #icon {
                    qproperty-shutterBrush: white;
                    qproperty-interlockBrush: white;
                }
                """
            )
        )

    def minimumSizeHint(self):
        return QtCore.QSize(self.iconSize / 4, self.iconSize)

    def sizeHint(self):
        return self.minimumSizeHint()

    @QtCore.Property(bool)
    def connected(self) -> bool:
        """
        Connection state of all PVs.

        Returns
        -------
        bool
        """
        return all(
            (
                self._interlock_connected,
                self._open_connected,
                self._close_connected,
            )
        )


class GateValve(TyphosDeviceMixin, PneumaticValve):
    """
    A Symbol Widget representing a BTS gate valve.

    Parameters
    ----------
    parent : QWidget
        The parent widget for the symbol

    Notes
    -----
    This widget allow for high customization through the Qt Stylesheets
    mechanism.
    As this widget is composed by internal widgets, their names can be used as
    selectors when writing your stylesheet to be used with this widget.
    Properties are also available to offer wider customization possibilities.
    """

    # _interlock_suffix = ":LSS_RBV"
    # _open_suffix = ":OPN_RBV"
    # _close_suffix = ":CLS_RBV"
    # _command_suffix = ":REQ_RBV"

    NAME = "Gate Valve"
    EXPERT_OPHYD_CLASS = "pcdsdevices.valve.VGC"
    device: Optional[VGC]

    def __init__(
        self,
        device: Optional[VGC] = None,
        parent: Optional[QtWidgets.QWidget] = None,
        **kwargs
    ):
        self.device = device
        super().__init__(parent=parent, **kwargs)
        self.setAutoFillBackground(False)
        self.setAttribute(QtCore.Qt.WA_NoSystemBackground)
        self.setStyleSheet(
            textwrap.dedent(
                """\
                GateValve[interlocked="true"] #interlock {
                    border: 5px solid red;
                }
                GateValve[interlocked="false"] #interlock {
                    border: 0px;
                }
                GateValve[interlocked="true"] #icon {
                    qproperty-interlockBrush: #FF0000;
                }
                GateValve[interlocked="false"] #icon {
                    qproperty-interlockBrush: #00FF00;
                }
                GateValve[error="Close"] #icon {
                    qproperty-penStyle: "Qt::DotLine";
                    qproperty-penWidth: 2;
                    qproperty-brush: red;
                }
                GateValve[state="Open"] #icon {
                    qproperty-penColor: green;
                    qproperty-penWidth: 2;
                }
                GateValve[connected="false"] #icon {
                    qproperty-interlockBrush: white;
                    qproperty-brush: white;
                }
            """
            )
        )

    @QtCore.Property(bool)
    def connected(self) -> bool:
        """
        Connection state of all PVs.

        Returns
        -------
        bool
        """
        return all(
            (self._error_connected, self._interlock_connected, self._state_connected)
        )

    def minimumSizeHint(self):
        return QtCore.QSize(self.iconSize, self.iconSize)

    def sizeHint(self):
        return self.minimumSizeHint()


EntryGateValve = GateValve
ExitGateValve = GateValve
