import textwrap

from pcdswidgets.icons.valves import BaseSymbolIcon
from pcdswidgets.vacuum.base import PCDSSymbolBase
from pcdswidgets.vacuum.mixins import InterlockMixin, OpenCloseStateMixin
from pcdswidgets.vacuum.valves import PneumaticValve
from qtpy import QtCore, QtGui


class LaserShutterIcon(BaseSymbolIcon):
    """A symbol for the laser shutter."""
    def __init__(self, parent=None, **kwargs):
        super().__init__(parent, **kwargs)
        self._interlock_brush = QtGui.QBrush(
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

    def draw_icon(self, painter):
        painter.drawRect(QtCore.QRectF(0.0, 0, 0.2, 1.0))


class LaserShutter(InterlockMixin, OpenCloseStateMixin, PCDSSymbolBase):
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
    EXPERT_OPHYD_CLASS = "pcdsdevices.valve.VGC"

    def __init__(self, parent=None, **kwargs):
        super().__init__(
            parent=parent,
            interlock_suffix=self._interlock_suffix,
            open_suffix=self._open_suffix,
            close_suffix=self._close_suffix,
            command_suffix=self._command_suffix,
            **kwargs)
        self.icon = LaserShutterIcon(parent=self)
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
                """
            )
        )

    def minimumSizeHint(self):
        return QtCore.QSize(self.iconSize / 4, self.iconSize)

    def sizeHint(self):
        return self.minimumSizeHint()


class GateValve(PneumaticValve):
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

    def __init__(self, parent=None, **kwargs):
        super().__init__(parent=parent, **kwargs)
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
            """
            )
        )

        self.setAutoFillBackground(False)
        self.setAttribute(QtCore.Qt.WA_NoSystemBackground)

    def minimumSizeHint(self):
        return QtCore.QSize(self.iconSize, self.iconSize)

    def sizeHint(self):
        return self.minimumSizeHint()


EntryGateValve = GateValve
ExitGateValve = GateValve
