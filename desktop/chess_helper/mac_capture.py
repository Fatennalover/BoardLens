"""Compositor snapshots exclude our panel without hiding it on screen.

Called by the vision worker, never by Qt's UI thread. Cancellation stays bounded
even when the system capture API is waiting for a frame or permission.
"""
from __future__ import annotations

from collections import Counter

import os
import threading
import time

import cv2
import numpy as np

_cached_content = None
_cached_at = 0.
_cached_exclusions = set()
_display_retry_at = {}


class CaptureCancelled(Exception):
    pass


class CaptureUnavailable(RuntimeError):
    pass


def _await(start, cancelled, timeout=2):
    if cancelled.is_set():
        raise CaptureCancelled()
    completed = threading.Event()
    result = []
    def callback(value, error):
        result.extend((value, error))
        completed.set()
    start(callback)
    deadline = time.monotonic()+timeout
    while not completed.wait(.03):
        if cancelled.is_set():
            raise CaptureCancelled()
        if time.monotonic()>deadline:
            raise CaptureUnavailable('Timed out waiting for macOS to return a frame.')
    if cancelled.is_set():
        raise CaptureCancelled()
    value, error = result
    if error or value is None:
        raise CaptureUnavailable(f'macOS returned no frame: {error or "no image"}.')
    return value


def _bgr(image):
    import Quartz as CG
    width, height = CG.CGImageGetWidth(image), CG.CGImageGetHeight(image)
    stride = CG.CGImageGetBytesPerRow(image)
    info = CG.CGImageGetBitmapInfo(image)
    raw = CG.CGDataProviderCopyData(CG.CGImageGetDataProvider(image))
    if CG.CGImageGetBitsPerPixel(image)==32:
        # IOSurface providers can include allocation padding after the last row.
        pixels = np.frombuffer(raw, np.uint8, count=height*stride).reshape(height, stride)[:, :width*4].reshape(height,width,4)
        # ScreenCaptureKit delivers BGRA, premultiplied first, little endian.
        if (info & CG.kCGBitmapByteOrderMask)==CG.kCGBitmapByteOrder32Little:
            return pixels[:,:,:3].copy()
        return cv2.cvtColor(pixels, cv2.COLOR_RGBA2BGR)
    # Handle less common OS pixel formats through Apple's image decoder.
    import AppKit
    rep = AppKit.NSBitmapImageRep.alloc().initWithCGImage_(image)
    png = rep.representationUsingType_properties_(AppKit.NSBitmapImageFileTypePNG,{})
    return cv2.imdecode(np.frombuffer(png,np.uint8),cv2.IMREAD_COLOR)


def visible_windows():
    import Quartz as CG
    flags = CG.kCGWindowListOptionOnScreenOnly | CG.kCGWindowListExcludeDesktopElements
    windows = CG.CGWindowListCopyWindowInfo(flags, CG.kCGNullWindowID) or []
    return [(int(window['kCGWindowNumber']), str(window.get('kCGWindowOwnerName','Application')),
             str(window.get('kCGWindowName','') or 'Window')) for window in windows
            if int(window.get('kCGWindowOwnerPID',0)) != os.getpid() and window.get('kCGWindowLayer') == 0
            and window.get('kCGWindowBounds',{}).get('Width',0) >= 96
            and window.get('kCGWindowBounds',{}).get('Height',0) >= 96]


def capture_window(window_id, cancelled):
    import objc
    import Quartz as CG
    import ScreenCaptureKit as SC
    with objc.autorelease_pool():
        if not CG.CGPreflightScreenCaptureAccess():
            raise CaptureUnavailable('Allow Screen Recording to capture a window.')
        content = _await(lambda callback: SC.SCShareableContent.
            getShareableContentExcludingDesktopWindows_onScreenWindowsOnly_completionHandler_(True,False,callback), cancelled)
        target = next((window for window in content.windows() if int(window.windowID()) == window_id),None)
        if target is None:
            raise CaptureUnavailable('That window is no longer available.')
        selection = SC.SCContentFilter.alloc().initWithDesktopIndependentWindow_(target)
        configuration = SC.SCStreamConfiguration.alloc().init()
        bounds = selection.contentRect().size
        factor = min(selection.pointPixelScale(), 2560/max(bounds.width,bounds.height,1))
        configuration.setWidth_(max(1,round(bounds.width*factor)))
        configuration.setHeight_(max(1,round(bounds.height*factor)))
        configuration.setShowsCursor_(False)
        configuration.setIgnoreShadowsSingleWindow_(True)
        image = _await(lambda callback: SC.SCScreenshotManager.
            captureImageWithFilter_configuration_completionHandler_(selection,configuration,callback), cancelled)
        return _bgr(image)


