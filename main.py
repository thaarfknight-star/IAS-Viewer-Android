# -*- coding: utf-8 -*-
"""IAS Viewer — نسخه‌ی اندروید (Kivy).

طراحی هم‌خانواده با نسخه‌ی ویندوز (IAS-CMS):
- صفحه‌ی اصلی: گرید پخش زنده + دراور کناری (دکمه‌ی ☰) شامل
  «اطلاعات ورود»، «اسکن شبکه» و «دوربین‌های من» — دقیقاً مثل سایدبار ویندوز.
- افزودن دوربین به سبک ویندوز: IP/پورت/یوزر/پس + تشخیص خودکار مسیر استریم.
- تنظیمات: تغییر رمز + درباره‌ی برنامه (لایسنس AGPL-3.0) + نسخه.
"""
import os
import threading

import kivy
kivy.require("2.0.0")

from kivy.animation import Animation
from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics.texture import Texture
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.floatlayout import FloatLayout
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
from network_scan import NetworkScanner, COMMON_CCTV_PORTS
from stream_worker import StreamWorker

BASE = os.path.dirname(os.path.abspath(__file__))


def _version():
    try:
        with open(os.path.join(BASE, "version.txt"), encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return "?"


VERSION = _version()

# تم تیره‌ی هم‌خانواده با نسخه‌ی دسکتاپ
C_BG = (0.10, 0.11, 0.14, 1)
C_PANEL = (0.16, 0.18, 0.22, 1)
C_ACCENT = (0.20, 0.55, 0.95, 1)
C_TEXT = (0.93, 0.93, 0.95, 1)
C_MUTED = (0.62, 0.65, 0.70, 1)
C_OK = (0.25, 0.75, 0.40, 1)
C_ERR = (0.95, 0.35, 0.35, 1)

# مسیرهای رایج استریم (زیرمجموعه‌ی CANDIDATE_PATHS ویندوز — پرتکرارترین‌ها)
CANDIDATE_PATHS = [
    "live/ch0",
    "cam/realmonitor?channel=1&subtype=0",
    "Streaming/Channels/101",
    "h264/ch1/main/av_stream",
    "live/main",
    "onvif1",
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
    """متن لاتین/عددی داخل متن فارسی: جلوگیری از به‌هم‌ریختگی bidi."""
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
                  background_color=(0.22, 0.24, 0.29, 1),
                  foreground_color=C_TEXT, hint_text_color=C_MUTED)
    return t


def group_title(text):
    """تیتر گروه‌های دراور — معادل QGroupBox ویندوز."""
    return mk_label(text, bold=True, size="16sp", height=dp(34))


# ----------------------------------------------------------------------------
class CameraTile(BoxLayout):
    """یک کاشی دوربین: نام + وضعیت + تصویر زنده. لمس → تمام‌صفحه."""

    def __init__(self, cam, **kwargs):
        super().__init__(**kwargs)
        self.orientation = "vertical"
        self.cam = cam
        self.worker = None
        self.padding = dp(4)
        self.spacing = dp(4)

        top = BoxLayout(orientation="horizontal", size_hint_y=None,
                        height=dp(30))
        self.name_lbl = mk_label(cam.get("name") or "?", bold=True,
                                 size="14sp", halign="right")
        self.status_lbl = mk_label("…", size="12sp", color=C_MUTED,
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
    """صفحه‌ی اصلی: گرید پخش زنده + دراور کناری به سبک سایدبار ویندوز."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.name = "main"
        self.tiles = []
        self.viewer_tile = None
        self.scanner = None
        self.drawer_open = False

        root = FloatLayout()

        # ---- بدنه‌ی اصلی ----
        self.main_box = BoxLayout(orientation="vertical")
        header = BoxLayout(orientation="horizontal", size_hint_y=None,
                           height=dp(52), padding=dp(6), spacing=dp(6))
        self.user_lbl = mk_label("", size="13sp", color=C_MUTED,
                                 halign="left")
        btn_settings = mk_button("⚙ تنظیمات", self.goto_settings,
                                 bg=(0.25, 0.30, 0.38, 1),
                                 size_hint_x=0.35)
        btn_logout = mk_button("خروج", self.do_logout,
                               bg=(0.45, 0.25, 0.25, 1),
                               size_hint_x=0.25)
        title = mk_label("IAS Viewer", bold=True, size="17sp")
        title.size_hint_x = 0.9
        btn_drawer = mk_button("☰", self.toggle_drawer,
                               bg=(0.25, 0.30, 0.38, 1),
                               size_hint_x=0.18)
        header.add_widget(self.user_lbl)
        header.add_widget(btn_settings)
        header.add_widget(btn_logout)
        header.add_widget(title)
        header.add_widget(btn_drawer)
        self.main_box.add_widget(header)

        self.body = BoxLayout(orientation="vertical")
        self.scroll = ScrollView()
        self.grid = GridLayout(cols=2, spacing=dp(8), padding=dp(8),
                               size_hint_y=None)
        self.grid.bind(minimum_height=self.grid.setter("height"))
        Window.bind(size=self._adapt_grid)
        self._adapt_grid()
        self.scroll.add_widget(self.grid)
        self.body.add_widget(self.scroll)
        self.empty_lbl = mk_label(
            "هنوز دوربینی تعریف نشده است.\nاز منوی ☰ دوربین اضافه کنید.",
            size="15sp", color=C_MUTED, halign="center")
        self.main_box.add_widget(self.body)

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
        self.main_box.add_widget(self.viewer)
        root.add_widget(self.main_box)

        # ---- اسکریم (بستن دراور با لمس بیرون) ----
        self.scrim = Button(size_hint=(1, 1), background_color=(0, 0, 0, 0),
                            opacity=0, disabled=True)
        self.scrim.bind(on_press=lambda *_: self.close_drawer())
        root.add_widget(self.scrim)

        # ---- دراور (سایدبار ویندوز) ----
        self.drawer_width = min(dp(340), int(Window.width * 0.88))
        self.drawer = BoxLayout(orientation="vertical", size_hint=(None, 1),
                                width=self.drawer_width,
                                x=Window.width, y=0)
        with self.drawer.canvas.before:
            from kivy.graphics import Color, Rectangle
            Color(*C_PANEL)
            self._drawer_bg = Rectangle(pos=self.drawer.pos,
                                        size=self.drawer.size)
        self.drawer.bind(pos=self._sync_drawer_bg, size=self._sync_drawer_bg)
        self._build_drawer_content()
        root.add_widget(self.drawer)

        Window.bind(size=self._on_window_resize)
        self.add_widget(root)

    def _sync_drawer_bg(self, *_):
        self._drawer_bg.pos = self.drawer.pos
        self._drawer_bg.size = self.drawer.size

    def _on_window_resize(self, *_):
        self.drawer_width = min(dp(340), int(Window.width * 0.88))
        self.drawer.width = self.drawer_width
        if not self.drawer_open:
            self.drawer.x = Window.width
        else:
            self.drawer.x = Window.width - self.drawer_width

    # ------------------------------------------------------------ دراور --
    def _build_drawer_content(self):
        d = self.drawer
        # سربرگ دراور
        dhead = BoxLayout(orientation="horizontal", size_hint_y=None,
                          height=dp(52), padding=dp(8), spacing=dp(6))
        dhead.add_widget(mk_label("منوی دوربین‌ها", bold=True, size="16sp"))
        dhead.add_widget(mk_button("✕", lambda *_: self.close_drawer(),
                                   bg=(0.45, 0.25, 0.25, 1),
                                   size_hint_x=0.25))
        d.add_widget(dhead)

        scroll = ScrollView()
        content = BoxLayout(orientation="vertical", spacing=dp(10),
                            padding=dp(12), size_hint_y=None)
        content.bind(minimum_height=content.setter("height"))

        # --- اطلاعات ورود (مثل ویندوز: فقط در حافظه) ---
        content.add_widget(group_title("🔑 اطلاعات ورود به دوربین‌ها"))
        self.scan_user = mk_input("نام کاربری", text="admin")
        self.scan_pass = mk_input("رمز عبور", password=True)
        content.add_widget(self.scan_user)
        content.add_widget(self.scan_pass)
        content.add_widget(mk_label("فقط در حافظه نگه‌داشته می‌شود.",
                                    size="12sp", color=C_MUTED,
                                    height=dp(24)))

        # --- اسکن شبکه (مثل ویندوز) ---
        content.add_widget(group_title("📡 اسکن شبکه"))
        self.scan_range = mk_input("رنج IP (مثلاً 192.168.1)",
                                   text="192.168.1")
        content.add_widget(self.scan_range)
        self.scan_btn = mk_button("اسکن شبکه", self.toggle_scan,
                                  size_hint_y=None, height=dp(48))
        content.add_widget(self.scan_btn)
        self.scan_status = mk_label("", size="12sp", color=C_MUTED,
                                    halign="center", height=dp(28))
        content.add_widget(self.scan_status)
        self.scan_results = BoxLayout(orientation="vertical",
                                      spacing=dp(6), size_hint_y=None)
        self.scan_results.bind(
            minimum_height=self.scan_results.setter("height"))
        content.add_widget(self.scan_results)

        # --- دوربین‌های من (مثل «دوربین‌ها و NVRهای من» ویندوز) ---
        content.add_widget(group_title("🎥 دوربین‌های من"))
        content.add_widget(mk_button("＋ افزودن دوربین",
                                     lambda *_: self.cam_form(None),
                                     size_hint_y=None, height=dp(48)))
        self.cam_list = BoxLayout(orientation="vertical", spacing=dp(6),
                                  size_hint_y=None)
        self.cam_list.bind(minimum_height=self.cam_list.setter("height"))
        content.add_widget(self.cam_list)
        content.add_widget(mk_label(
            "برای پخش زنده روی تصویر دوربین بزنید.",
            size="12sp", color=C_MUTED, halign="center", height=dp(28)))

        scroll.add_widget(content)
        d.add_widget(scroll)

    def toggle_drawer(self, *_):
        if self.drawer_open:
            self.close_drawer()
        else:
            self.open_drawer()

    def open_drawer(self):
        self.drawer_open = True
        self.refresh_cam_list()
        self.scrim.disabled = False
        self.scrim.opacity = 1
        # اسکریم نامرئی ولی لمسی
        self.scrim.background_color = (0, 0, 0, 0.001)
        Animation(x=Window.width - self.drawer_width,
                  duration=0.22, t="out_quad").start(self.drawer)

    def close_drawer(self):
        if not self.drawer_open:
            return
        self.drawer_open = False
        self.scrim.disabled = True
        self.scrim.opacity = 0
        Animation(x=Window.width, duration=0.2, t="in_quad").start(
            self.drawer)

    # ------------------------------------------------------- چرخه‌ی صفحه --
    def on_enter(self):
        self.rebuild_grid()

    def on_leave(self):
        self.close_drawer()
        self.stop_scan()
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

    # -------------------------------------------------------------- گرید --
    def _adapt_grid(self, *_):
        self.grid.cols = 2 if Window.height > Window.width else 3

    def stop_all(self):
        for t in self.tiles:
            t.stop()

    def rebuild_grid(self):
        self.close_viewer(silent=True)
        self.stop_all()
        self.tiles = []
        self.grid.clear_widgets()
        app = App.get_running_app()
        cams = app.cameras.enabled_cameras()
        if not cams:
            if self.empty_lbl.parent is None:
                self.body.add_widget(self.empty_lbl)
        else:
            if self.empty_lbl.parent is not None:
                self.body.remove_widget(self.empty_lbl)
        for cam in cams:
            tile = CameraTile(cam, size_hint_y=None, height=dp(220))
            self.tiles.append(tile)
            self.grid.add_widget(tile)
            tile.start()

    # -------------------------------------------------------- تمام‌صفحه --
    def open_viewer(self, tile):
        if self.viewer_tile is not None:
            return
        self.viewer_tile = tile
        self.grid.remove_widget(tile)
        self.viewer_slot.add_widget(tile)
        tile.size_hint_y = 1
        self.body.size_hint_y = None
        self.body.height = 0
        self.body.opacity = 0
        self.body.disabled = True
        self.viewer.size_hint_y = 1
        self.viewer.opacity = 1
        self.viewer.disabled = False

    def close_viewer(self, *_args, silent=False):
        if self.viewer_tile is None:
            return
        tile = self.viewer_tile
        self.viewer_tile = None
        self.viewer_slot.remove_widget(tile)
        tile.size_hint_y = None
        tile.height = dp(220)
        self.grid.clear_widgets()
        for t in self.tiles:
            self.grid.add_widget(t)
        self.body.size_hint_y = 1
        self.body.opacity = 1
        self.body.disabled = False
        self.viewer.size_hint_y = None
        self.viewer.height = 0
        self.viewer.opacity = 0
        self.viewer.disabled = True

    # ------------------------------------------------------- اسکن شبکه --
    def toggle_scan(self, *_):
        if self.scanner and self.scanner.is_alive():
            self.stop_scan()
            return
        self.scan_results.clear_widgets()
        self.scan_btn.text = fa("توقف اسکن")
        self.scan_btn.background_color = (0.65, 0.28, 0.28, 1)
        self.scan_status.text = fa("در حال اسکن…")
        self.scanner = NetworkScanner(
            self.scan_range.text,
            on_found=lambda dev: Clock.schedule_once(
                lambda dt: self._add_scan_row(dev)),
            on_done=lambda devs: Clock.schedule_once(
                lambda dt: self._scan_done(devs)),
        )
        self.scanner.start()

    def stop_scan(self):
        s, self.scanner = self.scanner, None
        if s and s.is_alive():
            s.stop()
        try:
            self.scan_btn.text = fa("اسکن شبکه")
            self.scan_btn.background_color = C_ACCENT
        except Exception:
            pass

    def _scan_done(self, devs):
        self.stop_scan()
        n = len(devs or [])
        self.scan_status.text = fa(
            "%d دستگاه یافت شد." % n if n else "دستگاهی یافت نشد.")

    def _add_scan_row(self, dev):
        ip = dev["ip"]
        ports = ", ".join(str(p) for p in dev["ports"])
        row = BoxLayout(orientation="horizontal", size_hint_y=None,
                        height=dp(48), spacing=dp(6))
        info = mk_label("%s\n%s" % (fa_ltr(ip), fa_ltr(ports)),
                        size="13sp", halign="right")
        info.size_hint_x = 0.65
        row.add_widget(info)
        row.add_widget(mk_button("افزودن",
                                 lambda _b, d=dev: self._scan_add(d),
                                 bg=(0.25, 0.55, 0.35, 1),
                                 size_hint_x=0.35))
        self.scan_results.add_widget(row)

    def _scan_add(self, dev):
        # باز کردن دیالوگ افزودن با IP و یوزر/پس از پیش پرشده (مثل ویندوز)
        self.cam_form(None, prefill_ip=dev["ip"],
                      prefill_user=self.scan_user.text.strip(),
                      prefill_pass=self.scan_pass.text)

    # ------------------------------------------------- لیست دوربین‌ها --
    def refresh_cam_list(self):
        self.cam_list.clear_widgets()
        app = App.get_running_app()
        for cam in app.cameras.cameras:
            row = BoxLayout(orientation="horizontal", size_hint_y=None,
                            height=dp(52), spacing=dp(6))
            name_lbl = mk_label("%s" % (cam.get("name") or "؟"),
                                size="14sp", bold=True)
            name_lbl.size_hint_x = 0.5
            row.add_widget(name_lbl)
            row.add_widget(mk_button("ویرایش",
                                     lambda _b, c=cam: self.cam_form(c),
                                     bg=(0.25, 0.30, 0.38, 1),
                                     size_hint_x=0.25))
            row.add_widget(mk_button("حذف",
                                     lambda _b, c=cam: self.cam_delete(c),
                                     bg=(0.55, 0.25, 0.25, 1),
                                     size_hint_x=0.25))
            self.cam_list.add_widget(row)

    # ------------------------------------------- دیالوگ افزودن/ویرایش --
    def cam_form(self, cam, prefill_ip="", prefill_user="", prefill_pass=""):
        is_new = cam is None
        box = BoxLayout(orientation="vertical", spacing=dp(8),
                        padding=dp(12))
        # مثل دیالوگ ویندوز: نام، IP، پورت، یوزر، پس، تشخیص خودکار، مسیر دستی
        name_in = mk_input("نام دوربین (مثلاً: ورودی اصلی)")
        ip_in = mk_input("آدرس IP دوربین")
        port_in = mk_input("پورت", text="554")
        user_in = mk_input("نام کاربری", text="admin")
        pass_in = mk_input("رمز عبور", password=True)
        if not is_new:
            name_in.text = cam.get("name", "")
            ip_in.text = cam.get("ip", "")
            port_in.text = str(cam.get("port", "554") or "554")
            user_in.text = cam.get("user", "")
            pass_in.text = cam.get("pass", "")
        if prefill_ip:
            ip_in.text = prefill_ip
            if prefill_user:
                user_in.text = prefill_user
            if prefill_pass:
                pass_in.text = prefill_pass
            if not name_in.text:
                name_in.text = prefill_ip

        auto_box = BoxLayout(orientation="horizontal", size_hint_y=None,
                             height=dp(40), spacing=dp(6))
        from kivy.uix.checkbox import CheckBox
        auto_chk = CheckBox(active=True, size_hint_x=None, width=dp(40))
        auto_box.add_widget(auto_chk)
        auto_box.add_widget(mk_label("تشخیص خودکار مسیر استریم",
                                     size="14sp"))
        path_in = mk_input("مسیر دستی استریم (مثلاً live/ch0)",
                           text="" if is_new else cam.get("path", ""))
        path_in.disabled = True
        auto_chk.bind(active=lambda _i, v: setattr(path_in, "disabled", v))

        msg = mk_label("", size="13sp", color=C_ERR, halign="center",
                       height=dp(32))
        for w in (name_in, ip_in, port_in, user_in, pass_in):
            box.add_widget(w)
        box.add_widget(auto_box)
        box.add_widget(path_in)
        box.add_widget(msg)

        popup = Popup(title=fa("افزودن دوربین" if is_new else "ویرایش دوربین"),
                      title_font=FONT, content=box,
                      size_hint=(0.92, 0.88))
        detect_thread = {"t": None, "cancel": False}

        def set_busy(busy, text=""):
            for w in (name_in, ip_in, port_in, user_in, pass_in, path_in):
                w.disabled = busy
            btn_save.disabled = busy
            if text:
                msg.text = fa(text)
                msg.color = C_MUTED

        def do_save(name, ip, port, user, pwd, path):
            app = App.get_running_app()
            if is_new:
                app.cameras.add(name, ip=ip, port=port, user=user,
                                pwd=pwd, path=path)
            else:
                app.cameras.update(cam["id"], name, ip=ip, port=port,
                                   user=user, pwd=pwd, path=path)
            popup.dismiss()
            self.refresh_cam_list()
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
            if auto_chk.active:
                # تشخیص خودکار مسیر (مثل ویندوز) در نخ جدا
                set_busy(True, "در حال تشخیص خودکار مسیر استریم…")
                detect_thread["cancel"] = False

                def detect():
                    found = ""
                    try:
                        import cv2
                    except Exception:
                        cv2 = None
                    for p in CANDIDATE_PATHS:
                        if detect_thread["cancel"]:
                            return
                        Clock.schedule_once(
                            lambda dt, pp=p: set_busy(
                                True, "در حال بررسی مسیر: %s…" % fa_ltr(pp)))
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
                                    ok, _frm = cap.read()
                                cap.release()
                            except Exception:
                                ok = False
                        if ok:
                            found = p
                            break
                    if detect_thread["cancel"]:
                        return
                    Clock.schedule_once(
                        lambda dt: _detect_done(found))

                def _detect_done(found):
                    if found:
                        msg.text = fa("مسیر پیدا شد: %s" % fa_ltr(found))
                        msg.color = C_OK
                        do_save(name_in.text.strip() or ip_in.text.strip(),
                                ip, port, user, pwd, found)
                    else:
                        set_busy(False)
                        msg.text = fa("مسیری پیدا نشد؛ دستی وارد کنید.")
                        msg.color = C_ERR
                        auto_chk.active = False

                detect_thread["t"] = threading.Thread(target=detect,
                                                      daemon=True)
                detect_thread["t"].start()
            else:
                do_save(name, ip, port, user, pwd, path_in.text.strip())

        def on_cancel(*_):
            detect_thread["cancel"] = True
            popup.dismiss()

        btns = BoxLayout(orientation="horizontal", size_hint_y=None,
                         height=dp(48), spacing=dp(8))
        btn_save = mk_button("ذخیره", on_save)
        btns.add_widget(mk_button("انصراف", on_cancel,
                                  bg=(0.30, 0.32, 0.36, 1)))
        btns.add_widget(btn_save)
        box.add_widget(btns)
        popup.bind(on_dismiss=lambda *_: detect_thread.update(cancel=True))
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
            self.refresh_cam_list()
            self.rebuild_grid()

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
متن کامل لایسنس: فایل LICENSE در ریپوی گیت‌هاب
سورس‌کد: https://github.com/thaarfknight-star/IAS-Viewer-Android"""


class SettingsScreen(Screen):
    """تنظیمات: تغییر رمز + درباره‌ی برنامه (لایسنس) + نسخه."""

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

        # --- درباره‌ی برنامه (لایسنس AGPL-3.0) ---
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
        """پاپ‌آپ اجباری تعویض رمز (اولین ورود ادمین)."""
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
