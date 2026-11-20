"""Generate tiny raster rank prototypes; does not distribute the source fonts."""
from pathlib import Path
import json,sys
from PIL import Image,ImageFont,ImageDraw
import cv2,numpy as np
root=Path(__file__).resolve().parents[1]
fonts=[Path(p) for p in sys.argv[1:]]
if not fonts:raise SystemExit('Pass local font paths (regular and bold sans-serif recommended).')
data={str(i):[] for i in range(1,9)}
for font in fonts:
 for size in (14,20,28,36):
  f=ImageFont.truetype(str(font),size)
  for digit in data:
   im=Image.new('L',(80,80));ImageDraw.Draw(im).text((5,5),digit,font=f,fill=255)
   im=im.crop(im.getbbox());a=np.array(im);a=(a>90).astype(np.float32)
   data[digit].append(np.rint(cv2.resize(a,(16,24),interpolation=cv2.INTER_AREA)*255).astype(int).ravel().tolist())
raw=json.dumps(data,separators=(',',':'))+'\n'
for path in [root/'desktop/chess_helper/assets/models/rank-labels.json',root/'mobile/android/app/src/main/assets/models/rank-labels.json']:
 path.write_text(raw)
