"""NumPy inference for pbaer's v3.1-nano model capsule (MIT)."""
import json
import math
from pathlib import Path
import sys

import chess
import numpy as np

SLIDING=((1,0),(1,1),(0,1),(-1,1),(-1,0),(-1,-1),(0,-1),(1,-1))
KNIGHT=((2,1),(2,-1),(-2,1),(-2,-1),(1,2),(1,-2),(-1,2),(-1,-2))


def canonical_square(board,square):
    return square if board.turn else square^56


def policy_index(board,move):
    start=canonical_square(board,move.from_square)
    end=canonical_square(board,move.to_square)
    dr,df=end//8-start//8,end%8-start%8
    if move.promotion in (chess.KNIGHT,chess.BISHOP,chess.ROOK):
        kind=64+(df+1)*3+move.promotion-2
    elif (dr,df) in KNIGHT:
        kind=56+KNIGHT.index((dr,df))
    else:
        distance=max(abs(dr),abs(df))
        kind=SLIDING.index((dr//abs(dr) if dr else 0,df//abs(df) if df else 0))*7+distance-1
    return start*73+kind


def feature_planes(board):
    planes=np.zeros((21,64),dtype=np.float32)
    piece_planes='prnbqk'
    for square,piece in board.piece_map().items():
        planes[piece_planes.index(piece.symbol().lower())+(0 if piece.color==board.turn else 6),
               canonical_square(board,square)]=1
    for n,color in enumerate((board.turn,not board.turn)):
        planes[12+n*2]=board.has_kingside_castling_rights(color)
        planes[13+n*2]=board.has_queenside_castling_rights(color)
    if board.ep_square is not None:planes[16,canonical_square(board,board.ep_square)]=1
    planes[17]=min(1.,board.halfmove_clock/100)
    planes[18]=min(2.,board.fullmove_number/100)
    planes[19]=1
    planes[20]=1 if board.is_repetition(3) else .5 if board.is_repetition(2) else 0
    return planes


class NeuralChess:
    def __init__(self,folder):
        capsule=json.loads((folder/'capsule.json').read_text())
        if capsule['model_id']!='v3.1-nano' or len(capsule['graph'])!=14:
            raise ValueError('Unsupported Neural-Chess capsule.')
        data=np.fromfile(folder/'weights.bin',dtype='<f4')
        self.weights={item['name']:data[item['offset']:item['offset']+item['length']].reshape(item['shape'])
                      for item in capsule['tensors']}
        squares=np.arange(64)
        self.relative=(squares[:,None]//8-squares[None,:]//8+7)*15+squares[:,None]%8-squares[None,:]%8+7
        self.erf=np.vectorize(math.erf,otypes=[np.float32])

    def linear(self,x,name):
        return x@self.weights[name+'.weight'].reshape(-1,x.shape[-1]).T+self.weights[name+'.bias']

    def norm(self,x,name):
        centered=x-x.mean(axis=-1,keepdims=True)
        return centered/np.sqrt(np.mean(centered**2,axis=-1,keepdims=True)+1e-5)*self.weights[name+'.weight']+self.weights[name+'.bias']

    def predict(self,board):
        x=np.maximum(0,self.linear(feature_planes(board).T,'stem.embed'))+self.weights['pos_emb'][0]
        for i in range(8):
            base=f'blocks.{i}.'
            q,k,v=self.linear(self.norm(x,base+'ln1'),base+'attn.qkv').reshape(64,3,4,8).transpose(1,2,0,3)
            score=q@k.transpose(0,2,1)/math.sqrt(8)+self.weights[base+'attn.rel_bias'][:,self.relative]
            score=np.exp(score-score.max(axis=2,keepdims=True))
            mix=((score/score.sum(axis=2,keepdims=True))@v).transpose(1,0,2).reshape(64,32)
            x=x+self.linear(mix,base+'attn.proj')
            hidden=self.linear(self.norm(x,base+'ln2'),base+'ffn.0')
            x=x+self.linear(hidden*.5*(1+self.erf(hidden/math.sqrt(2))),base+'ffn.2')
        x=self.norm(x,'final_ln')
        logits=self.linear(x,'policy_head').ravel()
        value=np.tanh(self.linear(np.maximum(0,self.linear(x.mean(axis=0),'value_fc1')),'value_fc2'))[0]
        return sorted(board.legal_moves,key=lambda m:float(logits[policy_index(board,m)]),reverse=True),float(value)


def main():
    model=NeuralChess(Path(sys.argv[1]))
    board=chess.Board()
    multipv=1
    for line in sys.stdin:
        args=line.strip().split()
        if not args:continue
        match args[0]:
            case 'uci':
                print('id name Neural-Chess v3.1 Nano\noption name MultiPV type spin default 1 min 1 max 10\nuciok',flush=True)
            case 'isready':print('readyok',flush=True)
            case 'setoption':
                if args[2]=='MultiPV':multipv=max(1,min(10,int(args[-1])))
            case 'position':
                parts=line.split(' moves ',1)
                board=chess.Board(parts[0].strip()[13:]) if args[1]=='fen' else chess.Board()
                if len(parts)>1:
                    for move in parts[1].split():board.push_uci(move)
            case 'go':
                moves,value=model.predict(board)
                # Bounded model value is surfaced as an expected result, not engine centipawns.
                for i,move in enumerate(moves[:multipv],1):
                    print(f'info depth 1 multipv {i} score cp {round(value*1000)} pv {move.uci()}',flush=True)
                print('bestmove '+(moves[0].uci() if moves else '0000'),flush=True)
            case 'quit':return


if __name__=='__main__':main()
