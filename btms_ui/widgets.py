from __future__ import annotations

from typing import ClassVar, Optional

from ophyd.status import MoveStatus
from pcdsdevices.lasers import btms_config
from pcdsdevices.lasers.btms_config import DestinationPosition, SourcePosition
from pcdsdevices.lasers.btps import BtpsSourceStatus, BtpsState
from pydm import widgets as pydm_widgets
from pydm.data_plugins import establish_connection
from qtpy import QtCore, QtWidgets
from typhos.positioner import TyphosPositionerWidget

from .core import DesignerDisplay
from .scene import BtmsStatusView


class BtmsLaserDestinationLabel(pydm_widgets.PyDMLabel):
    def setText(self, text: str):
        try:
            ld = int(text)
        except ValueError:
            return super().setText(f"(Unknown: {text})")

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


class QMoveStatus(QtCore.QObject):
    percent_changed = QtCore.Signal(float)
    finished_moving = QtCore.Signal()

    def __init__(self, move_status: MoveStatus):
        super().__init__()
        self.move_status = move_status
        move_status.watch(self._watch_callback)
        move_status.callbacks.append(self._finished_callback)

    def _watch_callback(self, fraction: Optional[float] = None, **kwargs):
        if fraction is not None:
            percent = 1.0 - fraction
            self.percent_changed.emit(percent)
            if percent >= (1.0 - 1e-6):
                # TODO: this might not be necessary
                self.finished_moving.emit()

    def _finished_callback(self, fraction: Optional[float] = None, **kwargs):
        self.percent_changed.emit(1.0)
        self.finished_moving.emit()


class BtmsLaserDestinationChoice(QtWidgets.QFrame):
    target_dest_combo: BtmsDestinationComboBox
    _device: Optional[BtpsSourceStatus]
    move_requested = QtCore.Signal(object)

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
        self.move_requested.emit(self.target_dest_combo.currentData())

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
    motion_progress_widget: QtWidgets.QProgressBar
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
        layout = QtWidgets.QGridLayout()
        self.source_name_label = QtWidgets.QLabel()
        self.source_name_label.setObjectName("source_name_label")
        self.current_dest_label = BtmsLaserDestinationLabel()
        self.current_dest_label.setObjectName("current_dest_label")
        self.target_dest_widget = BtmsLaserDestinationChoice()
        self.target_dest_widget.move_requested.connect(self.move_request)
        self.motion_progress_widget = QtWidgets.QProgressBar()
        self.motion_progress_widget.setMaximumWidth(150)
        self.motion_progress_widget.setVisible(False)
        for col, widget in enumerate(
            (
                self.source_name_label,
                self.current_dest_label,
                self.target_dest_widget,
                self.motion_progress_widget,
            )
        ):
            layout.addWidget(widget, 0, col)

        self.linear_widget = TyphosPositionerWidget()
        self.rotary_widget = TyphosPositionerWidget()
        self.goniometer_widget = TyphosPositionerWidget()

        for col, widget in enumerate(
            (
                self.linear_widget,
                self.rotary_widget,
                self.goniometer_widget,
             )
        ):
            layout.addWidget(widget, 1, col)

        TyphosPositionerWidget()
        self.setLayout(layout)

    def move_request(self, target: DestinationPosition):
        device = self.device

        if device is None:
            return

        def finished_moving():
            self.motion_progress_widget.setVisible(False)

        def update(percent: float):
            self.motion_progress_widget.setValue(percent * 100.0)

        self.motion_progress_widget.setValue(0.0)

        self._move_status = QMoveStatus(device.set_destination(target))
        self._move_status.percent_changed.connect(update)
        self._move_status.finished_moving.connect(finished_moving)
        self.motion_progress_widget.setVisible(not self._move_status.move_status.done)

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
        self.rotary_widget.add_device(device.rotary)
        self.linear_widget.add_device(device.linear)
        self.goniometer_widget.add_device(device.goniometer)


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
