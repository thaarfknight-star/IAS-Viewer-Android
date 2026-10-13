# -*- coding: utf-8 -*-
"""لیست NVRهای نسخه‌ی اندروید (nvrs.json).

مدل ویندوزی: NVRها جدا از دوربین‌ها ذخیره می‌شوند.
هر کانال NVR به‌عنوان یک دوربین مستقل در camera_store ذخیره می‌شود
با فیلدهای nvr_id (ارجاع به NVR والد) و channel (شماره کانال).
حذف NVR → حذف همه‌ی کانال‌هایش.
"""
import json
import os
import uuid


class NVRStore:
    def __init__(self, path):
        self.path = path
        self.nvrs = []
        self.load()

    def load(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
            nvrs = data.get("nvrs", []) or []
            self.nvrs = [n for n in nvrs if isinstance(n, dict)]
        except (OSError, ValueError):
            self.nvrs = []
        for n in self.nvrs:
            n.setdefault("id", uuid.uuid4().hex[:8])
            n.setdefault("name", "")
            n.setdefault("ip", "")
            n.setdefault("port", "554")
            n.setdefault("user", "")
            n.setdefault("pass", "")
            n.setdefault("brand", "")
            n.setdefault("max_channels", 16)

    def save(self):
        d = os.path.dirname(self.path)
        if d:
            os.makedirs(d, exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"nvrs": self.nvrs}, f, ensure_ascii=False, indent=1)
        os.replace(tmp, self.path)

    def add(self, name, ip="", port="554", user="", pwd="", brand="",
            max_channels=16):
        nvr = {"id": uuid.uuid4().hex[:8], "name": name.strip(),
               "ip": ip.strip(), "port": (port or "554").strip(),
               "user": user.strip(), "pass": pwd or "",
               "brand": (brand or "").strip(),
               "max_channels": int(max_channels or 16)}
        self.nvrs.append(nvr)
        self.save()
        return nvr

    def get(self, nvr_id):
        for n in self.nvrs:
            if n["id"] == nvr_id:
                return n
        return None

    def delete(self, nvr_id):
        n = len(self.nvrs)
        self.nvrs = [x for x in self.nvrs if x["id"] != nvr_id]
        if len(self.nvrs) != n:
            self.save()
            return True
        return False
