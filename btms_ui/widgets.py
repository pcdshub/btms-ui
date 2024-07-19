from __future__ import annotations

import logging
import threading
import time
from functools import partial
from typing import ClassVar

import numpy as np
from ophyd.status import MoveStatus
from pcdsdevices.lasers import btms_config
from pcdsdevices.lasers.btms_config import DestinationPosition, SourcePosition
from pcdsdevices.lasers.btps import (BtpsSourceStatus, BtpsState,
                                     RangeComparison)
from pydm import widgets as pydm_widgets
from pydm.data_plugins import establish_connection
from qtpy import QtCore, QtWidgets
from typhos.positioner import TyphosPositionerWidget
from typhos.suite import TyphosSuite

from btms_ui.util import channel_from_signal

from . import util
from .core import DesignerDisplay
from .scene import BtmsStatusView

logger = logging.getLogger(__name__)


class BtmsLaserDestinationLabel(pydm_widgets.PyDMLabel):
    new_destination: QtCore.Signal = QtCore.Signal(object)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._destination = None

    @property
    def destination(self) -> DestinationPosition | None:
        return self._destination

    def setText(self, text: str):
        try:
            ld = int(text)
        except ValueError:
            return super().setText(f"(Unknown: {text})")

        if ld == 0:
            text = "Unknown"
            self._destination = None
            self.new_destination.emit(None)
        elif ld < 0:
            text = "(Misconfiguration)"
            self._destination = None
            self.new_destination.emit(None)
        else:
            pos = DestinationPosition.from_index(ld)
            text = f"→ {pos.description} (LD{ld})"
            self._destination = pos
            self.new_destination.emit(pos)

        return super().setText(text)


class BtmsDestinationComboBox(QtWidgets.QComboBox):
    def __init__(self, parent: QtWidgets.QWidget | None = None, **kwargs):
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

    def _watch_callback(self, fraction: float | None = None, **kwargs):
        if fraction is not None:
            percent = 1.0 - fraction
            self.percent_changed.emit(percent)
            if percent >= (1.0 - 1e-6):
                # TODO: this might not be necessary
                self.finished_moving.emit()

    def _finished_callback(self, fraction: float | None = None, **kwargs):
        self.percent_changed.emit(1.0)
        self.finished_moving.emit()


class QCombinedMoveStatus(QtCore.QObject):
    move_statuses: list[MoveStatus]
    initials: tuple[float, ...]
    percents: tuple[float, ...]
    currents: tuple[float, ...]
    targets: tuple[float, ...]
    status_changed = QtCore.Signal(float, list, list)  # List[float]
    finished_moving = QtCore.Signal()

    def __init__(self, move_statuses: list[MoveStatus]):
        super().__init__()
        if not move_statuses:
            raise ValueError("At least one MoveStatus required")

        self.move_statuses = list(st for st in move_statuses)
        self.initials = tuple([0.0] * len(move_statuses))
        self.targets = tuple([0.0] * len(move_statuses))
        self.currents = tuple([0.0] * len(move_statuses))
        self.percents = tuple([0.0] * len(move_statuses))
        self.lock = threading.Lock()
        self._finished_count = 0
        for idx, move_status in enumerate(self.move_statuses):
            move_status.watch(partial(self._watch_callback, idx))
            move_status.callbacks.append(partial(self._finished_callback, idx))

    @property
    def current_deltas(self) -> list[float]:
        """Delta of current position to target position."""
        return [
            abs(target - current)
            for current, target in zip(self.currents, self.targets)
            if current is not None and target is not None
        ]

    @property
    def initial_deltas(self) -> list[float]:
        """Delta of initial position to target position."""
        return [
            abs(target - initial)
            for initial, target in zip(self.initials, self.targets)
            if initial is not None and target is not None
        ]

    def _watch_callback(
        self,
        index: int,
        /,
        fraction: float | None = None,
        initial: float | None = None,
        current: float | None = None,
        target: float | None = None,
        **kwargs,
    ):
        with self.lock:
            if self._finished_count == len(self.move_statuses):
                return

            if initial is not None:
                initials = list(self.initials)
                initials[index] = initial
                self.initials = tuple(initials)
            if target is not None:
                targets = list(self.targets)
                targets[index] = target
                self.targets = tuple(targets)
            if current is not None:
                currents = list(self.currents)
                currents[index] = current
                self.currents = tuple(currents)
            if fraction is not None:
                percents = list(self.percents)
                percents[index] = fraction
                self.percents = tuple(percents)

            current_deltas = self.current_deltas
            initial_deltas = self.initial_deltas

        if not current_deltas or not initial_deltas:
            return

        try:
            current_sum = sum(current_deltas)
            final_sum = sum(initial_deltas)
            overall = 1.0 - np.clip(current_sum / final_sum, 0, 1)
        except Exception:
            overall = None
        else:
            self.status_changed.emit(overall, current_deltas, initial_deltas)
            if overall >= (1.0 - 1e-6):
                self.finished_moving.emit()

    def _finished_callback(self, index: int, /, fraction: float | None = None, **kwargs):
        with self.lock:
            self._finished_count += 1
            current_deltas = self.current_deltas
            initial_deltas = self.initial_deltas

        if self._finished_count == len(self.move_statuses):
            self.status_changed.emit(1.0, current_deltas, initial_deltas)
            self.finished_moving.emit()


