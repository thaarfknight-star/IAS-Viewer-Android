# -*- coding: utf-8 -*-
"""IAS Viewer — نسخه‌ی اندروید (Kivy).

طراحی بر اساس لوگوی ایمن آرا سورنا: سپر آبی/سرمه‌ای.
- صفحه‌ی اصلی: گرید ۲×۲ پخش زنده (حداکثر ۴ دوربین)
- افزودن دوربین/NVR + اسکن شبکه
- صفحه‌ی تنظیمات
- موتور استریم: ffpyplayer (RTSP روی TCP)
"""
import os
import sys
import traceback

# لاگر شروع برنامه برای دیباگ کرش
def _dlog(msg):
    try:
        p = "/sdcard/Download/ias_startup.log"
        with open(p, "a", encoding="utf-8") as f:
            f.write(msg + "\n")
    except Exception:
        pass

_dlog("=== app started ===")
import threading

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import Color, RoundedRectangle, Rectangle
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.screenmanager import Screen, ScreenManager
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget\n_dlog('kivy imports ok')

from ptext import fa, fa_ltr, FONT, FONT_BOLD
from user_store import UserStore
from camera_store import CameraStore, camera_url, build_rtsp_url
from network_scan import NetworkScanner
from stream_worker import StreamWorker

VERSION = "2.1.0"


# ============================================================ پالت برند IAS
# استخراج‌شده از لوگوی سپر ایمن آرا سورنا
BRAND_BLUE = (0.059, 0.486, 0.757, 1)      # #0f7cc1 — آبی اصلی
BRAND_BLUE_LT = (0.165, 0.608, 0.847, 1)   # #2a9bd8 — آبی روشن
BRAND_BLUE_DK = (0.039, 0.353, 0.561, 1)   # #0a5a8f — آبی تیره
BRAND_SLATE = (0.227, 0.294, 0.322, 1)     # #3a4b52 — سرمه‌ای لوگو

C_BG = (0.055, 0.075, 0.098, 1)            # پس‌زمینه‌ی عمیق
C_SURFACE = (0.090, 0.125, 0.165, 1)       # سطح پنل‌ها
C_CARD = (0.120, 0.170, 0.220, 1)          # کارت‌ها
C_BORDER = (0.180, 0.250, 0.320, 1)        # حاشیه
C_TEXT = (1, 1, 1, 1)
C_MUTED = (0.550, 0.620, 0.670, 1)
C_OK = (0.180, 0.800, 0.443, 1)
C_ERR = (0.906, 0.298, 0.235, 1)

RADIUS = dp(14)      # شعاع گوشه‌های گرد
RADIUS_SM = dp(10)


# ============================================================ ابزارهای UI
def rounded_bg(widget, color, radius=RADIUS):
    """پس‌زمینه‌ی گرد برای ویجت."""
    with widget.canvas.before:
        Color(*color)
        rect = RoundedRectangle(pos=widget.pos, size=widget.size,
                                radius=[radius])
    def _sync(*_):
        rect.pos = widget.pos
        rect.size = widget.size
    widget.bind(pos=_sync, size=_sync)
    return rect


def mk_label(text, size="15sp", color=C_TEXT, bold=False, halign="center",
             height=None, size_hint_x=1):
    lbl = Label(text=fa(text), font_name=FONT_BOLD if bold else FONT,
                font_size=size, color=color, halign=halign,
                valign="middle", size_hint_x=size_hint_x)
    lbl.bind(size=lambda i, v: setattr(i, "text_size", (v[0], None)))
    if height is not None:
        lbl.size_hint_y = None
        lbl.height = dp(height)
    return lbl


def mk_button(text, on_press, bg=BRAND_BLUE, fg=C_TEXT, bold=True,
              radius=RADIUS_SM, height=52, size_hint_x=1, font_size="16sp"):
    btn = Button(text=fa(text), font_name=FONT_BOLD if bold else FONT,
                 font_size=font_size, color=fg,
                 size_hint_x=size_hint_x, size_hint_y=None,
                 height=dp(height), background_normal="",
                 background_down="", background_color=(0, 0, 0, 0))
    rounded_bg(btn, bg, radius)
    if on_press:
        btn.bind(on_press=on_press)
    return btn


def mk_input(hint, text="", password=False):
    t = TextInput(hint_text=fa(hint), text=text, font_name=FONT,
                  font_size="15sp", password=password, multiline=False,
                  size_hint_y=None, height=dp(52),
                  background_normal="", background_active="",
                  background_color=C_SURFACE,
                  foreground_color=C_TEXT, hint_text_color=C_MUTED,
                  cursor_color=BRAND_BLUE_LT)
    rounded_bg(t, C_SURFACE, RADIUS_SM)
    t.padding = [dp(14), dp(14), dp(14), dp(14)]
    return t


