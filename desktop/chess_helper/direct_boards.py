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


PLAY_OFFER_SECONDS=.65
PLAY_AUTH_MS=225
FRAME_SECONDS=.5


class BrowserReader:
    """Return analysis and test commands to the paired browser tab."""
    def __init__(self,port=8788):
        self.lock=threading.Lock();self.frames={};self.dashboard={};self.hints={};self.evaluation_visible=None;self.pending_play={};self.claimed_play={};self.rejected_at=0.;self.token=secrets.token_urlsafe(32)
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
                    if self.path=='/claim-play':
                        self.reply(200,{'play':owner.claim_play(payload)})
                    elif self.path=='/boards':
                        frames=owner.accept(payload)
                        self.reply(200,{'ok':True,'hints':owner.hints_for_post(frames),'evaluation_visible':owner.evaluation_visible})
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
            white=item.get('practice_white')
            read.practice_white=(white if kind=='computer-bot' and isinstance(white,bool) else None)
            if kind=='computer-bot' and read.practice_white is None:
                read.practice_id=None
            read.practice_kind=kind if read.practice_id else None
            read.practice_focused=bool(read.practice_id and item.get('practice_focused') is True)
            read.play_protocol=item.get('play_protocol') if read.practice_id else None
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

    @staticmethod
    def can_offer(command,read):
        return (read.play_protocol==2 and read.practice_focused and read.practice_id==command['page']
                and read.visible_fen==command['fen'] and not read.game_result
                and time.monotonic()-read.received_at<=FRAME_SECONDS)

    def offer_autoplay(self, read, move):
        """Advertise a short-lived offer. The browser must claim it before it can move."""
        if not read.practice_id or not read.exact_fen or read.play_protocol!=2:
            return None
        source=read.source_id
        command={'id':secrets.token_hex(16),'page':read.practice_id,'fen':read.visible_fen,'move':move.uci()}
        with self.lock:
            self.pending_play[source]=(time.monotonic()+PLAY_OFFER_SECONDS,command)
            self.claimed_play.pop(source,None)
        return command['id']

    def clear_autoplay(self, source):
        with self.lock:
            self.pending_play.pop(source,None)
            self.claimed_play.pop(source,None)

    def claim_play(self,payload):
        source=payload.get('source')
        index=payload.get('index')
        if not isinstance(source,str) or type(index) is not int or not 0<=index<3:
            return None
        identity=f'browser:{source}:{index}'
        with self.lock:
            pending=self.pending_play.get(identity)
            if not pending:
                return None
            expires,command=pending
            if expires<time.monotonic():
                self.pending_play.pop(identity)
                return None
            frames=self.frames.get(source,(0,()))[1]
            read=next((frame[2] for frame in frames if frame[0]==identity),None)
            if (not read or any(payload.get(key)!=command[key] for key in ('id','page','fen'))
                    or not self.can_offer(command,read)):
                return None
            self.pending_play.pop(identity)
            self.claimed_play[identity]=command['id']
            return {**command,'expires':int(time.time()*1000)+PLAY_AUTH_MS}

    def play_state(self,source,command_id):
        with self.lock:
            if self.claimed_play.get(source)==command_id:
                return 'claimed'
            pending=self.pending_play.get(source)
            if pending and pending[0]>=time.monotonic() and pending[1]['id']==command_id:
                return 'offered'
        return 'expired'

    def hints_for_post(self, frames):
        now=time.monotonic()
        with self.lock:
            hints=dict(self.hints)
            for source,pending in tuple(self.pending_play.items()):
                if pending[0]<now:
                    self.pending_play.pop(source)
            for source,_,read,_,_ in frames:
                pending=self.pending_play.get(source)
                if pending and self.can_offer(pending[1],read):
                    hints[source]={**hints.get(source,{}),'fen':read.visible_fen,'autoplay_offer':pending[1],
                                   'arrows':hints.get(source,{}).get('arrows',[])}
            return hints

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