class BtmsLaserDestinationChoice(QtWidgets.QFrame):
    target_dest_combo: BtmsDestinationComboBox
    _device: BtpsSourceStatus | None
    move_requested = QtCore.Signal(object)

    def __init__(self, parent: QtWidgets.QWidget | None = None, **kwargs):
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
    def device(self) -> BtpsSourceStatus | None:
        """The device for the BTMS."""
        return self._device

    @device.setter
    def device(self, device: BtpsSourceStatus):
        self._device = device


class BtmsStateDetails(QtWidgets.QFrame):
    def __init__(
        self,
        parent: QtWidgets.QWidget | None,
        state: BtpsState | None = None,
        source: SourcePosition | None = None,
        dest: DestinationPosition | None = None,
    ):
        super().__init__(parent)
        self._state = None
        self._source = None
        self._dest = None

        self._setup_ui()

        self.state = state
        self.source = source
        self.dest = dest
        self.setMinimumSize(800, 400)

    def _setup_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout()
        self.setLayout(layout)
        self.text_edit = QtWidgets.QTextEdit()
        layout.addWidget(self.text_edit)

    @property
    def state(self) -> BtpsState | None:
        """The BtpsState Bevice."""
        return self._state

    @state.setter
    def state(self, value: BtpsState | None):
        self._state = value
        self._update()

    @property
    def dest(self) -> DestinationPosition | None:
        """The destination."""
        return self._dest

    @dest.setter
    def dest(self, value: DestinationPosition | None):
        self._dest = value
        self._update()

    @property
    def source(self) -> SourcePosition | None:
        """The source."""
        return self._source

    @source.setter
    def source(self, value: SourcePosition | None):
        self._source = value
        self._update()

    def _update(self):
        source = self.source
        dest = self.dest
        state = self.state

        if source is None or dest is None or state is None:
            self.setWindowTitle("Motion conflict checks")
            return

        self.setWindowTitle(f"Checks for {source.name_and_desc} -> {dest.name_and_desc}")

        config = state.destinations[dest].sources[source]
        summary = config.summarize_checks()
        self.text_edit.setText("\n".join(summary))


