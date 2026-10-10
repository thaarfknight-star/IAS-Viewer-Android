# -*- coding: utf-8 -*-
"""نخ پخش ویدیو با ffpyplayer — RTSP روی TCP.

on_frame(buf, w, h): بایت‌های RGB خام + ابعاد (در نخ ورکر صدا زده می‌شود؛
    فراخواننده باید با Clock.schedule_once به نخ اصلی Kivy منتقلش کند).
on_state(state): یکی از "connecting" | "live" | "error".

بر اساس تحقیق: ffpyplayer تنها گزینه‌ی عملی برای RTSP در p4a است.
- lib_opts: گزینه‌های دیماکسر (rtsp_transport باید اینجا باشد، نه در ff_opts)
- ff_opts: گزینه‌های پلیر
"""
import threading
import time

FF_OPTS = {
    "an": True,         # بدون صدا
    "sn": True,         # بدون زیرنویس
    "sync": "video",    # کلاک اصلی = ویدیو
    "out_fmt": "rgb24", # خروجی RGB
    "framedrop": True,  # حذف فریم‌های عقب‌افتاده (پخش زنده)
    "infbuf": True,
}

LIB_OPTS = {
    # آپشن‌های تأییدشده از نسخه ویندوز (IASagent)
    "rtsp_transport": "tcp",      # حتماً TCP - با UDP اکثر دوربین‌ها مشکل دارن
    "stimeout": "5000000",        # تایم‌اوت سوکت: ۵ ثانیه
    "max_delay": "300000",
    "buffer_size": "102400",
    "fflags": "nobuffer",         # تأخیر کم
    "flags": "low_delay",
    "reconnect": "1",
    "reconnect_streamed": "1",
    "reconnect_delay_max": "5",
    "rw_timeout": "5000000",
}


def _plog(msg):
    try:
        with open("/sdcard/Download/ias_probe.log", "a", encoding="utf-8") as f:
            f.write(msg + chr(10))
    except Exception:
        pass

def probe(url, timeout=8.0):
    """تست اتصال به استریم — True یعنی مسیر درست است."""
    try:
        from ffpyplayer.player import MediaPlayer
    except Exception as e:
        _plog("probe: ffpyplayer import failed: " + str(e))
        return False
    _plog("probe: trying " + url)
    player = None
    try:
        player = MediaPlayer(url, ff_opts=dict(FF_OPTS),
                             lib_opts=dict(LIB_OPTS))
        t0 = time.time()
        while time.time() - t0 < timeout:
            try:
                meta = player.get_metadata()
            except Exception:
                break
            if meta.get("src_vid_size") not in (None, (0, 0)):
                _plog("probe: SUCCESS " + url)
                return True
            time.sleep(0.2)
        return False
    except Exception:
        return False
    finally:
        if player is not None:
            try:
                player.close_player()
            except Exception:
                pass


class StreamWorker(threading.Thread):
    # برای سازگاری با کد قدیمی که probe را از روی کلاس صدا می‌زند
    probe = staticmethod(probe)

    def __init__(self, url, on_frame, on_state=None, reconnect_delay=3.0):
        super().__init__(daemon=True)
        self.url = url
        self.on_frame = on_frame
        self.on_state = on_state
        self.reconnect_delay = reconnect_delay
        self._stop = threading.Event()
        self._dead = threading.Event()

    def stop(self):
        self._stop.set()
        self._dead.set()

    def _state(self, s):
        if self.on_state:
            try:
                self.on_state(s)
            except Exception:
                pass

    def _run_once(self):
        try:
            from ffpyplayer.player import MediaPlayer
        except Exception:
            self._dead.set()
            return
        player = None
        try:
            player = MediaPlayer(self.url, ff_opts=dict(FF_OPTS),
                                 lib_opts=dict(LIB_OPTS))
            # انتظار برای اطلاعات استریم (I-frame ممکن است چند ثانیه طول بکشد)
            t0 = time.time()
            while True:
                if self._stop.is_set() or self._dead.is_set():
                    return
                try:
                    meta = player.get_metadata()
                except Exception:
                    self._dead.set()
                    return
                if meta.get("src_vid_size") not in (None, (0, 0)):
                    break
                if time.time() - t0 > 12:
                    self._dead.set()
                    return
                time.sleep(0.1)
            self._state("live")
            while not self._stop.is_set() and not self._dead.is_set():
                try:
                    frame, val = player.get_frame()
                except Exception:
                    self._dead.set()
                    break
                if val == "eof" or frame is None:
                    time.sleep(0.01)
                    continue
                try:
                    img, _pts = frame
                    buf = bytes(img.to_memoryview()[0])  # کپی امن بین نخ‌ها
                    w, h = img.get_size()
                except Exception:
                    continue
                try:
                    self.on_frame(buf, w, h)
                except Exception:
                    pass
        finally:
            if player is not None:
                try:
                    player.close_player()
                except Exception:
                    pass

    def run(self):
        while not self._stop.is_set():
            self._dead.clear()
            self._state("connecting")
            try:
                self._run_once()
            except Exception:
                pass
            if self._dead.is_set() and not self._stop.is_set():
                self._state("error")
            if self._stop.wait(self.reconnect_delay):
                break
