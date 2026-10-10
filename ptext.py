# -*- coding: utf-8 -*-
"""متن فارسی برای Kivy: reshape + bidi + فونت وزیرمتن.

الگوی اثبات‌شده از پورت اندروید TahaAiVisualizer.
"""
import os

try:
    BASE = os.path.dirname(os.path.abspath(__file__))
except Exception:
    BASE = os.getcwd()
FONT = os.path.join(BASE, "assets", "fonts", "Vazirmatn-Regular.ttf")
FONT_BOLD = os.path.join(BASE, "assets", "fonts", "Vazirmatn-Bold.ttf")

try:
    import arabic_reshaper
    from bidi.algorithm import get_display

    def fa(text):
        """متن فارسی را برای نمایش صحیح در Kivy آماده می‌کند."""
        return get_display(arabic_reshaper.reshape(str(text)))
except Exception:  # اگر کتابخانه‌ها نبودند، متن خام برگردان
    def fa(text):
        return str(text)

def fa_ltr(text):
    return str(text)
