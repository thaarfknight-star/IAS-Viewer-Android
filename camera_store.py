# -*- coding: utf-8 -*-
"""لیست دوربین‌های نسخه‌ی اندروید (cameras.json).

مدل ویندوزی: هر دوربین با ip/port/user/pass/path ذخیره می‌شود و آدرس
استریم از روی آن‌ها ساخته می‌شود (مثل build_rtsp_url در نسخه‌ی ویندوز).
رکوردهای قدیمیِ فقط-url هم همچنان کار می‌کنند.
"""
import json
import os
import uuid
from urllib.parse import quote


def build_rtsp_url(ip, port, user, pwd, path):
    """ساخت آدرس RTSP از اجزا — معادل build_rtsp_url نسخه‌ی ویندوز."""
    ip = (ip or "").strip()
    if not ip:
        return ""
    port = str(port or "554").strip() or "554"
    user = (user or "").strip()
    pwd = (pwd or "").strip()
    path = (path or "").strip().lstrip("/")
    auth = ""
    if user:
        auth = quote(user, safe="") + (":" + quote(pwd, safe="") if pwd else "") + "@"
    url = "rtsp://%s%s:%s" % (auth, ip, port)
    if path:
        url += "/" + path
    return url


def camera_url(cam):
    """آدرس نهایی استریم یک دوربین: url ذخیره‌شده، یا ساخته‌شده از اجزا."""
    if not isinstance(cam, dict):
        return ""
    direct = (cam.get("url") or "").strip()
    if direct:
        return direct
    return build_rtsp_url(cam.get("ip"), cam.get("port"),
                          cam.get("user"), cam.get("pass"),
                          cam.get("path"))


class CameraStore:
    def __init__(self, path):
        self.path = path
        self.cameras = []
        self.load()

    def load(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
            cams = data.get("cameras", []) or []
            self.cameras = [c for c in cams if isinstance(c, dict)]
        except (OSError, ValueError):
            self.cameras = []
        for c in self.cameras:
            c.setdefault("id", uuid.uuid4().hex[:8])
            c.setdefault("name", "")
            c.setdefault("url", "")
            c.setdefault("ip", "")
            c.setdefault("port", "554")
            c.setdefault("user", "")
            c.setdefault("pass", "")
            c.setdefault("path", "")
            c.setdefault("enabled", True)

    def save(self):
        d = os.path.dirname(self.path)
        if d:
            os.makedirs(d, exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"cameras": self.cameras}, f, ensure_ascii=False, indent=1)
        os.replace(tmp, self.path)

    def add(self, name, ip="", port="554", user="", pwd="", path="", url=""):
        cam = {"id": uuid.uuid4().hex[:8], "name": name.strip(),
               "ip": ip.strip(), "port": (port or "554").strip(),
               "user": user.strip(), "pass": pwd or "",
               "path": path.strip(), "url": url.strip(),
               "enabled": True}
        self.cameras.append(cam)
        self.save()
        return cam

    def update(self, cam_id, name, ip="", port="554", user="", pwd="",
               path="", url=""):
        for c in self.cameras:
            if c["id"] == cam_id:
                c["name"] = name.strip()
                c["ip"] = ip.strip()
                c["port"] = (port or "554").strip()
                c["user"] = user.strip()
                c["pass"] = pwd or ""
                c["path"] = path.strip()
                c["url"] = url.strip()
                self.save()
                return True
        return False

    def delete(self, cam_id):
        n = len(self.cameras)
        self.cameras = [c for c in self.cameras if c["id"] != cam_id]
        if len(self.cameras) != n:
            self.save()
            return True
        return False

    def enabled_cameras(self):
        return [c for c in self.cameras
                if c.get("enabled") and camera_url(c)]
