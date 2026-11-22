"""Qt-owned companion state and command bridge; no widget access from HTTP."""
from __future__ import annotations
import base64,math,time
from html import escape
from concurrent.futures import Future
from copy import deepcopy
import chess,chess.svg,cv2,numpy as np
from PySide6.QtCore import QObject,QTimer,Signal
from PySide6.QtWidgets import QApplication
from .core import evaluation_text, square_to_cell
from .phone_server import PhoneServer,local_addresses
from .recognition import position_from_read
from .engine_config import configuration
from . import __version__, engine_library, engine_profiles
from .openings import opening_name, played_moves

NUMBERS={'advantage_seconds':'Scoring time (seconds)','advantage_depth':'Scoring depth','advantage_count':'Moves to compare (0 off)','prediction_plies':'Prediction length (plies)','prediction_seconds':'Reply time budget (seconds)','eval_seconds':'Evaluation think time','eval_depth':'Evaluation depth cap','eval_human_elo':'Evaluation human rating','seconds':'Think time (seconds)','depth':'Search depth','multipv':'Recommendation arrows','threads':'CPU threads per board','hash_mb':'Hash memory (MB)','arrow_count':'Arrow candidates','engine_skill':'Stockfish skill (0–20)','engine_elo':'Stockfish Elo','human_elo':'Maia target human rating'}
BOOLEANS={'advantage_gain_arrows':'Gain arrows','browser_eval_enabled':'Browser evaluation','screen_eval_enabled':'Screen evaluation','predict_continuations':'Predict opponent and my next move','only_my_color':'Only my color','stick_to_move':'Stick to one move','overlay_enabled':'Computer screen arrows','arrow_labels':'Arrow rank labels','show_white':'White suggestions','show_black':'Black suggestions','show_reply':'Opponent best reply','rank_best':'Show #1','rank_second':'Show #2','rank_others':'Show #3 and later','early_suggestions':'Show moves while thinking','global_keys':'Global keyboard shortcuts','always_top':'Desktop stays on top','steady_arrows':'Steady arrows · keep calculating','dashed_reply':'Dashed opponent reply arrow (desktop)'}
ENUMS={'advantage_mode':'Scoring search limit','advantage_engine':'Scoring engine','eval_engine':'Evaluation engine','mode':'Engine limit','source':'Board source','orientation':'Board orientation','turn':'Primary board turn','monitor':'Monitor to scan','engine_kind':'Analysis engine · choose manually','strength_mode':'Stockfish strength mode','playing_style':'Playing style','compare_a':'Compare engine A','compare_b':'Compare engine B','compare_c':'Compare engine C'}
ENUMS.update(source='Read from',turn='Side to move',monitor='Display to read')
BOOLEANS.update(auto_updates='Automatic desktop updates',threats_enabled='Threat highlights',threat_attacks='Attacked squares',threat_mates='Mate-in-one targets',lock_target='Lock target board')
PRESET_COMMANDS={'apply_preset','save_preset','delete_preset'}


def gain_svg(gains, bottom):
    """Draw the same outlined gains on the portable SVG board."""
    def point(square):
        row, col = square_to_cell(square, bottom)
        return 15 + (col + .5) * 45, 15 + (row + .5) * 45

    paths, badges = [], []
    for gain in gains:
        move = chess.Move.from_uci(gain['move'])
        x, y = point(move.from_square)
        tx, ty = point(move.to_square)
        length = math.hypot(tx - x, ty - y)
        dx, dy = (tx - x) / length, (ty - y) / length
        nx, ny = tx - 10 * dx, ty - 10 * dy
        shape = (f"M{x} {y}L{nx} {ny} M{nx-6*dy} {ny+6*dx}"
                 f"L{tx} {ty}L{nx+6*dy} {ny-6*dx}")
        color, label = escape(gain['color']), escape(gain['label'])
        dark = '#1a1527'
        for ink, width in ((dark, 4), (color, 1.7)):
            paths.append(f'<path d="{shape}" fill="none" stroke="{ink}" stroke-width="{width}" stroke-linecap="round"/>')
        cx, cy = (x + tx) / 2, (y + ty) / 2
        width = max(28, len(label) * 5 + 9)
        badges.append(f'<rect x="{cx-width/2}" y="{cy-7}" width="{width}" height="14" '
                      f'rx="4" fill="{dark}" stroke="{color}"/><text x="{cx}" y="{cy+3.2}" '
                      f'text-anchor="middle" font-family="system-ui" font-size="10" font-weight="700" '
                      f'fill="#f8f4ff">{label}</text>')
    return ''.join(paths + badges)