def mk_card():
    """کارت گرد."""
    card = BoxLayout(orientation="vertical", spacing=dp(8),
                     padding=dp(14))
    rounded_bg(card, C_CARD, RADIUS)
    return card


# ============================================================ مسیرهای استریم
# لیست کامل ویندوز (CANDIDATE_PATHS در add_camera_dialog.py)
CANDIDATE_PATHS = [
    "live/ch0", "snscview", "live/main", "live/ch1", "ch0",
    "h264/ch1/main/av_stream",
    "cam/realmonitor?channel=1&subtype=0",
    "cam/realmonitor?channel=1&subtype=1",
    "Streaming/Channels/101", "Streaming/Channels/1",
    "h264Preview_01_main", "stream1", "video1", "media/video1",
    "onvif1", "profile1", "",
]


def nvr_paths(channel):
    return [
        "cam/realmonitor?channel=%s&subtype=0" % channel,
        "cam/realmonitor?channel=%s&subtype=1" % channel,
        "Streaming/Channels/%s01" % channel,
        "Streaming/Channels/%s" % channel,
        "h264/ch%s/main/av_stream" % channel,
        "live/ch%s" % channel,
    ]


# ============================================================ صفحه‌ی ورود
class LoginScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        Window.clearcolor = C_BG
        root = BoxLayout(orientation="vertical", padding=dp(28),
                         spacing=dp(10))
        root.add_widget(Widget(size_hint_y=0.12))

        # لوگوی سپر
        logo = Image(source="assets/logo_shield.png",
                     size_hint=(None, None), size=(dp(110), dp(110)),
                     pos_hint={"center_x": 0.5})
        root.add_widget(logo)
        root.add_widget(mk_label("ایمن آرا سورنا", size="22sp", bold=True,
                                 height=36))
        root.add_widget(mk_label("IAS Viewer", size="15sp", color=C_MUTED,
                                 height=28))

        root.add_widget(Widget(size_hint_y=0.06))

        self.user_in = mk_input("نام کاربری")
        self.pass_in = mk_input("رمز عبور", password=True)
        self.msg = mk_label("", size="13sp", color=C_ERR, height=26)
        root.add_widget(self.user_in)
        root.add_widget(self.pass_in)
        root.add_widget(self.msg)
        root.add_widget(mk_button("ورود", self.do_login, height=56))
        root.add_widget(Widget(size_hint_y=0.18))
        root.add_widget(mk_label("نسخه‌ی %s" % fa_ltr(VERSION),
                                 size="12sp", color=C_MUTED, height=22))
        self.add_widget(root)

    def do_login(self, *_):
        app = App.get_running_app()
        u = self.user_in.text.strip()
        p = self.pass_in.text
        if not u:
            self.msg.text = fa("نام کاربری را وارد کنید.")
            return
        if app.users.verify(u, p):
            app.current_user = {"username": u}
            self.msg.text = ""
            self.pass_in.text = ""
            app.sm.current = "main"
        else:
            self.msg.text = fa("نام کاربری یا رمز عبور اشتباه است.")


