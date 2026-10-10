# -*- coding: utf-8 -*-
"""نخ خواندن فریم از دوربین (OpenCV) — اجرا در نخ جدا، تحویل فریم به نخ اصلی.

on_frame(frame_bgr): در نخ ورکر صدا زده می‌شود؛ فراخواننده باید با
Clock.schedule_once به نخ اصلی Kivy منتقلش کند.
on_state(state): یکی از "connecting" | "live" | "error".

روش اتصال دقیقاً مثل نسخه‌ی ویندوز (توصیه‌ی IASagent):
- RTSP حتماً روی TCP (با UDP تصویر قطع‌ووصل/سفید می‌شود)
- fflags=nobuffer + flags=low_delay برای تأخیر کم
- reconnect خودکار + rw_timeout برای جلوگیری از بلاک شدن
"""
import os
import threading
import time

# تنظیمات FFmpeg ویندوز — از طریق متغیر محیطی (قبل از باز کردن اعمال شود)
os.environ.setdefault(
    "OPENCOV_FFMPEG_CAPTURE_OPTIONS",
    "rtsp_transport;tcp|stimeout;5000000|max_delay;300000|"
    "buffer_size;102400|fflags;nobuffer|flags;low_delay|"
    "reconnect;1|reconnect_streamed;1|reconnect_delay_max;5|"
    "rw_timeout;5000000",
)


class StreamWorker(threading.Thread):
    def __init__(self, url, on_frame, on_state=None, reconnect_delay=3.0):
        super().__init__(daemon=True)
        self.url = url
        self.on_frame = on_frame
        self.on_state = on_state
        self.reconnect_delay = reconnect_delay
        self._stop = threading.Event()

    def stop(self):
        self._stop.set()

    def _state(self, s):
        if self.on_state:
            try:
                self.on_state(s)
            except Exception:
                pass

    def _open(self):
        """باز کردن استریم با چند تلاش (مثل ویندوز: اولین read اغلب False)."""
        try:
            import cv2
        except Exception:
            return None
        cap = cv2.VideoCapture(self.url)
        if not cap.isOpened():
            try:
                cap.release()
            except Exception:
                pass
            return None
        # تا ۴ بار تلاش برای اولین فریم (دی‌کدر هنوز به I-frame نرسیده)
        for _ in range(4):
            if self._stop.is_set():
                break
            ok, frame = cap.read()
            if ok and frame is not None:
                break
            time.sleep(0.4)
        else:
            try:
                cap.release()
            except Exception:
                pass
            return None
        try:
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        except Exception:
            pass
        return cap

    def run(self):
        cap = None
        while not self._stop.is_set():
            try:
                if cap is None:
                    self._state("connecting")
                    cap = self._open()
                    if cap is None:
                        self._state("error")
                        if self._stop.wait(self.reconnect_delay):
                            break
                        continue
                ok, frame = cap.read()
                if not ok or frame is None:
                    self._state("error")
                    try:
                        cap.release()
                    except Exception:
                        pass
                    cap = None
                    if self._stop.wait(self.reconnect_delay):
                        break
                    continue
                self._state("live")
                try:
                    self.on_frame(frame)
                except Exception:
                    pass
            except Exception:
                try:
                    if cap is not None:
                        cap.release()
                except Exception:
                    pass
                cap = None
                if self._stop.wait(self.reconnect_delay):
                    break
        try:
            if cap is not None:
                cap.release()
        except Exception:
            pass
