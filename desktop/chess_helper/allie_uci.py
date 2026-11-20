"""Optional Allie 2.x adapter using the upstream's pinned history-based API."""
import argparse
import json
from pathlib import Path
import sys

import chess

REVISIONS={
    'allie-2.0':'5e9e7f9341459eb188d3fad2eb5c1c40ac88d37b',
    'allie-2.1':'d2545701ff5af46a51ac947911844f779b355a08',
}


def analyze(model,board,elo,count):
    if board.root().fen()!=chess.STARTING_FEN:
        raise ValueError('Allie needs the game history from the standard starting position.')
    output=model.analyze([move.uci() for move in board.move_stack],white_elo=elo,black_elo=elo)
    w,d,l=output['wdl']
    legal={move.uci() for move in board.legal_moves}
    moves=[move for move in output['moves'] if move in legal][:count]
    return moves,max(-1000,min(1000,round((w-l)*1000)))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('model',choices=REVISIONS)
    parser.add_argument('folder',type=Path)
    parser.add_argument('--download',action='store_true')
    args=parser.parse_args()
    repo='yimingzhang/'+args.model
    revision=REVISIONS[args.model]
    if args.download:
        from huggingface_hub import snapshot_download
        snapshot_download(repo,revision=revision,local_dir=args.folder)
        return
    from transformers import AutoModel
    model=AutoModel.from_pretrained(str(args.folder),trust_remote_code=True,local_files_only=True)
    board=chess.Board()
    elo,count=1500,1
    for line in sys.stdin:
        fields=line.split()
        if not fields:continue
        match fields[0]:
            case 'uci':
                print('id name Allie '+args.model.split('-')[1]+'\noption name Elo type spin default 1500 min 600 max 2600\noption name MultiPV type spin default 1 min 1 max 10\nuciok',flush=True)
            case 'isready':print('readyok',flush=True)
            case 'setoption':
                if fields[2]=='Elo':elo=int(fields[-1])
                if fields[2]=='MultiPV':count=max(1,min(10,int(fields[-1])))
            case 'position':
                chunks=line.split(' moves ',1)
                board=chess.Board(chunks[0].strip()[13:]) if fields[1]=='fen' else chess.Board()
                if len(chunks)>1:
                    for move in chunks[1].split():board.push_uci(move)
            case 'go':
                try:moves,score=analyze(model,board,elo,count)
                except ValueError as exc:
                    print('info string '+str(exc),flush=True)
                    moves=[]
                for rank,move in enumerate(moves,1):
                    print(f'info depth 1 multipv {rank} score cp {score} pv {move}',flush=True)
                print('bestmove '+(moves[0] if moves else '0000'),flush=True)
            case 'quit':return


if __name__=='__main__':main()
