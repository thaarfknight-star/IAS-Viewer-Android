# -*- coding: utf-8 -*-
"""لیست دوربین‌های نسخه‌ی اندروید (cameras.json).

هر دوربین: id, name, url (آدرس RTSP/HTTP), enabled
"""
import json
import os
import uuid


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
            c.setdefault("enabled", True)

    def save(self):
        d = os.path.dirname(self.path)
        if d:
            os.makedirs(d, exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"cameras": self.cameras}, f, ensure_ascii=False, indent=1)
        os.replace(tmp, self.path)

    def add(self, name, url):
        cam = {"id": uuid.uuid4().hex[:8], "name": name.strip(),
               "url": url.strip(), "enabled": True}
        self.cameras.append(cam)
        self.save()
        return cam

    def update(self, cam_id, name, url):
        for c in self.cameras:
            if c["id"] == cam_id:
                c["name"] = name.strip()
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
        return [c for c in self.cameras if c.get("enabled") and c.get("url")]
