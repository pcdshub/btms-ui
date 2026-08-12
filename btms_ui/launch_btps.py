from qtpy import QtWidgets

from btms_ui.ui.btps_stacked_screen import BtpsPrototype


def main():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    widget = BtpsPrototype()

    widget.show()

    app.exec_()


if __name__ == "__main__":
    main()
