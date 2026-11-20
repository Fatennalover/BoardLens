"""Local, low-frequency recognition of visible result banners, separate from board inference."""
import os,re,sys,threading,time,tempfile,subprocess
from pathlib import Path
import cv2
from PySide6.QtCore import QObject,Signal


def reason(text):
    s=re.sub(r'[^a-z0-9½/ .-]',' ',text.lower());s=' '.join(s.split())
    if len(s)>180:return None
    patterns=(r'\b(checkmate|stalemate|game over|game aborted|game drawn)\b',
              r'\b(you|white|black) (won|wins|lost|loses|resigned)\b',
              r'\b(won|wins|draw|drawn|lost|loss) (by |on |due to )(resignation|timeout|time|agreement|repetition|abandonment|insufficient material|50.move rule)')
    return text.strip() if any(re.search(p,s) for p in patterns) else None


def read_text(image):
    if sys.platform=='darwin':
        import objc
        from Foundation import NSData,NSAutoreleasePool
        pool=NSAutoreleasePool.alloc().init()
        try:
            objc.loadBundle('Vision',bundle_path='/System/Library/Frameworks/Vision.framework',module_globals={})
            request=objc.lookUpClass('VNRecognizeTextRequest').new();request.setRecognitionLevel_(0);request.setUsesLanguageCorrection_(False)
            data=cv2.imencode('.png',image)[1].tobytes();handler=objc.lookUpClass('VNImageRequestHandler').alloc().initWithData_options_(NSData.dataWithBytes_length_(data,len(data)),{})
            answer=handler.performRequests_error_([request],None)
            ok,error=answer if isinstance(answer,tuple) else (answer,None)
            if not ok:raise RuntimeError(str(error))
            return [str(observation.topCandidates_(1)[0].string()) for observation in request.results() if observation.topCandidates_(1)]
        finally:del pool
    if sys.platform=='win32':
        # Windows' installed OCR language packs; runs without a console window.
        with tempfile.TemporaryDirectory(prefix='boardlens-result-') as tmp:
            path=Path(tmp)/'frame.png';cv2.imwrite(str(path),image)
            script=Path(__file__).with_name('windows_ocr.ps1')
            p=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',str(script),str(path)],capture_output=True,text=True,timeout=8,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            if p.returncode:raise RuntimeError('Windows OCR unavailable')
            return p.stdout.splitlines()
    return []


class ResultWatcher(QObject):
    found=Signal(str,str)
    def __init__(self,parent=None):super().__init__(parent);self.busy=False;self.next=0.;self.closed=False;self.error=''
    def offer(self,image,region,fen):
        if self.closed or self.busy or time.monotonic()<self.next:return
        self.next=time.monotonic()+1.;self.busy=True
        margin=region.size//3;x=max(0,region.x-margin);y=max(0,region.y-margin)
        crop=image[y:min(image.shape[0],region.y+region.size+margin),x:min(image.shape[1],region.x+region.size+margin)].copy()
        scale=min(1,1000/max(crop.shape[:2]));crop=cv2.resize(crop,None,fx=scale,fy=scale)
        def work():
            try:
                for text in read_text(crop):
                    result=reason(text)
                    if result and not self.closed:self.found.emit(fen,result);break
            except Exception as exc:self.error=str(exc)
            finally:self.busy=False
        threading.Thread(target=work,daemon=True,name='BoardLens-result-banner').start()
    def close(self):self.closed=True
