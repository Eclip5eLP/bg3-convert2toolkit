import shutil
import sys
import uuid
from pathlib import Path

from PyQt6.QtCore import (
    Qt,
    QTimer,
    QThread,
    pyqtSlot,
    QUrl
)
from PyQt6.QtGui import QIcon, QDesktopServices
from PyQt6.QtWidgets import (
    QMainWindow,
    QLineEdit,
    QVBoxLayout,
    QPushButton,
    QWidget,
    QLabel,
    QApplication,
    QHBoxLayout, QSizePolicy,
)
from pyqtwaitingspinner import SpinnerParameters, WaitingSpinner

from core import ConvertAPI

STYLE_CLASS = "class"
DEFAULT_STYLE = "default"
CONVERT_SOURCE_STYLE = "source"
OUTPUT_STYLE = "output"
HINT_LABEL = "hint_label"
INVALID_STYLE = "invalid"
HIGHLIGHT_STYLE = "highlight"
MENU_STYLE = "menu"
MENU_BUTTON_STYLE = "menu_button"


def add_classes(element: QWidget, *args):
    current_classes_prop = element.property(STYLE_CLASS)
    if current_classes_prop is not None:
        current_classes: list[str] = str(element.property(STYLE_CLASS)).split(' ')
    else:
        current_classes = []
    for arg in args:
        if not arg in current_classes:
            current_classes.append(arg)
    element.setProperty(STYLE_CLASS, ' '.join(current_classes))
    style_sheet = element.styleSheet()
    element.setStyleSheet(" ")
    element.setStyleSheet(style_sheet)

def remove_classes(element: QWidget, *args):
    current_classes_prop = element.property(STYLE_CLASS)
    if current_classes_prop is not None:
        current_classes: list[str] = str(element.property(STYLE_CLASS)).split(' ')
        for arg in args:
            if arg in current_classes:
                current_classes.remove(arg)
        element.setProperty(STYLE_CLASS, ' '.join(current_classes))
        style_sheet = element.styleSheet()
        element.setStyleSheet(" ")
        element.setStyleSheet(style_sheet)


