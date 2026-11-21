"""Exact board reads and loopback communication for opt-in connectors."""
from __future__ import annotations
import json,threading,time,secrets,hmac,re
from functools import lru_cache
from .core import data_dir
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import chess,numpy as np
from .core import ordered_symbols
from .recognition import Read
from .vision import Detection


def exact_read(fen,bottom,identity,points=None,desktop_rect=None):
    board=chess.Board(fen)
    if not board.is_valid():raise ValueError('The connector sent an invalid position.')
    read=Read(ordered_symbols(board,bottom),np.ones(64),np.zeros((64,13)),bottom,board.turn,
              np.full((256,256,3),32,dtype=np.uint8),Detection(0,0,256,1))
    read.exact_fen=board.fen();read.source_id=identity;read.points=points;read.desktop_rect=desktop_rect
    return read


@lru_cache(maxsize=24)
def verified_history(fen, san_moves):
    """Never attach an opening or move list to a different position."""
    board = chess.Board()
    try:
        for move in san_moves:
            board.push_san(move)
    except ValueError:
        return None
    return board if board.fen() == fen else None


FRAME_SECONDS=.5


class BrowserReader:
    """Return analysis to the paired browser tab."""
    def __init__(self,port=8788):
        self.lock=threading.Lock();self.frames={};self.dashboard={};self.hints={};self.evaluation_visible=None;self.rejected_at=0.;self.token=secrets.token_urlsafe(32)
        secret=data_dir()/'browser-reader-key'
        if secret.is_file() and len(secret.read_text().strip())>=40:self.token=secret.read_text().strip()
        else:secret.write_text(self.token);secret.chmod(0o600)
        owner=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def reply(self,status,data):
                raw=json.dumps(data).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
            def authorized(self):
                accepted=hmac.compare_digest(self.headers.get('Authorization',''),'Bearer '+owner.token)
                if not accepted:owner.rejected_at=time.monotonic()
                return accepted
            def do_GET(self):
                if not self.authorized():return self.reply(401,{'error':'Pair the browser reader with its desktop key.'})
                if self.path!='/hints':return self.reply(404,{'error':'Unknown reader endpoint.'})
                with owner.lock:data=dict(owner.hints)
                self.reply(200,data)
            def do_POST(self):
                if not self.authorized():return self.reply(401,{'error':'Pair the browser reader first.'})
                try:
                    length=int(self.headers.get('Content-Length','0'))
                    if not 0<length<100_000:raise ValueError('Invalid board message size.')
                    payload=json.loads(self.rfile.read(length))
                    if not isinstance(payload,dict):
                        raise ValueError('Invalid browser message.')
                    if self.path=='/boards':
                        owner.accept(payload)
                        with owner.lock:
                            response={'ok':True,'hints':dict(owner.hints),'evaluation_visible':owner.evaluation_visible}
                        self.reply(200,response)
                    else:
                        self.reply(404,{'error':'Unknown reader endpoint.'})
                except (ValueError,TypeError,KeyError) as exc:self.reply(400,{'error':str(exc)})
                except (BrokenPipeError,ConnectionResetError):pass
        self.http=ThreadingHTTPServer(('127.0.0.1',port),Handler);self.http.daemon_threads=True;self.port=self.http.server_port
        self.thread=threading.Thread(target=lambda:self.http.serve_forever(poll_interval=.1),daemon=True);self.thread.start()
    def accept(self,payload):
        source=payload['source'];boards=payload['boards']
        if not isinstance(source,str) or len(source)>100 or not isinstance(boards,list) or len(boards)>3:raise ValueError('Expected at most three visible boards.')
        focused = payload.get('focused')
        if focused is False:
            boards = []
        frames=[]
        seen=set()
        now=time.monotonic()
        for fallback_index,item in enumerate(boards):
            if not isinstance(item,dict) or not isinstance(item.get('white_bottom'),bool):
                continue
            index=item.get('index',fallback_index)
            if type(index) is not int or index not in range(3) or index in seen:
                continue
            identity=f'browser:{source}:{index}'
            try:
                read=exact_read(item['fen'],item['white_bottom'],identity)
            except (TypeError,ValueError,KeyError,AttributeError):
                continue
            read.received_at=now
            read.visible_fen=item['fen']
            board_id=item.get('board_id')
            read.game_identity=board_id if isinstance(board_id,str) and re.fullmatch(r'[a-f0-9]{32}',board_id) else None
            moves=item.get('moves')
            if (item.get('exact') is True and isinstance(moves,list) and 0 < len(moves) <= 600
                    and all(isinstance(move,str) and 0 < len(move) <= 16 for move in moves)):
                read.move_history=verified_history(read.exact_fen,tuple(moves))
            from .game_end import reason
            read.game_result=reason(item.get('game_result','')) if isinstance(item.get('game_result'),str) else None
            if item.get('exact') is False:read.exact_fen=None;read.turn_hint=item.get('turn_hint') if isinstance(item.get('turn_hint'),bool) else None
            page=item.get('practice_id')
            read.practice_id=(page if item.get('exact') is True and isinstance(page,str)
                              and re.fullmatch(r'[a-f0-9]{32}',page) else None)
            kind=item.get('practice_kind','analysis')
            if kind not in ('analysis','computer-bot'):
                read.practice_id=None
            read.practice_kind=kind if read.practice_id else None
            read.practice_focused=bool(read.practice_id and item.get('practice_focused') is True)
            seen.add(index)
            frames.append((identity,'Browser reader',read,256,256))
        invalid = bool(boards and not frames)
        if invalid and focused is not True:
            raise ValueError('The connector sent no valid positions.')
        with self.lock:
            if focused is True:
                # A tab can stay visible in a second window after focus changes.
                # An empty report from the focused tab must also replace it.
                self.frames.clear()
                self.dashboard.clear()
            self.frames[source]=(now,frames)
            self.frames={tab:value for tab,value in self.frames.items() if now-value[0]<5}
            self.dashboard.pop(source, None)
            if focused is True and payload.get('dashboard') is True and not boards:
                self.dashboard[source]=now
        if invalid:
            raise ValueError('The connector sent no valid positions.')
        return frames

    def suppress_screen_fallback(self):
        with self.lock:
            return any(time.monotonic() - at < FRAME_SECONDS for at in self.dashboard.values())

    def reads(self):
        with self.lock:
            now=time.monotonic()
            frames=[frame for at,frames in self.frames.values() if now-at<FRAME_SECONDS for frame in frames]
            return sorted(frames,key=lambda frame:(frame[2].practice_focused,frame[2].received_at),reverse=True)[:3]

    def connection_status(self):
        now=time.monotonic()
        with self.lock:
            latest=max((at for at,_ in self.frames.values()),default=0.)
            count=sum(len(frames) for at,frames in self.frames.values() if now-at<2)
        if self.rejected_at>latest and now-self.rejected_at<10:return 'Needs pairing · reconnect with the desktop key'
        if latest and now-latest<2:return f'Connected · {count} visible board'+('s' if count!=1 else '')
        return 'Disconnected · reader retries automatically' if latest else 'Waiting for the browser reader'

    def publish(self,hints,evaluation_visible=None):
        with self.lock:
            self.hints=hints
            self.evaluation_visible=evaluation_visible
    def close(self):self.http.shutdown();self.http.server_close()