class BtmsMoveConflictWidget(DesignerDisplay, QtWidgets.QFrame):
    filename: ClassVar[str] = "btms-move-request.ui"

    conflicts_label: QtWidgets.QLabel
    conflicts_list_widget: QtWidgets.QListWidget
    resolution_list_widget: QtWidgets.QListWidget
    apply_resolution_button: QtWidgets.QPushButton
    move_button: QtWidgets.QPushButton
    state: BtpsState
    source: SourcePosition
    dset: DestinationPosition

    request_move = QtCore.Signal()

    def __init__(
        self,
        parent: QtWidgets.QWidget | None,
        state: BtpsState,
        source: SourcePosition,
        dest: DestinationPosition,
    ):
        super().__init__(parent)
        self.state = state
        self.source = source
        self.dest = dest

        self.conflicts_label.setText(
            f"Issues detected moving {source.description} {source} to "
            f"{dest.description} {dest}:"
        )

        self._update_checks()
        self.apply_resolution_button.clicked.connect(self._resolve_all)
        self.update_button.clicked.connect(self._update_checks)
        self.move_button.clicked.connect(self._move)

    def _move(self):
        conflicts = "\n".join(
            self.conflicts_list_widget.item(idx).text()
            for idx in range(self.conflicts_list_widget.count())
        )
        if conflicts:
            self._confirmation = QtWidgets.QMessageBox()
            self._confirmation.setWindowTitle("Move request")
            self._confirmation.setText(
                f"Issues remain for {self.source}: ignore and move?"
            )
            self._confirmation.setInformativeText(conflicts)
            self._confirmation.setStandardButtons(
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
            )
            self._confirmation.setDefaultButton(
                QtWidgets.QMessageBox.No
            )
            should_move = self._confirmation.exec_()
            if should_move != QtWidgets.QMessageBox.Yes:
                return

        self.request_move.emit()
        self.close()

    def _update_checks(self):
        """Update the issue list."""
        self.issues = self.state.sources[self.source].check_move_all(self.dest)
        self.conflicts_list_widget.clear()
        self.resolution_list_widget.clear()
        for issue in self.issues:
            self.conflicts_list_widget.addItem(f"{issue.__class__.__name__}: {issue}")
            resolution = self.get_resolution_explanation(issue)
            if resolution is not None:
                self.resolution_list_widget.addItem(resolution)

        can_fix = any(self.can_fix_issue(issue) for issue in self.issues)
        self.apply_resolution_button.setEnabled(can_fix)

    def _resolve_all_thread(self):
        """Attempt to resolve all issues."""
        for issue in self.issues:
            self.fix_issue(issue)
        time.sleep(1.0)
        util.run_in_gui_thread(self._update_checks)

    def _resolve_all(self):
        """Attempt to resolve all issues."""
        self._thread = threading.Thread(target=self._resolve_all_thread, daemon=True)
        self._thread.start()

    def can_fix_issue(self, conflict: Exception) -> bool:
        """Are we able to fix the issue in ``conflict`` automatically?"""
        if isinstance(conflict, btms_config.MovingActiveSource):
            return True
        if isinstance(conflict, btms_config.PathCrossedError):
            return True

        return False

    def fix_issue(self, conflict: Exception) -> None:
        """Try to fix the issue in ``conflict`` automatically."""
        if isinstance(conflict, btms_config.MovingActiveSource):
            logger.warning("Closing shutter for %s", self.source)
            self.state.sources[self.source].open_request.set(0)
        elif isinstance(conflict, btms_config.PathCrossedError):
            logger.warning("Closing shutter for %s", conflict.crosses_source)
            self.state.sources[conflict.crosses_source].open_request.set(0)
        elif isinstance(conflict, btms_config.DestinationInUseError):
            # Any idea?
            ...

    def get_resolution_explanation(self, conflict: Exception) -> str | None:
        """
        Get an explanation about a resolution for the provided issue.

        Parameters
        ----------
        conflict : Exception
            The exception.

        Returns
        -------
        str or None
            An explanation of the resolution, if supported.
        """
        if isinstance(conflict, btms_config.MovingActiveSource):
            return f"Close shutter for {self.source}"

        if isinstance(conflict, btms_config.PathCrossedError):
            return f"Close shutter for active crossed source: {conflict.crosses_source}"

        return None


