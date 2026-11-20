"""Check real Windows window clicks and verify they leave the cursor in place."""
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QHBoxLayout, QPushButton, QWidget

from chess_helper.controls import ClickMove


def fixture(folder):
    app=QApplication([])
    window=QWidget()
    window.setWindowTitle('BoardLens offline input test')
    window.setGeometry(120,160,300,100)
    layout=QHBoxLayout(window)

    def clicked(name):
        with (folder/'clicks.txt').open('a') as record:
            record.write(name+'\n')

    buttons=[QPushButton(name) for name in ('source','destination')]
    for button in buttons:
        layout.addWidget(button)
        button.clicked.connect(lambda checked,name=button.text():clicked(name))
    window.show()
    window.raise_()

    def coordinates():
        points=[button.mapToGlobal(button.rect().center()) for button in buttons]
        (folder/'points.json').write_text(json.dumps([(point.x(),point.y()) for point in points]))

    QTimer.singleShot(500,coordinates)
    QTimer.singleShot(15000,app.quit)
    return app.exec()


def position():
    point=wintypes.POINT()
    if not ctypes.windll.user32.GetCursorPos(ctypes.byref(point)):
        raise OSError('Could not read Windows cursor location.')
    return point.x,point.y


def verify(folder):
    env=dict(os.environ,PYTHONPATH=str(Path(__file__).resolve().parents[1]))
    child=subprocess.Popen([sys.executable,__file__,str(folder)],env=env)
    try:
        for _ in range(80):
            if (folder/'points.json').exists():break
            time.sleep(.1)
        source,destination=json.loads((folder/'points.json').read_text())
        app=QApplication([])
        clicker=ClickMove()
        errors=[]
        clicker.failed.connect(errors.append)
        clicker.done.connect(lambda:QTimer.singleShot(300,app.quit))
        QTimer.singleShot(1500,app.quit)
        before=position()
        clicker.start(source,destination)
        app.exec()
        assert not errors,errors
        assert (folder/'clicks.txt').read_text().splitlines()==['source','destination']
        assert before==position()
        print('Two real Windows clicks reached the test app without moving the cursor.')
    finally:
        child.terminate()
        child.wait(timeout=5)


if __name__=='__main__':
    if len(sys.argv)>1:
        raise SystemExit(fixture(Path(sys.argv[1])))
    with tempfile.TemporaryDirectory(prefix='boardlens-cursor-test-') as temp:
        verify(Path(temp))
