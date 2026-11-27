"""A single vision worker with cancellation tokens; no detection on Qt's thread."""
from __future__ import annotations

import queue
import threading
from collections import OrderedDict
from copy import copy
from hashlib import blake2b
import cv2

from PySide6.QtCore import QObject, Signal

from .recognition import Recognizer, ReadQuality, board_overlap
from .vision import Detection


class TrackedReads:
    """Cache just the latest frame and clean reference for each tracked region."""

    def __init__(self, recognizer):
        self.recognizer = recognizer
        self.entries = OrderedDict()
        self.bytes = 0

    @staticmethod
    def pixels(image):
        size = min(image.shape[:2] + (256,))
        return cv2.resize(image, (size, size), interpolation=cv2.INTER_AREA)

    def read(self, key, detection, image, discovered=None):
        identity = (key, detection.x, detection.y, detection.size)
        pixels = self.pixels(image)
        digest = blake2b(pixels, digest_size=16).digest()
        old_digest, cached, reference = self.entries.pop(identity, (None, None, None))
        if reference is not None:
            self.bytes -= reference.image.nbytes
        if discovered is not None:
            current = reference = copy(discovered)
        elif old_digest == digest:
            current = cached
        else:
            current, reference = self.recognizer.read_tracked(image, reference)
        if reference is not None:
            reference = copy(reference)
            reference.image = self.pixels(reference.image) if reference.image is not image else pixels
            self.bytes += reference.image.nbytes
        if current is not None:
            current = copy(current)
            current.image = image
            current.detection = detection
        saved = copy(current)
        if saved is not None:
            saved.image = pixels
        self.entries[identity] = (digest, saved, reference)
        self.bytes += pixels.nbytes if saved is not None else 0
        self.bytes -= cached.image.nbytes if cached is not None else 0
        while self.bytes > 48 * 1024 * 1024:
            _, (_, read, clean) = self.entries.popitem(last=False)
            self.bytes -= sum(item.image.nbytes for item in (read, clean) if item is not None)
        return current


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
        self.supplement=None
        self.observer=None
        self.thread = threading.Thread(target=self._run, daemon=True, name="BoardLens-vision")
        self.thread.start()

    def submit(self, token, frames, regions=(), quality=ReadQuality()):
        if self.closed:
            return
        self.cancel()
        event = threading.Event()
        self.cancelled = event
        self.queue.put_nowait((token, frames, regions, quality, event))

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
        tracked_reads = TrackedReads(recognizer)
        while True:
            task = self.queue.get()
            if task is None:
                return
            token, frames, regions, quality, event = task
            if recognizer.quality != quality:
                recognizer.quality = quality
                tracked_reads = TrackedReads(recognizer)
            try:
                direct=self.provider() if self.provider else []
                if direct or direct == ():
                    if not event.is_set():
                        if direct and self.supplement is not None:
                            direct = [*direct, *self.supplement()]
                        self.signals.completed.emit(token, direct, "")
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
                        read = tracked_reads.read(key, Detection(x, y, size, 1.), image)
                        reads=[read] if read else []
                    else:
                        reads=recognizer.scan_all(image,event)
                        height,width=image.shape[:2]
                        for read in reads:
                            tracked_reads.read(key, read.detection, read.image, discovered=read)
                        for region in regions:
                            if (region.screen_name != key or event.is_set()
                                    or (width,height) != (region.screen_width,region.screen_height)):
                                continue
                            d = Detection(region.x, region.y, region.size, 1.)
                            if any(board_overlap(d, other.detection) > .35 for other in reads):
                                continue
                            crop = region.crop(image)
                            if crop.shape[:2] != (region.size, region.size):
                                continue
                            read = tracked_reads.read(key, d, crop)
                            if read is not None:
                                reads.append(read)
                    for read in reads:
                        answers.append((key,name,read,width,height))
                if not event.is_set():
                    if self.supplement is not None:
                        answers.extend(self.supplement())
                    answer=answers[0] if len(answers)==1 else answers or None
                    self.signals.completed.emit(token,answer,"")
            except Exception as exc:
                if not event.is_set():
                    self.signals.completed.emit(token, None, str(exc))
