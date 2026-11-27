"""Reproducible checks of screenshot discovery and timed UCI analysis."""
import argparse
from contextlib import ExitStack
import json
from pathlib import Path
from time import perf_counter, process_time
from unittest.mock import patch

import chess
import cv2
import numpy as np

from chess_helper.core import SearchSettings
from chess_helper.engine import EngineJob, EngineSession
from chess_helper import recognition
from chess_helper.recognition import Recognizer, position_from_read


def timing(samples):
    return {key: round(float(value),2) for key,value in (
        ('median_ms',np.median(samples)),('p95_ms',np.quantile(samples,.95)),('worst_ms',max(samples)))}


def screenshot_cases(directory):
    manifest = json.loads((directory/'testset-manifest.json').read_text())
    for name, expected in manifest.items():
        image = cv2.imread(str(directory/name))
        placement = expected['fen'] if expected['expect']=='match' else None
        yield name,image,placement,None,expected['orientation']
    yield 'non_board',cv2.imread(str(directory/'reddit-chrome-no-board.png')),None,0,None
    image = cv2.imread(str(directory/'chesscom-starting-board.png'))
    for rows,cols,side in ((1,1,128),(1,2,256),(1,3,256),(2,2,240),(2,4,216),(4,4,192)):
        board = cv2.resize(image,(side,side),interpolation=cv2.INTER_AREA)
        canvas = np.full((rows*(side+20)+20,cols*(side+20)+20,3),31,np.uint8)
        for row in range(rows):
            for col in range(cols):
                x,y = 20+col*(side+20),20+row*(side+20)
                canvas[y:y+side,x:x+side] = board
        yield f'{rows*cols} boards at {side}px',canvas,chess.STARTING_BOARD_FEN,rows*cols,'white'


def timed_calls(function, totals, stage):
    def measure(*args, **kwargs):
        start = perf_counter()
        try:
            return function(*args, **kwargs)
        finally:
            totals[stage] += (perf_counter() - start) * 1000
    return measure


def screen_trials(directory, count, track_stages=False):
    recognizer = Recognizer()
    recognizer.load()
    report = {}
    stages = dict(grid=0., pieces=0., position=0.)
    targets = (
        (recognition, 'grid_candidates', 'grid'),
        (recognition, 'complete_grid', 'grid'),
        (recognition, 'refine_grid', 'grid'),
        (recognizer, 'read', 'pieces'),
        (recognition, 'position_from_read', 'position'),
    )
    cpu_start = process_time()
    wall_start = perf_counter()
    with ExitStack() as stack:
        if track_stages:
            for owner, name, stage in targets:
                measured = timed_calls(getattr(owner,name), stages, stage)
                stack.enter_context(patch.object(owner,name,measured))
        for name,image,placement,expected,bottom in screenshot_cases(directory):
            assert image is not None, name
            latencies, found, correct = [], [], 0
            stage_samples = {stage: [] for stage in stages}
            for _ in range(count):
                for stage in stages:
                    stages[stage] = 0.
                start = perf_counter()
                reads = recognizer.scan_all(image)
                latencies.append((perf_counter()-start)*1000)
                for stage, elapsed in stages.items():
                    stage_samples[stage].append(elapsed)
                found.append(len(reads))
                if placement is None:
                    correct += not reads
                else:
                    matching = [read for read in reads if position_from_read(read)[0].board_fen()==placement
                                and read.white_bottom==(bottom=='white')]
                    correct += (len(matching)==expected==len(reads)) if expected is not None else bool(matching)
            report[name] = dict(timing(latencies),found_min=min(found),found_max=max(found),correct_trials=correct)
            if track_stages:
                report[name]['stages'] = {stage: timing(samples) for stage,samples in stage_samples.items()}
    return {'cases':report,'process_cpu_s':round(process_time()-cpu_start,2),'wall_s':round(perf_counter()-wall_start,2)}


def engine_trials(path, count):
    session = EngineSession()
    root = chess.Board()
    boards = [root.copy()]
    for uci in ('e2e4','c7c5','g1f3','d7d6','d2d4','c5d4'):
        root.push_uci(uci)
        boards.append(root.copy())
    first, final = [], []
    try:
        session.warm(path)
        for index in range(count):
            board = boards[index%len(boards)]
            started = perf_counter()
            streaming = []
            job = EngineJob()
            job.session = session
            job.on_update = lambda _: streaming.append((perf_counter()-started)*1000)
            settings = SearchSettings(seconds=.12,multipv=3,threads=1,hash_mb=32,
                                      prediction_plies=8,prediction_seconds=.35)
            result = job.run(path,board,settings)
            done = (perf_counter()-started)*1000
            first.append(streaming[0] if streaming else done)
            final.append(done)
            assert len(result['lines'])==3
            for line in result['lines']:
                probe = board.copy()
                for move in line['pv_moves']:
                    probe.push_uci(move)
    finally:
        session.close()
    return {'first_valid':timing(first),'complete':timing(final)}


def mac_capture_trials(count):
    from threading import Event

    import Quartz
    from chess_helper.mac_capture import capture_frames

    display = Quartz.CGMainDisplayID()
    bounds = Quartz.CGDisplayBounds(display)
    mode = Quartz.CGDisplayCopyDisplayMode(display)
    width = Quartz.CGDisplayModeGetPixelWidth(mode)
    height = Quartz.CGDisplayModeGetPixelHeight(mode)
    if width < 1064 or height < 672:
        raise ValueError('The main display must fit all eight benchmark crops.')
    spec = dict(key='display', name='Main display', geometry=(*bounds.origin, *bounds.size),
                width=width, height=height, masks=[])
    report = {}
    for region_count in (1, 2, 8):
        crops = [(40 + (index % 4) * 256, 160 + (index // 4) * 256, 256)
                 for index in range(region_count)]
        requests = [dict(spec, crop=crop) for crop in crops]
        samples = []
        for _ in range(count + 1):
            start = perf_counter()
            frames = capture_frames(requests, set(), Event())
            assert sorted(frame[3][:3] for frame in frames) == sorted(crops)
            assert all(frame[2].shape == (256, 256, 3) for frame in frames)
            samples.append((perf_counter() - start) * 1000)
        report[region_count] = timing(samples[1:])
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixtures',type=Path,default=Path(__file__).resolve().parents[1]/'tests/fixtures')
    parser.add_argument('--samples',type=int,default=15)
    parser.add_argument('--stockfish')
    parser.add_argument('--stages',action='store_true',help='time grid, piece, and position-validation calls')
    parser.add_argument('--mac-capture',action='store_true',help='benchmark macOS display-region capture only')
    args = parser.parse_args()
    if args.samples<1:
        parser.error('--samples must be positive')
    if args.mac_capture:
        import sys
        if sys.platform != 'darwin':
            parser.error('--mac-capture requires macOS')
        print(json.dumps({'samples':args.samples,'capture':mac_capture_trials(args.samples)},indent=2))
        return
    report = {'samples':args.samples,'recognition':screen_trials(args.fixtures,args.samples,args.stages)}
    if args.stockfish:
        report['engine'] = engine_trials(args.stockfish,args.samples)
    try:
        import resource
        import sys
        report['peak_rss_mib'] = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss /
                                       (1024**2 if sys.platform=='darwin' else 1024),1)
    except ImportError:
        pass
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    main()
