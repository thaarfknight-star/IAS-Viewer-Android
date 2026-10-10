# -*- coding: utf-8 -*-
"""IAS Viewer — نسخه‌ی اندروید (Kivy).

مثل مرکز صفحه‌ی اصلی ویندوز: گرید ۲×۲ پخش زنده (حداکثر ۴ دوربین) +
افزودن دوربین/NVR + صفحه‌ی تنظیمات. ساده و بدون حاشیه.
"""
import os
import threading

import kivy
kivy.require("2.0.0")

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics.texture import Texture
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

from ptext import fa, FONT, FONT_BOLD
from user_store import UserStore
from camera_store import CameraStore, camera_url, build_rtsp_url
from network_scan import NetworkScanner
from stream_worker import StreamWorker

BASE = os.path.dirname(os.path.abspath(__file__))
MAX_CAMERAS = 4


def _version():
    try:
        with open(os.path.join(BASE, "version.txt"), encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return "?"


VERSION = _version()

# تم تیره — هم‌خانواده با ویندوز
C_BG = (0.05, 0.07, 0.10, 1)
C_PANEL = (0.09, 0.11, 0.14, 1)
C_ACCENT = (0.12, 0.44, 0.94, 1)
C_TEXT = (0.93, 0.93, 0.95, 1)
C_MUTED = (0.55, 0.58, 0.63, 1)
C_OK = (0.25, 0.75, 0.40, 1)
C_ERR = (0.95, 0.35, 0.35, 1)

# مسیرهای رایج استریم دوربین تکی
CANDIDATE_PATHS = [
    "live/ch0",
    "cam/realmonitor?channel=1&subtype=0",
    "Streaming/Channels/101",
    "h264/ch1/main/av_stream",
    "live/main",
    "onvif1",
]


def nvr_channel_paths(channel):
    """مسیرهای رایج کانال NVR بر اساس شماره‌ی کانال."""
    try:
        ch = int(channel)
    except (TypeError, ValueError):
        ch = 1
    return [
        "Streaming/Channels/%d01" % ch,          # Hikvision
        "cam/realmonitor?channel=%d&subtype=0" % ch,  # Dahua اصلی
        "cam/realmonitor?channel=%d&subtype=1" % ch,  # Dahua فرعی
        "h264/ch%d/main/av_stream" % ch,          # Generic/XM
    ]


def mk_label(text, bold=False, size="15sp", color=C_TEXT, halign="right",
             height=None):
    lbl = Label(text=fa(text), font_name=FONT_BOLD if bold else FONT,
                font_size=size, color=color, halign=halign, valign="middle")
    lbl.bind(size=lbl.setter("text_size"))
    if height is not None:
        lbl.size_hint_y = None
        lbl.height = height
    return lbl


def fa_ltr(text):
    return "\u202A%s\u202C" % text


def mk_button(text, on_press, bg=C_ACCENT, size_hint_y=None, height=None,
              size_hint_x=None):
    b = Button(text=fa(text), font_name=FONT, font_size="15sp",
               background_color=bg, color=(1, 1, 1, 1))
    if size_hint_y is not None:
        b.size_hint_y = size_hint_y
    if height is not None:
        b.height = height
    if size_hint_x is not None:
        b.size_hint_x = size_hint_x
    b.bind(on_press=on_press)
    return b


def mk_input(hint="", password=False, multiline=False, text=""):
    t = TextInput(hint_text=fa(hint), text=text, font_name=FONT,
                  font_size="15sp", password=password, multiline=multiline,
                  size_hint_y=None, height=dp(48),
                  background_color=(0.13, 0.15, 0.19, 1),
                  foreground_color=C_TEXT, hint_text_color=C_MUTED)
    return t


# ----------------------------------------------------------------------------
class CameraTile(BoxLayout):
    """کاشی دوربین: تصویر زنده + نام + وضعیت. لمس → تمام‌صفحه."""

    def __init__(self, cam, **kwargs):
        super().__init__(**kwargs)
        self.orientation = "vertical"
        self.cam = cam
        self.worker = None
        self.padding = dp(4)
        self.spacing = dp(2)

        top = BoxLayout(orientation="horizontal", size_hint_y=None,
                        height=dp(28))
        self.name_lbl = mk_label(cam.get("name") or "?", bold=True,
                                 size="13sp", halign="right")
        self.status_lbl = mk_label("…", size="11sp", color=C_MUTED,
                                   halign="left")
        top.add_widget(self.name_lbl)
        top.add_widget(self.status_lbl)
        self.add_widget(top)

        self.img = Image(allow_stretch=True, keep_ratio=True)
        self.add_widget(self.img)

    def start(self):
        self.stop()
        url = camera_url(self.cam)
        if not url:
            self._on_state("error")
            return
        self.worker = StreamWorker(url, self._on_frame, self._on_state)
        self.worker.start()

    def stop(self):
        w, self.worker = self.worker, None
        if w:
            w.stop()

    def _on_frame(self, frame):
        try:
            import cv2
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        except Exception:
            return
        h, w = rgb.shape[:2]
        buf = rgb.tobytes()
        Clock.schedule_once(lambda dt: self._blit(buf, w, h))

    def _blit(self, buf, w, h):
        try:
            tex = self.img.texture
            if tex is None or tex.width != w or tex.height != h:
                tex = Texture.create(size=(w, h), colorfmt="rgb")
                tex.flip_vertical()
                self.img.texture = tex
            tex.blit_buffer(buf, colorfmt="rgb", bufferfmt="ubyte")
            self.img.canvas.ask_update()
        except Exception:
            pass

    def _on_state(self, state):
        Clock.schedule_once(lambda dt: self._show_state(state))

    def _show_state(self, state):
        mapping = {
            "connecting": ("در حال اتصال…", C_MUTED),
            "live": ("● زنده", C_OK),
            "error": ("قطع — تلاش مجدد…", C_ERR),
        }
        txt, col = mapping.get(state, ("…", C_MUTED))
        self.status_lbl.text = fa(txt)
        self.status_lbl.color = col

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            app = App.get_running_app()
            if app:
                app.root.get_screen("main").open_viewer(self)
            return True
        return super().on_touch_down(touch)


class EmptyTile(Button):
    """خانه‌ی خالی گرید (مثل «خالی» ویندوز) — لمس → افزودن دوربین."""

    def __init__(self, on_add, **kwargs):
        super().__init__(**kwargs)
        self.text = fa("خالی\n＋ افزودن")
        self.font_name = FONT
        self.font_size = "16sp"
        self.color = C_MUTED
        self.background_color = (0.09, 0.11, 0.14, 1)
        self.bind(on_press=lambda *_: on_add())


# ----------------------------------------------------------------------------
class LoginScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.name = "login"
        root = BoxLayout(orientation="vertical", padding=dp(24),
                         spacing=dp(12))
        root.add_widget(BoxLayout(size_hint_y=0.15))
        root.add_widget(mk_label("IAS Viewer", bold=True, size="28sp",
                                 halign="center"))
        root.add_widget(mk_label("ورود به برنامه", size="16sp",
                                 color=C_MUTED, halign="center"))
        self.username = mk_input("نام کاربری")
        self.password = mk_input("رمز عبور", password=True)
        self.err = mk_label("", size="14sp", color=C_ERR, halign="center")
        root.add_widget(self.username)
        root.add_widget(self.password)
        root.add_widget(mk_button("ورود", self.do_login,
                                  size_hint_y=None, height=dp(52)))
        root.add_widget(self.err)
        root.add_widget(BoxLayout(size_hint_y=0.35))
        self.add_widget(root)

    def do_login(self, *_):
        app = App.get_running_app()
        user = app.users.verify(self.username.text, self.password.text)
        if not user:
            self.err.text = fa("نام کاربری یا رمز عبور اشتباه است.")
            return
        self.err.text = ""
        self.password.text = ""
        app.current_user = user
        if user.get("must_change_password"):
            app.force_change_password(self._after_forced)
        else:
            self._go_main()

    def _after_forced(self, done):
        if done:
            self._go_main()

    def _go_main(self):
        app = App.get_running_app()
        app.root.get_screen("main").refresh_user()
        app.root.current = "main"


# ----------------------------------------------------------------------------
class MainScreen(Screen):
    """صفحه‌ی اصلی: گرید ۲×۲ پخش زنده (حداکثر ۴ دوربین) مثل ویندوز."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.name = "main"
        self.tiles = []
        self.viewer_tile = None

        root = BoxLayout(orientation="vertical")
        # هدر
        header = BoxLayout(orientation="horizontal", size_hint_y=None,
                           height=dp(52), padding=dp(6), spacing=dp(6))
        self.user_lbl = mk_label("", size="13sp", color=C_MUTED,
                                 halign="left")
        btn_settings = mk_button("⚙", self.goto_settings,
                                 bg=(0.25, 0.30, 0.38, 1),
                                 size_hint_x=0.16)
        btn_add = mk_button("＋", self.add_camera,
                            bg=(0.25, 0.55, 0.35, 1),
                            size_hint_x=0.16)
        title = mk_label("IAS Viewer", bold=True, size="17sp")
        btn_logout = mk_button("خروج", self.do_logout,
                               bg=(0.45, 0.25, 0.25, 1),
                               size_hint_x=0.22)
        header.add_widget(self.user_lbl)
        header.add_widget(btn_logout)
        header.add_widget(title)
        header.add_widget(btn_settings)
        header.add_widget(btn_add)
        root.add_widget(header)

        # گرید ۲×۲ ثابت
        self.grid = GridLayout(cols=2, spacing=dp(8), padding=dp(8))
        root.add_widget(self.grid)

        # نمای تمام‌صفحه
        self.viewer = BoxLayout(orientation="vertical", size_hint_y=None,
                                height=0, opacity=0, disabled=True)
        vheader = BoxLayout(orientation="horizontal", size_hint_y=None,
                            height=dp(52), padding=dp(6))
        vheader.add_widget(mk_button("◀ بازگشت", self.close_viewer,
                                     bg=(0.25, 0.30, 0.38, 1)))
        vheader.add_widget(mk_label("پخش زنده", bold=True, size="16sp"))
        self.viewer.add_widget(vheader)
        self.viewer_slot = BoxLayout(orientation="vertical")
        self.viewer.add_widget(self.viewer_slot)
        root.add_widget(self.viewer)

        self.add_widget(root)

    # -------------------------------------------------------------- چرخه --
    def on_enter(self):
        self.rebuild_grid()

    def on_leave(self):
        self.close_viewer(silent=True)
        self.stop_all()

    def refresh_user(self):
        app = App.get_running_app()
        u = app.current_user or {}
        self.user_lbl.text = fa("کاربر: %s" % u.get("username", ""))

    def do_logout(self, *_):
        self.on_leave()
        app = App.get_running_app()
        app.current_user = None
        app.root.current = "login"

    def goto_settings(self, *_):
        app = App.get_running_app()
        if not UserStore.can_access(app.current_user, "settings"):
            return
        self.on_leave()
        app.root.get_screen("settings").refresh()
        app.root.current = "settings"

    def add_camera(self, *_):
        app = App.get_running_app()
        if len(app.cameras.cameras) >= MAX_CAMERAS:
            return
        self.cam_form(None)

    # -------------------------------------------------------------- گرید --
    def stop_all(self):
        for t in self.tiles:
            t.stop()

    def rebuild_grid(self):
        self.close_viewer(silent=True)
        self.stop_all()
        self.tiles = []
        self.grid.clear_widgets()
        app = App.get_running_app()
        cams = app.cameras.enabled_cameras()[:MAX_CAMERAS]
        for cam in cams:
            tile = CameraTile(cam)
            self.tiles.append(tile)
            self.grid.add_widget(tile)
            tile.start()
        # خانه‌های خالی (مثل «خالی» ویندوز)
        for _ in range(MAX_CAMERAS - len(cams)):
            self.grid.add_widget(EmptyTile(self.add_camera))

    # -------------------------------------------------------- تمام‌صفحه --
    def open_viewer(self, tile):
        if self.viewer_tile is not None or not isinstance(tile, CameraTile):
            return
        self.viewer_tile = tile
        self.grid.remove_widget(tile)
        self.viewer_slot.add_widget(tile)
        tile.size_hint_y = 1
        self.grid.size_hint_y = None
        self.grid.height = 0
        self.grid.opacity = 0
        self.grid.disabled = True
        self.viewer.size_hint_y = 1
        self.viewer.opacity = 1
        self.viewer.disabled = False

    def close_viewer(self, *_args, silent=False):
        if self.viewer_tile is None:
            return
        tile = self.viewer_tile
        self.viewer_tile = None
        self.viewer_slot.remove_widget(tile)
        self.grid.size_hint_y = 1
        self.grid.opacity = 1
        self.grid.disabled = False
        self.viewer.size_hint_y = None
        self.viewer.height = 0
        self.viewer.opacity = 0
        self.viewer.disabled = True
        self.rebuild_grid()

    # ------------------------------------------- دیالوگ افزودن/ویرایش --
    def open_scan(self, on_pick):
        """پاپ‌آپ اسکن شبکه — با «افزودن» هر دستگاه، IP به فرم برمی‌گردد."""
        box = BoxLayout(orientation="vertical", spacing=dp(8),
                        padding=dp(12))
        range_in = mk_input("رنج IP (مثلاً 192.168.1)", text="192.168.1")
        box.add_widget(range_in)
        scan_btn = mk_button("اسکن شبکه", lambda *_: None,
                             size_hint_y=None, height=dp(48))
        box.add_widget(scan_btn)
        status = mk_label("", size="12sp", color=C_MUTED, halign="center",
                          height=dp(28))
        box.add_widget(status)
        scroll = ScrollView()
        results = BoxLayout(orientation="vertical", spacing=dp(6),
                            size_hint_y=None)
        results.bind(minimum_height=results.setter("height"))
        scroll.add_widget(results)
        box.add_widget(scroll)
        box.add_widget(mk_button("بستن", lambda *_: close(),
                                 bg=(0.30, 0.32, 0.36, 1),
                                 size_hint_y=None, height=dp(48)))

        popup = Popup(title=fa("📡 اسکن شبکه"), title_font=FONT,
                      content=box, size_hint=(0.92, 0.85))
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
                scan_btn.text = fa("اسکن شبکه")
                status.text = fa("متوقف شد.")
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
            row = BoxLayout(orientation="horizontal", size_hint_y=None,
                            height=dp(52), spacing=dp(6))
            row.add_widget(mk_label("%s\n%s" % (fa_ltr(ip), fa_ltr(ports)),
                                    size="13sp", size_hint_x=0.65))
            row.add_widget(mk_button("افزودن",
                                     lambda _b, d=dev: pick(d),
                                     bg=(0.25, 0.55, 0.35, 1),
                                     size_hint_x=0.35))
            results.add_widget(row)

        def done(devs):
            scanner["t"] = None
            scan_btn.text = fa("اسکن شبکه")
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

    def cam_form(self, cam, prefill=None):
        is_new = cam is None
        prefill = prefill or {}
        box = BoxLayout(orientation="vertical", spacing=dp(8),
                        padding=dp(12))

        # دکمه‌ی اسکن شبکه — IP پیدا شده را در فرم پر می‌کند
        def _pick_ip(ip):
            ip_in.text = ip
            if not name_in.text.strip():
                name_in.text = ip

        box.add_widget(mk_button("📡 اسکن شبکه",
                                 lambda *_: self.open_scan(_pick_ip),
                                 bg=(0.25, 0.30, 0.38, 1),
                                 size_hint_y=None, height=dp(48)))

        # انتخاب نوع: دوربین / NVR (مثل دکمه‌های ویندوز)
        type_box = BoxLayout(orientation="horizontal", size_hint_y=None,
                             height=dp(48), spacing=dp(8))
        btn_type_cam = mk_button("🎥 دوربین", lambda *_: set_type("cam"),
                                 bg=C_ACCENT)
        btn_type_nvr = mk_button("🖥 NVR", lambda *_: set_type("nvr"),
                                 bg=(0.25, 0.30, 0.38, 1))
        type_box.add_widget(btn_type_cam)
        type_box.add_widget(btn_type_nvr)
        box.add_widget(type_box)
        cam_type = {"v": "cam"}

        def set_type(t):
            cam_type["v"] = t
            is_nvr = (t == "nvr")
            btn_type_cam.background_color = (
                C_ACCENT if not is_nvr else (0.25, 0.30, 0.38, 1))
            btn_type_nvr.background_color = (
                C_ACCENT if is_nvr else (0.25, 0.30, 0.38, 1))
            chan_in.disabled = not is_nvr
            chan_in.opacity = 1 if is_nvr else 0
            chan_in.height = dp(48) if is_nvr else 0
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

        if not is_new:
            name_in.text = cam.get("name", "")
            ip_in.text = cam.get("ip", "")
            port_in.text = str(cam.get("port", "554") or "554")
            user_in.text = cam.get("user", "")
            pass_in.text = cam.get("pass", "")
            if cam.get("nvr_channel"):
                set_type("nvr")
                chan_in.text = str(cam.get("nvr_channel"))
        for k, w in (("name", name_in), ("ip", ip_in), ("user", user_in)):
            if prefill.get(k):
                w.text = prefill[k]
        if prefill.get("pass"):
            pass_in.text = prefill["pass"]

        from kivy.uix.checkbox import CheckBox
        auto_box = BoxLayout(orientation="horizontal", size_hint_y=None,
                             height=dp(40), spacing=dp(6))
        auto_chk = CheckBox(active=True, size_hint_x=None, width=dp(40))
        auto_box.add_widget(auto_chk)
        auto_box.add_widget(mk_label("تشخیص خودکار مسیر استریم",
                                     size="14sp"))
        path_in = mk_input("مسیر دستی (مثلاً live/ch0)")
        path_in.disabled = True
        auto_chk.bind(active=lambda _i, v: setattr(path_in, "disabled", v))

        msg = mk_label("", size="13sp", color=C_ERR, halign="center",
                       height=dp(32))
        for w in (name_in, ip_in, port_in, user_in, pass_in, chan_in):
            box.add_widget(w)
        box.add_widget(auto_box)
        box.add_widget(path_in)
        box.add_widget(msg)

        popup = Popup(title=fa("افزودن دوربین / NVR" if is_new else
                               "ویرایش دوربین"),
                      title_font=FONT, content=box, size_hint=(0.92, 0.92))
        detect_state = {"cancel": False}

        def set_busy(busy, text=""):
            for w in (name_in, ip_in, port_in, user_in, pass_in, path_in,
                      chan_in):
                w.disabled = busy
            btn_save.disabled = busy
            if text:
                msg.text = fa(text)
                msg.color = C_MUTED

        def do_save(name, ip, port, user, pwd, path, nvr_channel=""):
            app = App.get_running_app()
            if is_new:
                app.cameras.add(name, ip=ip, port=port, user=user,
                                pwd=pwd, path=path,
                                nvr_channel=nvr_channel)
            else:
                app.cameras.update(cam["id"], name, ip=ip, port=port,
                                   user=user, pwd=pwd, path=path,
                                   nvr_channel=nvr_channel)
            popup.dismiss()
            self.rebuild_grid()

        def on_save(*_):
            name = name_in.text.strip()
            ip = ip_in.text.strip()
            if not ip:
                msg.text = fa("آدرس IP لازم است.")
                msg.color = C_ERR
                return
            if not name:
                name = ip
            port = port_in.text.strip() or "554"
            user = user_in.text.strip()
            pwd = pass_in.text
            is_nvr = (cam_type["v"] == "nvr")
            channel = chan_in.text.strip() or "1" if is_nvr else ""

            if is_nvr:
                paths = nvr_channel_paths(channel)
            elif auto_chk.active:
                paths = CANDIDATE_PATHS
            else:
                do_save(name, ip, port, user, pwd, path_in.text.strip())
                return

            # تشخیص خودکار در نخ جدا
            set_busy(True, "در حال تشخیص خودکار مسیر استریم…")
            detect_state["cancel"] = False

            def detect():
                found = ""
                try:
                    import cv2
                except Exception:
                    cv2 = None
                for p in paths:
                    if detect_state["cancel"]:
                        return
                    Clock.schedule_once(
                        lambda dt, pp=p: set_busy(
                            True, "در حال بررسی: %s…" % fa_ltr(pp)))
                    url = build_rtsp_url(ip, port, user, pwd, p)
                    ok = False
                    if cv2 is not None:
                        try:
                            cap = cv2.VideoCapture()
                            try:
                                cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC,
                                        4000)
                            except Exception:
                                pass
                            if cap.open(url):
                                ok, _f = cap.read()
                            cap.release()
                        except Exception:
                            ok = False
                    if ok:
                        found = p
                        break
                if detect_state["cancel"]:
                    return
                Clock.schedule_once(lambda dt: _done(found))

            def _done(found):
                if found:
                    do_save(name_in.text.strip() or ip_in.text.strip(),
                            ip, port, user, pwd, found,
                            nvr_channel=channel if is_nvr else "")
                else:
                    set_busy(False)
                    msg.text = fa("مسیری پیدا نشد؛ دستی وارد کنید.")
                    msg.color = C_ERR
                    if not is_nvr:
                        auto_chk.active = False

            threading.Thread(target=detect, daemon=True).start()

        def on_cancel(*_):
            detect_state["cancel"] = True
            popup.dismiss()

        btns = BoxLayout(orientation="horizontal", size_hint_y=None,
                         height=dp(48), spacing=dp(8))
        btn_save = mk_button("ذخیره", on_save)
        btns.add_widget(mk_button("انصراف", on_cancel,
                                  bg=(0.30, 0.32, 0.36, 1)))
        btns.add_widget(btn_save)
        box.add_widget(btns)
        popup.bind(on_dismiss=lambda *_: detect_state.update(cancel=True))
        popup.open()

    def cam_delete(self, cam):
        box = BoxLayout(orientation="vertical", spacing=dp(10),
                        padding=dp(12))
        box.add_widget(mk_label("«%s» حذف شود؟" % (cam.get("name") or "؟"),
                                halign="center", height=dp(40)))
        btns = BoxLayout(orientation="horizontal", size_hint_y=None,
                         height=dp(48), spacing=dp(8))
        popup = Popup(title=fa("حذف دوربین"), title_font=FONT,
                      content=box, size_hint=(0.9, 0.4))

        def do_del(*_):
            App.get_running_app().cameras.delete(cam["id"])
            popup.dismiss()
            self.rebuild_grid()
            app = App.get_running_app()
            app.root.get_screen("settings").refresh()

        btns.add_widget(mk_button("انصراف", lambda *_: popup.dismiss(),
                                  bg=(0.30, 0.32, 0.36, 1)))
        btns.add_widget(mk_button("حذف", do_del, bg=(0.65, 0.28, 0.28, 1)))
        box.add_widget(btns)
        popup.open()


# ----------------------------------------------------------------------------
ABOUT_NOTICE_FA = """«IAS Viewer» — نسخه‌ی ANDROID
Copyright (C) 2026 Taha Arefi (طه عارفی)

این برنامه نرم‌افزار آزاد است: شما می‌توانید آن را تحت شرایط
«GNU Affero General Public License» نسخه‌ی ۳ (یا هر نسخه‌ی جدیدتر،
به انتخاب شما) بازتوزیع و/یا اصلاح کنید.
متن کامل لایسنس: فایل LICENSE در ریپوی گیت‌هاب + https://www.gnu.org/licenses/agpl-3.0.html
سورس‌کد: https://github.com/thaarfknight-star/IAS-Viewer-Android

---

IAS Viewer (ANDROID) — Copyright (C) 2026 Taha Arefi
This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published
by the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
Full text: LICENSE file in the GitHub repo — https://www.gnu.org/licenses/agpl-3.0.html"""


class SettingsScreen(Screen):
    """تنظیمات: دوربین‌ها + تغییر رمز + درباره‌ی برنامه + نسخه."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.name = "settings"
        root = BoxLayout(orientation="vertical")
        header = BoxLayout(orientation="horizontal", size_hint_y=None,
                           height=dp(52), padding=dp(6), spacing=dp(6))
        header.add_widget(mk_button("◀ بازگشت", self.go_back,
                                    bg=(0.25, 0.30, 0.38, 1),
                                    size_hint_x=0.35))
        header.add_widget(mk_label("⚙ تنظیمات", bold=True, size="17sp"))
        root.add_widget(header)

        scroll = ScrollView()
        self.content = BoxLayout(orientation="vertical", spacing=dp(10),
                                 padding=dp(12), size_hint_y=None)
        self.content.bind(minimum_height=self.content.setter("height"))
        scroll.add_widget(self.content)
        root.add_widget(scroll)
        self.add_widget(root)

    def go_back(self, *_):
        app = App.get_running_app()
        app.root.current = "main"

    def refresh(self):
        self.content.clear_widgets()
        app = App.get_running_app()
        u = app.current_user or {}
        self.content.add_widget(mk_label("کاربر: %s" % u.get("username", ""),
                                         size="14sp", color=C_MUTED,
                                         height=dp(28)))

        # --- دوربین‌ها ---
        self.content.add_widget(mk_label("دوربین‌ها", bold=True,
                                         size="17sp", height=dp(36)))
        for cam in app.cameras.cameras:
            row = BoxLayout(orientation="horizontal", size_hint_y=None,
                            height=dp(52), spacing=dp(6))
            tag = "🖥" if cam.get("nvr_channel") else "🎥"
            name = "%s %s" % (tag, cam.get("name") or "؟")
            row.add_widget(mk_label(name, size="14sp", bold=True,
                                    size_hint_x=0.5))
            row.add_widget(mk_button("ویرایش",
                                     lambda _b, c=cam: self._edit(c),
                                     bg=(0.25, 0.30, 0.38, 1),
                                     size_hint_x=0.25))
            row.add_widget(mk_button("حذف",
                                     lambda _b, c=cam: self._delete(c),
                                     bg=(0.55, 0.25, 0.25, 1),
                                     size_hint_x=0.25))
            self.content.add_widget(row)
        self.content.add_widget(mk_label(
            "حداکثر %d دوربین." % MAX_CAMERAS, size="12sp", color=C_MUTED,
            halign="center", height=dp(24)))

        # --- تغییر رمز ---
        self.content.add_widget(mk_label("تغییر رمز عبور", bold=True,
                                         size="17sp", height=dp(36)))
        self.old_pw = mk_input("رمز فعلی", password=True)
        self.new_pw = mk_input("رمز جدید", password=True)
        self.new_pw2 = mk_input("تکرار رمز جدید", password=True)
        self.pw_msg = mk_label("", size="13sp", halign="center",
                               height=dp(28))
        self.content.add_widget(self.old_pw)
        self.content.add_widget(self.new_pw)
        self.content.add_widget(self.new_pw2)
        self.content.add_widget(mk_button("ذخیره‌ی رمز جدید",
                                          self.change_password,
                                          size_hint_y=None, height=dp(48)))
        self.content.add_widget(self.pw_msg)

        # --- درباره‌ی برنامه ---
        self.content.add_widget(mk_label("درباره‌ی برنامه", bold=True,
                                         size="17sp", height=dp(36)))
        about = mk_label(ABOUT_NOTICE_FA, size="13sp", color=C_MUTED,
                         halign="right")
        about.size_hint_y = None
        about.bind(texture_size=lambda _i, v: setattr(about, "height",
                                                      v[1] + dp(16)))
        self.content.add_widget(about)

        # --- نسخه ---
        self.content.add_widget(mk_label(
            "نسخه‌ی برنامه: %s" % fa_ltr(VERSION),
            size="13sp", color=C_MUTED, halign="center", height=dp(28)))

    def _edit(self, cam):
        app = App.get_running_app()
        app.root.get_screen("main").cam_form(cam)

    def _delete(self, cam):
        app = App.get_running_app()
        app.root.get_screen("main").cam_delete(cam)

    # ------------------------------------------------------- تغییر رمز --
    def change_password(self, *_):
        app = App.get_running_app()
        u = app.current_user or {}
        if not app.users.verify(u.get("username", ""), self.old_pw.text):
            self.pw_msg.text = fa("رمز فعلی اشتباه است.")
            self.pw_msg.color = C_ERR
            return
        if len(self.new_pw.text) < 4:
            self.pw_msg.text = fa("رمز جدید باید حداقل ۴ کاراکتر باشد.")
            self.pw_msg.color = C_ERR
            return
        if self.new_pw.text != self.new_pw2.text:
            self.pw_msg.text = fa("تکرار رمز جدید مطابقت ندارد.")
            self.pw_msg.color = C_ERR
            return
        app.users.set_password(u["username"], self.new_pw.text)
        app.current_user = app.users.users[u["username"]]
        self.old_pw.text = self.new_pw.text = self.new_pw2.text = ""
        self.pw_msg.text = fa("رمز با موفقیت تغییر کرد.")
        self.pw_msg.color = C_OK


# ----------------------------------------------------------------------------
class IASViewerApp(App):
    def build(self):
        self.title = "IAS Viewer"
        data = self.user_data_dir
        self.users = UserStore(os.path.join(data, "users.json"))
        self.users.ensure_defaults()
        self.cameras = CameraStore(os.path.join(data, "cameras.json"))
        self.current_user = None

        sm = ScreenManager()
        sm.add_widget(LoginScreen())
        sm.add_widget(MainScreen())
        sm.add_widget(SettingsScreen())
        return sm

    def force_change_password(self, callback):
        box = BoxLayout(orientation="vertical", spacing=dp(10),
                        padding=dp(12))
        box.add_widget(mk_label("در اولین ورود باید رمز عبور را عوض کنید.",
                                halign="center", height=dp(40)))
        new1 = mk_input("رمز جدید", password=True)
        new2 = mk_input("تکرار رمز جدید", password=True)
        msg = mk_label("", size="13sp", color=C_ERR, halign="center",
                       height=dp(28))
        box.add_widget(new1)
        box.add_widget(new2)
        box.add_widget(msg)
        popup = Popup(title=fa("تعویض رمز عبور"), title_font=FONT,
                      content=box, size_hint=(0.9, 0.6),
                      auto_dismiss=False)

        def save(*_):
            if len(new1.text) < 4:
                msg.text = fa("رمز جدید باید حداقل ۴ کاراکتر باشد.")
                return
            if new1.text != new2.text:
                msg.text = fa("تکرار رمز مطابقت ندارد.")
                return
            u = self.current_user or {}
            self.users.set_password(u.get("username", ""), new1.text)
            self.current_user = self.users.users.get(u.get("username"))
            popup.dismiss()
            callback(True)

        def cancel(*_):
            self.current_user = None
            popup.dismiss()
            callback(False)

        btns = BoxLayout(orientation="horizontal", size_hint_y=None,
                         height=dp(48), spacing=dp(8))
        btns.add_widget(mk_button("انصراف", cancel,
                                  bg=(0.30, 0.32, 0.36, 1)))
        btns.add_widget(mk_button("ذخیره", save))
        box.add_widget(btns)
        popup.open()

    def on_stop(self):
        try:
            self.root.get_screen("main").stop_all()
        except Exception:
            pass


if __name__ == "__main__":
    IASViewerApp().run()