class BtmsSourceValidWidget(QtWidgets.QFrame):
    indicators: dict[DestinationPosition, list[pydm_widgets.PyDMByteIndicator]]

    def __init__(
        self,
        parent: QtWidgets.QWidget | None = None,
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
    def device(self) -> BtpsSourceStatus | None:
        """The device for the BTMS."""
        return self._device

    @device.setter
    def device(self, device: BtpsSourceStatus):
        self._device = device
        self.set_destination(self._destination)

    @property
    def destination(self) -> DestinationPosition | None:
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
    ) -> list[pydm_widgets.PyDMByteIndicator]:
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

        dest_conf = state.destinations[dest]

        yield_status = pydm_widgets.PyDMByteIndicator(
            init_channel=channel_from_signal(dest_conf.yields_control)
        )
        yield_status.setObjectName("yield_status_indicator")
        yield_label = QtWidgets.QLabel("Yielded")

        for widget in [yield_label, yield_status, *getattr(yield_status, "_indicators", [])]:
            widget.setToolTip(
                "Green if current destination hutch yielded control to others"
            )

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
            yield_status,
            yield_label,
            # Keep the checks button last:
            checks_button,
        ]
        for widget in widgets:
            # All widgets are added to the layout and selectively hidden/shown
            # instead of changing channels on the fly
            self.layout().addWidget(widget)
        return widgets

    @QtCore.Slot(object)
    def set_destination(self, destination: DestinationPosition | None):
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

    positioner_widgets: tuple[TyphosPositionerWidget, ...]

    current_dest_label: BtmsLaserDestinationLabel
    goniometer_widget: TyphosPositionerWidget
    linear_widget: TyphosPositionerWidget
    motion_progress_frame: QtWidgets.QFrame
    motion_progress_widget: QtWidgets.QProgressBar
    motion_stop_button: QtWidgets.QPushButton
    motor_frame: QtWidgets.QFrame
    rotary_widget: TyphosPositionerWidget
    save_nominal_button: QtWidgets.QPushButton
    save_centroid_nominal_button: QtWidgets.QPushButton
    show_cameras_button: QtWidgets.QPushButton
    source: BtpsSourceStatus | None
    source_name_label: QtWidgets.QLabel
    target_dest_widget: BtmsLaserDestinationChoice
    toggle_control_button: QtWidgets.QPushButton
    valid_widget: BtmsSourceValidWidget

    far_field_desc_label: QtWidgets.QLabel
    far_x_label: pydm_widgets.label.PyDMLabel
    far_y_label: pydm_widgets.label.PyDMLabel
    goniometer_desc_label: QtWidgets.QLabel
    goniometer_label: pydm_widgets.PyDMLabel
    linear_desc_label: QtWidgets.QLabel
    linear_label: pydm_widgets.PyDMLabel
    near_field_label: QtWidgets.QLabel
    near_x_label: pydm_widgets.PyDMLabel
    near_y_label: pydm_widgets.PyDMLabel
    overview_frame: QtWidgets.QFrame
    overview_layout: QtWidgets.QGridLayout
    rotary_desc_label: QtWidgets.QLabel
    rotary_label: pydm_widgets.label.PyDMLabel

    new_destination: QtCore.Signal = QtCore.Signal(object)

    def __init__(
        self,
        parent: QtWidgets.QWidget | None,
        prefix: str = "",
        source_index: int = 1,
        expert_mode: bool = True,
        **kwargs
    ):
        super().__init__(parent, **kwargs)
        self._prefix = prefix
        self._source_index = source_index

        self.pydm_widgets_to_suffix = {
            self.current_dest_label: "BTPS:CurrentLD_RBV",
        }
        self.positioner_widgets = (
            self.linear_widget,
            self.rotary_widget,
            self.goniometer_widget,
        )

        for widget in self.positioner_widgets:
            widget.ui.clear_error_button.setVisible(False)

        self.target_dest_widget.move_requested.connect(self.move_request)
        self.motion_progress_frame.setVisible(False)

        self.current_dest_label.new_destination.connect(self.new_destination.emit)
        self.current_dest_label.new_destination.connect(self.valid_widget.set_destination)

        self.show_cameras_button.clicked.connect(self.show_cameras)
        self.toggle_control_button.clicked.connect(self.show_motors)
        self.save_nominal_button.clicked.connect(self.save_motor_nominal)
        self.save_centroid_nominal_button.clicked.connect(self.save_centroid_nominal)
        self._camera_process = None
        self._expert_mode = None
        self.expert_mode = expert_mode

    def adjust_range(
        self, range_device: RangeComparison, value: float, delta: float = 1.0
    ):
        """Adjust a range comparison to the new value."""
        logger.warning(
            "Adjusting %s to %s +- %s",
            range_device.nominal.setpoint_pvname,
            value,
            delta,
        )
        range_device.nominal.put(value)
        low_value = range_device.low.get()
        high_value = range_device.high.get()
        if float(low_value) >= (value - delta) or low_value == 0.0:
            range_device.low.put(value - delta)
        if float(range_device.high.get()) <= (value + delta) or high_value == 0.0:
            range_device.high.put(value + delta)

    def _save_nominal(self, dest: DestinationPosition) -> None:
        """Save nominal positions to the BTPS for ``dest``."""
        if self.device is None:
            return

        config = self.device.parent.destinations[dest].sources[self.source_position]

        # The old nominal positions
        old_linear = config.linear.nominal.get()
        old_rotary = config.rotary.nominal.get()
        old_goniometer = config.goniometer.nominal.get()

        # The current motor positions
        linear = float(self.device.linear.user_readback.get())
        rotary = float(self.device.rotary.user_readback.get())
        goniometer = float(self.device.goniometer.user_readback.get())

        msg_str = (
            "Current nominal positions:",
            f"\tLinear: {old_linear:.4f}",
            f"\tRotary: {old_rotary:.4f}",
            f"\tGoniometer: {old_goniometer:.4f}",
            "",
            "New nominal positions:",
            f"\tLinear: {linear:.4f}",
            f"\tRotary: {rotary:.4f}",
            f"\tGoniometer: {goniometer:.4f}\n",
        )

        dest_str = dest.name_and_desc

        self._confirm_pos = QtWidgets.QMessageBox()
        self._confirm_pos.setWindowTitle("Confirm Nominal Positions")
        self._confirm_pos.setText(f"Update positions for {dest_str}?")
        self._confirm_pos.setInformativeText("\n".join(msg_str))
        self._confirm_pos.setStandardButtons(
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
        )
        self._confirm_pos.setDefaultButton(
            QtWidgets.QMessageBox.No
        )
        save = self._confirm_pos.exec_()
        if save == QtWidgets.QMessageBox.Yes:
            logger.info(
                "Set motor nominal for %s linear=%s rotary=%s goniometer=%s",
                dest.name_and_desc,
                linear,
                rotary,
                goniometer,
            )
            # Set the source-to-destination data store values:
            self.adjust_range(config.linear, linear, delta=1.0)
            self.adjust_range(config.rotary, rotary, delta=1.0)
            self.adjust_range(config.goniometer, goniometer, delta=1.0)

    def _save_centroid_nominal(self, dest: DestinationPosition) -> None:
        """Save the current centroid X/Y positions to the BTPS."""
        if self.device is None:
            return

        config = self.device.parent.destinations[dest].sources[self.source_position]

        # Get the old config values
        old_nf_x = float(config.near_field.centroid_x.nominal.get())
        old_nf_y = float(config.near_field.centroid_y.nominal.get())
        old_ff_x = float(config.far_field.centroid_x.nominal.get())
        old_ff_y = float(config.far_field.centroid_y.nominal.get())

        nf_x = float(config.near_field.centroid_x.value.get())
        nf_y = float(config.near_field.centroid_y.value.get())
        ff_x = float(config.far_field.centroid_x.value.get())
        ff_y = float(config.far_field.centroid_y.value.get())

        msg_str = (
            "Current nominal centroids:",
            f"\tNF X: {old_nf_x:.1f}",
            f"\tNF Y: {old_nf_y:.1f}",
            f"\tFF X: {old_ff_x:.1f}",
            f"\tFF Y: {old_ff_y:.1f}",
            "",
            "New nominal centroids:",
            f"\tNF X: {nf_x:.1f}",
            f"\tNF Y: {nf_y:.1f}",
            f"\tFF X: {ff_x:.1f}",
            f"\tFF Y: {ff_y:.1f}\n",
        )

        dest_str = dest.name_and_desc

        self._confirm_centroid = QtWidgets.QMessageBox()
        self._confirm_centroid.setWindowTitle("Confirm Nominal Centroids")
        self._confirm_centroid.setText(f"Update centroids for {dest_str}?")
        self._confirm_centroid.setInformativeText("\n".join(msg_str))
        self._confirm_centroid.setStandardButtons(
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
        )
        self._confirm_centroid.setDefaultButton(
            QtWidgets.QMessageBox.No
        )
        save = self._confirm_centroid.exec_()
        if save == QtWidgets.QMessageBox.Yes:
            logger.info(
                "Set nominal for %s nf=%s %s ff=%s %s",
                dest.name_and_desc,
                nf_x,
                nf_y,
                ff_x,
                ff_y,
            )

            # Set the source-to-destination data store values:
            if nf_x > 0.0:
                self.adjust_range(config.near_field.centroid_x, nf_x, delta=20.0)
            if nf_y > 0.0:
                self.adjust_range(config.near_field.centroid_y, nf_y, delta=20.0)
            if ff_x > 0.0:
                self.adjust_range(config.far_field.centroid_x, ff_x, delta=20.0)
            if ff_y > 0.0:
                self.adjust_range(config.far_field.centroid_y, ff_y, delta=20.0)

    def save_centroid_nominal(self) -> None:
        """Save the current centroid X/Y positions to the BTPS."""
        dest = self.get_destination()
        if dest is None:
            return

        self._save_centroid_nominal(dest)

    def get_destination(self) -> DestinationPosition | None:
        dest = self.current_dest_label.destination
        if dest is not None:
            return dest

        destinations = {
            dest.name_and_desc: dest
            for dest in DestinationPosition
        }
        dest_text, ok = QtWidgets.QInputDialog.getItem(
            self,
            "Select the destination to save nominal positions to",
            "Destinations:",
            tuple(destinations),
            0,
            False,
        )
        if ok:
            return destinations[dest_text]
        return None

    def save_motor_nominal(self):
        """Save the current positions to the BTPS nominal positions."""
        if self.device is None:
            return

        dest = self.get_destination()
        if dest is None:
            return

        self._save_nominal(dest)

    def show_cameras(self):
        """Show the camera control screen."""
        if self.device is None:
            return

        bay = self.device.source_pos.bay
        if bay is None:
            return

        if self._camera_process is not None:
            if self._camera_process.returncode is None:
                self._confirmation = QtWidgets.QMessageBox()
                self._confirmation.setWindowTitle("Camera screens open")
                self._confirmation.setText(
                    f"Camera screens for {self.source_position} are already running. "
                    f"Open a new set of screens?"
                )
                self._confirmation.setInformativeText(f"PID: {self._camera_process.pid}")
                self._confirmation.setStandardButtons(
                    QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
                )
                self._confirmation.setDefaultButton(
                    QtWidgets.QMessageBox.No
                )
                if self._confirmation.exec_() != QtWidgets.QMessageBox.Yes:
                    return

        self._camera_process = util.open_typhos_in_subprocess(
            f"las_lhn_bay{bay}_cam_nf",
            f"las_lhn_bay{bay}_cam_ff",
        )

    def show_motors(self, show: bool):
        for motor in self.positioner_widgets:
            motor.setVisible(show)

        show_position_labels = not show
        self.linear_label.setVisible(show_position_labels)
        self.goniometer_label.setVisible(show_position_labels)
        self.rotary_label.setVisible(show_position_labels)
        self.save_nominal_button.setVisible(show)
        self.save_centroid_nominal_button.setVisible(show)

    def _perform_move(
        self, target: DestinationPosition
    ) -> QCombinedMoveStatus | None:
        """
        Request move of this source to the ``target`` DestinationPosition.
        """
        device = self.device

        if device is None:
            return

        def stop_all():
            for st in status:
                try:
                    st.device.stop()
                except Exception:
                    logger.exception("Failed to stop device %s", st.device.name)

        def finished_moving():
            self.motion_progress_frame.setVisible(False)

        def update(overall_percent: float, current_deltas: list[float], initial_deltas: list[float]):
            self.motion_progress_widget.setValue(int(overall_percent * 100.0))

        self.motion_progress_widget.setValue(0)

        status = device.set_with_movestatus(target, check=False)
        self._move_status = QCombinedMoveStatus(list(status))
        self._move_status.status_changed.connect(update)
        self._move_status.finished_moving.connect(finished_moving)

        show_progress = not any(st.done for st in self._move_status.move_statuses)
        self.motion_stop_button.clicked.connect(stop_all)
        self.motion_progress_frame.setVisible(show_progress)
        return self._move_status

    def move_request(self, target: DestinationPosition) -> QCombinedMoveStatus | None:
        """
        Request move of this source to the ``target`` DestinationPosition.
        """
        device = self.device

        if device is None:
            return

        def finished_moving():
            self.motion_progress_frame.setVisible(False)

        def update(overall_percent: float, individual_percents: list[float]):
            self.motion_progress_widget.setValue(int(overall_percent * 100.0))

        self.motion_progress_widget.setValue(0)

        issues = device.check_move_all(target)

        if self.expert_mode:
            issues = util.prune_expert_issues(issues)

        if issues:
            self._conflict = BtmsMoveConflictWidget(
                parent=None,
                source=self.source_position,
                dest=target,
                state=device.parent,
            )
            self._conflict.request_move.connect(
                partial(self._perform_move, target)
            )
            self._conflict.show()
            return

        return self._perform_move(target)

    @QtCore.Property(bool)
    def expert_mode(self) -> bool:
        """The expert mode setting."""
        return self._expert_mode

    @expert_mode.setter
    def expert_mode(self, expert_mode: bool):
        if expert_mode == self._expert_mode:
            return

        self._expert_mode = bool(expert_mode)
        self.toggle_control_button.setVisible(self._expert_mode)
        if not self._expert_mode:
            self.show_motors(False)
            self.toggle_control_button.setChecked(False)

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
    def device(self) -> BtpsSourceStatus | None:
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
        self.linear_label.channel = channel_from_signal(device.linear.user_readback)
        self.rotary_label.channel = channel_from_signal(device.rotary.user_readback)
        self.goniometer_label.channel = channel_from_signal(device.goniometer.user_readback)
        self.near_x_label.channel = f"ca://{device.source_pos.near_field_camera_prefix}Stats2:CentroidX_RBV"
        self.near_y_label.channel = f"ca://{device.source_pos.near_field_camera_prefix}Stats2:CentroidY_RBV"
        self.far_x_label.channel = f"ca://{device.source_pos.far_field_camera_prefix}Stats2:CentroidX_RBV"
        self.far_y_label.channel = f"ca://{device.source_pos.far_field_camera_prefix}Stats2:CentroidY_RBV"


