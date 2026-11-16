"""
Kernel-R Profile Generator
Sinh fingerprint profile từ seed, corpus data, và proxy info.
"""
import hashlib
import json
import math
import os
import random
import struct
from pathlib import Path

CORPUS_DIR = Path(__file__).parent.parent.parent / "corpus"


class SeededRNG:
    """Domain-separated CSPRNG từ seed gốc."""

    def __init__(self, seed_hex: str, domain: str):
        h = hashlib.sha256(bytes.fromhex(seed_hex) + domain.encode()).digest()
        self._rng = random.Random(int.from_bytes(h[:8], "big"))

    def choice(self, seq):
        return self._rng.choice(seq)

    def weighted_choice(self, seq, weights):
        return self._rng.choices(seq, weights=weights, k=1)[0]

    def randint(self, a, b):
        return self._rng.randint(a, b)

    def shuffle(self, seq):
        self._rng.shuffle(seq)

    def uniform(self, a, b):
        return self._rng.uniform(a, b)


def load_corpus(name: str):
    """Load JSON corpus file."""
    path = CORPUS_DIR / name
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return None


def gen_screen(rng: SeededRNG) -> dict:
    REAL_SCREENS = [
        (1920, 1080, 1.0, 23),
        (2560, 1440, 1.0, 9),
        (1366, 768, 1.0, 8),
        (1536, 864, 1.25, 7),
        (1920, 1080, 1.25, 5),
        (3840, 2160, 1.5, 4),
        (1440, 900, 1.0, 3),
        (2560, 1440, 1.25, 2),
        (1680, 1050, 1.0, 2),
        (3840, 2160, 2.0, 2),
    ]
    screens = [(w, h, d) for w, h, d, _ in REAL_SCREENS]
    weights = [wt for _, _, _, wt in REAL_SCREENS]
    w, h, dpr = rng.weighted_choice(screens, weights)

    taskbar = rng.choice([40, 48])
    avail_h = h - taskbar
    color_depth = 24
    if dpr >= 1.5:
        color_depth = rng.choice([24, 30])

    scrollbar_w = rng.choice([0, 15, 17])
    inner_w = int(w / dpr) - scrollbar_w
    chrome_h = rng.choice([74, 102])
    inner_h = int(h / dpr) - int(taskbar / dpr) - chrome_h

    return {
        "w": w, "h": h,
        "avail_w": w, "avail_h": avail_h,
        "color_depth": color_depth, "pixel_depth": color_depth,
        "dpr": dpr,
        "inner_w": inner_w, "inner_h": inner_h,
        "outer_w": int(w / dpr), "outer_h": int(avail_h / dpr),
        "is_extended": False,
    }


def gen_navigator(rng: SeededRNG) -> dict:
    CPU_MEM_COMBOS = [
        (4, 4), (4, 8),
        (6, 8), (6, 16),
        (8, 8), (8, 16), (8, 32),
        (12, 16), (12, 32),
        (16, 16), (16, 32), (16, 64),
        (20, 32), (24, 32), (24, 64),
    ]
    cores, mem = rng.choice(CPU_MEM_COMBOS)
    device_memory = min(8, 2 ** int(math.log2(mem)))
    touch = rng.choice([0, 0, 0, 0, 10])

    return {
        "cores": cores,
        "device_memory": device_memory,
        "platform": "Win32",
        "max_touch_points": touch,
        "webdriver": False,
        "cookie_enabled": True,
        "pdf_viewer_enabled": True,
        "do_not_track": rng.choice([None, "1"]),
        "plugins_count": 5,
        "mime_types_count": 2,
    }


def gen_gpu(rng: SeededRNG) -> dict:
    gpu_db = load_corpus("gpu/gpu_db.json")
    if gpu_db and len(gpu_db) > 0:
        return rng.choice(gpu_db)
    return {"vendor": "PLACEHOLDER", "renderer": "PLACEHOLDER", "params": {}}


def gen_locale(rng: SeededRNG, proxy_country: str) -> dict:
    LOCALE_MAP = {
        "US": {
            "timezones": ["America/New_York", "America/Chicago", "America/Denver",
                          "America/Los_Angeles", "America/Phoenix"],
            "lang": "en-US",
            "languages": ["en-US", "en"],
        },
        "VN": {
            "timezones": ["Asia/Ho_Chi_Minh"],
            "lang": "vi-VN",
            "languages": ["vi-VN", "vi", "en-US", "en"],
        },
    }
    locale = LOCALE_MAP.get(proxy_country, LOCALE_MAP["US"])
    tz = rng.choice(locale["timezones"])
    return {
        "timezone": tz,
        "language": locale["lang"],
        "languages": locale["languages"],
    }


def gen_canvas(rng: SeededRNG, mode: str) -> dict:
    if mode == "native":
        return {"canvas_mode": "native"}
    gamma = round(rng.choice([1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 2.0, 2.1, 2.2]), 1)
    contrast = round(rng.uniform(0.0, 1.0), 1)
    return {"canvas_mode": "spoofed", "gamma": gamma, "contrast": contrast}


def gen_connection(rng: SeededRNG) -> dict:
    NET_PROFILES = [
        ("4g", 10.0, 50),
        ("4g", 5.65, 75),
        ("4g", 2.85, 100),
        ("4g", 1.45, 150),
        ("3g", 0.55, 300),
    ]
    eff, dl, rtt = rng.choice(NET_PROFILES)
    return {"effectiveType": eff, "downlink": dl, "rtt": rtt, "saveData": False}


def gen_toggles(preset: str = "all_spoofed") -> dict:
    all_keys = [
        "screen", "cpu_memory", "gpu_webgl", "canvas", "audio",
        "fonts", "locale_tz", "network", "voices", "permissions", "window_size",
    ]
    if preset == "all_native":
        return {k: False for k in all_keys}
    elif preset == "all_spoofed":
        return {k: True for k in all_keys}
    else:
        return {k: True for k in all_keys}


def generate_profile(seed_hex: str = None, proxy_country: str = "US",
                     canvas_mode: str = "spoofed", preset: str = "all_spoofed") -> dict:
    if seed_hex is None:
        seed_hex = os.urandom(32).hex()

    profile = {
        "schema": 1,
        "seed": seed_hex,
        "toggles": gen_toggles(preset),
        "screen": gen_screen(SeededRNG(seed_hex, "screen")),
        "navigator": gen_navigator(SeededRNG(seed_hex, "cpu")),
        "gpu": gen_gpu(SeededRNG(seed_hex, "gpu")),
        "locale": gen_locale(SeededRNG(seed_hex, "locale"), proxy_country),
        "canvas": gen_canvas(SeededRNG(seed_hex, "canvas"), canvas_mode),
        "connection": gen_connection(SeededRNG(seed_hex, "connection")),
    }
    return profile


if __name__ == "__main__":
    import sys
    seed = sys.argv[1] if len(sys.argv) > 1 else None
    country = sys.argv[2] if len(sys.argv) > 2 else "US"
    p = generate_profile(seed_hex=seed, proxy_country=country)
    print(json.dumps(p, indent=2, ensure_ascii=False))
