from __future__ import annotations

from typing import ClassVar, Optional, cast

from pcdsdevices.lasers import btms_config
from pcdsdevices.lasers.btms_config import DestinationPosition, SourcePosition
from pcdsdevices.lasers.btps import BtpsSourceStatus, BtpsState
from pydm import widgets as pydm_widgets
from pydm.data_plugins import establish_connection
from qtpy import QtCore, QtWidgets

from .core import DesignerDisplay
from .scene import BtmsStatusView


class BtmsLaserDestinationLabel(pydm_widgets.PyDMLabel):
    def setText(self, text: str):
        try:
            ld = int(text)
        except ValueError:
            return super().setText(text)

        if ld == 0:
            text = "Unknown"
        elif ld < 0:
            text = "(Misconfiguration)"
        else:
            pos = DestinationPosition.from_index(ld)
            text = f"Destination: {pos.description} (LD{ld})"

        return super().setText(text)


class BtmsDestinationComboBox(QtWidgets.QComboBox):
    def __init__(self, parent: Optional[QtWidgets.QWidget] = None, **kwargs):
        super().__init__(parent, **kwargs)

        for dest in sorted(DestinationPosition, key=lambda dest: dest.index):
            if dest in btms_config.valid_destinations:
                self.addItem(f"{dest.description} ({dest.value})", dest)


class BtmsLaserDestinationChoice(QtWidgets.QFrame):
    target_dest_combo: BtmsDestinationComboBox
    _device: Optional[BtpsSourceStatus]

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None, **kwargs):
        super().__init__(parent, **kwargs)
        self._device = None

        self.pydm_widgets_to_suffix = {
            # self.current_dest_label: "BTPS:CurrentLD_RBV",
        }

        self._setup_ui()

    def _setup_ui(self):
        layout = QtWidgets.QHBoxLayout()
        self.target_dest_combo = BtmsDestinationComboBox()
        self.go_button = QtWidgets.QPushButton("Go")
        self.go_button.clicked.connect(self._move_request)
        for widget in (
            self.target_dest_combo,
            self.go_button,
        ):
            layout.addWidget(widget)

        self.setLayout(layout)

    def _move_request(self):
        target = cast(DestinationPosition, self.target_dest_combo.currentData())
        device = self.device
        if device is None:
            return

        self._move_status = device.set_destination(target)

    @property
    def device(self) -> Optional[BtpsSourceStatus]:
        """The device for the BTMS."""
        return self._device

    @device.setter
    def device(self, device: BtpsSourceStatus):
        self._device = device


class BtmsSourceOverviewWidget(QtWidgets.QFrame):
    source_name_label: QtWidgets.QLabel
    current_dest_label: BtmsLaserDestinationLabel
    target_dest_widget: BtmsLaserDestinationChoice
    source: Optional[BtpsSourceStatus]

    def __init__(
        self,
        parent: Optional[QtWidgets.QWidget],
        prefix: str = "",
        source_index: int = 1,
        **kwargs
    ):
        super().__init__(parent, **kwargs)
        self._prefix = prefix
        self._source_index = source_index

        self._setup_ui()
        self.pydm_widgets_to_suffix = {
            self.current_dest_label: "BTPS:CurrentLD_RBV",
        }

    def _setup_ui(self):
        layout = QtWidgets.QHBoxLayout()
        self.source_name_label = QtWidgets.QLabel()
        self.source_name_label.setObjectName("source_name_label")
        self.current_dest_label = BtmsLaserDestinationLabel()
        self.current_dest_label.setObjectName("current_dest_label")
        self.target_dest_widget = BtmsLaserDestinationChoice()
        for widget in (
            self.source_name_label,
            self.current_dest_label,
            self.target_dest_widget,
        ):
            layout.addWidget(widget)

        self.setLayout(layout)

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

    @property
    def source_position(self) -> SourcePosition:
        """The source index, LS(index)."""
        return SourcePosition.from_index(self._source_index)

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

        self.source_name_label.setText(
            f"LS{source_index} ({self.source_position.description})"
        )

    @property
    def device(self) -> Optional[BtpsSourceStatus]:
        """The device for the BTMS."""
        return self._device

    @device.setter
    def device(self, device: BtpsSourceStatus):
        self._device = device
        self.target_dest_widget.device = device


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

    @property
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

        device = self.device
        if device is None:
            return

        for source in self.source_widgets:
            source.device = device.sources[source.source_position]
