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
from typhos.suite import TyphosSuite

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


class BtmsStateDetails(QtWidgets.QFrame):
    def __init__(
        self,
        parent: Optional[QtWidgets.QWidget],
        state: Optional[BtpsState] = None,
        source: Optional[SourcePosition] = None,
        dest: Optional[DestinationPosition] = None,
    ):
        super().__init__(parent)
        self._state = None
        self._source = None
        self._dest = None

        self._setup_ui()

        self.state = state
        self.source = source
        self.dest = dest

    def _setup_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout()
        self.setLayout(layout)
        self.text_edit = QtWidgets.QTextEdit()
        layout.addWidget(self.text_edit)

    @property
    def state(self) -> Optional[BtpsState]:
        """The BtpsState Bevice."""
        return self._state

    @state.setter
    def state(self, value: Optional[BtpsState]):
        self._state = value
        self._update()

    @property
    def dest(self) -> Optional[DestinationPosition]:
        """The destination."""
        return self._dest

    @dest.setter
    def dest(self, value: Optional[DestinationPosition]):
        self._dest = value
        self._update()

    @property
    def source(self) -> Optional[SourcePosition]:
        """The source."""
        return self._source

    @source.setter
    def source(self, value: Optional[SourcePosition]):
        self._source = value
        self._update()

    def _update(self):
        source = self.source
        dest = self.dest
        state = self.state

        if source is None or dest is None or state is None:
            self.setWindowTitle("Motion conflict checks")
            return

        self.setWindowTitle(f"Checks for {source} -> {dest}")

        config = state.destinations[dest].sources[source]
        summary = config.summarize_checks()
        self.text_edit.setText("\n".join(summary))


class BtmsMoveConflictWidget(DesignerDisplay, QtWidgets.QFrame):
    filename: ClassVar[str] = "btms-move-request.ui"

    conflicts_label: QtWidgets.QLabel
    conflicts_list_widget: QtWidgets.QListWidget
    resolution_list_widget: QtWidgets.QListWidget

    def __init__(
        self,
        parent: Optional[QtWidgets.QWidget],
        state: BtpsState,
        source: SourcePosition,
        dest: DestinationPosition,
    ):
        super().__init__(parent)
        self.state = state
        self.source = source
        self.dest = dest

        self.conflicts_label.setText(
            f"Conflicts detected moving {source.description} {source} to "
            f"{dest.description} {dest}:"
        )
        self.conflicts = state.sources[source].check_move_all(dest)
        for conflict in self.conflicts:
            self.conflicts_list_widget.addItem(f"{conflict.__class__.__name__}: {conflict}")
            self.resolution_list_widget.addItem(self.get_resolution_explanation(conflict))

    def get_resolution_explanation(self, conflict: Exception) -> str:
        if isinstance(conflict, btms_config.MovingActiveSource):
            return f"Close shutter for {self.source}"

        if isinstance(conflict, btms_config.DestinationInUseError):
            return "Destination already in use: cannot automatically resolve"

        if isinstance(conflict, btms_config.PathCrossedError):
            return f"Close shutter for active crossed source: {conflict.crosses_source}"

        return (
            f"Unknown issue, cannot automatically resolve: "
            f"{conflict.__class__.__name__} {conflict}"
        )


class BtmsSourceValidWidget(QtWidgets.QFrame):
    indicators: Dict[DestinationPosition, List[pydm_widgets.PyDMByteIndicator]]

    def __init__(
        self,
        parent: Optional[QtWidgets.QWidget] = None,
        **kwargs
    ):
        self._device = None
        self._destination = None
        self._details = {}
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

    def _open_details(
        self, source: SourcePosition, dest: DestinationPosition
    ) -> None:
        device = self.device
        if device is None:
            return

        details = BtmsStateDetails(
            None,
            state=device.parent,
            source=source,
            dest=dest,
        )
        details.show()
        self._details[source] = details

    def _get_indicators(
        self, state: BtpsState, source: SourcePosition, dest: DestinationPosition
    ) -> List[pydm_widgets.PyDMByteIndicator]:
        """
        Get the indicator widgets for a given source/dest combination.
        """
        conf = state.destinations[dest].sources[source]

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

        checks_button = QtWidgets.QToolButton()
        checks_button.setText("?")
        checks_button.setToolTip("Open details about checks...")
        checks_button.clicked.connect(partial(self._open_details, source, dest))

        data_valid.setObjectName("checks_ok_indicator")
        widgets = [
            data_valid,
            data_label,
            checks_ok,
            checks_label,
            checks_button,
        ]
        for widget in widgets:
            # All widgets are added to the layout and selectively hidden/shown
            # instead of changing channels on the fly
            self.layout().addWidget(widget)
        return widgets

    @QtCore.Slot(object)
    def set_destination(self, destination: Optional[DestinationPosition]):
        device = self._device

        self._destination = destination

        if device is None or destination is None:
            self.setVisible(False)
            return

        if not self.indicators:
            self.indicators = {
                dest: self._get_indicators(device.parent, device.source_pos, dest)
                for dest in btms_config.valid_destinations
            }

        for indicator_dest, indicators in self.indicators.items():
            for indicator in indicators:
                indicator.setVisible(indicator_dest == destination)

        self.setVisible(True)


class BtmsSourceOverviewWidget(DesignerDisplay, QtWidgets.QFrame):
    filename: ClassVar[str] = "btms-source.ui"

    current_dest_label: BtmsLaserDestinationLabel
    goniometer_widget: TyphosPositionerWidget
    linear_widget: TyphosPositionerWidget
    motor_frame: QtWidgets.QFrame
    motion_progress_widget: QtWidgets.QProgressBar
    rotary_widget: TyphosPositionerWidget
    show_motors_button: QtWidgets.QPushButton
    source: Optional[BtpsSourceStatus]
    source_name_label: QtWidgets.QLabel
    target_dest_widget: BtmsLaserDestinationChoice
    valid_widget: BtmsSourceValidWidget

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

        self.show_motors_button.clicked.connect(self.show_motors)
        self.show_motors(False)

    def show_motors(self, show: bool):
        self.motor_frame.setVisible(show)
        self.updateGeometry()

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

        failures = device.check_move_all(target)
        if failures:
            self._conflict = BtmsMoveConflictWidget(
                parent=None,
                source=self.source_position,
                dest=target,
                state=device.parent,
            )
            self._conflict.show()
            return

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
    # open_btps_config_button: QtWidgets.QPushButton
    open_btps_overview_button: QtWidgets.QPushButton
    _btps_overview: Optional[QtWidgets.QWidget]

    def __init__(self, *args, prefix: str = "", **kwargs):
        self._prefix = prefix
        super().__init__(*args, **kwargs)
        self.source_widgets = [
            self.ls1_widget,
            self.ls5_widget,
            self.ls8_widget,
        ]
        self.open_btps_overview_button.clicked.connect(self.open_btps_overview)
        self._btps_overview = None

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

    def open_btps_overview(self):
        overview = self._btps_overview
        if overview is not None:
            overview.setVisible(True)
            overview.raise_()
            return

        if self.device is None:
            return

        self._btps_overview = TyphosSuite.from_device(self.device)
        self._btps_overview.show()
