"""Opt-in autoplay for desktop practice boards."""
from dataclasses import dataclass
from math import ceil
import os,time
from pathlib import Path
import chess
from PySide6.QtCore import QObject,QTimer,Qt
from PySide6.QtWidgets import QHBoxLayout,QLabel,QComboBox,QSpinBox,QPushButton,QApplication,QWidget


def enabled():
    return os.environ.get('BOARDLENS_AUTOPLAY_LAB')=='1' or (Path(__file__).resolve().parents[1]/'AUTOPLAY-TEST').is_file()


@dataclass(frozen=True)
class PendingMove:
    command_id: str
    root: str
    expected: str
    deadline: float


class AutoplayTest(QObject):
    def __init__(self,window):
        super().__init__(window);self.w=window;self.active=False;self.color=None;self.candidate=None;self.due=0.;self.sent=set();self.awaiting=None;self.target=None;self.reader=None;self.last_ply=None;self.retried_root=None
        self.finished_fen = None
        self.target_kind = None
        self.controls=QWidget()
        row=QHBoxLayout(self.controls);row.setContentsMargins(0,0,0,0)
        row.addWidget(QLabel('Autoplay'))
        self.side=QComboBox();self.side.addItems(['My color','White','Black']);row.addWidget(self.side)
        row.addWidget(QLabel('Delay'))
        self.delay=QSpinBox();self.delay.setRange(0,10000);self.delay.setSingleStep(1);self.delay.setSuffix(' ms');self.delay.setValue(int(window.settings.get('autoplay_delay_ms',window.settings.get('lab_delay_ms',100))));self.delay.setToolTip('Extra delay after a confirmed move is ready. Set 0 for no added delay.');row.addWidget(self.delay)
        self.start_button=QPushButton('Start autoplay');self.start_button.clicked.connect(self.start);row.addWidget(self.start_button)
        self.stop_button=QPushButton('Stop autoplay');self.stop_button.setObjectName('stop');self.stop_button.clicked.connect(self.stop);row.addWidget(self.stop_button)
        self.label=QLabel('Off · Practice, Chess.com bots, or Lichess Analysis');self.label.setToolTip('Stop autoplay or use the Stop shortcut in Keys.');row.addWidget(self.label,1)
        window.autoplay_host.layout().addWidget(self.controls)
        self.controls.setVisible(enabled())
        window.autoplay_button.setChecked(enabled())
        window.autoplay_button.toggled.connect(self.controls.setVisible)
        if enabled():window.setWindowTitle('BoardLens · Autoplay Test')
        self.timer=QTimer(self);self.timer.setInterval(16);self.timer.timeout.connect(self.tick)
        self.send_timer=QTimer(self, singleShot=True, timerType=Qt.TimerType.PreciseTimer)
        self.send_timer.timeout.connect(self.tick)
        self.delay.valueChanged.connect(self.delay_changed)
        self.side.currentIndexChanged.connect(lambda _:self.stop())

    def start(self):
        w=self.w
        self.stop()
        if not w.practice and w.source.currentIndex() != 1:
            self.label.setText("Choose Live screen or Practice")
            return
        if not w.practice:
            read=w._last_read
            if not w.browser_reader or not getattr(read,'practice_id',None):
                self.label.setText('Connect the browser reader and open a bot game or Lichess Analysis')
                return
            if getattr(read,'play_protocol',None)!=2:
                self.label.setText('Reload Browser Reader and this chess tab')
                return
            self.reader=w.browser_reader
            self.target=(read.source_id,read.practice_id)
            self.target_kind=getattr(read,'practice_kind',None)
        else:
            self.reader=self.target=None
        assigned_color=(getattr(read,'practice_white',None) if not w.practice else None)
        selected=self.side.currentIndex()
        if assigned_color is not None and selected and assigned_color!=(selected==1):
            self.stop('Choose the color you are playing against the bot')
            return
        self.color=(assigned_color if assigned_color is not None else w.white_bottom) if selected==0 else selected==1
        self.active=True
        self.reset_round()
        self.timer.start()
        w.autoplay_button.setText('Autoplay on')
        if not w.practice and not w._monitoring:w.start_live()
        w.live_button.setChecked(True)
        self.label.setText(f"{'White' if self.color else 'Black'} · waiting for a confirmed move")
        board = w.tracker.board
        if board.turn == self.color and not w.job and not self.matching_result(board.fen()):
            w.suggest(from_poll=True)
        self.tick()

    def matching_result(self, fen):
        result = self.w.result
        if (result and result.get("fen") == fen and result.get("lines")
                and (not result.get("provisional") or result.get("primary_complete"))):
            return result
        return None

    def clear_pending(self):
        self.send_timer.stop()
        self.awaiting=None
        self.candidate=None
        if self.reader and self.target:
            self.reader.clear_autoplay(self.target[0])

    def wake(self):
        if self.active:
            self.send_timer.start(0)

    def delay_changed(self):
        self.w.queue_autosave()
        self.candidate = None
        self.wake()

    def stop(self,reason='Off'):
        self.active=False
        self.timer.stop()
        self.w.autoplay_button.setText('Autoplay')
        self.clear_pending()
        self.reader=self.target=None
        self.target_kind=self.finished_fen=None
        self.label.setText(reason if isinstance(reason,str) else 'Off')

    def fresh_browser_board(self):
        w=self.w;read=w._last_read
        if (self.reader is w.browser_reader and w._monitoring and w._screen_confirmed
                and w._turn_known and read and time.monotonic()-getattr(read,'received_at',0)<.5
                and getattr(read,'practice_id',None) and getattr(read,'play_protocol',None)==2
                and read.exact_fen==w.tracker.board.fen() and not getattr(read,'game_result',None)):
            return read
        return None

    def reset_round(self):
        self.clear_pending()
        self.sent.clear()
        self.last_ply = self.retried_root = self.finished_fen = None

    def wait_for_new_board(self, fen):
        if self.finished_fen != fen:
            self.clear_pending()
            self.finished_fen = fen
        self.label.setText('Game over · waiting for a new board')

    def follow_new_board(self, read, board):
        if (not read.practice_focused or read.source_id != self.target[0]
                or getattr(read,'practice_kind',None) != self.target_kind):
            return False
        new_identity = read.practice_id != self.target[1]
        fresh_start = board.ply() <= 1 and (
            self.finished_fen is not None or (
                self.target_kind == 'computer-bot' and self.last_ply is not None and self.last_ply > 1
            )
        )
        if not (new_identity and (self.finished_fen is not None or board.ply() <= 1) or fresh_start):
            return False
        side = self.side.currentIndex()
        assigned = getattr(read,'practice_white',None)
        if side and assigned is not None and assigned != (side == 1):
            self.label.setText('Paused · new board has a different playing color')
            return False
        self.reset_round()
        self.target = (read.source_id, read.practice_id)
        self.color = (self.w.white_bottom if assigned is None else assigned) if not side else side == 1
        self.label.setText('New board confirmed · autoplay on')
        return True

    def matches_board(self):
        if self.w.practice:
            return self.target is None
        read = self.w._last_read
        return (self.target is not None and getattr(read,'source_id',None) == self.target[0]
                and self.target[1] in (getattr(read,'practice_id',None), getattr(read,'game_identity',None)))

    @staticmethod
    def is_bot_reply(expected_fen, current):
        expected=chess.Board(expected_fen)
        if current.turn==expected.turn or current.ply()!=expected.ply()+1:
            return False
        for move in expected.legal_moves:
            reply=expected.copy(stack=False)
            reply.push(move)
            if reply.fen()==current.fen():
                return True
        return False

    def confirm_pending(self, read, board, fen):
        pending=self.awaiting
        state=self.reader.play_state(self.target[0],pending.command_id)
        if read and (fen==pending.expected or (read.practice_kind=='computer-bot'
                     and self.is_bot_reply(pending.expected,board))):
            self.clear_pending()
            self.retried_root=None
            self.label.setText('Move confirmed')
        elif state=='claimed':
            if read and fen!=pending.root:
                self.stop('The board changed before confirming the move')
            elif time.monotonic()>pending.deadline:
                if not read or not read.practice_focused:
                    self.label.setText('Paused · waiting to confirm the last move')
                elif self.retried_root==pending.root:
                    self.stop('No move confirmed · start again')
                else:
                    # The old authorization has expired, and a fresh read still shows its root.
                    self.retried_root=pending.root
                    self.clear_pending()
                    self.label.setText('Board confirmed · retrying the move')
        elif state=='expired' or not read or not read.practice_focused or fen!=pending.root:
            # No move permission was granted. A fresh read can safely offer again.
            self.clear_pending()

    def tick(self):
        if not self.active:return
        w=self.w;board=w.tracker.board;fen=board.fen()
        if self.matches_board() and (board.is_game_over() or w.game_ended):
            self.wait_for_new_board(fen)
            return
        if not w.practice and self.reader is not w.browser_reader:
            self.stop('Browser target changed · start again')
            return
        read=self.fresh_browser_board() if not w.practice and not w._reviewing else None
        if read and (self.finished_fen is not None or (read.source_id,read.practice_id)!=self.target
                     or self.last_ply is not None and board.ply()<self.last_ply):
            if not self.follow_new_board(read, board):
                read = None
        if self.finished_fen is not None:
            return
        if read:
            if self.last_ply is not None and board.ply()<self.last_ply:
                self.stop('Board moved backward · start again')
                return
            self.last_ply=board.ply()
        if self.awaiting:
            self.confirm_pending(read,board,fen)
            return
        board_page = w.workspace_stack.currentIndex() in (0, 1)
        if w._reviewing or (w.practice and not board_page) or (
            not w.practice and (not read or not read.practice_focused)
        ):
            self.candidate=None
            self.label.setText('Paused · return to the selected board')
            return
        if w.closing or w._reviewing or QApplication.activeModalWidget() or board.turn!=self.color:
            self.candidate=None
            return
        result=self.matching_result(fen)
        if result is None:
            return
        shown=w.displayed_result(result) or result
        move=chess.Move.from_uci(shown['lines'][0]['move'])
        if move not in board.legal_moves or fen in self.sent:
            return
        # Only a completed root result can be offered for play.
        key=(fen,move.uci(),w.white_bottom,w.region)
        if self.candidate!=key:
            self.candidate=key
            self.due=time.monotonic()+self.delay.value()/1000
        remaining = self.due - time.monotonic()
        if remaining > 0:
            if not self.send_timer.isActive():
                self.send_timer.start(max(1, ceil(remaining * 1000)))
            return
        self.send_timer.stop()
        try:
            if w.practice:
                self.sent.add(fen);board.push(move);w.invalidate(preserve_eval=True)
                w.refresh_board();w.suggest(from_poll=True);self.candidate=None
                self.label.setText(f'Played {move.uci()} · waiting for your turn')
            else:
                expected=board.copy(stack=False)
                expected.push(move)
                command_id=self.reader.offer_autoplay(read,move)
                if command_id:
                    self.awaiting=PendingMove(command_id,fen,expected.fen(),time.monotonic()+2.)
                    self.label.setText(f'Queued {move.uci()} · waiting for board')
        except Exception as exc:
            self.stop('Input failed: '+str(exc))