def capture_frames(specs, excluded_window_ids, cancelled):
    crops = Counter(spec['key'] for spec in specs if spec.get('crop'))
    shared = {key for key, count in crops.items() if count > 1}
    if not shared:
        return _capture_frames(specs, excluded_window_ids, cancelled)
    requests = []
    grouped = set()
    for spec in specs:
        key = spec['key']
        if key not in shared:
            requests.append(spec)
        elif key not in grouped:
            requests.append({name: value for name, value in spec.items() if name != 'crop'})
            grouped.add(key)
    frames = _capture_frames(requests, excluded_window_ids, cancelled)
    by_display = {frame[0]: frame for frame in frames if frame[0] in shared}
    output = [frame for frame in frames if frame[0] not in shared]
    for spec in specs:
        key = spec['key']
        if key not in by_display:
            continue
        _, name, image = by_display[key]
        if spec.get('crop'):
            x,y,size = spec['crop']
            output.append((key,name,image[y:y+size,x:x+size],(x,y,size,spec['width'],spec['height'])))
        else:
            output.append((key,name,image))
    return output


def _capture_frames(specs, excluded_window_ids, cancelled):
    import objc
    import Quartz  # Register CGImage's CoreFoundation bridge before callbacks.
    with objc.autorelease_pool():
        if not Quartz.CGPreflightScreenCaptureAccess():
            raise RuntimeError('Screen Recording access is required for your launcher. Allow it and restart BoardLens.')
        import ScreenCaptureKit as SC
        # The synchronous compositor snapshot avoids creating a new screenshot
        # session on each refresh. Explicit window IDs omit only our panel.
        # Run it here on the worker, so capture never blocks the UI.
        if (os.environ.get('BOARDLENS_LEGACY_CAPTURE')=='1' or not hasattr(SC,'SCScreenshotManager')) and hasattr(Quartz,'CGWindowListCreateImageFromArray'):
            windows=Quartz.CGWindowListCopyWindowInfo(Quartz.kCGWindowListOptionOnScreenOnly,0)
            frames=[]
            for spec in specs:
                if cancelled.is_set():
                    raise CaptureCancelled()
                full_spec=spec
                crop=spec.get('crop')
                if crop:
                    x,y,size=crop
                    gx,gy,gw,gh=spec['geometry']
                    spec=dict(spec,geometry=(gx+x*gw/spec['width'],gy+y*gh/spec['height'],
                                             size*gw/spec['width'],size*gh/spec['height']),width=size,height=size)
                gx,gy,gw,gh=spec['geometry']
                helper_masks=[]
                if 'owner_pid' in spec:
                    # A helper behind the browser does not obscure the board.
                    # Mask only parts of our UI which are actually visible.
                    helper_masks=_visible_helper_masks(windows,spec['owner_pid'],excluded_window_ids)
                    spec=dict(spec,masks=helper_masks)
                flags=Quartz.kCGWindowImageBoundsIgnoreFraming|Quartz.kCGWindowImageBestResolution
                obscured=any(rx<gx+gw and rx+rw>gx and ry<gy+gh and ry+rh>gy
                             for rx,ry,rw,rh in helper_masks)
                if 'owner_pid' in spec or obscured or len(excluded_window_ids)>1:
                    # Recompose without any of our UI, so opening Settings or
                    # expanding the helper cannot black out the target board.
                    ids=[int(w['kCGWindowNumber']) for w in windows
                         if int(w.get('kCGWindowOwnerPID',0))!=spec.get('owner_pid')
                         and int(w['kCGWindowNumber']) not in excluded_window_ids]
                    image=Quartz.CGWindowListCreateImageFromArray(Quartz.CGRectMake(gx,gy,gw,gh),ids,flags)
                    spec=dict(spec,masks=[])
                elif excluded_window_ids:
                    # Capture the composited windows underneath our floating
                    # panel, rather than re-rendering every app window separately.
                    image=Quartz.CGWindowListCreateImage(Quartz.CGRectMake(gx,gy,gw,gh),
                        Quartz.kCGWindowListOptionOnScreenBelowWindow,next(iter(excluded_window_ids)),flags)
                else:
                    image=Quartz.CGWindowListCreateImage(Quartz.CGRectMake(gx,gy,gw,gh),
                        Quartz.kCGWindowListOptionOnScreenOnly,0,flags)
                if image is None:
                    break
                pixels=_bgr(image)
                pixels=_normalize_and_mask(pixels,spec)
                frame=(spec['key'],spec['name'],pixels)
                if crop:frame+=(tuple(crop)+(full_spec['width'],full_spec['height']),)
                frames.append(frame)
            if len(frames)==len(specs):
                return frames
        return _capture_displays(SC, specs, excluded_window_ids, cancelled)


