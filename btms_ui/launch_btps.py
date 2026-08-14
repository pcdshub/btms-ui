import sys

from qtpy.QtWidgets import QApplication

from btms_ui.ui.btps_stacked_screen import BtpsStackedScreen


def ignore_rules_engine_errors(exc_type, exc_value, exc_traceback):
    """
    Suppress harmless RulesEngine cleanup errors.
    This usually happens after closeEvent concludes and the PyDMEmbeddedViews
    disagree existentially about their RulesEngines, but the pyqdm was already
    destroyed.
    """
    if exc_type == RuntimeError and "RulesEngine has been deleted" in str(exc_value):
        return
    sys.__excepthook__(exc_type, exc_value, exc_traceback)


def main():
    app = QApplication.instance() or QApplication([])
    sys.excepthook = ignore_rules_engine_errors

    widget = BtpsStackedScreen()
    widget.show()
    app.exec_()


if __name__ == "__main__":
    main()
