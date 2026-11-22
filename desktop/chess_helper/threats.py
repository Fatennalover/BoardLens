"""Legal-capture threat estimates, separate from engine move recommendations."""
from collections import Counter, OrderedDict
from functools import lru_cache
import logging
from threading import Thread
from time import monotonic

from PySide6.QtCore import QObject, QTimer, Signal
import chess
DEFAULT_COLORS = {"attack": "#ff8c73", "hanging": "#ff7185", "multiple": "#ffc460", "mate": "#c89bff"}

VALUES={chess.PAWN:100,chess.KNIGHT:320,chess.BISHOP:330,chess.ROOK:500,chess.QUEEN:900,chess.KING:20000}


def exchange_gain(board,square,depth=6,_budget=None):
    if _budget is None:_budget=[256]
    _budget[0]-=1
    if depth<=0 or _budget[0]<0:return 0
    best=0
    for move in board.generate_legal_captures(to_mask=chess.BB_SQUARES[square]):
        target=board.piece_at(square)
        if target is None or target.piece_type==chess.KING:continue
        gain=VALUES[target.piece_type]+(VALUES[move.promotion]-100 if move.promotion else 0)
        probe=board.copy(stack=False);probe.push(move)
        best=max(best,gain-exchange_gain(probe,square,depth-1,_budget))
    return best


@lru_cache(maxsize=48)
def analyze(fen):
    board=chess.Board(fen);hanging=[];mates=[]
    if not board.is_valid():return {'hanging':[],'mates':[],'attacks':{True:{},False:{}}}
    for square,piece in board.piece_map().items():
        if piece.piece_type==chess.KING or not board.is_attacked_by(not piece.color,square):continue
        probe=board.copy(stack=False)
        if probe.turn==piece.color:probe.turn=not piece.color;probe.ep_square=None
        gain=exchange_gain(probe,square)
        if gain > 0:
            attackers = {move.from_square for move in
                         probe.generate_legal_captures(to_mask=chess.BB_SQUARES[square])}
            sources = ', '.join(chess.square_name(origin) for origin in sorted(attackers))
            hanging.append({'square':square,'color':piece.color,'piece':chess.piece_name(piece.piece_type),
                            'loss':gain,'multiple':len(attackers)>1,
                            'text':f"{'White' if piece.color else 'Black'} {chess.piece_name(piece.piece_type)} on "
                                   f"{chess.square_name(square)} could lose material. Capture from {sources}."})
    if not board.is_game_over():
        for move in board.legal_moves:
            probe=board.copy(stack=False);probe.push(move)
            if probe.is_checkmate():mates.append({'move':move.uci(),'square':move.to_square,'color':board.turn,'text':f"{'White' if board.turn else 'Black'} has mate in one: {board.san(move)}."})
    attacks = {True: Counter(), False: Counter()}
    for square, piece in board.piece_map().items():
        attacks[piece.color].update(board.attacks(square))
    return {"hanging": sorted(hanging, key=lambda item: item["loss"], reverse=True),
            "mates": mates, "attacks": attacks}


def presentation(board, bottom, enabled=False, attacked=False, mates=True, *, colors=None, report=None):
    if not enabled:
        return [], []
    if report is None:
        report = analyze(board.fen())
    colors = colors or DEFAULT_COLORS
    marks = {}
    messages = []
    if attacked:
        for square, count in report["attacks"][not bottom].items():
            marks[square] = dict(square=square, color=colors["multiple" if count > 1 else "attack"],
                                 kind="attack")
    for item in report["hanging"]:
        square = item["square"]
        marks[square] = dict(square=square, color=colors["multiple" if item["multiple"] else "hanging"],
                             kind="hanging")
        messages.append(item["text"])
    if mates:
        for item in report["mates"]:
            square = item["square"]
            marks[square] = dict(square=square, color=colors["mate"], kind="mate")
            messages.append(item["text"])
    return list(marks.values()), messages


class ThreatUpdates(QObject):
    """Analyze at most one position at a time and keep only the newest waiting boards."""

    completed = Signal(str, object)
    changed = Signal(str)

    def __init__(self, parent):
        super().__init__(parent)
        self.pending = OrderedDict()
        self.cache = OrderedDict()
        self.running = None
        self.last_started = 0.0
        self.interval = .15
        self.closed = False
        self.timer = QTimer(self, singleShot=True)
        self.timer.timeout.connect(self.start)
        self.completed.connect(self.finish)

    def request(self, fen, interval_ms):
        if fen in self.cache:
            self.cache.move_to_end(fen)
            return self.cache[fen]
        if self.closed or self.running == fen:
            return None
        self.interval = interval_ms / 1000
        self.pending[fen] = None
        self.pending.move_to_end(fen)
        if len(self.pending) > 3:
            self.pending.popitem(last=False)
        self.schedule()
        return None

    def schedule(self):
        if not self.closed and self.running is None and self.pending and not self.timer.isActive():
            remaining = self.interval - (monotonic() - self.last_started)
            self.timer.start(max(0, round(1000 * remaining)))

    def start(self):
        if self.closed or not self.pending:
            return
        fen, _ = self.pending.popitem(last=False)
        self.running = fen
        self.last_started = monotonic()

        def work():
            try:
                report = analyze(fen)
            except Exception:
                logging.getLogger(__name__).exception("Could not calculate threat highlights")
                report = {"hanging": [], "mates": [], "attacks": {True: {}, False: {}}}
            if not self.closed:
                try:
                    self.completed.emit(fen, report)
                except RuntimeError:
                    pass

        Thread(target=work, daemon=True, name="BoardLens-threats").start()

    def finish(self, fen, report):
        if self.closed:
            return
        self.running = None
        self.cache[fen] = report
        if len(self.cache) > 48:
            self.cache.popitem(last=False)
        self.changed.emit(fen)
        self.schedule()

    def discard_pending(self):
        self.timer.stop()
        self.pending.clear()

    def close(self):
        self.closed = True
        self.discard_pending()
