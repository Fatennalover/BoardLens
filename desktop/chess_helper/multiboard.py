"""Independent positions, searches and passive overlays for additional boards."""
from __future__ import annotations
from collections import OrderedDict
from concurrent.futures import Future, ThreadPoolExecutor
from copy import deepcopy
from dataclasses import replace
import os
import threading
import time
import chess
from PySide6.QtCore import QObject,Signal,Qt,QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QLabel,QGridLayout,QComboBox,
    QPushButton,QDialog,QDialogButtonBox,QFormLayout,QDoubleSpinBox,QSpinBox,QScrollArea)
from . import engine_config, engine_library
from .capture import BoardRegion,screen_key
from .core import MAX_LOOKAHEAD_PLIES, PositionTracker,ordered_symbols
from .engine import EngineJob,EngineSession
from .hints import LiveHintFilter, merge_locked_suggestions
from .overlay import BoardOverlay
from .eval_overlay import EvaluationOverlay
from .recognition import position_from_read
from .studio import ArrowColorButton
from .widgets import BoardView,EvalBar,BoardArea


def near(a,b):
    if a.screen_name!=b.screen_name:return False
    dx=(a.x+a.size/2)-(b.x+b.size/2);dy=(a.y+a.size/2)-(b.y+b.size/2)
    return dx*dx+dy*dy < (max(a.size,b.size)*.55)**2


def region_of(answer):
    key,_,read,width,height=answer;d=read.detection
    return BoardRegion(key,width,height,d.x,d.y,d.size)


class BoardSearches(QObject):
    available = Signal()

    def __init__(self, workers):
        super().__init__()
        self.capacity = max(1,os.cpu_count() or 1)
        self.executor = ThreadPoolExecutor(max_workers=self.capacity, thread_name_prefix='BoardLens-board')
        self.workers = workers
        self.active = 0
        self.pending = OrderedDict()
        self.available.connect(self.finished)
        self.local = threading.local()
        self.lock = threading.Lock()
        self.sessions = []
        self.cache = OrderedDict()
        self.closed = False

    def submit(self, work, priority):
        ticket = Future()
        self.pending[ticket] = (time.monotonic(),priority,work)
        self.pump()
        return ticket

    def pump(self):
        for ticket in list(self.pending):
            if ticket.cancelled():
                self.pending.pop(ticket)
        while self.pending and not self.closed and self.active < self.workers:
            # Waiting long enough eventually beats a newer, high-priority request.
            ticket = max(self.pending, key=lambda item:self.pending[item][1]-self.pending[item][0])
            _,_,work = self.pending.pop(ticket)
            if ticket.set_running_or_notify_cancel():
                self.active += 1
                self.executor.submit(self.execute,ticket,work)

    def execute(self, ticket, work):
        try:
            work()
        finally:
            ticket.set_result(None)
            self.available.emit()

    def finished(self):
        self.active -= 1
        self.pump()

    def run(self, job, path, board, settings):
        key = (tuple(path) if isinstance(path, list) else path, board.root().fen(),
               tuple(move.uci() for move in board.move_stack), board.fen(), settings)
        with self.lock:
            if self.closed or job.cancelled.is_set():
                return None
            if key in self.cache:
                self.cache.move_to_end(key)
                return deepcopy(self.cache[key])
            if not hasattr(self.local, 'session'):
                self.local.session = EngineSession()
                self.sessions.append(self.local.session)
            job.session = self.local.session
        result = job.run(path, board, settings)
        if result and not job.cancelled.is_set():
            with self.lock:
                self.cache[key] = deepcopy(result)
                self.cache.move_to_end(key)
                if len(self.cache) > 128:
                    self.cache.popitem(last=False)
        return result

    def close(self):
        with self.lock:
            self.closed = True
            for session in self.sessions:
                session.close()
        self.executor.shutdown(wait=False, cancel_futures=True)
        for ticket in self.pending:
            ticket.cancel()
        self.pending.clear()


class BoardPage(QWidget):
    resized=Signal()
    def resizeEvent(self,event):
        super().resizeEvent(event)
        QTimer.singleShot(0,self.resized.emit)


