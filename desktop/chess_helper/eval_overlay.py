"""Animated, passive score panel beside the actual screen board."""
import math
from PySide6.QtCore import QRect, QRectF, Qt, QVariantAnimation, QEasingCurve, Signal
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath, QGuiApplication
from .core import evaluation_text
from .overlay import BoardOverlay


def panel_rect(board, safe):
    height=max(120,min(240,board.height()))
    if board.left()-52>=safe.left():return QRect(board.left()-52,max(safe.top(),min(board.top(),safe.bottom()-height+1)),44,height)
    if board.right()+52<=safe.right():return QRect(board.right()+8,max(safe.top(),min(board.top(),safe.bottom()-height+1)),44,height)
    width=min(212,safe.width())
    x=max(safe.left(),min(board.center().x()-width//2,safe.right()-width+1))
    y=board.top()-54 if board.top()-54>=safe.top() else board.bottom()+8
    y=max(safe.top(),min(y,safe.bottom()-46+1))
    return QRect(x,y,width,46)


class EvaluationOverlay(BoardOverlay):
    geometry_changed=Signal(object)
    def __init__(self):
        super().__init__()
        self.fraction=.5;self.target=.5;self.label='—';self.enabled=False
        self._score=(None,None,None)
        self.scale=1.;self.user_rect=None;self._drag=None;self._score_interactive=False
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents,False)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowTransparentForInput)
        self.setCursor(Qt.CursorShape.SizeAllCursor)
        self.animation=QVariantAnimation(self);self.animation.setDuration(200)
        self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.animation.valueChanged.connect(self._animate)

    def _animate(self,value):
        self.fraction=float(value);self._redraw()

    def set_score(self,board,white_bottom,cp,mate,screen,white_share=None):
        self.enabled=True;self.white_bottom=white_bottom
        self.scale=screen.devicePixelRatio() if screen else 1.
        safe=screen.availableGeometry() if screen else board.adjusted(-60,-60,60,60)
        if self.user_rect:
            rect=QRect(*self.user_rect)
            owner=next((s for s in QGuiApplication.screens() if s.availableGeometry().contains(rect.center())),screen)
            if owner:safe=owner.availableGeometry()
            rect.setWidth(min(rect.width(),safe.width()));rect.setHeight(min(rect.height(),safe.height()))
            rect.moveLeft(max(safe.left(),min(rect.left(),safe.right()-rect.width()+1)));rect.moveTop(max(safe.top(),min(rect.top(),safe.bottom()-rect.height()+1)))
        else:rect=panel_rect(board,safe)
        if not self._drag:self.setGeometry(rect)
        value=self.target
        if white_share is not None:value=white_share
        if cp is not None:value=1/(1+math.exp(-max(-1200,min(1200,cp))/220))
        if mate is not None:value=.99 if mate>0 else .01
        if cp is not None or mate is not None or white_share is not None:
            self._score=(cp,mate,white_share)
        self.label=evaluation_text(*self._score,white_bottom=white_bottom)
        side="White" if white_bottom else "Black"
        self.setAccessibleName(f"Evaluation for {side}: {self.label}")
        self.setToolTip(f"{side} perspective. Drag to move or resize from the lower-right corner.")
        if value!=self.target:
            self.animation.stop();self.target=value
            self.animation.setStartValue(self.fraction);self.animation.setEndValue(value);self.animation.start()
        self._configure_windows();self._redraw()

    def set_user_rect(self,value):
        self.user_rect=tuple(int(x) for x in value) if isinstance(value,(list,tuple)) and len(value)==4 and 40<=value[2]<=800 and 46<=value[3]<=900 else None

    def reset_position(self):self.user_rect=None;self.geometry_changed.emit(None)

    def _mac_panel(self):
        panel=super()._mac_panel()
        if not self._score_interactive:panel.make_score_interactive(self._gesture);self._score_interactive=True
        return panel

    def _configure_windows(self):
        super()._configure_windows()
        import sys
        if sys.platform=='win32':
            import ctypes
            user=ctypes.windll.user32;hwnd=int(self.winId());style=user.GetWindowLongPtrW(hwnd,-20);user.SetWindowLongPtrW(hwnd,-20,style&~0x20)

    def _gesture(self,kind,x,y,resize=False):
        if kind=='begin':self._drag=(float(x),float(y),self.geometry(),resize);return
        if not self._drag:return
        ax,ay,rect,resizing=self._drag;rect=QRect(rect);dx,dy=round(x-ax),round(y-ay)
        if resizing:rect.setWidth(max(44,min(800,rect.width()+dx)));rect.setHeight(max(46,min(900,rect.height()+dy)))
        else:rect.translate(dx,dy)
        self.user_rect=rect.getRect();self.setGeometry(rect);self._redraw()
        if kind=='end':self._drag=None;self.geometry_changed.emit(list(self.user_rect))

    def mousePressEvent(self,event):
        p=event.position();g=event.globalPosition();self._gesture('begin',g.x(),g.y(),p.x()>self.width()-16 and p.y()>self.height()-16)
    def mouseMoveEvent(self,event):
        g=event.globalPosition();self._gesture('move',g.x(),g.y())
    def mouseReleaseEvent(self,event):
        g=event.globalPosition();self._gesture('end',g.x(),g.y())

    def _paint(self,p):
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r=QRectF(self.rect());vertical=r.height()>r.width()
        p.setPen(Qt.PenStyle.NoPen);p.setBrush(QColor('#211932'));p.drawRoundedRect(r,8,8)
        p.setPen(QColor('#f0e4ff'));p.setFont(QFont('Arial',max(10,min(22,round(r.width()/4))) if vertical else max(12,min(22,round(r.height()/4))),QFont.Weight.Bold))
        p.drawText(QRectF(2,2,r.width()-4,23),Qt.AlignmentFlag.AlignCenter,self.label)
        track=QRectF(12,30,r.width()-24,r.height()-40) if vertical else QRectF(10,29,r.width()-20,8)
        clip=QPainterPath();clip.addRoundedRect(track,3,3)
        p.save();p.setClipPath(clip);p.fillRect(track,QColor('#352848'))
        if vertical:
            h=track.height()*self.fraction
            fill=QRectF(track.x(),track.bottom()-h if self.white_bottom else track.y(),track.width(),h)
        else:fill=QRectF(track.x(),track.y(),track.width()*self.fraction,track.height())
        p.fillRect(fill,QColor('#f4ecff'));p.restore()
        p.setPen(QColor('#8673a2'))
        for size in (4,8,12):p.drawLine(self.width()-size-2,self.height()-3,self.width()-3,self.height()-size-2)

    def _redraw(self):
        if not self.enabled:return
        if self._native_mac:
            image=QImage(round(self.width()*self.scale),round(self.height()*self.scale),QImage.Format.Format_ARGB32_Premultiplied)
            image.setDevicePixelRatio(self.scale);image.fill(Qt.GlobalColor.transparent)
            p=QPainter(image);self._paint(p);p.end()
            self._mac_panel().update_image(self.geometry(),image,QGuiApplication.primaryScreen().geometry().height())
        else:
            self.update()
            if not super().isVisible():self.show()

    def hide(self):
        self.enabled=False
        super().hide()

    def close(self):
        self.hide();self.animation.stop();return super().close()

    def paintEvent(self,event):
        p=QPainter(self);p.fillRect(self.rect(),Qt.GlobalColor.transparent);self._paint(p)