# ============================================================ کاشی دوربین
class CameraTile(BoxLayout):
    """کاشی گرد دوربین: ویدیوی زنده + نشان نام + قرص وضعیت."""

    def __init__(self, cam, **kwargs):
        super().__init__(**kwargs)
        self.orientation = "vertical"
        self.cam = cam
        self.worker = None
        self.padding = dp(6)
        self.spacing = dp(4)
        rounded_bg(self, C_SURFACE, RADIUS)
        # پس‌زمینه‌ی مشکی ناحیه‌ی ویدیو
        with self.canvas.before:
            Color(0, 0, 0, 1)
            self._vbg = RoundedRectangle(pos=self.pos, size=self.size,
                                         radius=[RADIUS])
        self.bind(pos=self._sync_bg, size=self._sync_bg)

        # نوار بالا: نام + قرص وضعیت
        top = BoxLayout(orientation="horizontal", size_hint_y=None,
                        height=dp(30), spacing=dp(6))
        name = cam.get("name") or cam.get("ip") or "؟"
        self.name_lbl = mk_label(name, size="13sp", bold=True,
                                 halign="right", size_hint_x=0.65)
        self.pill = mk_label("…", size="11sp", bold=True,
                             size_hint_x=0.35, height=24)
        rounded_bg(self.pill, C_BORDER, dp(12))
        top.add_widget(self.pill)
        top.add_widget(self.name_lbl)
        self.add_widget(top)

        # تصویر
        self.img = Image(allow_stretch=True, keep_ratio=True)
        self.add_widget(self.img)

        # لمس → تمام‌صفحه
        self.bind(on_touch_down=self._on_touch)

    def _sync_bg(self, *_):
        self._vbg.pos = self.pos
        self._vbg.size = self.size

    def _on_touch(self, _w, touch):
        if self.collide_point(*touch.pos) and touch.is_double_tap:
            app = App.get_running_app()
            ms = app.sm.get_screen("main")
            ms.open_fullscreen(self.cam)
            return True
        return False

    # ---------------------------------------------------------- استریم --
    def start(self):
        self.stop()
        url = camera_url(self.cam)
        if not url:
            self.set_state("error")
            return

        def _frame(buf, w, h):
            Clock.schedule_once(lambda dt: self._blit(buf, w, h))

        def _state(st):
            Clock.schedule_once(lambda dt: self.set_state(st))

        self.worker = StreamWorker(url, _frame, _state)
        self.worker.start()

    def stop(self):
        w, self.worker = self.worker, None
        if w:
            try:
                w.stop()
            except Exception:
                pass

    def _blit(self, buf, w, h):
        try:
            from kivy.graphics.texture import Texture
            tex = self.img.texture
            if tex is None or tex.width != w or tex.height != h:
                tex = Texture.create(size=(w, h), colorfmt="rgb")
                tex.flip_vertical()
                self.img.texture = tex
            tex.blit_buffer(buf, colorfmt="rgb", bufferfmt="ubyte")
            self.img.canvas.ask_update()
        except Exception:
            pass

    def set_state(self, state):
        mapping = {
            "connecting": ("در حال اتصال…", C_MUTED, C_BORDER),
            "live": ("زنده", C_TEXT, (0.15, 0.55, 0.30, 1)),
            "error": ("قطع", C_TEXT, C_ERR),
        }
        txt, fg, bg = mapping.get(state, ("…", C_MUTED, C_BORDER))
        self.pill.text = fa(txt)
        self.pill.color = fg
        # رنگ پس‌زمینه‌ی قرص
        for inst in self.pill.canvas.before.children:
            if isinstance(inst, Color):
                inst.rgba = bg
                break


class EmptyTile(Button):
    """خانه‌ی خالی گرد — لمس → افزودن دوربین."""

    def __init__(self, on_add, **kwargs):
        super().__init__(**kwargs)
        self.text = fa("+ افزودن دوربین")
        self.font_name = FONT
        self.font_size = "16sp"
        self.color = C_MUTED
        self.background_normal = ""
        self.background_down = ""
        self.background_color = (0, 0, 0, 0)
        rounded_bg(self, (0, 0, 0, 0), RADIUS)
        # حاشیه‌ی چین‌دار با کانواس
        with self.canvas.after:
            Color(*C_BORDER)
            from kivy.graphics import Line
            self._line = Line(rounded_rectangle=(
                self.x, self.y, self.width, self.height, RADIUS),
                width=dp(1.5))
        self.bind(pos=self._sync_line, size=self._sync_line)
        self.bind(on_press=lambda *_: on_add())

    def _sync_line(self, *_):
        self._line.rounded_rectangle = (
            self.x, self.y, self.width, self.height, RADIUS)


