# -*- coding: utf-8 -*-
"""IAS Viewer — نسخه‌ی اندروید (Kivy).

نسخه‌ی مینیمال: فقط «صفحه‌ی اصلی» (پخش زنده‌ی دوربین‌ها) و «تنظیمات»
(مدیریت دوربین‌ها + تغییر رمز). ورود با همان کاربران نسخه‌ی دسکتاپ.
"""
import os

import kivy
kivy.require("2.0.0")

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import Color, Line, RoundedRectangle
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
from camera_store import CameraStore
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
# پالت تایل ویندوز (CameraSlotWidget در نسخه‌ی دسکتاپ)
C_TILE = (0.149, 0.149, 0.149, 1)          # #262626
C_TILE_BORDER = (0.227, 0.227, 0.227, 1)   # #3a3a3a
C_VIDEO_BG = (0.118, 0.118, 0.118, 1)      # #1e1e1e
C_SELECT = (0.204, 0.596, 0.859, 1)        # #3498db (بوردر تایل انتخاب‌شده)
C_NAME = (0.867, 0.867, 0.867, 1)          # #dddddd


def mk_label(text, bold=False, size="15sp", color=C_TEXT, halign="right",
             height=None):
    lbl = Label(text=fa(text), font_name=FONT_BOLD if bold else FONT,
                font_size=size, color=color, halign=halign, valign="middle")
    # بدون text_size، halign/valign اثری ندارد
    lbl.bind(size=lbl.setter("text_size"))
    if height is not None:
        # در باکس‌های اسکرول‌شونده، لیبل بدون ارتفاع مشخص روی هم می‌خوابد
        lbl.size_hint_y = None
        lbl.height = height
    return lbl


def fa_ltr(text):
    """متن لاتین/عددی داخل متن فارسی: با LRE/PDF از به‌هم‌ریختگی bidi
    جلوگیری می‌کند (مثلاً '2.0.80-beta' که 'beta-2.0.80' نمایش داده می‌شد)."""
    return "\u202A%s\u202C" % text


def mk_button(text, on_press, bg=C_ACCENT, size_hint_y=None, height=None):
    b = Button(text=fa(text), font_name=FONT, font_size="15sp",
               background_color=bg, color=(1, 1, 1, 1))
    if size_hint_y is not None:
        b.size_hint_y = size_hint_y
    if height is not None:
        b.height = height
    b.bind(on_press=on_press)
    return b


def mk_input(hint="", password=False, multiline=False):
    t = TextInput(hint_text=fa(hint), font_name=FONT, font_size="15sp",
                  password=password, multiline=multiline,
                  size_hint_y=None, height=dp(48),
                  background_color=(0.22, 0.24, 0.29, 1),
                  foreground_color=C_TEXT, hint_text_color=C_MUTED)
    return t


