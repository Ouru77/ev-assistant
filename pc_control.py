"""
E.V. — PC control (Windows).
Safe, dependency-free desktop control: launch apps, media keys, volume,
open folders, and (with confirmation) run commands or power actions.
"""

import ctypes
import os
import subprocess

_LANG = "tr"


def set_language(lang: str):
    global _LANG
    _LANG = (lang or "tr").lower()


def _L(tr: str, en: str) -> str:
    return en if _LANG == "en" else tr

# --- Virtual key codes for media / volume (sent via keybd_event) ---
_VK = {
    "volume_up": 0xAF,
    "volume_down": 0xAE,
    "volume_mute": 0xAD,
    "play_pause": 0xB3,
    "next": 0xB0,
    "prev": 0xB1,
    "stop": 0xB2,
}
_KEYEVENTF_KEYUP = 0x0002


def _tap(vk: int, times: int = 1):
    for _ in range(times):
        ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
        ctypes.windll.user32.keybd_event(vk, 0, _KEYEVENTF_KEYUP, 0)


# --- Known apps: spoken name -> launch target -------------------------------
# Values are either an executable resolvable on PATH, a full path, or a URI.
APPS = {
    "not defteri": "notepad.exe",
    "notepad": "notepad.exe",
    "hesap makinesi": "calc.exe",
    "hesap makinası": "calc.exe",
    "calculator": "calc.exe",
    "dosya gezgini": "explorer.exe",
    "gezgin": "explorer.exe",
    "explorer": "explorer.exe",
    "denetim masası": "control.exe",
    "görev yöneticisi": "taskmgr.exe",
    "ayarlar": "ms-settings:",
    "paint": "mspaint.exe",
    "cmd": "cmd.exe",
    "komut istemi": "cmd.exe",
    "powershell": "powershell.exe",
    "chrome": "chrome.exe",
    "krom": "chrome.exe",
    "edge": "msedge.exe",
    "firefox": "firefox.exe",
    "spotify": "spotify.exe",
    "discord": "discord.exe",
    "steam": "steam.exe",
    "vs code": "code.exe",
    "vscode": "code.exe",
    "kod": "code.exe",
    "word": "winword.exe",
    "excel": "excel.exe",
    "kamera": "microsoft.windows.camera:",
    "takvim": "outlookcal:",
}

# Destructive actions require explicit confirmation before running.
_POWER = {
    "kapat": ["shutdown", "/s", "/t", "30"],
    "kapatma": ["shutdown", "/s", "/t", "30"],
    "shutdown": ["shutdown", "/s", "/t", "30"],
    "yeniden başlat": ["shutdown", "/r", "/t", "30"],
    "restart": ["shutdown", "/r", "/t", "30"],
    "iptal": ["shutdown", "/a"],
    "uyku": ["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"],
    "sleep": ["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"],
    "kilitle": ["rundll32.exe", "user32.dll,LockWorkStation"],
    "lock": ["rundll32.exe", "user32.dll,LockWorkStation"],
}


def open_app(name: str) -> str:
    """Launch an app by spoken name. Returns a short Turkish status line."""
    key = (name or "").strip().lower()
    target = APPS.get(key)
    try:
        if target is None:
            # Unknown → let Windows try to resolve it (PATH / registered app).
            os.startfile(key) if os.path.exists(key) else subprocess.Popen(
                ["cmd", "/c", "start", "", key], shell=False
            )
            return _L(f"{name} açılıyor.", f"Opening {name}.")
        if target.endswith(":") or "://" in target:  # URI (ms-settings: etc.)
            os.startfile(target)
        else:
            subprocess.Popen(["cmd", "/c", "start", "", target], shell=False)
        return _L(f"{name} açılıyor.", f"Opening {name}.")
    except Exception as e:
        return _L(f"{name} açılamadı: {e}", f"Couldn't open {name}: {e}")


def close_app(name: str) -> str:
    """Force-close a running app by image name (destructive — confirm first)."""
    key = (name or "").strip().lower()
    image = APPS.get(key, key)
    image = os.path.basename(image)
    if not image.lower().endswith(".exe"):
        image += ".exe"
    try:
        r = subprocess.run(
            ["taskkill", "/IM", image, "/F"],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode == 0:
            return _L(f"{name} kapatıldı.", f"{name} closed.")
        return _L(f"{name} zaten kapalı görünüyor.", f"{name} looks like it's already closed.")
    except Exception as e:
        return _L(f"{name} kapatılamadı: {e}", f"Couldn't close {name}: {e}")


def media(kind: str, amount: int = 4) -> str:
    """Media transport + volume via virtual media keys."""
    kind = (kind or "").strip().lower()
    labels = {
        "play_pause": _L("Oynat/duraklat.", "Play/pause."),
        "next": _L("Sonraki parça.", "Next track."),
        "prev": _L("Önceki parça.", "Previous track."),
        "stop": _L("Durduruldu.", "Stopped."),
        "volume_up": _L("Ses açıldı.", "Volume up."),
        "volume_down": _L("Ses kısıldı.", "Volume down."),
        "volume_mute": _L("Ses kapatıldı.", "Muted."),
    }
    if kind not in _VK:
        return _L("Bunu tam anlamadım.", "I didn't quite catch that.")
    _tap(_VK[kind], times=amount if "volume" in kind and kind != "volume_mute" else 1)
    return labels.get(kind, _L("Tamam.", "Done."))


def power(kind: str) -> str:
    """Power actions (destructive — confirm first)."""
    key = (kind or "").strip().lower()
    cmd = _POWER.get(key)
    if not cmd:
        return _L("Bu güç komutunu tanımadım.", "I don't recognize that power command.")
    try:
        subprocess.Popen(cmd, shell=False)
        if cmd[0] == "shutdown" and "/s" in cmd:
            return _L("30 saniye içinde kapanacak. Vazgeçersen 'iptal et' de.",
                      "Shutting down in 30 seconds. Say 'cancel' to stop it.")
        if cmd[0] == "shutdown" and "/r" in cmd:
            return _L("30 saniye içinde yeniden başlayacak. Vazgeçersen 'iptal et' de.",
                      "Restarting in 30 seconds. Say 'cancel' to stop it.")
        return _L("Tamam.", "Done.")
    except Exception as e:
        return _L(f"Olmadı: {e}", f"That didn't work: {e}")


def run_command(command: str) -> str:
    """Run an arbitrary shell command (destructive — confirm first)."""
    try:
        r = subprocess.run(
            command, shell=True, capture_output=True, text=True, timeout=30,
        )
        out = (r.stdout or "").strip() or (r.stderr or "").strip()
        return out[:1500] if out else _L("Komut çalıştı, çıktı yok.", "Command ran, no output.")
    except Exception as e:
        return _L(f"Komut çalışmadı: {e}", f"Command failed: {e}")
