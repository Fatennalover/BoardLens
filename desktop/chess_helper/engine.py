from __future__ import annotations

import threading
import time
import os
from copy import deepcopy
from dataclasses import replace

import chess
import chess.engine

from .recommendation_styles import flounder_index,style_index
from .core import MAX_LOOKAHEAD_PLIES, SearchSettings, advantage, describe_move, move_insights, simple_move, data_dir


def engine_environment(path):
    env=dict(os.environ,HF_HOME=str(data_dir()/'maia3-cache'))
    if isinstance(path,list) and 'maia3.uci' in path:env['HF_HUB_OFFLINE']='1'
    if isinstance(path,list) and ('maia3.uci' in path or any('maia2_uci.py' in str(part) for part in path)):
        env.update(OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',VECLIB_MAXIMUM_THREADS='1')
    if isinstance(path,list) and any(PathLike.endswith(('lc0','lc0.exe')) for PathLike in (str(part) for part in path)):
        env.update(OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',VECLIB_MAXIMUM_THREADS='1')
    return env


def uci_process_options(path):
    from pathlib import Path
    binary=Path(path[0] if isinstance(path,list) else path)
    if binary.is_absolute():return dict(env=engine_environment(path),cwd=str(binary.parent))
    return dict(env=engine_environment(path))


class EngineSession:
    """Keep the UCI process and its model loaded between searches."""
    def __init__(self):
        self.lock=threading.Lock()
        self.engine=None
        self.path=None
        self.closed = False

    def get(self,path):
        if self.closed:
            raise chess.engine.EngineTerminatedError('Engine session closed')
        if self.engine is None or self.path!=path or self.engine.returncode.done():
            if self.engine:
                self.engine.close()
            self.engine=chess.engine.SimpleEngine.popen_uci(path,timeout=90 if isinstance(path,list) else 15,
                **uci_process_options(path))
            self.path=path
        if self.closed:
            self.close()
            raise chess.engine.EngineTerminatedError('Engine session closed')
        return self.engine

    def warm(self, path):
        if not self.lock.acquire(blocking=False):
            return
        try:
            self.get(path).ping()
        except (chess.engine.EngineError, OSError, TimeoutError):
            # Suggest reports startup errors when the engine is needed.
            return
        finally:
            self.lock.release()

    def discard(self):
        engine, self.engine = self.engine, None
        if engine:
            engine.close()

    def close(self):
        self.closed = True
        self.discard()


class EngineJob:
    def __init__(self):
        self.cancelled = threading.Event()
        self.analysis = None
        self.lock = threading.Lock()
        self.session=None
        self.on_update=None

    def cancel(self):
        self.cancelled.set()
        with self.lock:
            active = self.analysis
            if active is not None:
                try:
                    active.stop()
                except (chess.engine.EngineError, RuntimeError):
                    pass
        if active is not None and self.session is not None:
            timer = threading.Timer(.4, self._interrupt, (active,))
            timer.daemon = True
            timer.start()

    def _interrupt(self, active):
        with self.lock:
            if self.analysis is active:
                self.session.discard()

    def run(self, path, board, settings: SearchSettings):
        if not board.is_valid():
            raise ValueError("Cannot analyze an invalid position.")
        if board.is_game_over():
            raise ValueError(f"Game over: {board.result()}")
        if self.session:
            while not self.session.lock.acquire(timeout=.03):
                if self.cancelled.is_set():return None
            try:
                if self.cancelled.is_set():return None
                try:
                    return self._search(self.session.get(path),board,settings)
                except (chess.engine.EngineTerminatedError, TimeoutError):
                    self.session.discard()
                    if self.cancelled.is_set():return None
                    return self._search(self.session.get(path),board,settings)
            finally:
                with self.lock:
                    self.analysis = None
                self.session.lock.release()
        with chess.engine.SimpleEngine.popen_uci(path, timeout=90 if isinstance(path,list) else 15,
                **uci_process_options(path)) as engine:
            return self._search(engine,board,settings)

    def _search(self, engine, board, settings):
        started = time.monotonic()
        result = self._search_once(engine, board, settings)
        if self.cancelled.is_set():
            return None
        if not result or not settings.predict_continuations:
            return result

        target = max(1, min(MAX_LOOKAHEAD_PLIES, int(settings.prediction_plies)))
        budget = max(.1, min(60., float(settings.prediction_seconds)))
        deadline = time.monotonic() + budget
        callback = self.on_update
        elapsed = result.get("elapsed", 0.)
        policy = settings.engine_kind in ('maia3', 'maia2', 'maia1', 'neural', 'allie')
        estimate = elapsed if policy else 0.
        candidates = []
        for line in result["lines"]:
            pv = describe_continuation(board, (line.get("pv_moves") or [line["move"]])[:target])
            line.update(pv)
            position = board.copy()
            for move in pv["pv_moves"]:
                position.push_uci(move)
            candidates.append((line, position))

        def waiting():
            return [(line, position) for line, position in candidates
                    if len(line["pv_moves"]) < target and not position.is_game_over() and not line.get("prediction_error")]

        def publish():
            if callback and not self.cancelled.is_set():
                callback(dict(deepcopy(result), continuation_pending=bool(waiting()), primary_complete=True))

        timed_out = False
        pending = waiting()
        if pending:
            publish()
        self.on_update = None
        try:
            while pending and not self.cancelled.is_set():
                # Complete a round of replies before deepening any one variation.
                pending.sort(key=lambda option: len(option[0]["pv_moves"]))
                for index, (line, position) in enumerate(pending):
                    remaining = deadline - time.monotonic()
                    if remaining <= 0 or remaining < estimate:
                        timed_out = True
                        break
                    if self.cancelled.is_set():
                        return None
                    seconds = min(settings.seconds, remaining / (len(pending)-index))
                    limits = replace(settings, multipv=1, seconds=seconds, predict_continuations=False,
                                     mode="Time + depth" if settings.mode == "Depth" else settings.mode)
                    try:
                        followup = self._search_once(engine, position, limits)
                        if not followup:
                            if self.cancelled.is_set():
                                return None
                            raise ValueError("Engine returned no follow-up move")
                        if policy:
                            estimate = followup.get("elapsed", estimate)
                        selected = followup["lines"][0]
                        moves = selected.get("pv_moves") or [selected["move"]]
                        current = line["pv_moves"]
                        extension = describe_continuation(position, moves[:target-len(current)])["pv_moves"]
                        if not extension:
                            raise ValueError("Engine returned no legal follow-up move")
                        for uci in extension:
                            position.push_uci(uci)
                        line.update(describe_continuation(board, current + extension))
                        publish()
                    except (ValueError, chess.engine.EngineError, TimeoutError) as error:
                        line["prediction_error"] = str(error)
                if timed_out:
                    break
                pending = waiting()
        finally:
            self.on_update = callback
        if self.cancelled.is_set():
            return None
        for line, position in candidates:
            completed = len(line["pv_moves"])
            complete = completed >= target
            outcome = position.outcome()
            line["prediction"] = {
                "requested_plies": target, "completed_plies": completed,
                "error": line.get("prediction_error", ""),
                "budget_exhausted": not complete and outcome is None and not line.get("prediction_error") and timed_out,
                "terminal": not complete and outcome is not None,
                "reply_budget": budget,
            }
            if target > 1 and completed < 2:
                line["reply_status"] = ("Checkmate" if position.is_checkmate() else "The game ends here" if outcome else
                                        "Reply budget reached" if line["prediction"]["budget_exhausted"] else "Reply unavailable")
        result.update(continuation_pending=False, primary_elapsed=elapsed,
                      elapsed=time.monotonic() - started, prediction=result["lines"][0]["prediction"])
        return result

    def _search_once(self,engine,board,settings):
        if self.cancelled.is_set():
            return None
        options = {}
        for name, value in (("Threads", settings.threads), ("Hash", settings.hash_mb), ("UCI_ShowWDL", True)):
            if name in engine.options:
                options[name] = value
        human=settings.engine_kind in ('maia3','maia2','maia1','neural','allie');tiny=settings.engine_kind.startswith('tiny');flounder=settings.engine_kind=='flounder'
        limited=not human and settings.strength!='Full strength'
        if 'Skill Level' in engine.options:options['Skill Level']=settings.skill if settings.strength=='Skill level' else engine.options['Skill Level'].max
        if 'UCI_LimitStrength' in engine.options:options['UCI_LimitStrength']=settings.strength=='Elo rating'
        if settings.strength=='Skill level' and not human and 'Skill Level' not in engine.options:
            raise ValueError('This engine does not support Skill Level. Choose full strength.')
        if settings.strength=='Elo rating' and not human:
            if 'UCI_Elo' not in engine.options or 'UCI_LimitStrength' not in engine.options:
                raise ValueError('This engine does not support Elo limiting. Choose full strength.')
            option=engine.options['UCI_Elo']
            if not option.min<=settings.elo<=option.max:raise ValueError(f'This engine supports Elo {option.min}–{option.max}.')
            options['UCI_Elo']=settings.elo
        if human:
            for name,value in (('Elo',settings.human_elo),('Temperature',0)):
                if name in engine.options:options[name]=value
        if settings.engine_kind=='toby':
            for name,value in (('White Rating',settings.human_elo),('Black Rating',settings.human_elo),
                               ('Precision','Fast'),('Stockfish Threads',settings.threads)):
                if name in engine.options:options[name]=value
        if 'OwnBook' in engine.options:options['OwnBook']=False
        if 'OnlineTB' in engine.options:options['OnlineTB']=False
        engine.configure(options)
        limit = chess.engine.Limit(nodes=1) if human else chess.engine.Limit(time=settings.seconds) if tiny or settings.engine_kind=='toby' else search_limit(settings,board)
        if settings.engine_kind=='allie' and board.root().fen()!=chess.STARTING_FEN:
            raise ValueError('Allie needs the game history from the standard starting position.')
        started=time.monotonic()
        count=min(board.legal_moves.count(),board.legal_moves.count() if flounder else max(settings.multipv,4 if limited else 8 if settings.style not in ('Balanced','Maximum strength') else 1))
        count=min(count,engine.options['MultiPV'].max) if 'MultiPV' in engine.options else 1
        with engine.analysis(board, limit, multipv=count if 'MultiPV' in engine.options else None) as analysis:
            with self.lock:
                self.analysis = analysis
                if self.cancelled.is_set():
                    analysis.stop()
            can_stream = (self.on_update and not limited and not human and not flounder
                          and settings.style in ('Balanced', 'Maximum strength'))
            last_update = None
            for info in analysis:
                if not can_stream or info.get('multipv', 1) != count or self.cancelled.is_set():
                    continue
                now = time.monotonic()
                if last_update is not None and now - last_update < .08:
                    continue
                infos = [dict(line) for line in analysis.multipv[:settings.multipv]
                         if line.get('pv') and 'score' in line
                         and not line.get('lowerbound') and not line.get('upperbound')]
                if len(infos) == min(settings.multipv, count):
                    self.on_update(summarize(board, infos, engine.id.get('name', 'UCI engine')))
                    last_update = now
            lines = list(analysis.multipv)
            selected=analysis.wait().move
            with self.lock:
                self.analysis = None
        if self.cancelled.is_set():
            return None
        lines=[info for info in lines if info.get('pv')]
        if tiny and selected and not lines:lines=[{'pv':[selected]}]
        objective=summarize(board,lines[:1],engine.id.get('name','UCI engine'),allow_unscored=tiny)['lines'][0] if lines else None
        # A limited engine's bestmove is its chosen recommendation. MultiPV is
        # still ordered by objective search score, so use bestmove explicitly.
        if limited and selected:
            chosen=[info for info in lines if info.get('pv') and info['pv'][0]==selected]
            if not chosen:raise ValueError('Engine did not return analysis for its selected move. Increase think time or candidates.')
            lines=chosen+[info for info in lines if info not in chosen]
        if lines and flounder:
            index=flounder_index(board,lines,settings.human_elo);lines=[lines[index]]+lines[:index]+lines[index+1:];selected=lines[0]['pv'][0]
        if lines and settings.style not in ('Balanced','Maximum strength') and not tiny:
            index=style_index(board,lines,settings.style);lines=[lines[index]]+lines[:index]+lines[index+1:];selected=lines[0]['pv'][0]
        result=summarize(board,lines[:settings.multipv],engine.id.get("name","UCI engine"),allow_unscored=tiny)
        if objective:result['evaluation']=objective
        result['chosen_move']=selected.uci() if selected else ''
        result['recommendation_type']='human prediction' if human else 'strength-limited choice' if limited else 'Flounder sampled recommendation' if flounder else 'native bot recommendation' if tiny else 'style-ranked recommendation' if settings.style not in ('Balanced','Maximum strength') else 'best moves'
        if settings.engine_kind in ('neural','allie'):
            result['evaluation_kind']='model expected score'
            for line in [*result['lines'],result.get('evaluation',{})]:
                if line.get('cp') is not None:
                    line['white_share']=max(0.,min(1.,.5+line['cp']/2000))
                    line.update(cp=None,mate=None,score=f"{line['white_share']:.0%}",advantage='Model expected score for White')
        elif human:
            result['evaluation_kind']='human-game outcome estimate'
            for line in result['lines']:
                line['advantage']='Maia human-game outcome estimate'
            if 'evaluation' in result:result['evaluation']['advantage']='Maia human-game outcome estimate'
        else:result['evaluation_kind']='not supplied by this bot' if tiny else 'engine search evaluation'
        result['configuration']={'kind':settings.engine_kind,'strength':settings.strength,'skill':settings.skill,'elo':settings.elo,'human_elo':settings.human_elo,'style':settings.style,'engine_id':settings.engine_id}
        result['elapsed']=time.monotonic()-started
        result['limits']={'mode':settings.mode,'seconds':settings.seconds,'depth':settings.depth,
                          'threads':settings.threads,'multipv':settings.multipv,'hash_mb':settings.hash_mb,'effective_seconds':limit.time,'effective_depth':limit.depth}
        return result


def search_limit(settings,board=None):
    if settings.mode=='Adaptive':
        moves=board.legal_moves.count() if board else 25
        tactical=bool(board and (board.is_check() or any(board.is_capture(move) for move in board.legal_moves)))
        factor=min(1.,.35+moves/90+(.2 if tactical else 0))
        return chess.engine.Limit(time=min(settings.seconds,max(.1,settings.seconds*factor)),depth=min(settings.depth,max(6,8+moves//8+(2 if tactical else 0))))
    return chess.engine.Limit(time=settings.seconds if settings.mode != "Depth" else None,
                              depth=settings.depth if settings.mode != "Time" else None)


def summarize(board, infos, engine_name,allow_unscored=False):
    lines = []
    for info in infos:
        pv = info.get("pv", [])
        if not pv or ("score" not in info and not allow_unscored):
            continue
        variation = describe_continuation(board, [move.uci() for move in pv[:MAX_LOOKAHEAD_PLIES]])
        if not variation["pv_moves"]:
            continue
        score = info['score'].white() if 'score' in info else None
        cp,mate=(score.score(mate_score=100000),score.mate()) if score else (None,None)
        wdl = info.get("wdl")
        wdl_text = ""
        expected_score = None
        if wdl:
            values = wdl.white()
            total = sum(values)
            if total:
                expected_score = (values.wins + values.draws / 2) / total
                wdl_text = f"White win {values.wins/total:.0%} · draw {values.draws/total:.0%} · Black win {values.losses/total:.0%}"
        lines.append({"move": pv[0].uci(), "san": board.san(pv[0]), "cp": cp, "mate": mate,
                      "score": (f"M{abs(mate)} {'White' if mate > 0 else 'Black'}" if mate is not None else f"{cp/100:+.2f}" if cp is not None else "—"),
                      "depth": info.get("depth", 0), **variation, "description": describe_move(board, pv[0]),
                      "simple": simple_move(board,pv[0]),
                      "insights": move_insights(board, pv[0]),
                      "advantage": advantage(cp, mate) if cp is not None else "This bot does not provide an evaluation", "wdl": wdl_text, "expected_score": expected_score})
    if not lines:
        raise ValueError("The engine returned no move. Try a longer thinking time.")
    return {"fen": board.fen(), "engine": engine_name, "lines": lines}


def describe_continuation(board, moves):
    probe = board.copy()
    san_moves, validated = [], []
    reply = reply_simple = future_simple = ''
    for index, uci in enumerate(moves):
        try:
            move = chess.Move.from_uci(uci)
        except (ValueError, TypeError, AttributeError):
            break
        if move not in probe.legal_moves:
            break
        prefix = f'{probe.fullmove_number}.' if probe.turn else (f'{probe.fullmove_number}...' if not san_moves else '')
        san = probe.san(move)
        san_moves.append(prefix + san)
        validated.append(move.uci())
        if index == 1:
            reply = san + ' — ' + describe_move(probe, move)
            reply_simple = simple_move(probe, move)
        if index == 2:
            future_simple = simple_move(probe, move)
        probe.push(move)
    return {
        'pv': ' '.join(san_moves), 'pv_moves': validated,
        'reply': reply, 'reply_move': validated[1] if len(validated) > 1 else '', 'reply_simple': reply_simple,
        'future_move': validated[2] if len(validated) > 2 else '', 'future_simple': future_simple,
    }


def prediction_status(line):
    prediction = line.get('prediction')
    if not prediction or prediction['completed_plies'] >= prediction['requested_plies']:
        return ''
    reason = ('position ends' if prediction['terminal'] else 'lookahead budget reached'
              if prediction['budget_exhausted'] else 'engine returned a shorter line')
    return f"{prediction['completed_plies']} of {prediction['requested_plies']} plies · {reason}"
