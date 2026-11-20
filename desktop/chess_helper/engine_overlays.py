"""Independent analysis profiles for the current live position."""
from dataclasses import asdict, replace
import math
import re
import threading

import chess
from PySide6.QtCore import QObject, Signal, Qt
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout,
    QGroupBox, QLabel, QMessageBox, QSpinBox, QTabWidget, QVBoxLayout,
)

from . import engine_config, engine_library, engine_profiles
from .engine import EngineJob, EngineSession
from .studio import ArrowColorButton

COLORS = ('#ec8be9', '#83e4bb', '#bb9aff')
STYLES = ('Balanced', 'Aggressive', 'Defensive', 'Human-like')
MODES = ('Time', 'Depth', 'Time + depth', 'Adaptive')


def validate_profiles(value):
    if not isinstance(value, list) or len(value)>len(COLORS):
        raise ValueError('Choose up to three additional engine profiles.')
    profiles=[]
    for item in value:
        if not isinstance(item,dict) or item.get('engine') not in engine_library.BY_ID:
            raise ValueError('Unknown engine profile.')
        engine=item['engine']
        if not re.fullmatch(r'#[0-9a-fA-F]{6}',str(item.get('color',''))):
            raise ValueError('Use a color in #RRGGBB format.')
        mode=item.get('mode','Time + depth')
        style=item.get('style','Balanced')
        if mode not in MODES or style not in STYLES:
            raise ValueError('Unknown search limit or style.')
        profile=dict(engine=engine,color=item['color'],mode=mode,style=style)
        for key,low,high,default in (
            ('seconds',.05,30,.25),('depth',1,60,18),('moves',1,5,1),
            ('plies',1,12,2),('rating',600,2600,1500),
        ):
            n=item.get(key,default)
            if isinstance(n,bool) or not isinstance(n,(int,float)) or not math.isfinite(n) or not low<=n<=high or (key!='seconds' and int(n)!=n):
                raise ValueError('Invalid engine profile '+key+'.')
            profile[key]=float(n) if key=='seconds' else int(n)
        profiles.append(profile)
    return profiles


