# -*- coding: utf-8 -*-
"""نخ خواندن فریم از دوربین (OpenCV) — اجرا در نخ جدا، تحویل فریم به نخ اصلی.

on_frame(frame_bgr): در نخ ورکر صدا زده می‌شود؛ فراخواننده باید با
Clock.schedule_once به نخ اصلی Kivy منتقلش کند.
on_state(state): یکی از "connecting" | "live" | "error".
"""
import threading
import time


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

    def run(self):
        try:
            import cv2
        except Exception:
            self._state("error")
            return
        cap = None
        while not self._stop.is_set():
            try:
                if cap is None:
                    self._state("connecting")
                    cap = cv2.VideoCapture(self.url)
                    # بافر کم برای تأخیر کمتر در پخش زنده
                    try:
                        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                    except Exception:
                        pass
                ok, frame = cap.read()
                if not ok or frame is None:
                    self._state("error")
                    try:
                        cap.release()
                    except Exception:
                        pass
                    cap = None
                    # مکث با امکان توقف سریع
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
