from qtpy import QtWidgets

from btms_ui.ui.btps_prototype import BtpsPrototype


def main():
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])

    widget = BtpsPrototype()

    widget.show()

    app.exec_()


if __name__ == "__main__":
    main()
