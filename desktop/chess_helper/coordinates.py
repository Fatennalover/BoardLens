"""Small local rank-label reader. Abstains when coordinates are absent/unclear."""
from functools import lru_cache
from pathlib import Path
import json
import cv2
import numpy as np


@lru_cache(maxsize=1)
def templates():
    data=json.loads((Path(__file__).parent/'assets/models/rank-labels.json').read_text())
    return [(int(k),np.array(v,dtype=np.float32).reshape(24,16)/255) for k,items in data.items() for v in items]


def normalized(mask):
    return cv2.resize(mask.astype(np.float32),(16,24),interpolation=cv2.INTER_AREA)


def rank_orientation(image):
    """White bottom -> ranks 8..1 down the left edge; Black -> 1..8.

    Require multiple matching labels and a clear margin over the reverse order.
    A piece silhouette or one ambiguous digit cannot flip the board.
    """
    h,w=image.shape[:2];cell=min(h,w)/8
    if cell<20 or abs(h-w)>cell*.1:return None
    votes=[]
    for row in range(8):
        x0,y0=round(cell*.015),round((row+.015)*cell)
        patch=image[y0:round((row+.29)*cell),x0:round(cell*.25)].astype(np.float32)
        if patch.size==0:continue
        bg=np.median(patch.reshape(-1,3),axis=0)
        mask=(np.linalg.norm(patch-bg,axis=2)>35).astype(np.uint8)
        n,labels,stats,_=cv2.connectedComponentsWithStats(mask)
        candidates=[]
        for at in range(1,n):
            x,y,cw,ch,area=stats[at]
            if not (.025*cell<=cw<=.18*cell and .07*cell<=ch<=.25*cell and area>=5):continue
            glyph=normalized((labels[y:y+ch,x:x+cw]==at).astype(np.float32))
            scores={digit:1. for digit in range(1,9)}
            for digit,tpl in templates():scores[digit]=min(scores[digit],float(np.mean((glyph-tpl)**2)))
            forward,reverse=scores[8-row],scores[row+1]
            candidates.append((min(forward,reverse),forward,reverse))
        if candidates:
            _,a,b=min(candidates)
            if min(a,b)<.18:votes.append((a,b))
    if len(votes)<4:return None
    good_white=sum(a+.035<b for a,b in votes)
    good_black=sum(b+.035<a for a,b in votes)
    if good_white>=4 and good_white-good_black>=3:return True
    if good_black>=4 and good_black-good_white>=3:return False
    return None