# ----------------------------------------------------------------------------
class CameraTile(BoxLayout):
    """یک کاشی دوربین عین نسخه‌ی ویندوز: قاب #262626 با بوردر گرد، هدر
    (نام بولد + دکمه‌ی 🔊 صدا مثل ویندوز)، ناحیه‌ی ویدیوی #1e1e1e با گوشه‌ی
    گرد، و خط وضعیت پایین. تک‌لمس = انتخاب (بوردر آبی #3498db مثل ویندوز)،
    دابل‌تپ = تمام‌صفحه (معادل دابل‌کلیک ویندوز)."""

    def __init__(self, cam, **kwargs):
        super().__init__(**kwargs)
        self.orientation = "vertical"
        self.cam = cam
        self.worker = None
        self.selected = False
        self.padding = dp(6)
        self.spacing = dp(4)

        # قاب ویندوزی
        with self.canvas.before:
            Color(*C_TILE)
            self._bg_rect = RoundedRectangle(pos=self.pos, size=self.size,
                                             radius=[dp(8)])
            self._border_color = Color(*C_TILE_BORDER)
            self._border_line = Line(
                rounded_rectangle=(self.x, self.y, self.width, self.height,
                                   dp(8)),
                width=dp(1))
        self.bind(pos=self._redraw_tile, size=self._redraw_tile)

        # هدر: نام + دکمه‌ی صدا
        header = BoxLayout(orientation="horizontal", size_hint_y=None,
                           height=dp(34), spacing=dp(4))
        self.name_lbl = mk_label(cam.get("name") or "؟", bold=True,
                                 size="13sp", color=C_NAME, halign="right")
        self.audio_btn = Button(text="\U0001F50A", font_size="16sp",
                                size_hint=(None, None), size=(dp(36), dp(34)),
                                background_color=(0, 0, 0, 0), color=C_TEXT)
        self.audio_btn.bind(on_press=self._on_audio)
        header.add_widget(self.name_lbl)
        header.add_widget(self.audio_btn)
        self.add_widget(header)

        # ناحیه‌ی ویدیو: #1e1e1e با گوشه‌ی گرد
        vbox = BoxLayout(padding=dp(2))
        with vbox.canvas.before:
            Color(*C_VIDEO_BG)
            self._video_rect = RoundedRectangle(pos=vbox.pos, size=vbox.size,
                                               radius=[dp(6)])
        vbox.bind(pos=self._redraw_video, size=self._redraw_video)
        self.img = Image(allow_stretch=True, keep_ratio=True)
        vbox.add_widget(self.img)
        self.add_widget(vbox)

        # خط وضعیت پایین (مثل ویندوز)
        self.status_lbl = mk_label("…", size="11sp", color=C_MUTED,
                                   halign="right", height=dp(20))
        self.add_widget(self.status_lbl)

    # ------------------------------------------------------------ رسم --
    def _redraw_tile(self, *args):
        self._bg_rect.pos = self.pos
        self._bg_rect.size = self.size
        self._border_line.rounded_rectangle = (
            self.x, self.y, self.width, self.height, dp(8))

    def _redraw_video(self, inst, val):
        self._video_rect.pos = inst.pos
        self._video_rect.size = inst.size

    def set_selected(self, sel):
        self.selected = sel
        if sel:
            self._border_color.rgba = C_SELECT
            self._border_line.width = dp(2)
        else:
            self._border_color.rgba = C_TILE_BORDER
            self._border_line.width = dp(1)

    def _on_audio(self, *_):
        app = App.get_running_app()
        if app:
            app.toast("پخش صدا به‌زودی فعال می‌شود")

    # ------------------------------------------------------------- استریم --
    def start(self):
        self.stop()
        self.worker = StreamWorker(self.cam["url"], self._on_frame,
                                   self._on_state)
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
            "live": ("متصل - پخش زنده", C_OK),
            "error": ("قطع — تلاش مجدد…", C_ERR),
        }
        txt, col = mapping.get(state, ("…", C_MUTED))
        self.status_lbl.text = fa(txt)
        self.status_lbl.color = col

    def on_touch_down(self, touch):
        # اول بچه‌ها (دکمه‌ی 🔊) فرصت بگیرند
        if super().on_touch_down(touch):
            return True
        if self.collide_point(*touch.pos):
            app = App.get_running_app()
            main = app.root.get_screen("main") if app else None
            if main is not None:
                if touch.is_double_tap:
                    main.open_viewer(self)
                else:
                    main.select_tile(self)
            return True
        return False


class LoginScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.name = "login"
        root = BoxLayout(orientation="vertical", padding=dp(24),
                         spacing=dp(12))
        root.add_widget(BoxLayout(size_hint_y=0.15))  # فاصله‌ی بالا
        title = mk_label("IAS Viewer", bold=True, size="28sp",
                         halign="center")
        root.add_widget(title)
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


class MainScreen(Screen):
    """صفحه‌ی اصلی: گرید پخش زنده‌ی دوربین‌ها."""

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
        btn_settings = mk_button("⚙ تنظیمات", self.goto_settings,
                                 bg=(0.25, 0.30, 0.38, 1))
        btn_settings.size_hint_x = 0.35
        btn_logout = mk_button("خروج", self.do_logout,
                               bg=(0.45, 0.25, 0.25, 1))
        btn_logout.size_hint_x = 0.25
        title = mk_label("IAS Viewer", bold=True, size="17sp")
        title.size_hint_x = 0.9
        header.add_widget(self.user_lbl)
        header.add_widget(btn_settings)
        header.add_widget(btn_logout)
        header.add_widget(title)
        root.add_widget(header)

        # بدنه: گرید دوربین‌ها
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
            "هنوز دوربینی تعریف نشده است.\nاز «تنظیمات» دوربین اضافه کنید.",
            size="15sp", color=C_MUTED, halign="center")
        root.add_widget(self.body)

        # نمای تمام‌صفحه (در ابتدا مخفی)
        self.viewer = BoxLayout(orientation="vertical", size_hint_y=None,
                                height=0, opacity=0, disabled=True)
        vheader = BoxLayout(orientation="horizontal", size_hint_y=None,
                            height=dp(52), padding=dp(6))
        vheader.add_widget(mk_button("◀ بازگشت", self.close_viewer,
                                     bg=(0.25, 0.30, 0.38, 1)))
        vheader.add_widget(mk_label("پخش زنده", bold=True, size="16sp"))
        audio_v = Button(text="\U0001F50A", font_size="16sp",
                         size_hint=(None, None), size=(dp(44), dp(44)),
                         background_color=(0, 0, 0, 0), color=C_TEXT)
        audio_v.bind(on_press=lambda *_: App.get_running_app().toast(
            "پخش صدا به‌زودی فعال می‌شود"))
        vheader.add_widget(audio_v)
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

    # -------------------------------------------------------------- گرید --
    def _adapt_grid(self, *_):
        # عمودی: ۲ ستون، افقی: ۳ ستون — در هر دو جهت قابل استفاده
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

    def select_tile(self, tile):
        # مثل ویندوز: تک‌کلیک فقط انتخاب می‌کند (بوردر آبی)
        for t in self.tiles:
            if t is not tile and t.selected:
                t.set_selected(False)
        if not tile.selected:
            tile.set_selected(True)

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
        # برگرداندن به گرید (مرتب‌سازی بر اساس ترتیب اولیه)
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


