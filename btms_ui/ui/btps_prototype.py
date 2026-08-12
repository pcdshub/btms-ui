import json
import logging
from functools import partial
from typing import ClassVar

from pydm.widgets import PyDMEmbeddedDisplay, PyDMEnumComboBox, PyDMLineEdit
from qtpy.QtCore import QRegularExpression
from qtpy.QtWidgets import QPushButton, QStackedWidget, QWidget

from btms_ui import util
from btms_ui.config import btms_config
from btms_ui.core import DesignerDisplay

logger = logging.getLogger(__name__)


class BtpsPrototype(DesignerDisplay, QWidget):
    filename: ClassVar[str] = "btps/btps_stacked_screen.ui"
    stacked_widget: QStackedWidget
    btps_overview_widget: PyDMEmbeddedDisplay
    editor_button: QPushButton

    LS1_button: QPushButton
    LS2_button: QPushButton
    LS3_button: QPushButton
    LS4_button: QPushButton
    LS5_button: QPushButton
    LS6_button: QPushButton
    LS7_button: QPushButton
    LS8_button: QPushButton

    LD1_button: QPushButton
    LD2_button: QPushButton
    LD3_button: QPushButton
    LD4_button: QPushButton
    LD5_button: QPushButton
    LD6_button: QPushButton
    LD7_button: QPushButton
    LD8_button: QPushButton
    LD9_button: QPushButton
    LD10_button: QPushButton
    LD11_button: QPushButton
    LD12_button: QPushButton
    LD13_button: QPushButton
    LD14_button: QPushButton

    def __init__(self, parent: QWidget | None = None,):
        super().__init__(parent)
        self.stack_widget_dict = {}
        self.current_view = {"source": "LS0", "dest": "LD0"}
        self.sources = [str(source) for source in btms_config.valid_sources]
        self.destinations = [str(dest) for dest in btms_config.valid_destinations]
        # Hold onto a list of embedded displays to destroy properly later
        self._embedded_displays = []

        self.btps_overview_widget.setFilename(
            str(util.BTMS_SOURCE_PATH / "ui/btps/btps-overview.ui")
        )

        self.editor_button.toggled.connect(self.toggle_edit_button)
        self.build_stacked_widget()
        self.update_view()
        self.init_buttons()

    def build_stacked_widget(self) -> None:
        """
        Build stacked widgets for example layout
        """
        logger.debug("Building stacked widget")
        # Gotta initialize and hardcode the landing page
        self.stack_widget_dict["LS0_LD0"] = 0

        for source in self.sources:
            for dest in self.destinations:
                self.add_stacked_frame(source, dest)

    def add_stacked_frame(self, source: str, dest: str) -> None:
        """
        Build a frame to add to the stackedWidget

        Parameters
        ----------
        source : int
            Laser source identifier.  1 < source < 8.
        dest : int
            Laser destination identifier. 1 < dest < 14
        """
        temp_widget = PyDMEmbeddedDisplay(parent=self.stackedWidget)
        macros = {"SOURCE": f"LTLHN:{dest}:{source}:",
                  "DEST": f"LTLHN:{dest}:",
                  "SHUTTER": f"LTLHN:{source}:BTPS:",
                  "RANGE_SCREEN": str(util.BTMS_SOURCE_PATH / "ui/btps/btps-range-config.ui")}
        temp_widget.setMacros(json.dumps(macros))
        temp_widget.loadWhenShown = True
        temp_widget.setFilename(
            str(util.BTMS_SOURCE_PATH / "ui/btps/btps-source-dest.ui"))

        temp_widget.setObjectName(f"{source}_{dest}_widget")
        # Add it to the stacked widget
        idx = self.stackedWidget.addWidget(temp_widget)
        logger.debug(f"Adding {source}_{dest} widget to stacked index {idx}")
        # Add it to the stacked widget dict
        self.stack_widget_dict[f"{source}_{dest}"] = idx
        self._embedded_displays.append(temp_widget)

    def init_buttons(self) -> None:
        """
        Set up all the navigator buttons
        """
        logger.debug("Initializing navigator buttons")

        invalid_sources = [src for src in [f"LS{i}" for i in range(1, 9)]
                           if src not in self.sources]
        invalid_dest = [dest for dest in [f"LD{j}" for j in range(1, 15)]
                        if dest not in self.destinations]

        for source in self.sources:
            self.configure_button(name=f"{source}_button")

        for dest in self.destinations:
            self.configure_button(name=f"{dest}_button")

        for bad_btn in invalid_sources + invalid_dest:
            logger.debug(f"{bad_btn} is unused, hiding it.")
            self.hide_button(bad_btn)

    def configure_button(self, name: str) -> None:
        """
        Configure the stylesheet and make the button checkable
        """
        button: QPushButton
        logger.debug(f"Configuring button: {name}")

        stylesheet = """
        QPushButton {
            background-color: #f0f0f0;
            border: 1px solid #ababab;
            padding: 5px;
            border-radius: 3px;
        }
        QPushButton:hover {
            background-color: #e0e0e0;
        }
        QPushButton:checked {
            background-color: #3cda02;
            color: white;
            font-weight: bold;
            border: 1px solid #3dcb0a;
        }
        QPushButton:checked:hover {
            background-color: #3dcb0a;
        }
        """
        button = getattr(self, name)
        button.setStyleSheet("")
        button.setCheckable(True)
        button.toggled.connect(partial(self.toggle_button, button))
        button.setStyleSheet(stylesheet)

    def hide_button(self, name: str) -> None:
        """
        Disable and hide a QPushButton for a source/dest that doesn't exist yet

        Parameters
        ----------
        name : str
            Name of the QPushbutton obj
        """
        button: QPushButton

        button = getattr(self, f"{name}_button")
        button.setEnabled(False)
        # Paradoxically, you set the size policy for hidden objects this way
        size_policy = button.sizePolicy()
        size_policy.setRetainSizeWhenHidden(True)
        button.setSizePolicy(size_policy)
        # Then hide it without rearranging your layouts
        button.hide()

    def toggle_button(self, button: QPushButton) -> None:
        temp: QPushButton

        name = button.objectName()
        # Check to see if this button is already active

        if button.isChecked():
            if "LS" in name:
                iterator = self.sources
                self.current_view["source"] = name.split('_', maxsplit=1)[0]
            elif "LD" in name:
                iterator = self.destinations
                self.current_view["dest"] = name.split('_', maxsplit=1)[0]
            else:
                logger.warning(f"{name} is in an unknown state, aborting toggle!")
                return

            for it in iterator:
                temp = getattr(self, f"{it}_button")
                if temp != button:
                    if temp.isChecked():
                        self.uncheck_quietly(temp)

            button.setChecked(True)

        else:
            # Then just deactivate it
            self.uncheck_quietly(button)
            self.current_view = {"source": "LS0", "dest": "LD0"}
            self.update_view()
            return

        # Then we should update our view
        self.update_view()

    def uncheck_quietly(self, button: QPushButton) -> None:
        """
        Toggle a checkable QPushbutton without emitting a signal, avoiding accidental callbacks.
        """
        logger.debug(f"Quietly unchecking {button.objectName}")

        button.blockSignals(True)
        button.setChecked(False)
        button.blockSignals(False)

    def update_view(self) -> None:
        """
        Update the stacked widget based on the selector buttons. Use the dict to select
        the correct index from the stackedWidget.
        """

        source = self.current_view["source"]
        dest = self.current_view["dest"]

        key = f"{source}_{dest}"
        logger.debug(f"Received update to view {key}")

        idx = self.stack_widget_dict[key] if key in self.stack_widget_dict else 0
        logger.debug(f"Stacked view set to index: {idx}")

        self.stackedWidget.setCurrentIndex(idx)
        self.toggle_edit_widgets(enabled=self.editor_button.isChecked(),
                                 page=self.stackedWidget.currentWidget())

    def toggle_edit_button(self) -> None:
        """
        Handles the latched state on the editor button and updates the enable state on
        the appropriate config edit widgets.
        """
        checked = self.editor_button.isChecked()

        if checked:
            logger.debug("Edit mode requested")
            self.editor_button.setText("Edit Mode")
        else:
            logger.debug("View mode requested")
            self.editor_button.setText("View Mode")

        self.toggle_edit_widgets(checked)

    def toggle_edit_widgets(self, enabled: bool, page: PyDMEmbeddedDisplay = None):
        """
        Toggle the enable and show/hide state of config edit widgets
        """
        widget: PyDMLineEdit | PyDMEnumComboBox

        current_page = page

        if not page:
            current_page = self.stackedWidget.currentWidget()
            logger.debug("No page detected. "
                         f"Setting to current widget: {current_page.objectName}")

        edit_widgets = current_page.findChildren((PyDMLineEdit, PyDMEnumComboBox),
                                                 QRegularExpression("Setpoint"))

        logger.debug(f"Enable state is set to {enabled} "
                     "Updating widgets.")
        for widget in edit_widgets:
            widget.setEnabled(enabled)
            if enabled:
                widget.show()
            else:
                widget.hide()