class BoardCard(QWidget):
    def __init__(self,parent=None):
        super().__init__(parent)
        self.setObjectName('boardCard')
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground,True)
        layout=QVBoxLayout(self);layout.setContentsMargins(12,10,12,10);layout.setSpacing(5)
        self.title=QLabel();self.title.setStyleSheet('font-size:15px;font-weight:600;color:#d0bafa;')
        self.state=QLabel('Reading board…');self.state.setWordWrap(True)
        layout.addWidget(self.title);layout.addWidget(self.state)
        self.bar=EvalBar();self.bar.setFixedWidth(54)
        self.bar.score_label.setStyleSheet("background:#493960;color:white;border-radius:5px;font-size:12px;font-weight:700;padding:0;")
        self.view=BoardView();self.view.setStyleSheet('background:transparent;')
        self.view.setToolTip('Recognized live position. Play moves on the original board.')
        self.board_holder=BoardArea(self.view,self.bar)
        self.board_holder.setMinimumSize(180,160)
        layout.addWidget(self.board_holder)
        self.move=QLabel('Waiting for analysis');self.move.setWordWrap(True)
        self.score=QLabel('Evaluation —');self.score.setWordWrap(True)
        layout.addWidget(self.move);layout.addWidget(self.score)
        self.turn=QComboBox();self.turn.addItems(['Auto turn','White to move','Black to move'])
        self.turn.setToolTip('Use if joining a static position without a turn clue. Each board tracks its own moves.')
        layout.addWidget(self.turn)
        controls = QHBoxLayout()
        self.pause = QPushButton('Pause'); self.pause.setCheckable(True)
        self.keep=QPushButton('Keep');self.keep.setCheckable(True)
        self.keep.setToolTip('Keep this board and its settings when it is temporarily out of view.')
        self.options = QPushButton('Search settings…')
        for button in (self.pause,self.keep,self.options):
            controls.addWidget(button)
        layout.addLayout(controls)
        layout.addStretch(1)
        self.setStyleSheet('QWidget#boardCard {background:#1a172a;border:1px solid #403656;border-radius:10px;} QWidget#boardCard QLabel {background:transparent;border:none;}')

    def resizeEvent(self,event):
        super().resizeEvent(event)
        height=max(160,min(self.width()-24,self.height()-215))
        self.board_holder.setFixedHeight(height)


class BoardState:
    def __init__(self,identity,answer):
        self.identity=identity;self.region=region_of(answer);self.name=answer[1]
        self.read=answer[2];self.tracker=None;self.known=False
        self.key=None;self.stable=0;self.confirmed=False;self.misses=0
        self.result=None;self.pinned=None;self.hint_filter=LiveHintFilter();self.job=None;self.generation=0
        self.last_requested=None;self.closed=False;self.future=None
        self.paused=False;self.engine_id=None;self.limits={};self.error='';self.retry_at=0.
        self.priority=0;self.arrow_color=None;self.show_arrows=True;self.confirm_frames=None;self.missing_at=0.
        self.overlay=BoardOverlay();self.eval_overlay=EvaluationOverlay();self.card=BoardCard();self.turn_override=None

    def cancel(self,close=False):
        self.generation+=1
        if self.job:self.job.cancel();self.job=None
        if self.future is not None:self.future.cancel();self.future=None
        self.overlay.hide();self.eval_overlay.hide();self.last_requested=None
        if close:
            self.closed=True;self.overlay.close();self.eval_overlay.close();self.card.deleteLater()


