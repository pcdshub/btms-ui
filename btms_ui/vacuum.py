from pcdswidgets.icons.valves import PneumaticValveSymbolIcon
from pcdswidgets.vacuum.base import PCDSSymbolBase
from pcdswidgets.vacuum.mixins import (ButtonControl, InterlockMixin,
                                       OpenCloseStateMixin)
from qtpy import QtCore


class GateValve(InterlockMixin, OpenCloseStateMixin, ButtonControl, PCDSSymbolBase):
    """
    A Symbol Widget representing a Pneumatic Valve with the proper icon and
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

    **Internal Components**

    +-----------+--------------+---------------------------------------+
    |Widget Name|Type          |What is it?                            |
    +===========+==============+=======================================+
    |interlock  |QFrame        |The QFrame wrapping this whole widget. |
    +-----------+--------------+---------------------------------------+
    |controls   |QFrame        |The QFrame wrapping the controls panel.|
    +-----------+--------------+---------------------------------------+
    |icon       |BaseSymbolIcon|The widget containing the icon drawing.|
    +-----------+--------------+---------------------------------------+

    **Additional Properties**

    +-----------+-------------------------------------------------------+
    |Property   |Values                                                 |
    +===========+=======================================================+
    |interlocked|`true` or `false`                                      |
    +-----------+-------------------------------------------------------+
    |error      |`Vented`, `At Vacuum`, `Differential Pressure` or      |
    |           |`Lost Vacuum`                                          |
    +-----------+-------------------------------------------------------+
    |state      |`Open`, `Closed`, `Moving`, `Invalid`                  |
    +-----------+-------------------------------------------------------+

    Examples
    --------

    .. code-block:: css

        PneumaticValve[interlocked="true"] #interlock {
            border: 5px solid red;
        }
        PneumaticValve[interlocked="false"] #interlock {
            border: 0px;
        }
        PneumaticValve[interlocked="true"] #icon {
            qproperty-interlockBrush: #FF0000;
        }
        PneumaticValve[interlocked="false"] #icon {
            qproperty-interlockBrush: #00FF00;
        }
        PneumaticValve[error="Lost Vacuum"] #icon {
            qproperty-penStyle: "Qt::DotLine";
            qproperty-penWidth: 2;
            qproperty-brush: red;
        }
        PneumaticValve[state="Open"] #icon {
            qproperty-penColor: green;
            qproperty-penWidth: 2;
        }

    """
    _interlock_suffix = ":LSS_RBV"
    _open_suffix = ":OPN_RBV"
    _close_suffix = ":CLS_RBV"
    _command_suffix = ":REQ"

    NAME = "Gate Valve"
    EXPERT_OPHYD_CLASS = "pcdsdevices.valve.VGC"

    def __init__(self, parent=None, **kwargs):
        super().__init__(
            parent=parent,
            interlock_suffix=self._interlock_suffix,
            open_suffix=self._open_suffix,
            close_suffix=self._close_suffix,
            command_suffix=self._command_suffix,
            **kwargs)
        self.icon = PneumaticValveSymbolIcon(parent=self)

    def sizeHint(self):
        return QtCore.QSize(180, 70)


EntryGateValve = GateValve
ExitGateValve = GateValve
