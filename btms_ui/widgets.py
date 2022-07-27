from typing import ClassVar, Optional

from pcdsdevices.lasers.btps import BtpsSourceStatus, BtpsState
# from pydm import widgets as pydm_widgets
from pydm.data_plugins import establish_connection
from qtpy import QtCore, QtWidgets

from .core import DesignerDisplay
from .scene import BtmsStatusView


class BtmsSourceOverviewWidget(DesignerDisplay, QtWidgets.QWidget):
    filename: ClassVar[str] = "btms-source.ui"
    # source_name_label: pydm_widgets.PyDMLabel
    source_name_label: QtWidgets.QLabel
    source: Optional[BtpsSourceStatus]

    def __init__(self, *args, prefix: str = "", source_index: int = 1, **kwargs):
        self._prefix = prefix
        self._source_index = source_index
        self._widget_to_suffix = {}
        super().__init__(*args, **kwargs)
        self.pydm_widgets_to_suffix = {
            # self.source_name_label: "{}BTPS:Name_RBV",
        }

    @QtCore.Property(str)
    def prefix(self) -> str:
        """The PV prefix for the BTMS."""
        return self._prefix

    @prefix.setter
    def prefix(self, prefix: str):
        self._prefix = prefix

    @property
    def source_prefix(self) -> str:
        return f"{self.prefix}LTLHN:LS{self.source_index}:"

    @QtCore.Property(int)
    def source_index(self) -> int:
        """The source index, LS(index)."""
        return self._source_index

    @source_index.setter
    def source_index(self, source_index: int):
        self._source_index = source_index

        for widget, suffix in self.pydm_widgets_to_suffix.items():
            widget.channel = f"ca://{self.source_prefix}{suffix}"
            for channel in widget.channels() or []:
                establish_connection(channel)

        self.source_name_label.setText(f"LS{source_index}")


class BtmsDiagramWidget(DesignerDisplay, QtWidgets.QWidget):
    filename: ClassVar[str] = "btms-diagram.ui"
    view: BtmsStatusView

    def __init__(self, *args, prefix: str = "", **kwargs):
        self._prefix = prefix
        super().__init__(*args, **kwargs)

    @QtCore.Property(str)
    def prefix(self) -> str:
        """The PV prefix for the BTMS."""
        return self._prefix

    @prefix.setter
    def prefix(self, prefix: str):
        self.view.device_prefix = prefix
        self._prefix = prefix


class BtmsMain(DesignerDisplay, QtWidgets.QWidget):
    """
    Main display, including diagram and source information.
    """
    filename: ClassVar[str] = "btms.ui"
    diagram_widget: BtmsDiagramWidget
    ls1_widget: BtmsSourceOverviewWidget
    ls5_widget: BtmsSourceOverviewWidget
    ls8_widget: BtmsSourceOverviewWidget

    def __init__(self, *args, prefix: str = "", **kwargs):
        self._prefix = prefix
        super().__init__(*args, **kwargs)
        self.source_widgets = [
            self.ls1_widget,
            self.ls5_widget,
            self.ls8_widget,
        ]

    def device(self) -> Optional[BtpsState]:
        """The pcdsdevices BtpsState device; available after prefix is set."""
        return self.diagram_widget.view.device

    @QtCore.Property(str)
    def prefix(self) -> str:
        """The PV prefix for the BTMS."""
        return self._prefix

    @prefix.setter
    def prefix(self, prefix: str):
        self.diagram_widget.prefix = prefix
        self._prefix = prefix

        for source in self.source_widgets:
            source.device = self.device