# ============================================================ افزودن/ویرایش
class MainScreenAddMixin:
    """متدهای افزودن دوربین برای MainScreen."""

    def add_camera(self, *_):
        self.cam_form(None)

    def edit_camera(self, cam):
        self.cam_form(cam)

    def open_scan(self, on_pick):
        box = BoxLayout(orientation="vertical", spacing=dp(10),
                        padding=dp(16))
        rounded_bg(box, C_BG, RADIUS)
        box.add_widget(mk_label("اسکن شبکه", size="18sp", bold=True,
                               height=32))
        range_in = mk_input("رنج IP (مثلاً 192.168.1)", text="192.168.1")
        box.add_widget(range_in)
        scan_btn = mk_button("شروع اسکن", lambda *_: None, height=50)
        box.add_widget(scan_btn)
        status = mk_label("", size="12sp", color=C_MUTED, height=26)
        box.add_widget(status)
        scroll = ScrollView()
        results = BoxLayout(orientation="vertical", spacing=dp(8),
                            size_hint_y=None, padding=dp(4))
        results.bind(minimum_height=results.setter("height"))
        scroll.add_widget(results)
        box.add_widget(scroll)
        box.add_widget(mk_button("بستن", lambda *_: close(),
                                 bg=C_CARD, height=50))

        popup = Popup(title="", content=box, size_hint=(0.94, 0.88),
                      background="", background_color=(0, 0, 0, 0),
                      separator_color=(0, 0, 0, 0))
        scanner = {"t": None}

        def close():
            s = scanner["t"]
            if s and s.is_alive():
                s.stop()
            scanner["t"] = None
            popup.dismiss()

        def toggle(*_):
            s = scanner["t"]
            if s and s.is_alive():
                s.stop()
                scanner["t"] = None
                scan_btn.text = fa("شروع اسکن")
                return
            results.clear_widgets()
            status.text = fa("در حال اسکن…")
            scan_btn.text = fa("توقف")

            def on_found(dev):
                Clock.schedule_once(lambda dt: add_row(dev))

            def on_done(devs):
                Clock.schedule_once(lambda dt: done(devs))

            scanner["t"] = NetworkScanner(range_in.text,
                                         on_found=on_found,
                                         on_done=on_done)
            scanner["t"].start()

        def add_row(dev):
            ip = dev["ip"]
            ports = ", ".join(str(p) for p in dev["ports"])
            row = mk_card()
            row.orientation = "horizontal"
            row.size_hint_y = None
            row.height = dp(60)
            row.spacing = dp(8)
            row.add_widget(mk_button("افزودن",
                                     lambda _b, d=dev: pick(d),
                                     bg=(0.15, 0.55, 0.30, 1),
                                     size_hint_x=0.35, height=44))
            row.add_widget(mk_label("%s\n%s" % (fa_ltr(ip), fa_ltr(ports)),
                                    size="13sp", halign="right",
                                    size_hint_x=0.65))
            results.add_widget(row)

        def done(devs):
            scanner["t"] = None
            scan_btn.text = fa("شروع اسکن")
            n = len(devs or [])
            status.text = fa("%d دستگاه یافت شد." % n if n
                             else "دستگاهی یافت نشد.")

        def pick(dev):
            ip = dev["ip"]
            close()
            on_pick(ip)

        scan_btn.bind(on_press=toggle)
        popup.bind(on_dismiss=lambda *_: (
            scanner["t"].stop() if scanner["t"] and
            scanner["t"].is_alive() else None))
        popup.open()

