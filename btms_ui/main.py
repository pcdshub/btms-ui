from typing import ClassVar

from qtpy import QtWidgets

from .core import DesignerDisplay


class BtmsMain(DesignerDisplay, QtWidgets.QWidget):
    filename: ClassVar[str] = "btms.ui"


def main():
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])
    widget = BtmsMain()
    widget.show()
    app.exec_()


if __name__ == "__main__":
    main()