class PhoneCompanion(QObject):
    requested=Signal(object,object)
    def __init__(self,window):
        super().__init__(window);self.window=window;self.server=None;self.svg_cache={};self.move_logs={}
        self.requested.connect(self.handle)
        from .phone_analysis import PhoneAnalysis
        self.analysis=PhoneAnalysis(window)
        self.timer=QTimer(self);self.timer.setInterval(250);self.timer.timeout.connect(self.publish)

    def start(self,port=8789,host='0.0.0.0'):
        self.close();self.server=PhoneServer(self.submit,port,host)
        self.timer.start();self.publish()
        return local_addresses(self.server.port),self.server.code

    def submit(self,data):
        future=Future();self.requested.emit(data,future)
        try:return future.result(timeout=4)
        except TimeoutError:future.cancel();raise

    def handle(self,data,future):
        if future.cancelled():return
        try:
            result=self.execute(data)
            # Publish before acknowledging so an immediate phone refresh cannot
            # read the previous settings and appear to undo a successful edit.
            self.publish()
            if not future.cancelled():future.set_result(result)
        except Exception as exc:
            if not future.cancelled():future.set_exception(exc)

    def schema(self):
        w=self.window;values={};schema=[]
        for name,label in NUMBERS.items():
            field=getattr(w,name);values[name]=field.value()
            schema.append({'key':name,'label':label,'type':'number','min':field.minimum(),'max':field.maximum(),'step':1 if isinstance(field.value(),int) else 0.01,'enabled':field.isEnabled()})
        for name,label in BOOLEANS.items():
            values[name]=getattr(w,name).isChecked();schema.append({'key':name,'label':label,'type':'boolean','enabled':getattr(w,name).isEnabled()})
        for name,label in ENUMS.items():
            field=getattr(w,name)
            value=field.currentData() if name=='monitor' else field.currentText() if name in ('mode','advantage_mode') else field.currentIndex()
            options=[{'value':field.itemData(i) if name=='monitor' else field.itemText(i) if name in ('mode','advantage_mode') else i,'label':field.itemText(i)} for i in range(field.count())]
            if name in ('engine_kind','eval_engine'):
                for i,option in enumerate(options):
                    entry=engine_library.ENTRIES[i if name=='engine_kind' else field.itemData(i)]
                    option.update(engine_type=entry.kind,profile=engine_profiles.profile(entry.identity))
            if name=='engine_kind':
                options=[option for option in options if engine_library.available(engine_library.ENTRIES[option['value']])]
            if name=='advantage_engine':
                options=[option for option in options if not field.view().isRowHidden(option['value'])]
            values[name]=value;schema.append({'key':name,'label':label,'type':'select','options':options,'enabled':field.isEnabled()})
        values['extra_engines']=w.extra_engines.profiles
        values['primary_arrow_color']=w.extra_engines.primary_color
        values['engine_path']=w.engine_path.text();schema.append({'key':'engine_path','label':'Desktop Stockfish path','type':'text'})
        values['custom_engine']=w.custom_engine.text();schema.append({'key':'custom_engine','label':'Desktop custom UCI path','type':'text'})
        return values,schema

    def board(self,identity,title,board,bottom,result,displayed,arrows,known=True):
        marks,messages=self.window.threat_marks(board,bottom)
        gains = self.window.move_advantage.marks(board) if identity == 'primary' else []
        key=(identity,board.fen(),bottom,tuple((a['move'].uci(),a['color']) for a in arrows),tuple((m['square'],m['color']) for m in marks),
             tuple((g['move'],g['label'],g['color']) for g in gains))
        if key not in self.svg_cache:
            if len(self.svg_cache)>18:self.svg_cache.clear()
            svg = chess.svg.board(board, orientation=bottom, size=600,
                arrows=[chess.svg.Arrow(a['move'].from_square, a['move'].to_square,
                                       color=a['color']) for a in arrows],
                fill={m['square']:m['color']+'44' for m in marks if m['kind'] != 'attack'})
            self.svg_cache[key] = svg[:-6] + gain_svg(gains, bottom) + '</svg>'
        lead=self.window.evaluations.score(board,result)
        w=self.window;current,other=(board.turn==bottom,False) if w.only_my_color.isChecked() else ((w.show_white.isChecked(),w.show_black.isChecked()) if board.turn else (w.show_black.isChecked(),w.show_white.isChecked()))
        lines=[]
        if displayed and current:
            for rank,line in enumerate(displayed['lines'][:1 if w.stick_to_move.isChecked() else w.multipv.value()],1):
                if not w.visible_rank(rank):continue
                item=dict(deepcopy(line),rank=rank)
                if not w.predict_continuations.isChecked():item['future_simple']=''
                if w.only_my_color.isChecked() or w.stick_to_move.isChecked() or not other or not w.show_reply.isChecked():
                    item['reply']=item['reply_simple']=''
                if w.only_my_color.isChecked() or w.stick_to_move.isChecked():item['pv']=''
                lines.append(item)
        history_key = (key[1], tuple(board.move_stack), w._opening_index is not None)
        cached = self.move_logs.get(identity)
        if cached is None or cached[0] != history_key:
            if len(self.move_logs) >= 12:
                self.move_logs.clear()
            cached = history_key, played_moves(board), opening_name(board, w._opening_index)
            self.move_logs[identity] = cached
        comparison = w.move_advantage.result if identity == 'primary' else None
        return {'id':identity,'title':title,'fen':key[1],'svg':self.svg_cache[key],
                'move_advantage':comparison if comparison and comparison['fen']==key[1] else None,
                'played_moves':cached[1],'opening':cached[2],'turn':'White' if board.turn else 'Black',
                'your_color':'White' if bottom else 'Black','turn_known':known,'lines':lines,'cp':lead['cp'] if lead else None,
                'mate':lead.get('mate'),'white_share':lead.get('white_share'),
                'bar_score':evaluation_text(lead.get('cp'), lead.get('mate'), lead.get('white_share'), white_bottom=bottom),
                'score':lead['score'] if lead else '—','advantage':lead['advantage'] if lead else 'Waiting for analysis',
                'thinking':bool(result and result.get('provisional')),'locked':w.stick_to_move.isChecked(),
                'evaluation_kind':lead.get('kind',''),'evaluation_engine':lead.get('provider',''),'move_engine':result.get('engine','') if result else '', 'recommendation_evaluation_kind':result.get('evaluation_kind','') if result else '',
                'recommendation_type':result.get('recommendation_type','best moves') if result else '',
                'extra_engines':w.extra_engines.snapshot(board) if identity=='primary' and current else [],
                'waiting_for_turn':w.only_my_color.isChecked() and board.turn!=bottom,'threats':messages}

    def snapshot(self):
        w=self.window;boards=[]
        primary_valid=w.practice or w._reviewing or (w.source.currentIndex()==2 and w.snapshot is not None) or (w._position_locked and w._last_read is not None and w._lost_frames<3)
        if primary_valid:
            boards.append(self.board('primary','Board 1',w.tracker.board,w.white_bottom,w.result,w.displayed_result(w.result),w.board_view.arrows,w._turn_known))
        for index,state in enumerate(w.multi.states,2):
            if state.tracker and state.misses<3:
                shown=state.pinned if w.stick_to_move.isChecked() else state.hint_filter.select(state.result,w.steady_arrows.isChecked())
                boards.append(self.board(str(state.identity),f'Board {index}',state.tracker.board,state.read.white_bottom,state.result,shown,state.card.view.arrows,state.known))
        for board in boards:
            board['turn_override']=w.turn.currentIndex() if board['id']=='primary' else next(s.card.turn.currentIndex() for s in w.multi.states if str(s.identity)==board['id'])
        values,schema=self.schema()
        return {'app':'BoardLens','version':__version__,'updated':time.time(),'status':w.status_label.text(),'monitoring':w._monitoring,
                'auto_suggest':w.live_button.isChecked(),'practice':w.practice,'reviewing':w._reviewing,
                'boards':boards,'settings':values,'schema':schema,'keys':{k:f.text() for k,f in w.key_fields.items()},
                'engine_configuration':configuration(w),'phone_analysis':self.analysis.snapshot(),
                'phone_engines':[{'id':e.identity,'label':e.label,'kind':e.kind,'profile':engine_profiles.profile(e.identity),'available':bool(w.custom_engine.text()) if e.kind=='custom' else engine_library.available(e)} for e in engine_library.ENTRIES],
                'comparison':w.comparison.snapshot() if hasattr(w,'comparison') else None,'presets':w.analysis_presets.snapshot(),
                'history':{'index':w._history_index,'count':len(w._history)},'desktop_minimized':w.isMinimized()}

    def publish(self):
        if not self.server:return
        self.server.publish(self.snapshot())
        if hasattr(self.window,'phone_connection_status'):
            count=self.server.client_count();self.window.phone_connection_status.setText(f'{count} connected device'+('s' if count!=1 else ''))

    def execute(self,data):
        w=self.window
        if w.closing:raise ValueError('The desktop app is closing.')
        command=data.get('command');payload=data.get('data',{})
        if not isinstance(payload,dict):raise ValueError('Expected command data.')
        if QApplication.activeModalWidget() and command!='stop':raise ValueError('Close the open desktop dialog first.')
        actions={'scan':w.scan_now,'stop':w.stop,'suggest':w.suggest,'previous':w.history_previous,'next':w.history_next,'resume':w.resume_live,
                 'save':w.save,'new_game':w.new_game,'undo':w.undo,'install_engine':w.install_engine,'minimize':w.showMinimized,'show_desktop':w.showNormal,'compare':lambda:w.open_engine_comparison(show=False)}
        if command=='analyze_phone':return self.analysis.request(payload)
        if command=='cancel_phone':
            if payload.get('request_id')==self.analysis.state.get('request_id'):self.analysis.cancel()
            return 'Phone analysis stopped'
        if command=='help_search':
            query=payload.get('query','')
            if not isinstance(query,str) or len(query)>512:raise ValueError('Use a question up to 512 characters.')
            if not hasattr(self,'help_index'):
                from .help_index import HelpIndex
                self.help_index=HelpIndex()
            return self.help_index.search(query)
        if command in actions:actions[command]();return w.status_label.text()
        if command in PRESET_COMMANDS:return w.analysis_presets.command(command,payload)
        if command=='lock_board':
            if w.source.currentIndex()!=1:raise ValueError('Choose a live board before locking it.')
            identity=str(payload.get('id','primary'))
            target=0 if identity=='primary' else next((s.identity for s in w.multi.states if str(s.identity)==identity and s.confirmed),None)
            if target is None or target==0 and not w._screen_confirmed:raise ValueError('That board is no longer confirmed.')
            if w.lock_target.isChecked():w.lock_target.setChecked(False)
            w.target_board.setCurrentIndex(w.target_board.findData(target));w.lock_target.setChecked(True)
            return 'Target board locked.'
        if command=='watch':
            enabled=payload.get('enabled')
            if not isinstance(enabled,bool):raise ValueError('Expected on/off value.')
            w.live_button.setChecked(enabled);w.toggle_live(enabled)
        elif command=='play':
            if not w.practice:raise ValueError('Manual engine moves are available on the Practice board only.')
            if payload.get('fen')!=w.tracker.board.fen():raise ValueError('The position changed. Refresh before playing.')
            w.play_best()
        elif command=='settings':self.apply_settings(payload);return 'Settings synced.'
        elif command=='keys':
            if set(payload)!=set(w.key_fields):raise ValueError('Supply all keyboard shortcuts.')
            from .core import validate_keys
            validated=validate_keys(payload)
            for key,value in validated.items():w.key_fields[key].setText(value)
            w.apply_keys()
        elif command=='fen':
            fen=payload.get('fen','');board=chess.Board(fen)
            if not board.is_valid():raise ValueError('Invalid FEN.')
            w.source.setCurrentIndex(0);w.stop();w.set_position(board)
        elif command=='turn':
            identity=str(payload.get('id'));index=payload.get('index')
            if index not in (0,1,2):raise ValueError('Choose Auto, White or Black.')
            if identity=='primary':w.turn.setCurrentIndex(index)
            else:
                state=next((s for s in w.multi.states if str(s.identity)==identity),None)
                if state is None:raise ValueError('That board is no longer present.')
                state.card.turn.setCurrentIndex(index)
        elif command=='practice_move':
            if not w.practice or payload.get('fen')!=w.tracker.board.fen():raise ValueError('Practice position changed. Refresh first.')
            move=chess.Move.from_uci(str(payload.get('move','')))
            if move not in w.tracker.board.legal_moves:raise ValueError('That move is not legal.')
            w.tracker.board.push(move);w.invalidate();w.refresh_board()
        elif command=='screenshot':
            raw=base64.b64decode(payload.get('image',''),validate=True)
            if len(raw)>5*1024*1024:raise ValueError('Use an image smaller than 5 MB.')
            image=cv2.imdecode(np.frombuffer(raw,np.uint8),cv2.IMREAD_COLOR)
            if image is None or image.size>40_000_000:raise ValueError('Unsupported or oversized image.')
            read=w._recognizer.scan(image)
            if read is None:raise ValueError('No complete supported chessboard found in that image.')
            board,_=position_from_read(read);w.stop();w.source.setCurrentIndex(2)
            w.snapshot=read.image.copy();w._last_read=read;w._white_bottom=read.white_bottom;w.set_position(board);w.suggest()
        else:raise ValueError('Unknown companion command.')
        return w.status_label.text()

    def apply_settings(self,values):
        w=self.window;validated=[]
        from .engine_overlays import validate_profiles
        profiles=validate_profiles(values['extra_engines']) if 'extra_engines' in values else None
        color=values.get('primary_arrow_color',w.extra_engines.primary_color)
        import re
        if not isinstance(color,str) or not re.fullmatch(r'#[0-9a-fA-F]{6}',color):
            raise ValueError('Use a color in #RRGGBB format.')
        engine_index=values.get('engine_kind',w.engine_kind.currentIndex())
        if isinstance(engine_index,bool) or not isinstance(engine_index,int) or not 0<=engine_index<len(engine_library.ENTRIES):raise ValueError('Invalid engine choice.')
        max_candidates=1 if engine_library.ENTRIES[engine_index].kind=='tiny' else 10
        if values.get('lock_target') is True and not w.target_lock.active and not w._screen_confirmed:raise ValueError('Read a live board before locking the target.')
        if values.get('only_my_color',w.only_my_color.isChecked()) and values.get('orientation',0)!=0:
            raise ValueError('Only my color uses automatic board orientation.')
        for key,value in values.items():
            if key in ('extra_engines','primary_arrow_color'):continue
            if key in NUMBERS:
                field=getattr(w,key)
                if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not field.minimum()<=value<=(max_candidates if key=='multipv' else field.maximum()):raise ValueError(f'Invalid value for {key}.')
                if isinstance(field.value(),int) and not float(value).is_integer():raise ValueError(f'Expected a whole number for {key}.')
                validated.append((field,'number',int(value) if isinstance(field.value(),int) else value))
            elif key in BOOLEANS:
                if not isinstance(value,bool):raise ValueError(f'Expected on/off for {key}.')
                validated.append((getattr(w,key),'boolean',value))
            elif key in ENUMS:
                field=getattr(w,key)
                index=field.findData(value) if key=='monitor' else field.findText(value) if key in ('mode','advantage_mode') else value
                if not isinstance(index,int) or not 0<=index<field.count():raise ValueError(f'Invalid choice for {key}.')
                if key == 'advantage_engine' and field.view().isRowHidden(index) and index != field.currentIndex():
                    raise ValueError('Install this scoring engine on the desktop first.')
                validated.append((field,'select',index))
            elif key in ('engine_path','custom_engine') and isinstance(value,str) and len(value)<4096:validated.append((getattr(w,key),'text',value))
            else:raise ValueError(f'Unknown setting: {key}.')
        if color!=w.extra_engines.primary_color:
            w.extra_engines.primary_color=color
            w.queue_autosave()
            w.update_visuals()
        if profiles is not None:w.extra_engines.configure(profiles)
        validated.sort(key=lambda item:0 if item[0] is w.engine_kind else 1)
        for field,kind,value in validated:
            if kind=='number':
                if field is w.multipv:w.recommendation_preset(value)
                else:field.setValue(value)
            elif kind=='boolean':field.setChecked(value)
            elif kind=='select':field.setCurrentIndex(value)
            else:field.setText(value);w.engine_settings_changed()

    def close(self):
        self.analysis.cancel()
        if self.window.closing:self.analysis.close()
        self.timer.stop()
        if self.server:self.server.close();self.server=None
