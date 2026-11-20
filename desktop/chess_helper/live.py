"""A single vision worker with cancellation tokens; no detection on Qt's thread."""
from __future__ import annotations

import queue
import threading
from collections import OrderedDict
from copy import copy
import cv2

from PySide6.QtCore import QObject, Signal

from .recognition import Recognizer
from .vision import Detection, complete_grid


class LiveSignals(QObject):
    completed = Signal(int, object, str)


class LiveWorker:
    def __init__(self, parent=None):
        self.signals = LiveSignals(parent)
        self.queue = queue.Queue(maxsize=1)
        self.cancelled = threading.Event()
        self.cancelled.set()
        self.closed = False
        self.provider=None
        self.observer=None
        self.thread = threading.Thread(target=self._run, daemon=True, name="BoardLens-vision")
        self.thread.start()

    def submit(self, token, frames, hint=None):
        if self.closed:
            return
        self.cancel()
        event = threading.Event()
        self.cancelled = event
        self.queue.put_nowait((token, frames, hint, event))

    def cancel(self):
        self.cancelled.set()
        try:
            self.queue.get_nowait()
        except queue.Empty:
            pass

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.cancel()
        self.queue.put_nowait(None)

    def _run(self):
        recognizer = Recognizer()
        tracked_reads = OrderedDict()
        while True:
            task = self.queue.get()
            if task is None:
                return
            token, frames, hint, event = task
            try:
                direct=self.provider() if self.provider else []
                if direct or direct == ():
                    if not event.is_set():self.signals.completed.emit(token,direct,"")
                    continue
                if callable(frames):
                    frames=frames(event)
                answers = []
                for frame in frames:
                    key,name,image=frame[:3]
                    if self.observer:self.observer(frame)
                    if event.is_set():
                        break
                    if len(frame)==4:
                        x,y,size,width,height=frame[3]
                        # Unchanged tracked boards come back without re-running ONNX.
                        # Keep high-frequency square detail so a flip or a changed piece
                        # cannot reuse the previous orientation or placement.
                        pixels=cv2.resize(image,(min(size,256),min(size,256)),interpolation=cv2.INTER_AREA)
                        signature=(key,x,y,size,pixels.tobytes())
                        if signature in tracked_reads:
                            read=copy(tracked_reads[signature])
                        else:
                            read=recognizer.read(image) if complete_grid(image) else None
                            if read and not read.reliable:read=None
                            if read:read.detection=Detection(x,y,size,1.)
                            tracked_reads[signature]=copy(read)
                            if len(tracked_reads)>8:tracked_reads.popitem(last=False)
                        reads=[read] if read else []
                    else:
                        reads=recognizer.scan_all(image,event)
                        height,width=image.shape[:2]
                    for read in reads:
                        answers.append((key,name,read,width,height))
                if not event.is_set():
                    answer=answers[0] if len(answers)==1 else answers or None
                    self.signals.completed.emit(token,answer,"")
            except Exception as exc:
                if not event.is_set():
                    self.signals.completed.emit(token, None, str(exc))