# custom input to support drag-n-drop
class DragNDropQLabel(QLabel):
    text_input = None
    def __init__(self,
                 parent,
                 text_input: QLineEdit,
                 convert_api: ConvertAPI,
                 allow_paks: bool,
                 *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self.text_input = text_input
        self.convert_api = convert_api
        self.allow_paks = allow_paks
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.accept()
            add_classes(self, HIGHLIGHT_STYLE)
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        remove_classes(self, HIGHLIGHT_STYLE)

    def dropEvent(self, event):
        remove_classes(self, HIGHLIGHT_STYLE)
        url = event.mimeData().urls()[0]
        drop_path = Path(url.toLocalFile())

        if drop_path.is_dir() or (self.allow_paks and self.convert_api.is_pak(drop_path)):
            self.text_input.setText(str(drop_path.resolve()))
        else:
            self.text_input.setText(str(drop_path.parent.resolve()))


# thread object to support converting
class ConvertQThread(QThread):
    def __init__(self, parent,
                 convert_api: ConvertAPI,
                 source_path_input: str,
                 output_path_input: str):
        super().__init__(parent)
        self.convert_api: ConvertAPI = convert_api
        self.source_path_input: str = source_path_input
        self.output_path_input: str = output_path_input

    def run(self):
        source_path: Path = Path(self.source_path_input).resolve()
        output_path: Path = Path(self.output_path_input).resolve()

        if self.convert_api.is_pak(source_path):
            output_tmp = output_path / f'tmp_{uuid.uuid4()}'
            pak_tmp = output_tmp / source_path.stem
            pak_tmp.mkdir(parents=True, exist_ok=True)
            self.convert_api.unpack_file(source_path, pak_tmp)
            self.convert_api.convert(output_tmp, output_path, False)
            shutil.rmtree(str(output_tmp))
        else:
            self.convert_api.convert(source_path, output_path, False)


# thread object to support compiling auxdb
class CompileQThread(QThread):
    def __init__(self, parent,
                 convert_api: ConvertAPI):
        super().__init__(parent)
        self.convert_api: ConvertAPI = convert_api

    def run(self):
        self.convert_api.refresh_aux_db()


# timer used for delay before validating source/output fields
class DebounceQTimer(QTimer):
    def __init__(self,
                 timeout_function):
        super().__init__()
        self.setInterval(300)
        self.setSingleShot(True)
        # noinspection PyUnresolvedReferences
        self.timeout.connect(timeout_function)


# custom text inputs for file paths
class PathQLineEdit(QLineEdit):
    def __init__(self,
                 disable_function,
                 timeout_function):
        super().__init__()
        # Timer to give slight pause before checking path
        self.source_debounce = DebounceQTimer(timeout_function)
        add_classes(self, DEFAULT_STYLE)
        # noinspection PyUnresolvedReferences
        self.textChanged.connect(self.source_debounce.start)
        # noinspection PyUnresolvedReferences
        self.textChanged.connect(disable_function)


# top level UI pyqt6 object
class ConverterUIWindow(QMainWindow):
    def __init__(self,
                 default_source_path: Path,
                 default_output_path: Path,
                 path_to_resources: Path,
                 convert_api: ConvertAPI) -> None:
        super().__init__()
        self.convert_api: ConvertAPI = convert_api

        # main window's name and size:
        self.setWindowTitle("Eclip5e™ Convert2Toolkit")
        self.setWindowIcon(QIcon(str(path_to_resources / 'convert.ico')))
        self.setGeometry(300, 300, 800, 490)

        # text input for source path
        self.source_text_input = PathQLineEdit(
            disable_function=self.disable_convert_button,
            timeout_function=self.validate_paths
        )

        # text input for output path
        self.output_text_input = PathQLineEdit(
            disable_function=self.disable_convert_button,
            timeout_function=self.validate_paths
        )

        # main convert button
        self.convert_button = QPushButton("Convert")
        add_classes(self.convert_button, DEFAULT_STYLE)
        self.convert_button.setObjectName("convert_button")
        self.convert_button.setToolTip("Provide valid path for converting")
        # noinspection PyUnresolvedReferences
        self.convert_button.clicked.connect(self.run_convert)
        self.enable_convert_button(False)

        # compile aux db button
        self.compile_button = QPushButton("Compile AuxDB")
        add_classes(self.compile_button, MENU_BUTTON_STYLE)
        self.compile_button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        self.compile_button.setToolTip("Compile additional UUIDs from Editor projects")
        # noinspection PyUnresolvedReferences
        self.compile_button.clicked.connect(self.run_compile_auxdb)

        # github link button
        self.github_button = QPushButton("GitHub")
        add_classes(self.github_button, MENU_BUTTON_STYLE)
        self.github_button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        self.github_button.setToolTip("View GitHub Repository")
        # noinspection PyUnresolvedReferences
        self.github_button.clicked.connect(self.open_github)

        # loading spinner for convert button
        spin_pars = SpinnerParameters(
            disable_parent_when_spinning=True,
            inner_radius=6,
            line_length=12,
            line_width=3,
            number_of_lines=12,
            trail_fade_percentage=80
        )
        self.spinner = WaitingSpinner(self.convert_button, spin_pars)

        # ui group for menu buttons
        self.menu_container = QHBoxLayout()
        self.menu_container.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self.menu_container.addWidget(self.github_button)
        self.menu_container.addWidget(self.compile_button)
        self.menu_container_widget = QLabel(self)
        self.menu_container_widget.setLayout(self.menu_container)
        add_classes(self.menu_container_widget, MENU_STYLE)

        # ui group for source path
        self.convert_container = QHBoxLayout()
        self.convert_container.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self.convert_container.addWidget(self.source_text_input)
        self.convert_container_widget = DragNDropQLabel(
            parent=self,
            text_input=self.source_text_input,
            convert_api=self.convert_api,
            allow_paks=True
        )
        self.convert_container_widget.setLayout(self.convert_container)
        add_classes(self.convert_container_widget, CONVERT_SOURCE_STYLE)

        # ui group for output path
        self.output_container = QHBoxLayout()
        self.output_container.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self.output_container.addWidget(self.output_text_input)
        self.output_container_widget = DragNDropQLabel(
            parent=self,
            text_input=self.output_text_input,
            convert_api=self.convert_api,
            allow_paks=False
        )
        self.output_container_widget.setLayout(self.output_container)
        add_classes(self.output_container_widget, OUTPUT_STYLE, CONVERT_SOURCE_STYLE)

        # hint label for user on input
        self.convert_info_label = QLabel("Drop pak file/directory or enter path to convert")
        add_classes(self.convert_info_label, DEFAULT_STYLE, HINT_LABEL)

        # hint label for user on output
        self.output_info_label = QLabel("Drop directory or enter path for output")
        add_classes(self.output_info_label, DEFAULT_STYLE, HINT_LABEL)

        # setup main container for window
        self.main_container = QVBoxLayout()
        self.main_container.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.main_container.addWidget(self.menu_container_widget)
        self.main_container.addWidget(self.convert_info_label)
        self.main_container.addWidget(self.convert_container_widget)
        self.main_container.addWidget(self.output_info_label)
        self.main_container.addWidget(self.output_container_widget)
        self.main_container.addWidget(self.convert_button)

        # assemble central widget
        self.widget = QWidget()
        self.widget.setLayout(self.main_container)
        self.setCentralWidget(self.widget)

        # this is done late to detect change
        if not default_source_path is None:
            self.source_text_input.setText(str(default_source_path.resolve()))
        if not default_output_path is None:
            self.output_text_input.setText(str(default_output_path.resolve()))

    def validate_paths(self):
        valid_source = self.check_source_path()
        valid_output = self.check_output_path()
        if valid_source and valid_output:
            self.enable_convert_button(True)

    def check_source_path(self) -> bool:
        path_text = self.source_text_input.text()
        if path_text and self.convert_api.is_valid_source(Path(path_text)):
            remove_classes(self.convert_container_widget, INVALID_STYLE)
            return True
        else:
            add_classes(self.convert_container_widget, INVALID_STYLE)
            return False

    def check_output_path(self) -> bool:
        path_text = self.output_text_input.text()
        output_path = Path(path_text)
        if path_text and output_path.exists() and output_path.is_dir():
            remove_classes(self.output_container_widget, INVALID_STYLE)
            return True
        else:
            add_classes(self.output_container_widget, INVALID_STYLE)
            return False

    def disable_convert_button(self):
        self.enable_convert_button(False)

    def enable_convert_button(self, enable: bool = True):
        if enable:
            self.convert_button.setEnabled(True)
            self.convert_button.setToolTip("Convert Files")
        else:
            self.convert_button.setEnabled(False)
            self.convert_button.setToolTip("Provide valid input & output path for converting")

    def run_convert(self):
        self.spinner.start()
        self.compile_button.setDisabled(True)

        # spawn convert thread for processing
        convert_qthread = ConvertQThread(
            parent=self,
            convert_api=self.convert_api,
            source_path_input=self.source_text_input.text(),
            output_path_input=self.output_text_input.text()
        )
        convert_qthread.finished.connect(self._convert_finished)
        convert_qthread.start()

    @staticmethod
    def open_github():
        url = QUrl("https://github.com/Eclip5eLP/bg3-convert2toolkit")
        QDesktopServices.openUrl(url)

    def run_compile_auxdb(self):
        self.spinner.start()
        self.compile_button.setDisabled(True)

        compile_qthread = CompileQThread(
            parent=self,
            convert_api=self.convert_api
        )
        compile_qthread.finished.connect(self._compile_auxdb_finished)
        compile_qthread.start()


    @pyqtSlot()
    def _convert_finished(self):
        # TODO: may need to do cleanup?  notify user?
        self.spinner.stop()
        self.compile_button.setDisabled(False)


    @pyqtSlot()
    def _compile_auxdb_finished(self):
        # TODO: may need to do cleanup?  notify user?
        self.spinner.stop()
        self.compile_button.setDisabled(False)


# Controlling object for GUI
class ConvertGUI:
    def __init__(self,
                 convert_api: ConvertAPI,
                 path_to_root: Path,
                 path_to_resources: Path):
        self.convert_api: ConvertAPI = convert_api
        self.path_to_root: Path = path_to_root
        self.path_to_resources: Path = path_to_resources

    def run(self):
        """
            Profound description
        """
        app = QApplication([])

        # load in qss for custom styling
        with open(f"{self.path_to_resources}/style.qss", "r") as f:
            _style = f.read()
            app.setStyleSheet(_style)

        # create and launch ui window
        window = ConverterUIWindow(
            # TODO: should default paths come from settings?
            default_source_path=self.path_to_root / 'convert',
            default_output_path=self.path_to_root / 'convert',
            path_to_resources=self.path_to_resources,
            convert_api=self.convert_api
        )

        window.show()
        sys.exit(app.exec())
