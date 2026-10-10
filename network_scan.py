# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Taha Arefi (طه عارفی)
# This file is part of IAS Viewer.
# IAS Viewer is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# -*- coding: utf-8 -*-
"""اسکن شبکه برای یافتن دوربین‌ها/NVRها — اقتباس موبایلی از scanner.py ویندوز.

رنج IP (مثل «192.168.1»، «192.168.1.20-80»، «192.168.2.0/24») گرفته می‌شود و
پورت‌های رایج دوربین مداربسته بررسی می‌شوند:
  554=RTSP, 80=HTTP/ONVIF, 8000/37777/8899=مدیریت NVRهای رایج
"""
import concurrent.futures
import ipaddress
import socket
import threading

COMMON_CCTV_PORTS = [554, 80, 8000, 37777, 8899]
MAX_SCAN_HOSTS = 2048  # سقف موبایلی؛ محافظت در برابر رنج‌های غول‌پیکر

_FA_AR_DIGITS = str.maketrans(
    "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩",
    "01234567890123456789",
)


def _normalize(text):
    return (text or "").translate(_FA_AR_DIGITS).strip()


def _parse_single(part):
    part = part.strip()
    if "/" in part:
        try:
            net = ipaddress.ip_network(part, strict=False)
        except ValueError:
            raise ValueError("رنج نامعتبر است: «%s»" % part)
        if net.version != 4:
            raise ValueError("فقط IPv4 پشتیبانی می‌شود.")
        hosts = [str(h) for h in net.hosts()]
        if len(hosts) > MAX_SCAN_HOSTS:
            raise ValueError("رنج «%s» خیلی بزرگ است." % part)
        if not hosts:
            raise ValueError("رنج «%s» هیچ آدرسی ندارد." % part)
        return hosts
    if "-" in part:
        left, _, right = part.partition("-")
        left, right = left.strip(), right.strip()
        try:
            start_ip = ipaddress.ip_address(left)
        except ValueError:
            raise ValueError("ابتدای بازه نامعتبر است: «%s»" % left)
        if "." in right:
            end_ip = ipaddress.ip_address(right)
        elif right.isdigit():
            base = ".".join(left.split(".")[:3])
            end_ip = ipaddress.ip_address("%s.%s" % (base, right))
        else:
            raise ValueError("انتهای بازه نامعتبر است: «%s»" % right)
        lo, hi = int(start_ip), int(end_ip)
        if hi < lo:
            raise ValueError("انتهای بازه از ابتدایش کوچک‌تر است.")
        if hi - lo + 1 > MAX_SCAN_HOSTS:
            raise ValueError("بازه «%s» خیلی بزرگ است." % part)
        return [str(ipaddress.ip_address(i)) for i in range(lo, hi + 1)]
    try:
        single = ipaddress.ip_address(part)
        if single.version == 4:
            return [part]
    except ValueError:
        pass
    octets = part.split(".")
    if len(octets) == 3:
        try:
            ipaddress.ip_address(".".join(octets) + ".0")
        except ValueError:
            raise ValueError("رنج نامعتبر است: «%s»" % part)
        return ["%s.%d" % (part, i) for i in range(1, 255)]
    raise ValueError("رنج نامعتبر است: «%s»" % part)


def parse_ip_range(text):
    """متن رنج IP را به لیست آدرس تبدیل می‌کند؛ در غیر این صورت ValueError فارسی."""
    text = _normalize(text)
    if not text:
        raise ValueError("رنج IP خالی است.")
    ips, seen = [], set()
    for chunk in text.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        for ip in _parse_single(chunk):
            if ip not in seen:
                seen.add(ip)
                ips.append(ip)
    if not ips:
        raise ValueError("رنج IP معتبری وارد نشده است.")
    return ips


def check_ip_port(ip, port, timeout=0.5):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout)
            return sock.connect_ex((ip, port)) == 0
    except Exception:
        return False


def scan_single_host(ip):
    open_ports = [p for p in COMMON_CCTV_PORTS if check_ip_port(ip, p)]
    return {"ip": ip, "ports": open_ports} if open_ports else None


class NetworkScanner(threading.Thread):
    """اسکن شبکه در نخ جدا.

    on_found(device): با هر دستگاه یافت‌شده صدا زده می‌شود (نخ اسکن!).
    on_done(devices): در پایان اسکن (نخ اسکن!).
    """

    def __init__(self, range_text, on_found=None, on_done=None,
                 max_threads=32):
        super().__init__(daemon=True)
        self.range_text = range_text
        self.on_found = on_found
        self.on_done = on_done
        self.max_threads = max_threads
        self._stop = threading.Event()

    def stop(self):
        self._stop.set()

    def run(self):
        devices = []
        try:
            ip_list = parse_ip_range(self.range_text)
        except ValueError:
            ip_list = []
        try:
            with concurrent.futures.ThreadPoolExecutor(
                    max_workers=self.max_threads) as ex:
                futures = {ex.submit(scan_single_host, ip): ip
                           for ip in ip_list}
                for fut in concurrent.futures.as_completed(futures):
                    if self._stop.is_set():
                        ex.shutdown(wait=False, cancel_futures=True)
                        break
                    try:
                        res = fut.result()
                    except Exception:
                        res = None
                    if res:
                        devices.append(res)
                        if self.on_found:
                            try:
                                self.on_found(res)
                            except Exception:
                                pass
        except Exception:
            pass
        if self.on_done and not self._stop.is_set():
            try:
                self.on_done(devices)
            except Exception:
                pass