class MultiBoards(QObject):
    updated=Signal(object,int,object,str,bool)

    def __init__(self,window):
        super().__init__(window)
        self.window=window;self.states=[];self.serial=0;self.primary_misses=0
        self.searches = BoardSearches(max(1, min(4, (os.cpu_count() or 2) // 2)))
        self.manual_regions = []
        self.updated.connect(self.finished)
        self.primary_card=BoardCard();self.primary_card.turn.hide()
        self.primary_card.pause.hide();self.primary_card.keep.hide();self.primary_card.options.hide()
        self.page=BoardPage();self.page.resized.connect(self.layout_cards);self.grid=QGridLayout(self.page);self.grid.setContentsMargins(0,0,0,0);self.grid.setSpacing(10)
        self.scroll = QScrollArea();self.scroll.setWidgetResizable(True);self.scroll.setWidget(self.page)
        self.count=0;self._columns=0

    def regions(self):
        regions = ([self.window.region] if self.window.region else [])+[s.region for s in self.states]
        for region in self.manual_regions:
            if not any(near(region,existing) for existing in regions):
                regions.append(region)
        return regions

    def add_region(self, region):
        if region not in self.manual_regions:
            self.manual_regions.append(region)

    def remove_region(self, region):
        self.manual_regions.remove(region)

    def overlays(self):return [self.window.overlay,self.window.screen_eval]+[o for s in self.states for o in (s.overlay,s.eval_overlay)]

    def accept(self,answers):
        w=self.window;remaining=list(answers)
        primary=None
        connector_prefixes = ('browser:', 'native:')
        if remaining and w.region and not w.target_lock.active:
            direct = remaining[0][0].startswith(connector_prefixes)
            if direct != w.region.screen_name.startswith(connector_prefixes):
                # Pixel rectangles and connector IDs are different coordinate spaces.
                w.region = None
                w._stable_key = None
                w._stable_frames = 0
                w._position_locked = False
                w.invalidate(release_move=True)
        if w.region:
            matches=[a for a in remaining if near(w.region,region_of(a))]
            if matches:primary=min(matches,key=lambda a:abs(region_of(a).x-w.region.x)+abs(region_of(a).y-w.region.y))
        elif remaining:primary=remaining[0]
        if primary:
            self.primary_misses=0;remaining=[a for a in remaining if a is not primary]
        else:self.primary_misses+=1
        if primary is None and remaining and self.primary_misses>=3:
            primary=remaining.pop(0);self.primary_misses=0
            w._stable_key=None;w._stable_frames=0;w._position_locked=False
            w.invalidate(release_move=True)
        used=set()
        for answer in remaining:
            region=region_of(answer)
            state=next((s for s in self.states if s.identity not in used and near(s.region,region)),None)
            if state is None:
                self.serial+=1;state=BoardState(self.serial,answer);self.states.append(state)
                state.card.turn.currentIndexChanged.connect(lambda index,state=state:self.turn_changed(state,index))
                state.card.pause.toggled.connect(lambda paused,state=state:self.pause_changed(state,paused))
                state.card.options.clicked.connect(lambda checked=False,state=state:self.change_settings(state))
            used.add(state.identity);self.observe(state,answer)
        for state in list(self.states):
            if primary and near(state.region,region_of(primary)):
                state.cancel(close=True);self.states.remove(state);continue
            if state.identity not in used:
                state.misses+=1;state.confirmed=False
                if state.misses==1:
                    state.missing_at=time.monotonic()
                reconnecting=getattr(state.read,'background_capable',False) and time.monotonic()-state.missing_at<8.
                if state.misses>=3 and not state.card.keep.isChecked() and not reconnecting:
                    state.cancel(close=True);self.states.remove(state)
                else:self.render(state)
        self.count=(1 if primary or (w.region and self.primary_misses<3) else 0)+len(self.states)
        self.layout_cards()
        w.refresh_targets()
        return primary

    def observe(self,state,answer):
        previous_region=state.region;was_confirmed=state.confirmed
        state.region=region_of(answer);state.name=answer[1];read=answer[2];state.misses=0
        previous_id = getattr(state.read, 'game_identity', None)
        game_id = getattr(read, 'game_identity', None)
        if previous_id and game_id and previous_id != game_id:
            state.cancel()
            state.tracker = None
            state.result = state.pinned = None
            state.hint_filter.reset()
        key=(getattr(read,'game_identity',None),tuple(read.symbols),read.white_bottom,getattr(read,'exact_fen',None))
        if (was_confirmed and key==state.key and state.region==previous_region and state.tracker is not None
                and all(getattr(state.read,field,None)==getattr(read,field,None)
                        for field in ('desktop_rect','points','move_history','game_result'))):
            state.read=read
            if state.last_requested is None and state.job is None and state.known and not state.paused:
                if not state.tracker.board.is_game_over():
                    self.search(state)
                    self.render(state)
            return
        if key!=state.key:
            state.key=key;state.stable=0
        state.stable+=1;state.read=read
        needed = state.confirm_frames or self.window.screen_settings.frames.value()
        state.confirmed = bool(getattr(read,'exact_fen',None) or state.stable >= needed)
        if not state.confirmed:
            state.overlay.hide();self.render(state);return
        try:
            if getattr(read, 'exact_fen', None):
                if state.tracker is None:
                    state.tracker = PositionTracker(chess.Board(read.exact_fen))
                history = getattr(read, 'move_history', None)
                if state.tracker.board.fen() != read.exact_fen or (history and state.tracker.board.move_stack != history.move_stack):
                    state.tracker.update_exact(chess.Board(read.exact_fen), history)
                state.known = True
            elif state.tracker is None:
                board,state.known=position_from_read(read,state.turn_override);state.tracker=PositionTracker(board)
            else:
                matches=[]
                for bottom in (True,False):
                    probe=PositionTracker(state.tracker.board)
                    status,_=probe.update(read.symbols,bottom)
                    if status=='unmatched':status,_=probe.reconcile(read.symbols,bottom)
                    if status!='unmatched':matches.append(bottom)
                if len(matches)==1:read.white_bottom=matches[0]
                status,_=state.tracker.update(read.symbols,read.white_bottom)
                if status=='unmatched':status,_=state.tracker.reconcile(read.symbols,read.white_bottom)
                if status=='unmatched':
                    board,state.known=position_from_read(read,state.turn_override,state.tracker.board)
                    state.tracker=PositionTracker(board)
                elif status=='moved':state.known=True
            fen=state.tracker.board.fen()
            if (state.last_requested and state.last_requested!=fen) or (state.result and state.result['fen']!=fen):
                state.cancel();state.result=None;state.pinned=None;state.hint_filter.reset()
            if state.pinned and state.pinned['fen']!=fen:state.pinned=None
            if state.last_requested!=fen and state.job is None and not state.tracker.board.is_game_over():self.search(state)
        except ValueError:state.confirmed=False
        self.render(state)

    def search(self,state):
        w=self.window
        if not w._monitoring or w._reviewing or state.closed or state.paused or not state.known or time.monotonic()<state.retry_at:return
        try:
            settings = replace(w.search_settings(), **state.limits)
            if state.engine_id is None:
                path=w.analysis_command()
            else:
                entry = engine_library.BY_ID[state.engine_id]
                path = engine_config.command(w, engine_library.ENTRIES.index(entry))
                settings = replace(settings, engine_id=entry.identity,
                    engine_kind=entry.identity if entry.kind=='tiny' else entry.kind,
                    strength='Full strength', style='Balanced', multipv=1 if entry.kind=='tiny' else settings.multipv)
        except ValueError as exc:
            state.error = str(exc)
            state.retry_at = time.monotonic() + 1.
            return
        board=state.tracker.board.copy();w.evaluations.request(board)
        state.generation+=1;generation=state.generation
        state.last_requested=board.fen();job=state.job=EngineJob();state.error=''
        job.on_update=lambda result:self.updated.emit(state,generation,result,'',True)
        def work():
            try:result,error=self.searches.run(job,path,board,settings),''
            except Exception as exc:result,error=None,str(exc)
            if not w.closing:self.updated.emit(state,generation,result,error,False)
        state.future = self.searches.submit(work,state.priority)

    def finished(self,state,generation,result,error,provisional):
        if state.closed or self.window.closing or generation!=state.generation:return
        if provisional and not self.window.early_suggestions.isChecked() and not (result or {}).get('primary_complete'):return
        if not provisional:state.job=None;state.future=None
        if error:
            state.error=error;state.last_requested=None;state.retry_at=time.monotonic()+1.
            self.render(state);return
        if not result or state.tracker is None or result['fen']!=state.tracker.board.fen():return
        state.result=dict(result,provisional=provisional)
        self.render(state)

    def render(self,state):
        w=self.window;card=state.card
        index=self.states.index(state)+2 if state in self.states else 2
        card.title.setText(f'Board {index}')
        if state.tracker is None:
            card.state.setText('Confirming position…');card.view.hide();card.bar.hide();return
        card.view.show();card.bar.show()
        board=state.tracker.board;bottom=state.read.white_bottom
        card.view.board=board.copy();card.view.white_bottom=bottom
        card.bar.white_bottom=bottom
        text=f"{'White' if board.turn else 'Black'} to move · {'White' if bottom else 'Black'} bottom"
        if not state.known:text='Choose White or Black to confirm the turn'
        if state.paused:text+=' · paused'
        if state.misses:text+=' · unavailable'
        elif not state.confirmed:text+=' · checking board'
        if state.error:text+=' · '+state.error
        card.state.setText(text)
        raw=state.result if not state.paused else None
        if not w.stick_to_move.isChecked():state.pinned=None
        elif state.pinned is None and raw:
            previous=state.hint_filter.displayed
            state.pinned=deepcopy(previous if previous and previous['fen']==board.fen() else raw)
        shown=state.pinned if w.stick_to_move.isChecked() else state.hint_filter.select(raw,w.steady_arrows.isChecked())
        if state.pinned and raw:
            merge_locked_suggestions(state.pinned, raw, state.limits.get('multipv', w.multipv.value()))
        arrows=[]
        current=(board.turn==bottom) if w.only_my_color.isChecked() else (w.show_white.isChecked() if board.turn else w.show_black.isChecked())
        other=not w.only_my_color.isChecked() and (w.show_black.isChecked() if board.turn else w.show_white.isChecked())
        if shown and shown['fen']==board.fen():
            lead=shown['lines'][0];locked=w.stick_to_move.isChecked()
            card.move.setText(lead['simple']+(' · locked' if locked else '') if current else 'Waiting for your turn' if w.only_my_color.isChecked() else 'Suggestions hidden')
            for rank,line in enumerate(shown['lines'][:min(w.arrow_count.value(),w.multipv.value())],1):
                if current and w.visible_rank(rank):arrows.append({'move':chess.Move.from_uci(line['move']),
                    'color':state.arrow_color if state.arrow_color and rank==1 else w.recommendation_color(rank)})
            continuation = []
            if current and w.rank_best.isChecked() and state.limits.get(
                    'predict_continuations', w.predict_continuations.isChecked()):
                count = state.limits.get('prediction_plies', w.prediction_plies.value())
                continuation = w.add_lookahead_arrows(arrows, board, lead.get('pv_moves', []), count)
            if other and w.show_reply.isChecked() and w.rank_best.isChecked() and lead.get('reply_move') and len(continuation) < 2:
                arrows.append({'move':chess.Move.from_uci(lead['reply_move']),'color':'#53e2e4','reply':True,'dashed':w.dashed_reply.isChecked()})
        else:
            queued = state.future is not None and not state.future.running()
            card.move.setText('Paused' if state.paused else 'Queued…' if queued else 'Thinking…' if state.job else 'Waiting for analysis')
        lead=w.evaluations.score(board,raw if state.engine_id is None else None)
        if lead['kind'] != 'pending':
            card.bar.cp,card.bar.mate,card.bar.white_share=lead['cp'],lead['mate'],lead.get('white_share')
            card.score.setText(f"{card.bar.score_text()} · {lead['advantage']}"+(' · thinking' if (raw or {}).get('provisional') else ''))
        if w.screen_eval_enabled.isChecked() and w._monitoring and state.confirmed and not state.paused and not w._reviewing:
            from PySide6.QtCore import QRect
            target=next((screen for screen in QGuiApplication.screens() if screen_key(screen)==state.region.screen_name),None)
            desktop_rect=getattr(state.read,'desktop_rect',None)
            if desktop_rect:
                rect=QRect(*[round(value) for value in desktop_rect])
                target=next((screen for screen in QGuiApplication.screens() if screen.geometry().contains(rect.center())),None)
            elif target:
                rect=state.region.desktop_rect(target.geometry())
            if target and lead['kind'] != 'pending':
                state.eval_overlay.set_score(rect,bottom,card.bar.cp,card.bar.mate,target,card.bar.white_share)
            elif not target:
                state.eval_overlay.hide()
        else:
            state.eval_overlay.hide()
        if not state.show_arrows:
            arrows.clear()
        marks,messages=w.threat_marks(board,bottom);card.view.marks=marks;card.view.setToolTip("\n".join(messages));card.view.arrows=arrows;card.view.update();card.bar.update()
        card.view.overlap_color = state.overlay.overlap_color = w.overlap_color
        if (arrows or marks) and w.overlay_enabled.isChecked() and w._monitoring and state.confirmed and not state.paused and not w._reviewing:
            if getattr(state.read,'desktop_rect',None):
                from PySide6.QtCore import QRect
                rect=QRect(*[round(v) for v in state.read.desktop_rect]);target=next((s for s in QGuiApplication.screens() if s.geometry().contains(rect.center())),w.window_screen());state.overlay.set_arrows(rect,bottom,[dict(a,points=state.read.points) for a in arrows],target,[dict(m,points=state.read.points) for m in marks]);return
            target=next((s for s in QGuiApplication.screens() if screen_key(s)==state.region.screen_name),None)
            if target:state.overlay.set_arrows(state.region.desktop_rect(target.geometry()),bottom,arrows,target,marks)
        else:state.overlay.hide()

    def update_primary(self):
        w=self.window;card=self.primary_card;card.title.setText('Board 1')
        card.state.setText(w.position_label.text());card.view.board=w.tracker.board.copy();card.view.white_bottom=w.white_bottom
        card.view.overlap_color = w.overlap_color
        card.view.arrows=list(w.board_view.arrows);card.view.marks=list(w.board_view.marks);card.view.update()
        card.bar.cp,card.bar.mate=w.eval_bar.cp,w.eval_bar.mate;card.bar.white_share=w.eval_bar.white_share;card.bar.white_bottom=w.white_bottom;card.bar.update()
        card.move.setText(w.simple_label.text());card.score.setText(w.eval_label.text())

    def layout_cards(self):
        w=self.window
        if not hasattr(w,'boards_button'):return
        cards=([self.primary_card] if self.count>len(self.states) else [])+[s.card for s in self.states]
        columns=max(1,min(len(cards),self.scroll.viewport().width()//250))
        existing=[self.grid.itemAt(i).widget() for i in range(self.grid.count())]
        if existing!=cards or columns!=self._columns:
            while self.grid.count():self.grid.takeAt(0)
            for index,card in enumerate(cards):self.grid.addWidget(card,index//columns,index%columns)
            self._columns=columns
        self.update_primary()
        previous_count = getattr(self, "_shown_count", 0)
        self._shown_count = self.count
        w.boards_button.setText(f'All boards ({self.count})')
        index = w.workspace_stack.currentIndex()
        if index in (0, 1):
            if self.count <= 1 and index == 1:
                w.workspace_stack.setCurrentIndex(0)
            elif previous_count <= 1 < self.count and not w._compact:
                w.workspace_stack.setCurrentIndex(1)
        w.update_workspace_navigation(w.workspace_stack.currentIndex())

    def repaint(self):
        for state in self.states:self.render(state)
        self.update_primary()

    def turn_changed(self,state,index):
        state.turn_override=None if index==0 else index==1
        if state.read:
            try:
                board,state.known=position_from_read(state.read,state.turn_override)
            except ValueError as error:
                state.error=str(error);self.render(state);return
            state.cancel();state.tracker=PositionTracker(board);state.result=None;state.pinned=None
            state.error='';state.retry_at=0.
            if state.confirmed:self.search(state)
        self.render(state)

    def settings_changed(self, release_move=True):
        for state in self.states:
            state.cancel()
            state.result = None
            state.hint_filter.reset()
            if release_move:
                state.pinned = None
            if state.confirmed:self.search(state)
            self.render(state)

    def pause_changed(self,state,paused):
        state.paused=paused
        state.card.pause.setText('Resume' if paused else 'Pause')
        state.cancel()
        state.pinned=None;state.hint_filter.reset()
        if not paused and state.confirmed and state.tracker is not None:self.search(state)
        self.render(state)

    def change_settings(self,state):
        dialog=QDialog(self.window);dialog.setWindowTitle(state.card.title.text()+' search settings')
        form=QFormLayout(dialog)
        engines=QComboBox();engines.addItem('Use main engine',None)
        for entry in engine_library.ENTRIES:
            if engine_library.available(entry) or entry.identity==state.engine_id or entry.kind in ('stockfish','custom'):
                engines.addItem(entry.label,entry.identity)
        engines.setCurrentIndex(max(0,engines.findData(state.engine_id)))
        form.addRow('Analysis engine',engines)
        settings=replace(self.window.search_settings(),**state.limits)
        mode=QComboBox();mode.addItems(['Time','Depth','Time + depth']);mode.setCurrentText(settings.mode)
        form.addRow('Search limit',mode)
        fields={}
        for name,label,minimum,maximum in (('seconds','Calculation time',.05,60.),('depth','Engine depth',1,60),
            ('multipv','Candidate moves',1,5),('prediction_plies','Lookahead (plies)',1,MAX_LOOKAHEAD_PLIES),
            ('prediction_seconds','Lookahead time',.1,60.),('threads','CPU threads',1,self.searches.capacity),
            ('hash_mb','Hash memory',16,4096)):
            field=QDoubleSpinBox() if isinstance(minimum,float) else QSpinBox()
            field.setRange(minimum,maximum);field.setValue(getattr(settings,name));fields[name]=field
            form.addRow(label,field)
        fields['prediction_plies'].setToolTip('Includes the candidate move. One ply is one side’s move.')
        for name in ('seconds','prediction_seconds'):fields[name].setSuffix(' s')
        fields['hash_mb'].setSuffix(' MB')
        priority=QComboBox();priority.addItems(['Low','Normal','High']);priority.setCurrentIndex(state.priority+1)
        form.addRow('Analysis priority',priority)
        stability=QSpinBox();stability.setRange(1,6);stability.setSpecialValueText('Use main setting')
        stability.setValue(state.confirm_frames or 1);form.addRow('Position stability',stability)
        arrows=QComboBox();arrows.addItems(['Show','Hide']);arrows.setCurrentIndex(int(not state.show_arrows));form.addRow('Move arrows',arrows)
        arrow_color=ArrowColorButton(state.arrow_color or self.window.recommendation_color(1),'Lead arrow color')
        form.addRow('Lead arrow color',arrow_color)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel|QDialogButtonBox.StandardButton.Reset)
        buttons.accepted.connect(dialog.accept);buttons.rejected.connect(dialog.reject)
        buttons.button(QDialogButtonBox.StandardButton.Reset).clicked.connect(lambda:dialog.done(2))
        form.addRow(buttons)
        action=dialog.exec()
        if not action or state.closed:return
        state.engine_id=engines.currentData() if action==1 else None
        state.limits={name:field.value() for name,field in fields.items()} if action==1 else {}
        state.priority=priority.currentIndex()-1 if action==1 else 0
        state.confirm_frames=stability.value() if action==1 and stability.value()>1 else None
        state.show_arrows=arrows.currentIndex()==0 if action==1 else True
        state.arrow_color=arrow_color.color if action==1 else None
        if action==1:state.limits.update(mode=mode.currentText(),predict_continuations=fields['prediction_plies'].value()>1)
        state.cancel();state.result=None;state.pinned=None;state.hint_filter.reset();state.error='';state.retry_at=0.
        if state.confirmed and state.tracker is not None:self.search(state)
        self.render(state)

    def stop(self):
        for state in self.states:state.cancel()

    def reset(self,keep_browser=False):
        for state in list(self.states):
            if keep_browser and getattr(state.read,'background_capable',False):continue
            state.cancel(close=True);self.states.remove(state)
        self.primary_misses=0;self.count=len(self.states);self.layout_cards()

    def close(self):
        self.reset()
        self.searches.close()