def _capture_displays(SC, specs, excluded_window_ids, cancelled):
    global _cached_content, _cached_at, _cached_exclusions
    if not specs:
        raise CaptureUnavailable('The selected display is temporarily unavailable.')
    now = time.monotonic()
    if (_cached_content is None or now-_cached_at>.25
            or excluded_window_ids!=_cached_exclusions):
        _cached_content = None
        _cached_content = _await(lambda cb: SC.SCShareableContent.
            getShareableContentExcludingDesktopWindows_onScreenWindowsOnly_completionHandler_(True,True,cb),
            cancelled, timeout=.9)
        _cached_at = time.monotonic()
        _cached_exclusions=set(excluded_window_ids)
    content = _cached_content
    owners={spec.get('owner_pid') for spec in specs}
    excluded = [w for w in content.windows() if int(w.windowID()) in excluded_window_ids
                or (w.owningApplication() and int(w.owningApplication().processID()) in owners)]
    for key, deadline in tuple(_display_retry_at.items()):
        if deadline <= now:
            _display_retry_at.pop(key)
    ready = [spec for spec in specs if spec['key'] not in _display_retry_at]
    frames, failures = [], []
    for spec in ready or specs:
        if cancelled.is_set():
            raise CaptureCancelled()
        try:
            frames.append(_capture_display(SC, content.displays(), excluded, spec, cancelled))
        except CaptureUnavailable as error:
            # Other displays can still supply frames. Rebuild capture filters
            # next time and give this display a short chance to settle.
            _cached_content = None
            _display_retry_at[spec['key']] = time.monotonic()+.75
            failures.append(str(error))
    if frames:
        return frames
    raise CaptureUnavailable(failures[0])


def _capture_display(SC, displays, excluded, spec, cancelled):
    width, height = spec['width'], spec['height']
    if spec.get('owner_pid'):
        spec=dict(spec,masks=[])
    crop=spec.get('crop')
    gx,gy,gw,gh = spec['geometry']
    matches = [d for d in displays if abs(d.frame().origin.x-gx)<2
               and abs(d.frame().origin.y-gy)<2 and abs(d.frame().size.width-gw)<2
               and abs(d.frame().size.height-gh)<2]
    if len(matches)!=1:
        raise CaptureUnavailable(f"{spec['name']} is temporarily unavailable.")
    display_filter = SC.SCContentFilter.alloc().initWithDisplay_excludingWindows_(matches[0],excluded)
    config = SC.SCStreamConfiguration.alloc().init()
    config.setWidth_(width)
    config.setHeight_(height)
    config.setShowsCursor_(False)
    if crop:
        x,y,size=crop
        config.setSourceRect_(((x*gw/width,y*gh/height),(size*gw/width,size*gh/height)))
        config.setWidth_(size);config.setHeight_(size)
        spec=dict(spec,geometry=(gx+x*gw/width,gy+y*gh/height,
                                 size*gw/width,size*gh/height),width=size,height=size)
    image = _await(lambda cb: SC.SCScreenshotManager.
        captureImageWithFilter_configuration_completionHandler_(display_filter,config,cb),
        cancelled, timeout=.75)
    pixels = _bgr(image)
    if pixels is None or (not pixels[::16,::16].any() and not pixels.any()):
        raise CaptureUnavailable(f"{spec['name']} returned a blank frame.")
    pixels = _normalize_and_mask(pixels,spec)
    frame=(spec['key'],spec['name'],pixels)
    if crop:
        frame+=(tuple(crop)+(width,height),)
    return frame


def _normalize_and_mask(pixels,spec):
    if pixels.shape[:2]!=(spec['height'],spec['width']):
        pixels=cv2.resize(pixels,(spec['width'],spec['height']),interpolation=cv2.INTER_LINEAR)
    h,w=pixels.shape[:2]
    gx,gy,gw,gh=spec['geometry']
    for rx,ry,rw,rh in spec['masks']:
        x0,y0=max(0,round((rx-gx)*w/gw)),max(0,round((ry-gy)*h/gh))
        x1,y1=min(w,round((rx+rw-gx)*w/gw)),min(h,round((ry+rh-gy)*h/gh))
        pixels[y0:y1,x0:x1]=(24,30,36)
    return pixels


def _subtract_rect(rect, cover):
    x,y,w,h=rect;cx,cy,cw,ch=cover
    left,top=max(x,cx),max(y,cy)
    right,bottom=min(x+w,cx+cw),min(y+h,cy+ch)
    if right<=left or bottom<=top:
        return [rect]
    result=[]
    if top>y:result.append((x,y,w,top-y))
    if bottom<y+h:result.append((x,bottom,w,y+h-bottom))
    if left>x:result.append((x,top,left-x,bottom-top))
    if right<x+w:result.append((right,top,x+w-right,bottom-top))
    return result


def _visible_helper_masks(windows, owner_pid, excluded):
    covers=[];masks=[]
    for window in windows:
        if int(window.get('kCGWindowNumber',0)) in excluded:
            continue
        bounds=window.get('kCGWindowBounds',{})
        rect=tuple(float(bounds.get(key,0)) for key in ('X','Y','Width','Height'))
        if rect[2]<=0 or rect[3]<=0:
            continue
        if int(window.get('kCGWindowOwnerPID',0))==owner_pid:
            parts=[rect]
            for cover in covers:
                parts=[piece for part in parts for piece in _subtract_rect(part,cover)]
            masks.extend(parts)
        elif window.get('kCGWindowLayer',0)==0 and window.get('kCGWindowAlpha',1)>=.99:
            covers.append(rect)
    return masks
