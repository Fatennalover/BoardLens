"""Local, calibration-free chess tile inference using the MIT Fenshot CNN."""
from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

import chess
import cv2
import numpy as np

from .core import board_from_symbols, ordered_symbols
from .detection import grid_candidates,refine_grid
from .vision import Detection, checker_score, complete_grid
from .coordinates import rank_orientation

LABELS = ".KQRBNPkqrbnp"


@dataclass(frozen=True)
class ReadQuality:
    piece: float = .70
    average: float = .90
    grid: float = .90


@dataclass
class Read:
    symbols: list[str]
    confidence: np.ndarray
    probabilities: np.ndarray
    white_bottom: bool
    turn_hint: bool | None
    image: np.ndarray
    detection: Detection | None = None

    @property
    def reliable(self):
        return self.meets(ReadQuality())

    def meets(self, quality):
        return bool(self.confidence.min() >= quality.piece and self.confidence.mean() >= quality.average
                    and self.symbols.count("K") == 1 and self.symbols.count("k") == 1)


def orientation(symbols):
    white = [i // 8 for i, symbol in enumerate(symbols) if symbol == "P"]
    black = [i // 8 for i, symbol in enumerate(symbols) if symbol == "p"]
    if white and black and abs(np.mean(white) - np.mean(black)) > .5:
        return bool(np.mean(white) > np.mean(black))
    wk, bk = symbols.index("K") if "K" in symbols else 60, symbols.index("k") if "k" in symbols else 4
    return wk > bk


def last_move_turn(image, symbols, white_bottom=None):
    """Last-move squares normally share a highlight distinct from both tile colors."""
    h, w = image.shape[:2]
    rows,cols=np.indices((8,8)).reshape(2,-1)
    samples=[image[((rows+dy)*h/8).astype(int),((cols+dx)*w/8).astype(int)]
             for dy,dx in ((.08,.08),(.08,.92),(.92,.08),(.92,.92))]
    colors=np.median(samples,axis=0)
    parity = np.indices((8,8)).sum(0).ravel() % 2
    means = [np.median(colors[parity == p], axis=0) for p in (0,1)]
    errors = np.linalg.norm(colors - np.array(means)[parity], axis=1)
    highlighted = np.flatnonzero(errors > 45)
    if len(highlighted) != 2:
        return None
    origin, destination = sorted(highlighted,key=lambda index:symbols[index]!='.')
    piece = symbols[destination]
    if symbols[origin] != '.' or piece == '.':
        return None
    sr,sf = divmod(int(origin),8)
    dr,df = divmod(int(destination),8)
    advance, shift = dr-sr, abs(df-sf)
    span = abs(advance)
    kind = piece.lower()
    if white_bottom is None:
        white_bottom = orientation(symbols)
    plausible = {
        'p': advance * (-1 if piece.isupper()==white_bottom else 1) in (1,2) and shift <= 1 and (span==1 or shift==0),
        'n': {span,shift}=={1,2},
        'b': span==shift,
        'r': not (span and shift),
        'q': span==shift or not (span and shift),
        'k': max(span,shift)==1 or (span==0 and shift==2),
    }
    if plausible[kind]:
        return not piece.isupper()
    return None


class Recognizer:
    def __init__(self):
        self.session = None
        self.quality = ReadQuality()

    def load(self):
        if self.session is None:
            import onnxruntime as ort
            options = ort.SessionOptions()
            options.intra_op_num_threads = 2
            options.inter_op_num_threads = 1
            model = Path(__file__).parent / "assets/models/chess-tiles-v2.onnx"
            self.session = ort.InferenceSession(str(model), sess_options=options,
                                               providers=["CPUExecutionProvider"])

    def read(self, image, white_bottom=None):
        self.load()
        # Match the model's luma conversion and normal bilinear sampling.
        gray = image[...,2].astype(np.float32)*.299 + image[...,1].astype(np.float32)*.587 + image[...,0].astype(np.float32)*.114
        probabilities = self._classify(gray, cv2.INTER_LINEAR)
        result = self._read_result(image, probabilities, white_bottom)
        if not result.meets(self.quality) and min(gray.shape) >= 768 and result.confidence.mean() >= .85:
            # Retina downsampling can alias small decorations into piece edges.
            # Retry the same grid with area sampling and retain known squares.
            retry = self._read_result(image, self._classify(gray, cv2.INTER_AREA), white_bottom)
            if retry.meets(self.quality) and all(
                before == after or confidence < .90
                for before, after, confidence in zip(result.symbols, retry.symbols, result.confidence)
            ):
                return retry
        return result

    def read_tracked(self, image, previous=None):
        # A visually obstructed frame cannot establish a new position. If all
        # previously occupied squares still contain the same piece silhouettes,
        # treat the new shapes on empty squares as temporary annotations.
        from .vision import checker_score
        if not complete_grid(image,self.quality.grid):
            if previous is not None and checker_score(image) >= .75 and same_piece_shapes(previous, image):
                return replace(previous, image=image), previous
            return None, previous
        current = self.read(image)
        if current.meets(self.quality):
            return current, current
        if previous is not None and same_piece_shapes(previous, image):
            return replace(previous, image=image), previous
        return None, previous

    def read_visible_squares(self, image, top_left, columns, rows, white_bottom):
        file = chess.square_file(top_left)
        rank = chess.square_rank(top_left)
        file_step = 1 if white_bottom else -1
        rank_step = -file_step
        if (not 1 <= columns <= 8 or not 1 <= rows <= 8
                or not 0 <= file + (columns-1)*file_step < 8
                or not 0 <= rank + (rows-1)*rank_step < 8):
            raise ValueError('The selection extends beyond the board. Check the coordinates and orientation.')
        if image.shape[1] < 8 * columns or image.shape[0] < 8 * rows:
            raise ValueError('The selected squares are too small to read reliably.')
        self.load()
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255
        normalized = cv2.resize(gray, (32*columns,32*rows), interpolation=cv2.INTER_LINEAR)
        tiles = normalized.reshape(rows,32,columns,32).transpose(0,2,1,3).reshape(-1,1024).copy()
        probabilities = self.session.run(['probs'], {'tiles': tiles})[0]
        visible = {}
        for index, values in enumerate(probabilities):
            row, col = divmod(index, columns)
            square = chess.square(file + col*file_step, rank + row*rank_step)
            confidence = float(values.max())
            visible[square] = (LABELS[values.argmax()] if confidence >= .70 else None, confidence)
        return visible

    def _classify(self, gray, interpolation):
        # Inference expects tiles in A1..H8 order.
        board = cv2.resize(gray, (256,256), interpolation=interpolation) / 255
        tiles = board.reshape(8,32,8,32).transpose(0,2,1,3)[::-1].reshape(64,1024).copy()
        output = self.session.run(["probs"], {"tiles": tiles})[0]
        probabilities = output.reshape(8,8,13)[::-1].reshape(64,13).copy()
        uncertain = np.flatnonzero(probabilities.max(1) < .70)
        if uncertain.size:
            display_tiles = tiles.reshape(8,8,32,32)[::-1].reshape(64,32,32)
            self._read_overflow(display_tiles, probabilities, uncertain)
        return probabilities

    def _read_result(self, image, probabilities, white_bottom):
        symbols = [LABELS[index] for index in probabilities.argmax(1)]
        labeled=rank_orientation(image) if white_bottom is None else white_bottom
        bottom = orientation(symbols) if labeled is None else labeled
        return Read(symbols, probabilities.max(1), probabilities,bottom,last_move_turn(image,symbols,bottom),image)

    def _read_overflow(self, tiles, probabilities, uncertain):
        # Tall piece decorations can extend into the square above. Check for
        # a continuous shape crossing that edge before reading it as empty.
        candidates = []
        for index in uncertain:
            if index >= 56 or probabilities[index + 8, 1:].max() < .70:
                continue
            tile = tiles[index]
            center = tile[:, 5:27]
            background = np.median(center[2:20])
            if (np.abs(center[2:20] - background) > .12).sum() > 4:
                continue
            below = tiles[index + 8]
            below_background = np.median(np.concatenate((below[2:14, 4:7], below[2:14, 25:28]), axis=1))
            last_rows = center[-2:]
            next_rows = below[:2, 5:27]
            connected = ((np.abs(last_rows - background) > .12).all(axis=0)
                         & (np.abs(next_rows - below_background) > .12).all(axis=0)
                         & (np.abs(last_rows.mean(axis=0) - next_rows.mean(axis=0)) < .10))
            if connected.sum() < 5:
                continue
            cleared = tile.copy()
            cleared[20:, 5:27] = background
            candidates.append((index, cleared.ravel()))
        if candidates:
            result = self.session.run(["probs"], {"tiles": np.stack([tile for _, tile in candidates])})[0]
            for (index, _), prediction in zip(candidates, result):
                if prediction[0] >= .70:
                    probabilities[index] = prediction

    def read_candidate(self,image,detection):
        d=detection
        crop=image[d.y:d.y+d.size,d.x:d.x+d.size]
        if crop.shape[:2]!=(d.size,d.size) or not complete_grid(crop,self.quality.grid):return None
        result=self.read(crop)
        result.detection=d
        if not result.meets(self.quality):
            height,width = image.shape[:2]
            side = min(height,width)
            geometries = [refine_grid(image,d)]
            if d.size >= side*.95:
                geometries.extend(Detection(x,y,side,d.score) for x in {0,width-side} for y in {0,height-side}
                                  if abs(d.x-x)<side*.05 and abs(d.y-y)<side*.05)
            for refined in dict.fromkeys(geometries):
                if refined == d:
                    continue
                crop=image[refined.y:refined.y+refined.size,refined.x:refined.x+refined.size]
                if complete_grid(crop,self.quality.grid):
                    alternative=self.read(crop)
                    alternative.detection=refined
                    if alternative.meets(self.quality):
                        return alternative
                    if alternative.confidence.mean()>result.confidence.mean():
                        result=alternative
        return result

    def scan(self, image, hint=None, cancelled=None):
        # A screenshot containing exactly the board has no outside border for
        # the grid finder to vote on. Validate and read its complete 8x8 grid.
        if image.shape[0] == image.shape[1] and complete_grid(image,self.quality.grid):
            result = self.read(image)
            if result.meets(self.quality):
                try:
                    position_from_read(result)
                    result.detection = Detection(0,0,image.shape[0],1.)
                    return result
                except ValueError:
                    pass
        if hint:
            x,y,size = hint
            if min(x,y) >= 0 and x+size <= image.shape[1] and y+size <= image.shape[0]:
                crop = image[y:y+size,x:x+size]
                if complete_grid(crop,self.quality.grid):
                    result = self.read(crop)
                    if result.meets(self.quality):
                        result.detection = Detection(x,y,size,1.)
                        return result
        search = image.copy()
        for _ in range(3):
            best, quality = None, -1
            candidates = grid_candidates(search, cancelled=cancelled)
            for detection in candidates:
                if cancelled and cancelled.is_set():
                    return None
                x,y,size = detection.x,detection.y,detection.size
                crop = image[y:y+size,x:x+size]
                if crop.shape[:2] != (size,size):
                    continue
                if not complete_grid(crop,self.quality.grid):
                    continue
                result = self.read_candidate(image,detection)
                if result is None:continue
                # Missing a border file often yields many confident empty
                # squares. Grid coverage must outweigh that artificial gain.
                score = float(result.confidence.mean()) + .30*detection.score + .00001*size
                if result.meets(self.quality) and score > quality:
                    try:
                        position_from_read(result)
                    except ValueError:
                        continue
                    best, quality = result, score
            if best:
                return best
            if not candidates:
                break
            # Empty decorative boards and this app's mirror must not hide a
            # smaller populated board elsewhere in the same screenshot.
            for d in candidates:
                search[d.y:d.y+d.size,d.x:d.x+d.size] = (24,30,36)
        return None

    def scan_all(self, image, cancelled=None, limit=None):
        height, width = image.shape[:2]
        if height == width and complete_grid(image,self.quality.grid):
            read = self.read(image)
            if valid_read(read,self.quality):
                read.detection = Detection(0, 0, height, 1.)
                return [read]

        reads = []
        search = image
        for _ in range(3):
            candidates = grid_candidates(search, cancelled=cancelled, limit=None)
            rejected = []
            for candidate in candidates:
                if cancelled is not None and cancelled.is_set():
                    return []
                if any(board_overlap(candidate, read.detection) > .35 for read in reads):
                    continue
                read = self.read_candidate(image, candidate)
                if valid_read(read,self.quality):
                    reads.append(read)
                    if limit is not None and len(reads) >= limit:
                        break
                else:
                    rejected.append(candidate)
            if reads or not rejected:
                break
            # An oversized decorative board can dominate discovery of a smaller
            # populated board. Mask candidates only after none can be accepted.
            if search is image:
                search = image.copy()
            for d in rejected:
                search[d.y:d.y + d.size, d.x:d.x + d.size] = (24, 30, 36)
        return sorted(reads, key=lambda r: (r.detection.y // max(1, r.detection.size // 2), r.detection.x))


def valid_read(read,quality):
    if read is None or not read.meets(quality):
        return False
    try:
        position_from_read(read)
    except ValueError:
        return False
    return True


def same_piece_shapes(previous, image):
    width = 24

    def contrast_tiles(frame):
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        small = cv2.resize(gray, (8 * width, 8 * width), interpolation=cv2.INTER_AREA)
        tiles = small.reshape(8, width, 8, width).transpose(0, 2, 1, 3).reshape(64, width, width).astype(np.float32)
        corners = tiles[:, (2, 2, -3, -3), (2, -3, 2, -3)]
        return tiles[:, 3:-3, 3:-3] - np.median(corners, axis=1)[:, None, None]

    occupied = np.asarray(previous.symbols) != '.'
    reference, current = (contrast_tiles(frame)[occupied] for frame in (previous.image, image))
    foreground = np.abs(reference) >= 36
    area = foreground.sum(axis=(1, 2))
    agreement = (foreground & (np.abs(reference - current) < 34)).sum(axis=(1, 2))
    return bool(area.size and (area >= 15).all() and (agreement >= area * .76).all())


def visible_attacks(visible):
    """Find geometric attacks wholly inside known squares of a partial board."""
    board = chess.Board(None)
    occupied = {}
    for square in chess.SQUARES:
        symbol = visible.get(square,(None,0))[0]
        if symbol is None:
            # An unknown square ends a ray. It is never shown as a piece.
            board.set_piece_at(square,chess.Piece(chess.PAWN,chess.WHITE))
        elif symbol != '.':
            occupied[square] = chess.Piece.from_symbol(symbol)
            board.set_piece_at(square,occupied[square])
    return [(origin,target) for origin,piece in occupied.items() for target in board.attacks(origin)
            if target in occupied and occupied[target].color != piece.color]


def board_overlap(a,b):
    intersection=max(0,min(a.x+a.size,b.x+b.size)-max(a.x,b.x))*max(0,min(a.y+a.size,b.y+b.size)-max(a.y,b.y))
    return intersection/max(1,min(a.size,b.size)**2)


def position_from_read(read, turn_override=None, previous=None):
    """Recover the visible position. Turn/history metadata is kept when tracked."""
    if getattr(read,'exact_fen',None):
        board=chess.Board(read.exact_fen)
        if turn_override is not None:board.turn=turn_override
        return board,True
    turn = turn_override if turn_override is not None else read.turn_hint
    if read.symbols == ordered_symbols(chess.Board(), read.white_bottom):
        board = chess.Board()
        if turn_override is not None:
            board.turn = turn_override
        return board, True
    if previous is not None and turn_override is None:
        from .core import PositionTracker
        tracker=PositionTracker(previous)
        state,_=tracker.update(read.symbols,read.white_bottom)
        if state=='unmatched':state,_=tracker.reconcile(read.symbols,read.white_bottom)
        if state!='unmatched':return tracker.board,True
        raise ValueError("Waiting for a complete legal move; the previous turn is retained.")
    if previous is None and turn_override is None:
        from .core import PositionTracker
        opening=PositionTracker(chess.Board())
        state,_=opening.update(read.symbols,read.white_bottom)
        if state=='unmatched':state,_=opening.reconcile(read.symbols,read.white_bottom)
        if state!='unmatched' and (turn is None or turn==opening.board.turn):
            return opening.board,True
    selected_turn = turn if turn is not None else chess.WHITE
    try:
        board = board_from_symbols(read.symbols, read.white_bottom, selected_turn)
    except ValueError:
        if turn_override is not None:
            raise
        board = board_from_symbols(read.symbols, read.white_bottom, not selected_turn)
        turn = not selected_turn
    # A checked king must belong to the side to move. Never let an invalid turn
    # suppress an otherwise recognized board.
    eligible = []
    for king, rook, flag in ((chess.E1,chess.H1,"K"),(chess.E1,chess.A1,"Q"),
                              (chess.E8,chess.H8,"k"),(chess.E8,chess.A8,"q")):
        color = flag.isupper()
        if board.piece_at(king) == chess.Piece(chess.KING,color) and board.piece_at(rook) == chess.Piece(chess.ROOK,color):
            eligible.append(flag)
    board.set_castling_fen("".join(eligible) or "-")
    if previous is not None:
        board.castling_rights &= previous.castling_rights
    return board, turn is not None
