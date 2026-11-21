"""Guided installation and pairing for the optional browser reader."""
from io import BytesIO

from PySide6.QtCore import QSaveFile, QTimer
from PySide6.QtWidgets import QDialog, QFileDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from .browser_archive import write_archive


class BrowserSetup(QDialog):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.setWindowTitle("BoardLens · Browser setup")
        self.resize(660, 650)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(12)
        heading = QLabel("Connect your browser")
        heading.setObjectName("workspaceTitle")
        layout.addWidget(heading)
        self.explain(layout, "Use Chrome or Edge for direct reading on Chess.com and Lichess. For ordinary screen scanning, you can skip this setup.")

        install = self.step(layout, "1. Download and load Browser Reader",
                            "Save the ZIP and extract it wherever you like. Open chrome://extensions or edge://extensions, enable Developer mode, then choose Load unpacked. Select the extracted BrowserReader folder.")
        self.button(install, "Download Browser Reader ZIP…", self.download_extension)

        pair = self.step(layout, "2. Pair with BoardLens",
                         "Enable the reader, then copy the pairing key. Open BoardLens Browser Reader from the browser toolbar or its Extensions menu, open Desktop connection, paste the key, then click Connect.")
        buttons = QHBoxLayout()
        self.enable = self.button(buttons, "Enable browser reader", self.enable_reader)
        self.key = self.button(buttons, "Copy pairing key", self.copy_key)
        pair.addLayout(buttons)

        finish = self.step(layout, "3. Open a board",
                           "Reload the chess tab. In BoardLens, select Live screen. Use the browser toolbar menu to enable Coach.")
        self.status = QLabel()
        self.status.setWordWrap(True)
        finish.addWidget(self.status)
        layout.addStretch()
        self.feedback = QLabel()
        self.feedback.setWordWrap(True)
        layout.addWidget(self.feedback)
        self.button(layout, "Done", self.accept)
        self.timer = QTimer(self, interval=350)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()
        self.refresh()

    @staticmethod
    def explain(layout, text):
        detail = QLabel(text)
        detail.setWordWrap(True)
        layout.addWidget(detail)

    def step(self, layout, title, text):
        card = QWidget()
        card.setObjectName("browserSetupStep")
        body = QVBoxLayout(card)
        body.setContentsMargins(14, 10, 14, 12)
        heading = QLabel(title)
        heading.setObjectName("browserSetupHeading")
        body.addWidget(heading)
        self.explain(body, text)
        layout.addWidget(card)
        return body

    @staticmethod
    def button(layout, text, action):
        button = QPushButton(text)
        button.clicked.connect(action)
        layout.addWidget(button)
        return button

    def refresh(self):
        reader = self.window.browser_reader
        self.enable.setEnabled(reader is None)
        self.key.setEnabled(reader is not None)
        self.status.setText(reader.connection_status() if reader else "Browser reader is off")

    def download_extension(self):
        destination, _ = QFileDialog.getSaveFileName(
            self, "Save Browser Reader ZIP", "BoardLens-BrowserReader.zip", "ZIP archives (*.zip)"
        )
        if not destination:
            return
        try:
            with BytesIO() as archive:
                write_archive(archive)
                payload = archive.getvalue()
            output = QSaveFile(destination)
            if not output.open(QSaveFile.OpenModeFlag.WriteOnly):
                raise OSError(output.errorString())
            if output.write(payload) != len(payload) or not output.commit():
                raise OSError(output.errorString())
        except OSError as error:
            self.feedback.setText(f"Could not save Browser Reader: {error}")
            return
        self.feedback.setText("ZIP saved. Extract it, then select BrowserReader in Load unpacked.")

    def enable_reader(self):
        self.window.browser_reader_button.setChecked(True)
        if self.window.browser_reader is None:
            self.feedback.setText("Could not enable the reader. Quit other copies of BoardLens and try again.")
        self.refresh()

    def copy_key(self):
        if self.window.browser_reader:
            self.window.copy_text(self.window.browser_reader.token)
            self.feedback.setText("Pairing key copied to clipboard.")