class BtmsDiagramWidget(DesignerDisplay, QtWidgets.QWidget):
    filename: ClassVar[str] = "btms-diagram.ui"
    view: BtmsStatusView

    def __init__(self, *args, prefix: str = "", **kwargs):
        self._prefix = prefix
        super().__init__(*args, **kwargs)

        self.setSizePolicy(
            QtWidgets.QSizePolicy.MinimumExpanding,
            QtWidgets.QSizePolicy.MinimumExpanding,
        )
        self.view.setSizePolicy(
            QtWidgets.QSizePolicy.MinimumExpanding,
            QtWidgets.QSizePolicy.MinimumExpanding,
        )

    @QtCore.Property(str)
    def prefix(self) -> str:
        """The PV prefix for the BTMS."""
        return self._prefix

    @prefix.setter
    def prefix(self, prefix: str):
        self.view.device_prefix = prefix
        self._prefix = prefix


class HutchOverviewDisplay(DesignerDisplay, QtWidgets.QWidget):
    """
    Hutch information display, including maintenance mode status and hutch
    control state.
    """
    filename: ClassVar[str] = "btms-hutch.ui"


class BtmsMain(DesignerDisplay, QtWidgets.QWidget):
    """
    Main display, including diagram and source information.
    """
    filename: ClassVar[str] = "btms.ui"
    diagram_widget: BtmsDiagramWidget
    ls1_widget: BtmsSourceOverviewWidget
    ls5_widget: BtmsSourceOverviewWidget
    ls8_widget: BtmsSourceOverviewWidget
    open_btps_overview_button: QtWidgets.QPushButton
    open_hutch_overview_button: QtWidgets.QPushButton
    expert_mode_checkbox: QtWidgets.QCheckBox
    source_widgets: list[BtmsSourceOverviewWidget]
    _btps_overview: QtWidgets.QWidget | None
    _hutch_overview: QtWidgets.QWidget | None

    def __init__(self, *args, prefix: str = "", expert_mode: bool = False, **kwargs):
        self._prefix = prefix
        super().__init__(*args, **kwargs)
        self.source_widgets = [
            self.ls1_widget,
            self.ls5_widget,
            self.ls8_widget,
        ]
        # TODO: hiding the BTPS screen for now as a workaround
        self.open_btps_overview_button.setVisible(False)
        self.open_btps_overview_button.clicked.connect(self.open_btps_overview)
        self.open_hutch_overview_button.clicked.connect(self.open_hutch_overview)
        self._btps_overview = None
        self._hutch_overview = None
        self.expert_mode_checkbox.clicked.connect(self._set_expert_mode)
        self._set_expert_mode(expert_mode)

    def _set_expert_mode(self, expert_mode: bool):
        """Toggle expert mode widgets."""
        for source_widget in self.source_widgets:
            source_widget.expert_mode = expert_mode

    @property
    def device(self) -> BtpsState | None:
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
        """Open the btps overview screen."""
        overview = self._btps_overview
        if overview is not None:
            overview.setVisible(True)
            overview.raise_()
            return

        if self.device is None:
            return

        self._btps_overview = TyphosSuite.from_device(self.device)
        self._btps_overview.show()

    def open_hutch_overview(self):
        """Open the hutch overview screen."""
        overview = self._hutch_overview
        if overview is not None:
            overview.setVisible(True)
            overview.raise_()
            return

        if self.device is None:
            return

        self._hutch_overview = HutchOverviewDisplay()
        self._hutch_overview.show()