# ============================================================ صفحه‌ی اصلی
class MainScreen(MainScreenAddMixin, Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        Window.clearcolor = C_BG
        root = BoxLayout(orientation="vertical", spacing=dp(8),
                         padding=[dp(12), dp(8), dp(12), dp(12)])

        # هدر برند
        header = BoxLayout(orientation="horizontal", size_hint_y=None,
                           height=dp(56), spacing=dp(8))
        rounded_bg(header, C_SURFACE, RADIUS_SM)
        header.padding = [dp(10), dp(6), dp(10), dp(6)]

        logo = Image(source="assets/logo_shield.png",
                     size_hint=(None, None), size=(dp(40), dp(40)))
        title_box = BoxLayout(orientation="vertical", size_hint_x=0.45)
        title_box.add_widget(mk_label("IAS Viewer", size="16sp", bold=True,
                                      halign="right", height=24))
        title_box.add_widget(mk_label("ایمن آرا سورنا", size="11sp",
                                      color=C_MUTED, halign="right",
                                      height=18))

        btn_add = mk_button("+", self.add_camera, height=44,
                            size_hint_x=None, font_size="22sp")
        btn_add.width = dp(52)
        btn_set = mk_button("تنظیمات", self.goto_settings, height=44,
                            size_hint_x=0.30, bg=C_CARD, font_size="14sp")
        btn_out = mk_button("خروج", self.do_logout, height=44,
                            size_hint_x=0.22, bg=(0.45, 0.22, 0.22, 1),
                            font_size="14sp")

        header.add_widget(btn_out)
        header.add_widget(btn_set)
        header.add_widget(title_box)
        header.add_widget(btn_add)
        header.add_widget(logo)
        root.add_widget(header)

        # گرید ۲×۲
        self.grid = GridLayout(cols=2, rows=2, spacing=dp(10))
        root.add_widget(self.grid)
        self.add_widget(root)

    def on_enter(self):
        self.rebuild_grid()

    def on_leave(self):
        for child in self.grid.children:
            if isinstance(child, CameraTile):
                child.stop()

    def rebuild_grid(self):
        for child in list(self.grid.children):
            if isinstance(child, CameraTile):
                child.stop()
            self.grid.remove_widget(child)
        app = App.get_running_app()
        cams = app.cameras.cameras[:4]
        for cam in cams:
            tile = CameraTile(cam)
            self.grid.add_widget(tile)
            tile.start()
        for _ in range(4 - len(cams)):
            self.grid.add_widget(EmptyTile(self.add_camera))

    # -------------------------------------------------------- تمام‌صفحه --
    def open_fullscreen(self, cam):
        box = BoxLayout(orientation="vertical", spacing=dp(8),
                        padding=dp(12))
        top = BoxLayout(orientation="horizontal", size_hint_y=None,
                        height=dp(48), spacing=dp(8))
        top.add_widget(mk_button("بازگشت", lambda *_: popup.dismiss(),
                                 bg=C_CARD, size_hint_x=0.35, height=44))
        top.add_widget(mk_label(cam.get("name") or "", size="16sp",
                               bold=True, halign="right"))
        box.add_widget(top)
        img = Image(allow_stretch=True, keep_ratio=True)
        box.add_widget(img)
        popup = Popup(title="", content=box, size_hint=(0.96, 0.92),
                      background="", background_color=(0, 0, 0, 0),
                      separator_color=(0, 0, 0, 0))
        rounded_bg(box, C_BG, RADIUS)

        worker = {"w": None}

        def _frame(buf, w, h):
            Clock.schedule_once(lambda dt: blit(buf, w, h))

        def blit(buf, w, h):
            try:
                from kivy.graphics.texture import Texture
                tex = img.texture
                if tex is None or tex.width != w or tex.height != h:
                    tex = Texture.create(size=(w, h), colorfmt="rgb")
                    tex.flip_vertical()
                    img.texture = tex
                tex.blit_buffer(buf, colorfmt="rgb", bufferfmt="ubyte")
                img.canvas.ask_update()
            except Exception:
                pass

        url = camera_url(cam)
        if url:
            worker["w"] = StreamWorker(url, _frame)
            worker["w"].start()

        def _close(*_):
            w = worker["w"]
            if w:
                try:
                    w.stop()
                except Exception:
                    pass
            popup.dismiss()

        popup.bind(on_dismiss=lambda *_: (
            worker["w"].stop() if worker["w"] else None))
        popup.open()





# ============================================================ فرم دوربین
def _cam_form(self, cam, prefill=None):
        is_new = cam is None
        prefill = prefill or {}
        box = BoxLayout(orientation="vertical", spacing=dp(10),
                        padding=dp(16))
        rounded_bg(box, C_BG, RADIUS)
        box.add_widget(mk_label("افزودن دوربین" if is_new else "ویرایش دوربین",
                                size="18sp", bold=True, height=32))

        # اسکن شبکه
        def _open_scan_from_form(*_):
            state = {
                "name": name_in.text, "ip": ip_in.text,
                "port": port_in.text, "user": user_in.text,
                "pass": pass_in.text, "path": path_in.text,
                "channel": chan_in.text, "type": cam_type["v"],
            }
            detect_state["cancel"] = True
            popup.dismiss()

            def _on_ip_picked(ip):
                state["ip"] = ip
                if not state["name"].strip():
                    state["name"] = ip
                self.cam_form(cam, prefill=state)

            self.open_scan(_on_ip_picked)

        box.add_widget(mk_button("اسکن شبکه", _open_scan_from_form,
                                 bg=C_CARD, height=50))

        # نوع: دوربین / NVR
        type_box = BoxLayout(orientation="horizontal", size_hint_y=None,
                             height=dp(50), spacing=dp(8))
        btn_type_cam = mk_button("دوربین", lambda *_: set_type("cam"),
                                 height=50)
        btn_type_nvr = mk_button("NVR", lambda *_: set_type("nvr"),
                                 height=50, bg=C_CARD)
        type_box.add_widget(btn_type_cam)
        type_box.add_widget(btn_type_nvr)
        box.add_widget(type_box)
        cam_type = {"v": "cam"}

        def set_type(t):
            cam_type["v"] = t
            is_nvr = (t == "nvr")
            for inst in btn_type_cam.canvas.before.children:
                from kivy.graphics import Color as _C
                if isinstance(inst, _C):
                    inst.rgba = BRAND_BLUE if not is_nvr else C_CARD
            for inst in btn_type_nvr.canvas.before.children:
                from kivy.graphics import Color as _C
                if isinstance(inst, _C):
                    inst.rgba = BRAND_BLUE if is_nvr else C_CARD
            chan_in.disabled = not is_nvr
            chan_in.opacity = 1 if is_nvr else 0
            chan_in.height = dp(52) if is_nvr else 0
            auto_box.disabled = is_nvr
            auto_box.opacity = 1 if not is_nvr else 0.4
            path_in.disabled = True if is_nvr else not auto_chk.active

        name_in = mk_input("نام (مثلاً: ورودی اصلی)")
        ip_in = mk_input("آدرس IP")
        port_in = mk_input("پورت", text="554")
        user_in = mk_input("نام کاربری", text="admin")
        pass_in = mk_input("رمز عبور", password=True)
        chan_in = mk_input("شماره‌ی کانال (مثلاً 1)", text="1")
        chan_in.disabled = True
        chan_in.opacity = 0
        chan_in.height = 0

        from kivy.uix.checkbox import CheckBox
        auto_box = BoxLayout(orientation="horizontal", size_hint_y=None,
                             height=dp(44), spacing=dp(8))
        auto_chk = CheckBox(active=True, size_hint_x=None, width=dp(44),
                            color=BRAND_BLUE_LT)
        auto_box.add_widget(auto_chk)
        auto_box.add_widget(mk_label("تشخیص خودکار مسیر استریم",
                                     size="14sp", halign="right"))
        path_in = mk_input("مسیر دستی (مثلاً live/ch0)")
        path_in.disabled = True
        auto_chk.bind(active=lambda _i, v: setattr(path_in, "disabled", v))

        if not is_new:
            name_in.text = cam.get("name", "")
            ip_in.text = cam.get("ip", "")
            port_in.text = str(cam.get("port", "554") or "554")
            user_in.text = cam.get("user", "")
            pass_in.text = cam.get("pass", "")
            if cam.get("nvr_channel"):
                set_type("nvr")
                chan_in.text = str(cam.get("nvr_channel"))
        if prefill.get("name"):
            name_in.text = prefill["name"]
        if prefill.get("ip"):
            ip_in.text = prefill["ip"]
        if prefill.get("port"):
            port_in.text = prefill["port"]
        if prefill.get("user"):
            user_in.text = prefill["user"]
        if prefill.get("pass"):
            pass_in.text = prefill["pass"]
        if prefill.get("path"):
            path_in.text = prefill["path"]
            auto_chk.active = False
        if prefill.get("channel"):
            chan_in.text = prefill["channel"]
        if prefill.get("type") == "nvr":
            set_type("nvr")

        msg = mk_label("", size="13sp", color=C_ERR, height=28)
        scroll = ScrollView()
        form = BoxLayout(orientation="vertical", spacing=dp(10),
                         size_hint_y=None, padding=dp(4))
        form.bind(minimum_height=form.setter("height"))
        for w in (name_in, ip_in, port_in, user_in, pass_in, chan_in):
            form.add_widget(w)
        form.add_widget(auto_box)
        form.add_widget(path_in)
        form.add_widget(msg)
        scroll.add_widget(form)
        box.add_widget(scroll)

        btn_row = BoxLayout(orientation="horizontal", size_hint_y=None,
                            height=dp(52), spacing=dp(10))
        btn_row.add_widget(mk_button("انصراف", lambda *_: cancel(),
                                     bg=C_CARD, height=52))
        btn_row.add_widget(mk_button("ذخیره", lambda *_: save(),
                                     height=52))
        box.add_widget(btn_row)

        popup = Popup(title="", content=box, size_hint=(0.94, 0.92),
                      background="", background_color=(0, 0, 0, 0),
                      separator_color=(0, 0, 0, 0))
        detect_state = {"cancel": False, "busy": False}

        def cancel():
            detect_state["cancel"] = True
            popup.dismiss()

        def set_busy(b, t=""):
            detect_state["busy"] = b
            msg.text = fa(t)
            msg.color = C_MUTED if b else C_ERR

        def save():
            if detect_state["busy"]:
                return
            name = name_in.text.strip()
            ip = ip_in.text.strip()
            port = port_in.text.strip() or "554"
            user = user_in.text.strip() or "admin"
            pwd = pass_in.text
            nvr_channel = chan_in.text.strip() if cam_type["v"] == "nvr" else ""
            if not ip:
                msg.text = fa("آدرس IP را وارد کنید.")
                return
            if cam_type["v"] == "nvr" and not nvr_channel:
                msg.text = fa("شماره‌ی کانال NVR را وارد کنید.")
                return
            if not name:
                name = ip

            auto = auto_chk.active and cam_type["v"] == "cam"
            manual_path = path_in.text.strip()

            if not auto:
                do_save(name, ip, port, user, pwd, manual_path,
                        nvr_channel)
                return

            # تشخیص خودکار
            set_busy(True, "در حال تشخیص مسیر استریم…")
            paths = nvr_paths(nvr_channel) if nvr_channel else CANDIDATE_PATHS

            def detect():
                found = ""
                for p in paths:
                    if detect_state["cancel"]:
                        return
                    Clock.schedule_once(
                        lambda dt, pp=p: set_busy(
                            True, "در حال بررسی: %s…" % fa_ltr(pp)))
                    url = build_rtsp_url(ip, port, user, pwd, p)
                    if StreamWorker.probe(url):
                        found = p
                        break
                def _done(dt):
                    if detect_state["cancel"]:
                        return
                    set_busy(False)
                    if found:
                        do_save(name, ip, port, user, pwd, found,
                                nvr_channel)
                    else:
                        msg.text = fa("مسیری پیدا نشد. دستی وارد کنید یا "
                                      "تیک تشخیص خودکار را بردارید.")
                        msg.color = C_ERR
                Clock.schedule_once(_done)
            threading.Thread(target=detect, daemon=True).start()

        def do_save(name, ip, port, user, pwd, path, nvr_channel=""):
            app = App.get_running_app()
            if is_new:
                for c in app.cameras.cameras:
                    if (c.get("ip") or "").strip() == ip:
                        msg.text = fa("این دوربین قبلاً اضافه شده است.")
                        msg.color = C_ERR
                        set_busy(False)
                        return
                app.cameras.add(name, ip=ip, port=port, user=user,
                                pwd=pwd, path=path,
                                nvr_channel=nvr_channel)
            else:
                app.cameras.update(cam["id"], name, ip=ip, port=port,
                                   user=user, pwd=pwd, path=path,
                                   nvr_channel=nvr_channel)
            popup.dismiss()
            self.rebuild_grid()

        popup.bind(on_dismiss=lambda *_: detect_state.update(cancel=True))
        popup.open()


def _goto_settings(self, *_):
    App.get_running_app().sm.current = "settings"


def _do_logout(self, *_):
    app = App.get_running_app()
    app.current_user = None
    app.sm.current = "login"


# اتصال به MainScreen
MainScreen.cam_form = _cam_form
MainScreen.goto_settings = _goto_settings
MainScreen.do_logout = _do_logout


# ============================================================ تنظیمات
ABOUT_NOTICE_FA = """«IAS Viewer» — نسخه‌ی ANDROID
حق نشر © 2026 طه عارفی (Taha Arefi)

این برنامه نرم‌افزار آزاد است: شما می‌توانید آن را تحت شرایط
«GNU Affero General Public License» نسخه‌ی ۳ (یا هر نسخه‌ی جدیدتر،
به انتخاب شما) بازنشر و/یا تغییر دهید.

متن کامل لایسنس: فایل LICENSE در ریپوی گیت‌هاب + https://www.gnu.org/licenses/agpl-3.0.html
سورس‌کد: https://github.com/thaarfknight-star/IAS-Viewer-Android

IAS Viewer (ANDROID) — Copyright (C) 2026 Taha Arefi
This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as
published by the Free Software Foundation, either version 3 of the
License, or (at your option) any later version.
Full text: LICENSE file in the GitHub repo — https://www.gnu.org/licenses/agpl-3.0.html"""


class SettingsScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        Window.clearcolor = C_BG
        root = BoxLayout(orientation="vertical", spacing=dp(10),
                         padding=[dp(12), dp(8), dp(12), dp(12)])

        header = BoxLayout(orientation="horizontal", size_hint_y=None,
                           height=dp(56), spacing=dp(8))
        rounded_bg(header, C_SURFACE, RADIUS_SM)
        header.padding = [dp(10), dp(6), dp(10), dp(6)]
        header.add_widget(mk_button("بازگشت", self.go_back,
                                    bg=C_CARD, size_hint_x=0.32,
                                    height=44, font_size="14sp"))
        header.add_widget(mk_label("تنظیمات", size="17sp", bold=True,
                                   halign="right"))
        logo = Image(source="assets/logo_shield.png",
                     size_hint=(None, None), size=(dp(40), dp(40)))
        header.add_widget(logo)
        root.add_widget(header)

        scroll = ScrollView()
        self.content = BoxLayout(orientation="vertical", spacing=dp(12),
                                 size_hint_y=None, padding=dp(4))
        self.content.bind(minimum_height=self.content.setter("height"))
        scroll.add_widget(self.content)
        root.add_widget(scroll)
        self.add_widget(root)

    def go_back(self, *_):
        App.get_running_app().sm.current = "main"

    def on_enter(self):
        self.build()

    def section(self, title):
        card = mk_card()
        card.add_widget(mk_label(title, size="16sp", bold=True,
                                 halign="right", height=30))
        self.content.add_widget(card)
        return card

    def build(self):
        self.content.clear_widgets()
        app = App.get_running_app()

        # --- دوربین‌ها ---
        card = self.section("دوربین‌ها")
        for cam in app.cameras.cameras:
            tag = "[NVR] " if cam.get("nvr_channel") else ""
            name = "%s%s" % (tag, cam.get("name") or "؟")
            row = BoxLayout(orientation="horizontal", size_hint_y=None,
                            height=dp(52), spacing=dp(8))
            row.add_widget(mk_button("حذف", lambda _b, c=cam: self.ask_del(c),
                                     bg=C_ERR, size_hint_x=0.28, height=44,
                                     font_size="14sp"))
            row.add_widget(mk_button("ویرایش",
                                     lambda _b, c=cam: self.edit_cam(c),
                                     bg=C_CARD, size_hint_x=0.32, height=44,
                                     font_size="14sp"))
            row.add_widget(mk_label(name, size="14sp", halign="right",
                                    size_hint_x=0.40))
            card.add_widget(row)

        # --- تغییر رمز ---
        card = self.section("تغییر رمز عبور")
        u = (app.current_user or {}).get("username", "")
        card.add_widget(mk_label("کاربر: %s" % fa_ltr(u), size="13sp",
                                 color=C_MUTED, halign="right", height=24))
        self.old_in = mk_input("رمز فعلی", password=True)
        self.new_in = mk_input("رمز جدید", password=True)
        self.pw_msg = mk_label("", size="13sp", color=C_ERR, height=26)
        card.add_widget(self.old_in)
        card.add_widget(self.new_in)
        card.add_widget(self.pw_msg)
        card.add_widget(mk_button("ذخیره‌ی رمز جدید", self.save_pw,
                                  height=50))

        # --- درباره ---
        card = self.section("درباره‌ی برنامه")
        card.add_widget(mk_label("نسخه‌ی %s" % fa_ltr(VERSION),
                                 size="14sp", bold=True, height=28))
        about = mk_label(ABOUT_NOTICE_FA, size="12sp", color=C_MUTED,
                         halign="right")
        about.bind(size=lambda i, v: setattr(i, "text_size", (v[0], None)))
        card.add_widget(about)

    def edit_cam(self, cam):
        app = App.get_running_app()
        ms = app.sm.get_screen("main")
        app.sm.current = "main"
        Clock.schedule_once(lambda dt: ms.cam_form(cam), 0.1)

    def ask_del(self, cam):
        box = BoxLayout(orientation="vertical", spacing=dp(12),
                        padding=dp(18))
        rounded_bg(box, C_BG, RADIUS)
        box.add_widget(mk_label("«%s» حذف شود؟" % (cam.get("name") or "؟"),
                                size="16sp", height=40))
        row = BoxLayout(orientation="horizontal", size_hint_y=None,
                        height=dp(52), spacing=dp(10))
        row.add_widget(mk_button("انصراف", lambda *_: p.dismiss(),
                                 bg=C_CARD, height=52))
        row.add_widget(mk_button("حذف", lambda *_: self.do_del(cam, p),
                                 bg=C_ERR, height=52))
        box.add_widget(row)
        p = Popup(title="", content=box, size_hint=(0.85, 0.35),
                  background="", background_color=(0, 0, 0, 0),
                  separator_color=(0, 0, 0, 0))
        p.open()

    def do_del(self, cam, popup):
        App.get_running_app().cameras.remove(cam["id"])
        popup.dismiss()
        self.build()
        App.get_running_app().sm.get_screen("main").rebuild_grid()

    def save_pw(self, *_):
        app = App.get_running_app()
        u = (app.current_user or {}).get("username", "")
        if not app.users.verify(u, self.old_in.text):
            self.pw_msg.text = fa("رمز فعلی اشتباه است.")
            return
        if len(self.new_in.text) < 4:
            self.pw_msg.text = fa("رمز جدید حداقل ۴ کاراکتر باشد.")
            return
        app.users.set_password(u, self.new_in.text)
        self.pw_msg.text = fa("رمز با موفقیت تغییر کرد.")
        self.pw_msg.color = C_OK
        self.old_in.text = ""
        self.new_in.text = ""


# ============================================================ اپ
class IASViewerApp(App):
    def build(self):
        Window.clearcolor = C_BG
        self.users = UserStore()
        self.cameras = CameraStore()
        self.current_user = None
        self.sm = ScreenManager()
        self.sm.add_widget(LoginScreen(name="login"))
        self.sm.add_widget(MainScreen(name="main"))
        self.sm.add_widget(SettingsScreen(name="settings"))
        return self.sm


if __name__ == "__main__":
    IASViewerApp().run()
