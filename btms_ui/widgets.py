from __future__ import annotations

import threading
from functools import partial
from typing import ClassVar, Dict, List, Optional, Tuple

from ophyd.status import MoveStatus
from pcdsdevices.lasers import btms_config
from pcdsdevices.lasers.btms_config import DestinationPosition, SourcePosition
from pcdsdevices.lasers.btps import BtpsSourceStatus, BtpsState
from pydm import widgets as pydm_widgets
from pydm.data_plugins import establish_connection
from qtpy import QtCore, QtWidgets
from typhos.positioner import TyphosPositionerWidget

from btms_ui.util import channel_from_signal

from .core import DesignerDisplay
from .scene import BtmsStatusView


class BtmsLaserDestinationLabel(pydm_widgets.PyDMLabel):
    new_destination: QtCore.Signal = QtCore.Signal(object)

    def setText(self, text: str):
        try:
            ld = int(text)
        except ValueError:
            return super().setText(f"(Unknown: {text})")

        if ld == 0:
            text = "Unknown"
            self.new_destination.emit(None)
        elif ld < 0:
            text = "(Misconfiguration)"
            self.new_destination.emit(None)
        else:
            pos = DestinationPosition.from_index(ld)
            text = f"→ {pos.description} (LD{ld})"
            self.new_destination.emit(pos)

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


class QCombinedMoveStatus(QtCore.QObject):
    move_statuses: List[MoveStatus]
    percents: Tuple[float, ...]
    percents_changed = QtCore.Signal(float, list)  # List[float]
    finished_moving = QtCore.Signal()

    def __init__(self, move_statuses: List[MoveStatus]):
        super().__init__()
        if not move_statuses:
            raise ValueError("At least one MoveStatus required")

        self.move_statuses = list(st for st in move_statuses)
        self.percents = [0.0] * len(move_statuses)
        self.lock = threading.Lock()
        self._finished_count = 0
        for idx, move_status in enumerate(self.move_statuses):
            move_status.watch(partial(self._watch_callback, idx))
            move_status.callbacks.append(partial(self._finished_callback, idx))

    def _watch_callback(self, index: int, /, fraction: Optional[float] = None, **kwargs):
        if fraction is not None:
            percent = 1.0 - fraction
            with self.lock:
                percents = list(self.percents)
                percents[index] = percent
                self.percents = tuple(percents)

            overall = sum(percents) / len(percents)
            self.percents_changed.emit(overall, percents)
            if overall >= (1.0 - 1e-6):
                self.finished_moving.emit()

    def _finished_callback(self, index: int, /, fraction: Optional[float] = None, **kwargs):
        with self.lock:
            self._finished_count += 1

        if self._finished_count == len(self.move_statuses):
            self.percents_changed.emit(1.0, [1.0] * len(self.move_statuses))
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


class BtmsSourceValidWidget(QtWidgets.QFrame):
    indicators: Dict[DestinationPosition, List[pydm_widgets.PyDMByteIndicator]]

    def __init__(
        self,
        parent: Optional[QtWidgets.QWidget] = None,
        **kwargs
    ):
        self._device = None
        self._destination = None
        self.indicators = {}
        super().__init__(parent, **kwargs)
        self.setLayout(QtWidgets.QHBoxLayout())
        self.setSizePolicy(QtWidgets.QSizePolicy.Maximum, QtWidgets.QSizePolicy.Maximum)

    @property
    def device(self) -> Optional[BtpsSourceStatus]:
        """The device for the BTMS."""
        return self._device

    @device.setter
    def device(self, device: BtpsSourceStatus):
        self._device = device
        self.set_destination(self._destination)

    @property
    def destination(self) -> Optional[DestinationPosition]:
        """The destination for the BTMS."""
        return self._destination

    @destination.setter
    def destination(self, destination: DestinationPosition):
        self.set_destination(self._destination)

    @QtCore.Slot(object)
    def set_destination(self, destination: Optional[DestinationPosition]):
        device = self._device

        self._destination = destination

        if device is None or destination is None:
            self.setVisible(False)
            return

        state = device.parent
        source_pos = device.source_pos

        def get_indicators(dest: DestinationPosition) -> List[pydm_widgets.PyDMByteIndicator]:
            conf = state.destinations[dest].sources[source_pos]

            data_valid = pydm_widgets.PyDMByteIndicator(
                init_channel=channel_from_signal(conf.data_valid)
            )
            data_valid.setObjectName("data_valid_indicator")
            data_label = QtWidgets.QLabel("Data")
            for indicator in getattr(data_valid, "_indicators", []):
                indicator.setToolTip(f"Green if data is valid ({dest})")
            checks_ok = pydm_widgets.PyDMByteIndicator(
                init_channel=channel_from_signal(conf.checks_ok)
            )
            checks_label = QtWidgets.QLabel("Checks")
            for indicator in getattr(checks_ok, "_indicators", []):
                checks_ok.setToolTip(f"Green if all checks are OK ({dest})")
            data_valid.setObjectName("checks_ok_indicator")
            self.layout().addWidget(data_valid)
            self.layout().addWidget(data_label)
            self.layout().addWidget(checks_ok)
            self.layout().addWidget(checks_label)
            return [data_valid, data_label, checks_ok, checks_label]

        if not self.indicators:
            self.indicators = {
                dest: get_indicators(dest)
                for dest in btms_config.valid_destinations
            }

        for indicator_dest, indicators in self.indicators.items():
            for indicator in indicators:
                indicator.setVisible(indicator_dest == destination)

        self.setVisible(True)


class BtmsSourceOverviewWidget(DesignerDisplay, QtWidgets.QFrame):
    filename: ClassVar[str] = "btms-source.ui"

    valid_widget: BtmsSourceValidWidget
    source_name_label: QtWidgets.QLabel
    current_dest_label: BtmsLaserDestinationLabel
    target_dest_widget: BtmsLaserDestinationChoice
    motion_progress_widget: QtWidgets.QProgressBar
    linear_widget: TyphosPositionerWidget
    rotary_widget: TyphosPositionerWidget
    goniometer_widget: TyphosPositionerWidget
    source: Optional[BtpsSourceStatus]

    new_destination: QtCore.Signal = QtCore.Signal(object)

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

        self.pydm_widgets_to_suffix = {
            self.current_dest_label: "BTPS:CurrentLD_RBV",
        }

        self.target_dest_widget.move_requested.connect(self.move_request)
        self.motion_progress_widget.setVisible(False)

        self.current_dest_label.new_destination.connect(self.new_destination.emit)
        self.current_dest_label.new_destination.connect(self.valid_widget.set_destination)

    def move_request(self, target: DestinationPosition):
        """
        Request move of this source to the ``target`` DestinationPosition.
        """
        device = self.device

        if device is None:
            return

        def finished_moving():
            self.motion_progress_widget.setVisible(False)

        def update(overall_percent: float, individual_percents: List[float]):
            self.motion_progress_widget.setValue(int(overall_percent * 100.0))

        self.motion_progress_widget.setValue(0)

        self._move_status = QCombinedMoveStatus(device.set_with_movestatus(target))
        self._move_status.percents_changed.connect(update)
        self._move_status.finished_moving.connect(finished_moving)
        self.motion_progress_widget.setVisible(
            not any(st.done for st in self._move_status.move_statuses)
        )

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
        self.valid_widget.device = device
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