class SettingsScreen(Screen):
    """تنظیمات: مدیریت دوربین‌ها + تغییر رمز + نسخه."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.name = "settings"
        root = BoxLayout(orientation="vertical")
        header = BoxLayout(orientation="horizontal", size_hint_y=None,
                           height=dp(52), padding=dp(6), spacing=dp(6))
        header.add_widget(mk_button("◀ بازگشت", self.go_back,
                                    bg=(0.25, 0.30, 0.38, 1)))
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
                            height=dp(48), spacing=dp(6))
            row.add_widget(mk_label(cam.get("name") or "؟", size="14sp"))
            b_edit = mk_button("ویرایش", lambda _b, c=cam: self.cam_form(c),
                               bg=(0.25, 0.30, 0.38, 1))
            b_edit.size_hint_x = 0.3
            b_del = mk_button("حذف", lambda _b, c=cam: self.cam_delete(c),
                              bg=(0.55, 0.25, 0.25, 1))
            b_del.size_hint_x = 0.3
            row.add_widget(b_edit)
            row.add_widget(b_del)
            self.content.add_widget(row)
        self.content.add_widget(mk_button("＋ افزودن دوربین",
                                          lambda *_: self.cam_form(None),
                                          size_hint_y=None, height=dp(48)))

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

        # --- نسخه ---
        self.content.add_widget(mk_label(
            "نسخه‌ی برنامه: %s" % fa_ltr(VERSION),
            size="13sp", color=C_MUTED, halign="center", height=dp(28)))

    # ------------------------------------------------------- دوربین‌ها --
    def cam_form(self, cam):
        is_new = cam is None
        box = BoxLayout(orientation="vertical", spacing=dp(10),
                        padding=dp(12))
        name_in = mk_input("نام دوربین (مثلاً: ورودی اصلی)")
        url_in = mk_input("آدرس استریم (مثلاً rtsp://…)")
        if not is_new:
            name_in.text = cam.get("name", "")
            url_in.text = cam.get("url", "")
        msg = mk_label("", size="13sp", color=C_ERR, halign="center")
        box.add_widget(name_in)
        box.add_widget(url_in)
        box.add_widget(msg)
        btns = BoxLayout(orientation="horizontal", size_hint_y=None,
                         height=dp(48), spacing=dp(8))
        popup = Popup(title=fa("افزودن دوربین" if is_new else "ویرایش دوربین"),
                      title_font=FONT, content=box,
                      size_hint=(0.9, 0.55))

        def save(*_):
            app = App.get_running_app()
            if not name_in.text.strip() or not url_in.text.strip():
                msg.text = fa("نام و آدرس هر دو لازم است.")
                return
            if is_new:
                app.cameras.add(name_in.text, url_in.text)
            else:
                app.cameras.update(cam["id"], name_in.text, url_in.text)
            popup.dismiss()
            self.refresh()

        btns.add_widget(mk_button("انصراف", lambda *_: popup.dismiss(),
                                  bg=(0.30, 0.32, 0.36, 1)))
        btns.add_widget(mk_button("ذخیره", save))
        box.add_widget(btns)
        popup.open()

    def cam_delete(self, cam):
        box = BoxLayout(orientation="vertical", spacing=dp(10),
                        padding=dp(12))
        box.add_widget(mk_label("«%s» حذف شود؟" % (cam.get("name") or "؟"),
                                halign="center"))
        btns = BoxLayout(orientation="horizontal", size_hint_y=None,
                         height=dp(48), spacing=dp(8))
        popup = Popup(title=fa("حذف دوربین"), title_font=FONT,
                      content=box, size_hint=(0.9, 0.4))

        def do_del(*_):
            App.get_running_app().cameras.delete(cam["id"])
            popup.dismiss()
            self.refresh()

        btns.add_widget(mk_button("انصراف", lambda *_: popup.dismiss(),
                                  bg=(0.30, 0.32, 0.36, 1)))
        btns.add_widget(mk_button("حذف", do_del, bg=(0.65, 0.28, 0.28, 1)))
        box.add_widget(btns)
        popup.open()

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
                                halign="center"))
        new1 = mk_input("رمز جدید", password=True)
        new2 = mk_input("تکرار رمز جدید", password=True)
        msg = mk_label("", size="13sp", color=C_ERR, halign="center")
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

    def toast(self, msg):
        """پیام کوتاه محو‌شونده (جایگزین Toast اندروید)."""
        popup = Popup(title="", content=mk_label(msg, halign="center"),
                      size_hint=(0.85, None), height=dp(64),
                      background_color=(0.15, 0.16, 0.19, 1),
                      separator_height=0)
        popup.open()
        Clock.schedule_once(lambda dt: popup.dismiss(), 1.6)

    def on_stop(self):
        try:
            self.root.get_screen("main").stop_all()
        except Exception:
            pass


if __name__ == "__main__":
    IASViewerApp().run()