class EngineOverlays(QObject):
    result_ready=Signal(int,int,object,str)

    def __init__(self,window):
        super().__init__(window)
        self.window=window
        self.sessions=[EngineSession() for _ in COLORS]
        try:
            self.profiles=validate_profiles(window.settings.get('extra_engines',[]))
        except ValueError:
            self.profiles=[]
        color=window.settings.get('primary_arrow_color','#ffc65c')
        self.primary_color=color if re.fullmatch(r'#[0-9a-fA-F]{6}',str(color)) else '#ffc65c'
        self.jobs={}
        self.results={}
        self.errors={}
        self.fen=''
        self.generation=0
        self.result_ready.connect(self.finish)

    def configure(self,profiles):
        profiles=validate_profiles(profiles)
        if profiles==self.profiles:return
        def searches(values):
            return [{key: value for key, value in profile.items() if key != "color"} for profile in values]
        changed = searches(self.profiles) != searches(profiles)
        self.profiles = profiles
        if changed:
            self.cancel()
        self.window.queue_autosave()
        self.window.update_visuals()
        if changed and self.window._monitoring and self.window._screen_confirmed:
            self.request(self.window.tracker.board)

    def request(self,board):
        if not self.profiles or board.is_game_over() or board.fen()==self.fen:return
        self.cancel()
        self.fen=board.fen()
        for i,profile in enumerate(self.profiles):
            entry=engine_library.BY_ID[profile['engine']]
            try:
                command=engine_config.command(self.window,engine_library.ENTRIES.index(entry))
            except (ValueError,OSError) as exc:
                self.errors[i]=str(exc)
                continue
            settings=replace(
                self.window.search_settings(), engine_kind=entry.identity if entry.kind=='tiny' else entry.kind,
                engine_id=entry.identity, strength='Full strength', threads=1, hash_mb=32,
                seconds=profile['seconds'],depth=profile['depth'],
                mode='Time' if entry.kind=='tiny' else profile['mode'],
                multipv=1 if entry.kind=='tiny' else profile['moves'],
                style=profile['style'] if entry.kind not in ('maia1','maia2','maia3','tiny') else 'Balanced',
                human_elo=profile['rating'],predict_continuations=profile['plies']>1,
                prediction_plies=profile['plies'],prediction_seconds=profile['seconds'],
            )
            job=EngineJob();job.session=self.sessions[i];self.jobs[i]=job
            token=self.generation
            job.on_update=lambda result,slot=i,key=token:self.result_ready.emit(key,slot,result,'') if result.get('primary_complete') else None

            def run(job=job, command=command, settings=settings, slot=i, token=token, position=board.copy()):
                try:
                    result=job.run(command,position,settings)
                    self.result_ready.emit(token,slot,result,'')
                except (RuntimeError,OSError,ValueError,chess.engine.EngineError) as exc:
                    if not job.cancelled.is_set():
                        self.result_ready.emit(token,slot,None,str(exc))
            threading.Thread(target=run,daemon=True,name='BoardLens-overlay-engine').start()

    def finish(self,token,slot,result,error):
        if token!=self.generation or self.window.closing:return
        if result and result.get('fen')==self.fen:self.results[slot]=result
        if error:self.errors[slot]=error
        self.window.update_visuals()

    def arrows(self,board):
        if board.fen()!=self.fen:return []
        arrows=[]
        for i,result in sorted(self.results.items()):
            profile=self.profiles[i]
            for rank,line in enumerate(result['lines'],1):
                move=chess.Move.from_uci(line['move'])
                if move in board.legal_moves:
                    arrows.append(dict(move=move,color=profile['color'],label=f'{i+2}.{rank}',engine=result['engine']))
        return arrows

    def snapshot(self,board):
        if board.fen()!=self.fen:return []
        return [dict(profile,
                     label=engine_library.BY_ID[profile['engine']].label,
                     lines=self.results.get(i,{}).get('lines',[]),error=self.errors.get(i,''))
                for i,profile in enumerate(self.profiles)]

    def cancel(self):
        self.generation+=1
        for job in self.jobs.values():job.cancel()
        self.jobs.clear()
        self.results.clear()
        self.errors.clear()
        self.fen=''

    def close(self):
        self.cancel()
        for session in self.sessions:session.close()

    def edit(self):
        dialog=QDialog(self.window)
        dialog.setWindowTitle('Arrow engines')
        layout=QVBoxLayout(dialog)
        primary=ArrowColorButton(self.primary_color,'Main arrow color')
        head=QFormLayout();head.addRow('Main arrow color',primary);layout.addLayout(head)
        tabs=QTabWidget();layout.addWidget(tabs)
        choices=[entry for entry in engine_library.ENTRIES if engine_library.available(entry)]
        rows=[]
        for i,color in enumerate(COLORS):
            profile=self.profiles[i] if i<len(self.profiles) else {}
            group=QGroupBox();form=QFormLayout(group);tabs.addTab(group,f'Engine {i+2}')
            engine=QComboBox();engine.addItem('Off','')
            for entry in choices:engine.addItem(entry.label,entry.identity)
            engine.setCurrentIndex(max(0,engine.findData(profile.get('engine',''))))
            form.addRow('Engine',engine)
            for row,entry in enumerate(choices,1):
                engine.setItemData(row,engine_profiles.description(entry.identity),Qt.ItemDataRole.ToolTipRole)
            profile_label=QLabel()
            profile_label.setWordWrap(True)
            def show_profile(_,combo=engine,label=profile_label):
                identity=combo.currentData()
                label.setText(engine_profiles.description(identity) if identity else '')
                label.setVisible(bool(identity))
            form.addRow(profile_label)
            engine.currentIndexChanged.connect(show_profile)
            show_profile(0)
            tint=ArrowColorButton(profile.get('color',color),f'Engine {i+2} arrow color');form.addRow('Arrow color',tint)
            mode=QComboBox();mode.addItems(MODES);mode.setCurrentText(profile.get('mode','Time + depth'));form.addRow('Limit',mode)
            style=QComboBox();style.addItems(STYLES);style.setCurrentText(profile.get('style','Balanced'));form.addRow('Style',style)
            fields={}
            for key,label,min_value,max_value,default in (
                ('seconds','Seconds',.05,30,.25),('depth','Depth',1,60,18),
                ('moves','Moves',1,5,1),('plies','Prediction plies',1,12,2),
                ('rating','Human rating',600,2600,1500),
            ):
                field=QDoubleSpinBox() if key=='seconds' else QSpinBox()
                field.setRange(min_value,max_value);field.setValue(profile.get(key,default))
                form.addRow(label,field);fields[key]=field
            rows.append((engine,tint,mode,style,fields))
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        def save():
            try:
                profiles=validate_profiles([
                    dict(engine=e.currentData(),color=c.color,mode=m.currentText(),style=s.currentText(),
                         **{key:field.value() for key,field in fields.items()})
                    for e,c,m,s,fields in rows if e.currentData()])
            except ValueError as exc:
                QMessageBox.warning(dialog,'Arrow engines',str(exc))
                return
            self.primary_color=primary.color
            self.configure(profiles)
            self.window.queue_autosave()
            self.window.update_visuals()
            dialog.accept()
        buttons.accepted.connect(save);buttons.rejected.connect(dialog.reject);layout.addWidget(buttons)
        dialog.exec()
