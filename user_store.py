# -*- coding: utf-8 -*-
"""مدیریت کاربران نسخه‌ی اندروید IAS Viewer.

همان طرح user_manager.py نسخه‌ی دسکتاپ، مینیمال برای دو صفحه:
home (صفحه‌ی اصلی) و settings (تنظیمات).

کاربران پیش‌فرض (در اولین اجرا ساخته می‌شوند):
- admin / Aa@@Sorena — ادمین، تعویض رمز در اولین ورود اجباری
- Test / 123456 — فقط صفحه‌ی اصلی و تنظیمات
"""
import hashlib
import hmac
import json
import os
import secrets

DEFAULT_ADMIN_USER = "admin"
DEFAULT_ADMIN_PASS = "Aa@@Sorena"

DEFAULT_TEST_USER = "Test"
DEFAULT_TEST_PASS = "123456"

PAGE_KEYS = ("home", "settings")
TEST_USER_PAGES = ("home", "settings")

_PBKDF2_ITERATIONS = 200_000
_SALT_BYTES = 16


def hash_password(password, salt=None):
    if salt is None:
        salt = secrets.token_bytes(_SALT_BYTES)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt,
                             _PBKDF2_ITERATIONS)
    return salt.hex(), dk.hex()


def verify_password(password, salt_hex, hash_hex):
    salt = bytes.fromhex(salt_hex)
    _, h = hash_password(password, salt)
    return hmac.compare_digest(h, hash_hex)


def _blank_user(username, is_admin=False):
    return {
        "username": username,
        "is_admin": is_admin,
        "salt": "",
        "pass_hash": "",
        "must_change_password": False,
        "permissions": {k: False for k in PAGE_KEYS},
    }


class UserStore:
    def __init__(self, path):
        self.path = path
        self.users = {}
        self.load()

    # ---------------------------------------------------------- ذخیره‌سازی --
    def load(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
            self.users = data.get("users", {}) or {}
        except (OSError, ValueError):
            self.users = {}
        # ترمیم رکوردهای قدیمی
        for rec in self.users.values():
            for k in PAGE_KEYS:
                rec.setdefault("permissions", {}).setdefault(k, False)

    def save(self):
        d = os.path.dirname(self.path)
        if d:
            os.makedirs(d, exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"users": self.users}, f, ensure_ascii=False, indent=1)
        os.replace(tmp, self.path)

    # ---------------------------------------------------------- کاربران پیش‌فرض --
    def ensure_default_admin(self):
        if self.users:
            return False
        rec = _blank_user(DEFAULT_ADMIN_USER, is_admin=True)
        salt, h = hash_password(DEFAULT_ADMIN_PASS)
        rec["salt"] = salt
        rec["pass_hash"] = h
        rec["must_change_password"] = True
        rec["permissions"] = {k: True for k in PAGE_KEYS}
        self.users[DEFAULT_ADMIN_USER] = rec
        self.save()
        return True

    def ensure_test_user(self):
        rec = self.users.get(DEFAULT_TEST_USER)
        changed = False
        if rec is None:
            rec = _blank_user(DEFAULT_TEST_USER, is_admin=False)
            salt, h = hash_password(DEFAULT_TEST_PASS)
            rec["salt"] = salt
            rec["pass_hash"] = h
            rec["must_change_password"] = False
            self.users[DEFAULT_TEST_USER] = rec
            changed = True
        want_perms = {k: (k in TEST_USER_PAGES) for k in PAGE_KEYS}
        if rec.get("permissions") != want_perms:
            rec["permissions"] = want_perms
            changed = True
        if rec.get("is_admin"):
            rec["is_admin"] = False
            changed = True
        if changed:
            self.save()
        return changed

    def ensure_defaults(self):
        self.ensure_default_admin()
        self.ensure_test_user()

    # ---------------------------------------------------------------- ورود --
    def verify(self, username, password):
        rec = self.users.get((username or "").strip())
        if not rec or not rec.get("pass_hash"):
            return None
        if verify_password(password or "", rec["salt"], rec["pass_hash"]):
            return rec
        return None

    def set_password(self, username, new_password):
        rec = self.users.get(username)
        if not rec:
            return False
        salt, h = hash_password(new_password)
        rec["salt"] = salt
        rec["pass_hash"] = h
        rec["must_change_password"] = False
        self.save()
        return True

    @staticmethod
    def can_access(user, page_key):
        if not user:
            return False
        if user.get("is_admin"):
            return True
        return bool(user.get("permissions", {}).get(page_key))
