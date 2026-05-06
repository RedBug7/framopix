# =========================================================
# FRAMOPIX
# Studio Utility Tool
# Developed by Anson Antony E
# =========================================================

import os
import sys
import base64
import hashlib
import uuid
import platform
import webbrowser
import urllib.parse
import urllib.request
import json
from datetime import datetime, timedelta
try:
    import winreg
except ImportError:
    winreg = None
import shutil
import threading
import time
import tkinter as tk

from tkinter import filedialog
from tkinter import ttk
from tkinter import messagebox

from PIL import Image
from PIL import ImageEnhance
from PIL import ImageFilter

import cv2
import numpy as np

# =========================================================
# RESOURCE PATH (works both in dev and as PyInstaller exe)
# =========================================================
def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except AttributeError:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


def set_icon(window):
    try:
        icon_path = resource_path("icon.ico")
        window.iconbitmap(default=icon_path)
    except Exception:
        pass


def check_debug():
    """Detect debugger — report tampering to sheet then exit."""
    try:
        debugger_found = False
        if sys.gettrace() is not None:
            debugger_found = True
        import ctypes
        if hasattr(ctypes, "windll"):
            if ctypes.windll.kernel32.IsDebuggerPresent():
                debugger_found = True
        if debugger_found:
            hwid, key = get_stored_credentials()
            if hwid and key:
                report_tampering(hwid, key)
            sys.exit(0)
    except Exception:
        pass

# =========================================================
# ACTIVATION SYSTEM
# =========================================================
_SECRET_SALT = "FPX-AE-2025-7K9X-SALT"
_API_URL   = "https://script.google.com/macros/s/AKfycbw-lwiJUIA7IWXFD67seEiWuHM-g0zD3bBunxhcpKE9MXUTdpU0hA0m1PzMTomPGYRh/exec"
_API_TOKEN = "FPX-TOKEN-2025-XK9M-SECURE"  # ← Paste your deployed URL here

ACTIVATION_FILE = os.path.join(
    os.path.expanduser("~"),
    ".framopix_lic"
)
# =========================================================
# 5 HIDDEN CREDENTIAL STORE LOCATIONS (fake names)
# =========================================================
_APPDATA    = os.environ.get("APPDATA",    os.path.expanduser("~"))
_LOCALAPP   = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
_TEMP       = os.environ.get("TEMP", os.path.expanduser("~"))
_HOME       = os.path.expanduser("~")

HIDDEN_LOCATIONS = [
    # 1. Registry — disguised as Windows DWM session data (never cleared)
    ("registry", r"Software\Microsoft\Windows\DWM\Sessions", "SessionCache"),
    # 2. Registry — disguised as Windows Shell user data (never cleared)
    ("registry", r"Software\Microsoft\Windows\CurrentVersion\Shell Extensions", "CacheData"),
    # 3. AppData\Roaming disguised as font cache (never cleared by cleaners)
    ("file", os.path.join(_APPDATA, "Microsoft", "Windows", "Fonts", ".fntcache.dat"), None),
    # 4. LocalAppData disguised as DirectX shader cache (never cleared by basic cleanup)
    ("file", os.path.join(_LOCALAPP, "Microsoft", "DirectX", "ShaderCache", ".d3dcache.tmp"), None),
    # 5. AppData\Roaming disguised as Office telemetry (never cleared)
    ("file", os.path.join(_APPDATA, "Microsoft", "Office", "16.0", "Telemetry", ".telem.cache"), None),
    # 6. LocalAppData disguised as Windows Search index metadata (never cleared)
    ("file", os.path.join(_LOCALAPP, "Microsoft", "Windows", "Search", ".srchidx.dat"), None),
    # 7. Registry — disguised as input method data (never cleared)
    ("registry", r"Software\Microsoft\CTF\Assemblies", "ProfileCache"),
]


def get_hwid():
    try:
        mac = str(uuid.getnode())
        cpu = platform.processor() or platform.machine()
        vol = ""
        try:
            import subprocess
            r = subprocess.run(
                ["cmd", "/c", "vol", "C:"],
                capture_output=True, text=True, timeout=3
            )
            vol = r.stdout.strip()
        except Exception:
            pass
        raw = f"{mac}::{cpu}::{vol}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16].upper()
    except Exception:
        return "UNKNOWN-HWID"


def _generate_expected_key(hwid):
    raw = f"{hwid}::{_SECRET_SALT}"
    h = hashlib.sha256(raw.encode()).hexdigest().upper()
    return f"{h[0:4]}-{h[4:8]}-{h[8:12]}-{h[12:16]}"


def validate_key(hwid, key):
    return key.strip().upper() == _generate_expected_key(hwid)


def save_activation(hwid, key, last_check=None):
    if last_check is None:
        last_check = datetime.now().isoformat()
    payload = f"{hwid}||{key.strip().upper()}||{last_check}"
    encoded = base64.b64encode(payload.encode()).decode()
    checksum = hashlib.sha256(encoded.encode()).hexdigest()[:12]
    with open(ACTIVATION_FILE, "w") as f:
        f.write(f"{encoded}.{checksum}")
    _save_all_hidden(hwid, key.strip().upper())


def is_activated():
    """Check local license file integrity. Report + revoke if tampered."""
    if not os.path.exists(ACTIVATION_FILE):
        return False
    try:
        with open(ACTIVATION_FILE, "r") as f:
            raw = f.read().strip()

        # ── Checksum check ──
        if "." not in raw:
            _handle_tamper("License File Structure Tampered")
            return False

        encoded, stored_checksum = raw.rsplit(".", 1)
        expected_checksum = hashlib.sha256(encoded.encode()).hexdigest()[:12]

        if stored_checksum != expected_checksum:
            # Decode what we can to get HWID/key before revoking
            try:
                payload = base64.b64decode(encoded).decode()
                parts   = payload.split("||")
                if len(parts) >= 2:
                    _handle_tamper(
                        "License File Checksum Tampered",
                        hwid=parts[0],
                        key=parts[1]
                    )
            except Exception:
                _handle_tamper("License File Checksum Tampered")
            return False

        payload = base64.b64decode(encoded).decode()
        parts = payload.split("||")
        if len(parts) != 3:
            _handle_tamper("License File Format Tampered")
            return False

        stored_hwid, stored_key, _ = parts

        current_hwid = get_hwid()
        if stored_hwid != current_hwid:
            return False

        if not validate_key(current_hwid, stored_key):
            _handle_tamper(
                "License Key Tampered",
                hwid=stored_hwid,
                key=stored_key
            )
            return False

        return True

    except Exception:
        return False



def _encode_credentials(hwid, key):
    raw   = f"{hwid}||{key}"
    enc   = base64.b64encode(raw.encode()).decode()
    check = hashlib.sha256(enc.encode()).hexdigest()[:12]
    return f"{enc}.{check}"


def _decode_credentials(data):
    try:
        if "." not in data:
            return None, None
        enc, check = data.rsplit(".", 1)
        if hashlib.sha256(enc.encode()).hexdigest()[:12] != check:
            return None, None
        raw   = base64.b64decode(enc).decode()
        parts = raw.split("||")
        if len(parts) >= 2:
            return parts[0], parts[1]
        return None, None
    except Exception:
        return None, None


def _save_all_hidden(hwid, key):
    """Save credentials to all 5 hidden locations."""
    data = _encode_credentials(hwid, key)
    for loc in HIDDEN_LOCATIONS:
        try:
            if loc[0] == "registry" and winreg:
                reg_key = winreg.CreateKeyEx(
                    winreg.HKEY_CURRENT_USER,
                    loc[1],
                    0,
                    winreg.KEY_SET_VALUE
                )
                winreg.SetValueEx(reg_key, loc[2], 0, winreg.REG_SZ, data)
                winreg.CloseKey(reg_key)
            elif loc[0] == "file":
                os.makedirs(os.path.dirname(loc[1]), exist_ok=True)
                with open(loc[1], "w") as f:
                    f.write(data)
        except Exception:
            pass


def _delete_all_hidden():
    """Delete credentials from all 5 hidden locations."""
    for loc in HIDDEN_LOCATIONS:
        try:
            if loc[0] == "registry" and winreg:
                reg_key = winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    loc[1], 0,
                    winreg.KEY_SET_VALUE
                )
                winreg.DeleteValue(reg_key, loc[2])
                winreg.CloseKey(reg_key)
            elif loc[0] == "file":
                if os.path.exists(loc[1]):
                    os.remove(loc[1])
        except Exception:
            pass


def get_backup_credentials():
    """Try all 5 hidden locations, return first valid credentials found."""
    for loc in HIDDEN_LOCATIONS:
        try:
            data = None
            if loc[0] == "registry" and winreg:
                reg_key = winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    loc[1], 0,
                    winreg.KEY_READ
                )
                data, _ = winreg.QueryValueEx(reg_key, loc[2])
                winreg.CloseKey(reg_key)
            elif loc[0] == "file" and os.path.exists(loc[1]):
                with open(loc[1], "r") as f:
                    data = f.read().strip()
            if data:
                hwid, key = _decode_credentials(data)
                if hwid and key:
                    return hwid, key
        except Exception:
            pass
    return None, None

def _handle_tamper(reason, hwid=None, key=None):
    """Report tampering — revoke online, wipe all 5 hidden locations."""
    try:
        if not hwid or not key:
            hwid, key = get_backup_credentials()
        if hwid and key:
            validate_online(hwid, key, action="revoke", remark=reason)
        if os.path.exists(ACTIVATION_FILE):
            os.remove(ACTIVATION_FILE)
        _delete_all_hidden()
    except Exception:
        pass


def get_stored_credentials():
    """Return (hwid, key) from local license file."""
    try:
        with open(ACTIVATION_FILE, "r") as f:
            raw = f.read().strip()
        encoded, _ = raw.rsplit(".", 1)
        payload = base64.b64decode(encoded).decode()
        parts = payload.split("||")
        return parts[0], parts[1]
    except Exception:
        return None, None


def validate_online(hwid, key, action="check", remark=""):
    """
    Calls Google Apps Script to validate key online.
    action: "check" | "revoke"
    Returns: "OK", "INVALID", "REVOKED", "FORBIDDEN", or "OFFLINE"
    """
    try:
        token = urllib.parse.quote(_API_TOKEN)
        url = (
            f"{_API_URL}"
            f"?hwid={urllib.parse.quote(hwid)}"
            f"&key={urllib.parse.quote(key)}"
            f"&token={token}"
            f"&action={urllib.parse.quote(action)}"
            f"&remark={urllib.parse.quote(remark)}"
        )
        req = urllib.request.Request(url, headers={"User-Agent": "FramopixApp/1.0"})
        with urllib.request.urlopen(req, timeout=10) as response:
            result = json.loads(response.read().decode())
            return result.get("status", "INVALID")
    except Exception:
        return "OFFLINE"


def report_tampering(hwid, key):
    """Silently report tampering to Google Sheet then exit."""
    try:
        validate_online(hwid, key, action="revoke", remark="App Tampering Detected")
    except Exception:
        pass
    sys.exit(0)



def deactivate():
    answer = messagebox.askyesno(
        "Deactivate Framopix",
        "Are you sure you want to deactivate?\n\nYou can re-activate anytime using your existing activation key."
    )
    if answer:
        try:
            if os.path.exists(ACTIVATION_FILE):
                os.remove(ACTIVATION_FILE)
            _delete_all_hidden()
        except Exception:
            pass
        app.withdraw()
        show_activation_window()


# =========================================================
# APP WINDOW
# =========================================================
app = tk.Tk()
app.title("Framopix")
set_icon(app)
app.withdraw()
app.configure(bg="#1e272e")

width = 1000
height = 760

screen_width = app.winfo_screenwidth()
screen_height = app.winfo_screenheight()

x = (screen_width // 2) - (width // 2)
y = (screen_height // 2) - (height // 2)

app.geometry(f"{width}x{height}+{x}+{y}")
app.minsize(950, 760)


# =========================================================
# SPLASH SCREEN — shown every launch while checking online
# =========================================================
def show_splash_and_verify():
    splash = tk.Toplevel()
    splash.title("Framopix")
    splash.configure(bg="#1e272e")
    splash.resizable(False, False)
    set_icon(splash)

    sw_w, sw_h = 420, 280
    sx = (screen_width  // 2) - (sw_w // 2)
    sy = (screen_height // 2) - (sw_h // 2)
    splash.geometry(f"{sw_w}x{sw_h}+{sx}+{sy}")
    splash.grab_set()
    splash.protocol("WM_DELETE_WINDOW", lambda: app.destroy())

    # Logo
    tk.Label(
        splash, text="FRAMOPIX",
        font=("Segoe UI", 26, "bold"),
        fg="#9c88ff", bg="#1e272e"
    ).pack(pady=(36, 2))

    tk.Label(
        splash, text="Studio Utility Tool",
        font=("Segoe UI", 10),
        fg="#7f8fa6", bg="#1e272e"
    ).pack()

    # Divider
    tk.Frame(splash, bg="#2f3640", height=1).pack(fill="x", padx=40, pady=18)

    # Status label
    status_var = tk.StringVar(value="Checking activation...")
    status_lbl = tk.Label(
        splash,
        textvariable=status_var,
        font=("Segoe UI", 10),
        fg="#dcdde1",
        bg="#1e272e"
    )
    status_lbl.pack()

    # Animated dots
    dot_var = tk.StringVar(value="")
    dot_lbl = tk.Label(
        splash,
        textvariable=dot_var,
        font=("Segoe UI", 14),
        fg="#9c88ff",
        bg="#1e272e"
    )
    dot_lbl.pack(pady=4)

    dots_cycle = ["●  ○  ○", "○  ●  ○", "○  ○  ●", "○  ●  ○"]
    dot_index  = [0]

    def animate_dots():
        dot_var.set(dots_cycle[dot_index[0] % len(dots_cycle)])
        dot_index[0] += 1
        splash.after(320, animate_dots)

    animate_dots()

    # Run online check in background thread
    result_holder = [None]

    def do_check():
        hwid, key = get_stored_credentials()
        if hwid and key:
            result_holder[0] = validate_online(hwid, key)
        else:
            result_holder[0] = "NO_LICENSE"

    def finish_check():
        result = result_holder[0]

        if result == "OK":
            hwid, key = get_stored_credentials()
            save_activation(hwid, key)
            splash.destroy()
            app.deiconify()

        elif result == "REVOKED":
            dot_var.set("")
            status_var.set("✗  License has been revoked.")
            status_lbl.config(fg="#e84118")
            try:
                if os.path.exists(ACTIVATION_FILE):
                    os.remove(ACTIVATION_FILE)
            except Exception:
                pass
            splash.after(2500, lambda: [splash.destroy(), show_activation_window()])

        elif result == "NO_LICENSE":
            splash.destroy()
            show_activation_window()

        elif result == "OFFLINE":
            dot_var.set("")
            status_var.set("⚠  No internet connection.")
            status_lbl.config(fg="#e1b12c")
            sub_var = tk.StringVar(value="Please connect to internet and relaunch.")
            tk.Label(
                splash,
                textvariable=sub_var,
                font=("Segoe UI", 9),
                fg="#7f8fa6",
                bg="#1e272e"
            ).pack(pady=(4, 0))
            tk.Button(
                splash,
                text="Close",
                command=app.destroy,
                bg="#c23616",
                fg="white",
                font=("Segoe UI", 10, "bold"),
                relief="flat",
                padx=20, pady=6,
                cursor="hand2"
            ).pack(pady=14)

        else:
            dot_var.set("")
            status_var.set("✗  Validation failed. Try again.")
            status_lbl.config(fg="#e84118")
            splash.after(2500, lambda: app.destroy())

    def poll_result():
        if result_holder[0] is None:
            splash.after(200, poll_result)
        else:
            finish_check()

    threading.Thread(target=do_check, daemon=True).start()
    splash.after(200, poll_result)
    splash.wait_window()


# =========================================================
# ACTIVATION WINDOW
# =========================================================
def show_activation_window():

    win = tk.Toplevel()
    win.title("Framopix — Activation")
    win.configure(bg="#1e272e")
    win.resizable(False, False)
    set_icon(win)

    aw = 520
    ah = 600

    ax = (screen_width // 2) - (aw // 2)
    ay = (screen_height // 2) - (ah // 2)

    win.geometry(f"{aw}x{ah}+{ax}+{ay}")
    win.grab_set()

    def on_close():
        app.destroy()

    win.protocol("WM_DELETE_WINDOW", on_close)

    # Header
    tk.Label(
        win,
        text="FRAMOPIX",
        font=("Segoe UI", 28, "bold"),
        fg="#9c88ff",
        bg="#1e272e"
    ).pack(pady=(30, 0))

    tk.Label(
        win,
        text="Studio Utility Tool  •  v1.1",
        font=("Segoe UI", 10),
        fg="#7f8fa6",
        bg="#1e272e"
    ).pack()

    tk.Label(
        win,
        text="One-time activation required",
        font=("Segoe UI", 10),
        fg="#dcdde1",
        bg="#1e272e"
    ).pack(pady=(18, 4))

    # HWID Card
    hwid_card = tk.Frame(win, bg="#2f3640", pady=12, padx=16)
    hwid_card.pack(fill="x", padx=40, pady=6)

    tk.Label(
        hwid_card,
        text="Your Machine ID (HWID)",
        font=("Segoe UI", 9, "bold"),
        fg="#7f8fa6",
        bg="#2f3640"
    ).pack(anchor="w")

    hwid_row = tk.Frame(hwid_card, bg="#2f3640")
    hwid_row.pack(fill="x", pady=(4, 0))

    current_hwid = get_hwid()

    hwid_display = tk.Label(
        hwid_row,
        text=current_hwid,
        font=("Courier New", 14, "bold"),
        fg="#00d2d3",
        bg="#2f3640",
        cursor="hand2"
    )
    hwid_display.pack(side="left")

    def copy_hwid():
        win.clipboard_clear()
        win.clipboard_append(current_hwid)
        copy_btn.config(text="Copied ✓", fg="#44bd32")
        win.after(2000, lambda: copy_btn.config(
            text="Copy", fg="white"
        ))

    copy_btn = tk.Button(
        hwid_row,
        text="Copy",
        command=copy_hwid,
        bg="#40739e",
        fg="white",
        font=("Segoe UI", 9, "bold"),
        relief="flat",
        padx=10,
        pady=3,
        cursor="hand2"
    )
    copy_btn.pack(side="right")

    tk.Label(
        hwid_card,
        text="Send this ID to Anson Antony E to receive your key",
        font=("Segoe UI", 9),
        fg="#7f8fa6",
        bg="#2f3640"
    ).pack(anchor="w", pady=(6, 0))

    # Key Entry
    key_card = tk.Frame(win, bg="#2f3640", pady=12, padx=16)
    key_card.pack(fill="x", padx=40, pady=6)

    tk.Label(
        key_card,
        text="Activation Key",
        font=("Segoe UI", 9, "bold"),
        fg="#7f8fa6",
        bg="#2f3640"
    ).pack(anchor="w")

    key_var = tk.StringVar()

    key_entry = tk.Entry(
        key_card,
        textvariable=key_var,
        font=("Courier New", 13, "bold"),
        bg="#1e272e",
        fg="#f5f6fa",
        insertbackground="white",
        relief="flat",
        justify="center"
    )
    key_entry.pack(fill="x", pady=(6, 0), ipady=6)
    key_entry.focus()

    # Status label
    status_var = tk.StringVar(value="")
    status_lbl = tk.Label(
        win,
        textvariable=status_var,
        font=("Segoe UI", 9),
        fg="#e84118",
        bg="#1e272e"
    )
    status_lbl.pack(pady=(6, 0))

    def attempt_activation():
        entered_key = key_var.get().strip().upper()
        if not entered_key:
            status_var.set("⚠  Please enter your activation key")
            return

        # First check key format locally
        if not validate_key(current_hwid, entered_key):
            status_var.set("✗  Invalid key — please check and try again")
            key_entry.config(fg="#e84118")
            win.after(300, lambda: key_entry.config(fg="#f5f6fa"))
            return

        # Key format valid — now verify online
        status_var.set("⏳  Verifying online...")
        activate_btn.config(state="disabled")
        win.update()

        online_result = validate_online(current_hwid, entered_key)

        if online_result == "OK":
            save_activation(current_hwid, entered_key)
            status_var.set("")
            win.destroy()
            app.deiconify()

        elif online_result == "REVOKED":
            status_var.set("✗  This license has been revoked. Contact support.")
            activate_btn.config(state="normal")

        elif online_result == "OFFLINE":
            status_var.set("⚠  No internet. Please connect and try again.")
            activate_btn.config(state="normal")

        else:
            status_var.set("✗  Invalid key — please check and try again")
            key_entry.config(fg="#e84118")
            win.after(300, lambda: key_entry.config(fg="#f5f6fa"))
            activate_btn.config(state="normal")

    key_entry.bind("<Return>", lambda e: attempt_activation())

    activate_btn = tk.Button(
        win,
        text="ACTIVATE",
        command=attempt_activation,
        bg="#9c88ff",
        fg="white",
        font=("Segoe UI", 11, "bold"),
        relief="flat",
        padx=30,
        pady=10,
        cursor="hand2"
    )
    activate_btn.pack(pady=14)

    # Email section
    email_frame = tk.Frame(win, bg="#2f3640", pady=12, padx=16)
    email_frame.pack(fill="x", padx=40, pady=(0, 6))

    tk.Label(
        email_frame,
        text="Need a key? Send your HWID to:",
        font=("Segoe UI", 9),
        fg="#7f8fa6",
        bg="#2f3640"
    ).pack(anchor="w")

    tk.Label(
        email_frame,
        text="activate.framopix@gmail.com",
        font=("Segoe UI", 10, "bold"),
        fg="#9c88ff",
        bg="#2f3640"
    ).pack(anchor="w", pady=(2, 8))

    def open_email():
        subject = urllib.parse.quote(
            f"Framopix Activation Key Request — HWID: {current_hwid}"
        )
        body = urllib.parse.quote(
            f"Hi Anson,\n\n"
            f"I would like to purchase and activate Framopix.\n\n"
            f"My Machine ID (HWID): {current_hwid}\n\n"
            f"Please send me the activation key and payment details.\n\n"
            f"Thank you."
        )
        gmail_url = (
            f"https://mail.google.com/mail/?view=cm"
            f"&to=activate.framopix@gmail.com"
            f"&su={subject}"
            f"&body={body}"
        )
        webbrowser.open(gmail_url)

    tk.Button(
        email_frame,
        text="✉  Open Email to Request Key",
        command=open_email,
        bg="#40739e",
        fg="white",
        font=("Segoe UI", 10, "bold"),
        relief="flat",
        padx=14,
        pady=8,
        cursor="hand2"
    ).pack(fill="x")

    win.wait_window()


# =========================================================
# VARIABLES
# =========================================================
main_folder = ""
shortlisted_folder = ""
output_folder = ""

compress_input_folder = ""
compress_output_folder = ""

enhance_input_folder = ""
enhance_output_folder = ""

copy_unmatched_var = tk.BooleanVar(value=True)

# =========================================================
# PROCESS FLAGS
# =========================================================
cancel_match = False
pause_match = False

cancel_compress = False
pause_compress = False

cancel_enhance = False
pause_enhance = False

match_processed_files = []
compress_processed_files = []
enhance_processed_files = []

# =========================================================
# MAIN CONTAINER
# =========================================================
main_container = tk.Frame(app, bg="#1e272e")
main_container.pack(fill="both", expand=True)

# =========================================================
# NOTEBOOK
# =========================================================
notebook = ttk.Notebook(main_container)
notebook.pack(fill="both", expand=True)

# =========================================================
# STATUS BAR
# =========================================================
status_container = tk.Frame(
    app,
    bg="#353b48",
    height=32
)

status_container.pack(
    side="bottom",
    fill="x"
)

status_container.pack_propagate(False)

status_label = tk.Label(
    status_container,
    text="Ready | Framopix v1.1 | Developed by Anson Antony E",
    anchor="w",
    fg="white",
    bg="#353b48",
    font=("Segoe UI", 9),
    padx=10
)

status_label.pack(
    side="left",
    fill="both",
    expand=True
)

deactivate_btn = tk.Button(
    status_container,
    text="⏏  Deactivate",
    command=deactivate,
    bg="#353b48",
    fg="#7f8fa6",
    font=("Segoe UI", 8),
    relief="flat",
    padx=10,
    pady=0,
    cursor="hand2",
    activebackground="#c23616",
    activeforeground="white",
    bd=0
)

deactivate_btn.pack(
    side="right",
    padx=6
)

# =========================================================
# FUNCTIONS
# =========================================================
def update_status(message):

    status_label.config(
        text=f"{message} || Framopix v1.1 | Developed by Anson Antony E"
    )


def log(message, widget):

    widget.insert(tk.END, message + "\n")
    widget.see(tk.END)

    app.update_idletasks()


def reset_progress(bar, label):

    bar["value"] = 0
    label.config(text="0%")


def select_folder(label_widget, folder_type):

    global main_folder
    global shortlisted_folder
    global output_folder

    global compress_input_folder
    global compress_output_folder

    global enhance_input_folder
    global enhance_output_folder

    folder = filedialog.askdirectory()

    if folder:

        label_widget.config(text=folder)

        if folder_type == "main":
            main_folder = folder

        elif folder_type == "shortlisted":
            shortlisted_folder = folder

        elif folder_type == "output":
            output_folder = folder

        elif folder_type == "compress_input":
            compress_input_folder = folder

        elif folder_type == "compress_output":
            compress_output_folder = folder

        elif folder_type == "enhance_input":
            enhance_input_folder = folder

        elif folder_type == "enhance_output":
            enhance_output_folder = folder


def folder_row(parent, title, var_type):

    frame = tk.Frame(parent, bg="#2f3640")

    frame.pack(fill="x", pady=10, padx=15)

    tk.Label(
        frame,
        text=title,
        width=24,
        anchor="w",
        fg="white",
        bg="#2f3640",
        font=("Segoe UI", 11)
    ).pack(side="left")

    label = tk.Label(
        frame,
        text="No folder selected",
        fg="#dcdde1",
        bg="#2f3640",
        anchor="w",
        font=("Segoe UI", 10)
    )

    label.pack(side="right", fill="x", expand=True)

    btn = tk.Button(
        frame,
        text="Browse",
        command=lambda: select_folder(label, var_type),
        bg="#40739e",
        fg="white",
        relief="flat",
        font=("Segoe UI", 10, "bold"),
        padx=12,
        pady=5,
        cursor="hand2"
    )

    btn.pack(side="right", padx=10)

    return label

# =========================================================
# IMAGE HELPERS
# =========================================================
def auto_white_balance(img, strength=0.05):

    result = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)

    avg_a = np.average(result[:, :, 1])
    avg_b = np.average(result[:, :, 2])

    result[:, :, 1] = result[:, :, 1] - (
        (avg_a - 128) *
        (result[:, :, 0] / 255.0) *
        strength
    )

    result[:, :, 2] = result[:, :, 2] - (
        (avg_b - 128) *
        (result[:, :, 0] / 255.0) *
        strength
    )

    result = cv2.cvtColor(result, cv2.COLOR_LAB2BGR)

    return result


def apply_clahe(img, clip_limit=1.4):

    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)

    l, a, b = cv2.split(lab)

    clahe = cv2.createCLAHE(
        clipLimit=0.6,
        tileGridSize=(16, 16)
    )

    cl = clahe.apply(l)

    cl = cv2.addWeighted(
        l,
        0.75,
        cl,
        0.25,
        0
    )

    merged = cv2.merge((cl, a, b))

    final = cv2.cvtColor(
        merged,
        cv2.COLOR_LAB2BGR
    )

    return final

# =========================================================
# MATCH THREAD
# =========================================================
def start_match_thread():

    global cancel_match
    global pause_match

    cancel_match = False
    pause_match = False

    thread = threading.Thread(
        target=run_match_copy,
        daemon=True
    )

    thread.start()

# =========================================================
# COMPRESS THREAD
# =========================================================
def start_compression_thread():

    global cancel_compress
    global pause_compress

    cancel_compress = False
    pause_compress = False

    thread = threading.Thread(
        target=compress_images,
        daemon=True
    )

    thread.start()

# =========================================================
# ENHANCE THREAD
# =========================================================
def start_enhance_thread():

    global cancel_enhance
    global pause_enhance

    cancel_enhance = False
    pause_enhance = False

    thread = threading.Thread(
        target=auto_image_enhance,
        daemon=True
    )

    thread.start()

# =========================================================
# MATCH & COPY
# =========================================================
def run_match_copy():

    global cancel_match
    global pause_match
    global match_processed_files

    match_processed_files = []

    try:

        start_btn.config(state="disabled")

        if not main_folder or not shortlisted_folder or not output_folder:

            update_status("⚠ Please select all folders")

            start_btn.config(state="normal")

            return

        log_box.delete("1.0", tk.END)

        main_map = {}
        shortlisted_map = {}

        for f in os.listdir(main_folder):

            full_path = os.path.join(main_folder, f)

            if os.path.isfile(full_path):

                base_name = os.path.splitext(f)[0]
                main_map[base_name] = f

        for f in os.listdir(shortlisted_folder):

            full_path = os.path.join(shortlisted_folder, f)

            if os.path.isfile(full_path):

                base_name = os.path.splitext(f)[0]
                shortlisted_map[base_name] = f

        base_list = list(shortlisted_map.keys())

        total = len(base_list)

        progress["maximum"] = total
        progress["value"] = 0

        copied_main = []
        missing = []

        for i, name in enumerate(base_list, start=1):

            while pause_match:
                time.sleep(0.1)

            if cancel_match:

                log(
                    "\n⚠ PROCESS CANCELLED",
                    log_box
                )

                update_status("Process Cancelled")

                break

            if name in main_map:

                src = os.path.join(main_folder, main_map[name])
                dst = os.path.join(output_folder, main_map[name])

                shutil.copy2(src, dst)

                match_processed_files.append(dst)

                copied_main.append(name)

                log(
                    f"✔ MATCHED → {main_map[name]}",
                    log_box
                )

            else:

                missing.append(name)

                if copy_unmatched_var.get():

                    src = os.path.join(
                        shortlisted_folder,
                        shortlisted_map[name]
                    )

                    dst = os.path.join(
                        output_folder,
                        shortlisted_map[name]
                    )

                    shutil.copy2(src, dst)

                    match_processed_files.append(dst)

                    log(
                        f"⚠ UNMATCHED COPIED → {shortlisted_map[name]}",
                        log_box
                    )

            progress["value"] = i

            percent = int((i / total) * 100)

            progress_label.config(
                text=f"{percent}%"
            )

            app.update_idletasks()

        if not cancel_match:

            log("\n========== FINAL REPORT ==========", log_box)

            log(f"Total Files      : {total}", log_box)
            log(f"Matched Files    : {len(copied_main)}", log_box)
            log(f"Unmatched Files  : {len(missing)}", log_box)

            update_status(
                f"Completed | Matched: {len(copied_main)}"
            )

        time.sleep(1)

        reset_progress(progress, progress_label)

        start_btn.config(state="normal")

    except Exception as e:

        update_status(f"Error: {str(e)}")

        start_btn.config(state="normal")

# =========================================================
# COMPRESS IMAGES
# =========================================================
def compress_images():

    global cancel_compress
    global pause_compress
    global compress_processed_files

    compress_processed_files = []

    try:

        compress_btn.config(state="disabled")

        if not compress_input_folder or not compress_output_folder:

            update_status("⚠ Please select folders")

            compress_btn.config(state="normal")

            return

        compress_log_box.delete("1.0", tk.END)

        image_extensions = (
            ".jpg",
            ".jpeg",
            ".png",
            ".webp"
        )

        files = [
            f for f in os.listdir(compress_input_folder)
            if f.lower().endswith(image_extensions)
        ]

        total = len(files)

        compress_progress["maximum"] = total
        compress_progress["value"] = 0

        selected_quality = quality_var.get()

        if selected_quality == "High Quality (90%)":
            quality_value = 90

        elif selected_quality == "Balanced (70%)":
            quality_value = 70

        elif selected_quality == "Aggressive Compression (50%)":
            quality_value = 50

        else:
            quality_value = 30

        for i, file in enumerate(files, start=1):

            while pause_compress:
                time.sleep(0.1)

            if cancel_compress:

                log(
                    "\n⚠ PROCESS CANCELLED",
                    compress_log_box
                )

                update_status("Compression Cancelled")

                break

            src = os.path.join(compress_input_folder, file)
            dst = os.path.join(compress_output_folder, file)

            try:

                img = Image.open(src)

                max_size = (2500, 2500)

                img.thumbnail(max_size)

                if img.mode in ("RGBA", "P"):
                    img = img.convert("RGB")

                img.save(
                    dst,
                    optimize=True,
                    quality=quality_value
                )

                compress_processed_files.append(dst)

                log(
                    f"✔ COMPRESSED ({quality_value}%) → {file}",
                    compress_log_box
                )

            except Exception as img_error:

                log(
                    f"⚠ FAILED → {file} | {str(img_error)}",
                    compress_log_box
                )

            compress_progress["value"] = i

            percent = int((i / total) * 100)

            compress_progress_label.config(
                text=f"{percent}%"
            )

            app.update_idletasks()

        time.sleep(1)

        reset_progress(
            compress_progress,
            compress_progress_label
        )

        compress_btn.config(state="normal")

    except Exception as e:

        update_status(f"Error: {str(e)}")

        compress_btn.config(state="normal")

# =========================================================
# AUTO ENHANCE
# =========================================================
def auto_image_enhance():

    global cancel_enhance
    global pause_enhance
    global enhance_processed_files

    enhance_processed_files = []

    try:

        enhance_btn.config(state="disabled")

        if not enhance_input_folder or not enhance_output_folder:

            update_status("⚠ Please select folders")

            enhance_btn.config(state="normal")

            return

        enhance_log_box.delete("1.0", tk.END)

        image_extensions = (
            ".jpg",
            ".jpeg",
            ".png",
            ".webp"
        )

        files = [
            f for f in os.listdir(enhance_input_folder)
            if f.lower().endswith(image_extensions)
        ]

        total = len(files)

        enhance_progress["maximum"] = total
        enhance_progress["value"] = 0

        preset = preset_var.get()

        for i, file in enumerate(files, start=1):

            while pause_enhance:
                time.sleep(0.1)

            if cancel_enhance:

                log(
                    "\n⚠ PROCESS CANCELLED",
                    enhance_log_box
                )

                update_status("Auto Enhance Cancelled")

                break

            src = os.path.join(enhance_input_folder, file)
            dst = os.path.join(enhance_output_folder, file)

            try:

                img_cv = cv2.imread(src)

                if img_cv is None:
                    continue

                if preset == "Basic":

                    wb_strength = 0.02
                    clahe_strength = 1.2

                    contrast_strength = 1.00
                    saturation_strength = 1.00
                    sharpness_strength = 1.00

                elif preset == "Natural":

                    wb_strength = 0.05
                    clahe_strength = 1.4

                    contrast_strength = 1.00
                    saturation_strength = 1.00
                    sharpness_strength = 1.01

                else:

                    wb_strength = 0.08
                    clahe_strength = 1.8

                    contrast_strength = 1.02
                    saturation_strength = 1.02
                    sharpness_strength = 1.04

                img_cv = auto_white_balance(
                    img_cv,
                    strength=wb_strength
                )

                img_cv = cv2.convertScaleAbs(
                    img_cv,
                    alpha=0.97,
                    beta=-3
                )

                gray_check = cv2.cvtColor(
                    img_cv,
                    cv2.COLOR_BGR2GRAY
                )

                brightness = np.mean(gray_check)

                if brightness < 95:

                    img_cv = apply_clahe(
                        img_cv,
                        clip_limit=clahe_strength
                    )

                face_soft = cv2.bilateralFilter(
                    img_cv,
                    9,
                    28,
                    28
                )
                img_cv = cv2.addWeighted(
                    img_cv,
                    0.92,
                    face_soft,
                    0.08,
                    0
                )

                img_rgb = cv2.cvtColor(
                    img_cv,
                    cv2.COLOR_BGR2RGB
                )
                img = Image.fromarray(img_rgb)

                img = ImageEnhance.Contrast(img).enhance(
                    contrast_strength
                )

                img = ImageEnhance.Color(img).enhance(
                    saturation_strength
                )

                img = ImageEnhance.Sharpness(img).enhance(
                    sharpness_strength
                )

                if preset == "Aggressive":

                    img = img.filter(ImageFilter.SHARPEN)

                img.save(
                    dst,
                    quality=95,
                    optimize=True
                )

                enhance_processed_files.append(dst)

                log(
                    f"✔ {preset.upper()} ENHANCED → {file}",
                    enhance_log_box
                )

            except Exception as e:

                log(
                    f"⚠ FAILED → {file} | {str(e)}",
                    enhance_log_box
                )

            enhance_progress["value"] = i

            percent = int((i / total) * 100)

            enhance_progress_label.config(
                text=f"{percent}%"
            )

            app.update_idletasks()

        time.sleep(1)

        reset_progress(
            enhance_progress,
            enhance_progress_label
        )

        enhance_btn.config(state="normal")

    except Exception as e:

        update_status(f"Error: {str(e)}")

        enhance_btn.config(state="normal")

# =========================================================
# CANCEL FUNCTIONS
# =========================================================
def cancel_match_process():

    global pause_match
    global cancel_match

    pause_match = True

    answer = messagebox.askyesno(
        "Cancel Process",
        "Do you want to delete already processed output files?"
    )

    if answer:

        cancel_match = True

        pause_match = False

        for file in match_processed_files:

            try:
                if os.path.exists(file):
                    os.remove(file)
            except:
                pass

        reset_progress(progress, progress_label)

    else:

        pause_match = False


def cancel_compress_process():

    global pause_compress
    global cancel_compress

    pause_compress = True

    answer = messagebox.askyesno(
        "Cancel Compression",
        "Do you want to delete already processed output files?"
    )

    if answer:

        cancel_compress = True

        pause_compress = False

        for file in compress_processed_files:

            try:
                if os.path.exists(file):
                    os.remove(file)
            except:
                pass

        reset_progress(
            compress_progress,
            compress_progress_label
        )

    else:

        pause_compress = False


def cancel_enhance_process():

    global pause_enhance
    global cancel_enhance

    pause_enhance = True

    answer = messagebox.askyesno(
        "Cancel Auto Enhance",
        "Do you want to delete already processed output files?"
    )

    if answer:

        cancel_enhance = True

        pause_enhance = False

        for file in enhance_processed_files:

            try:
                if os.path.exists(file):
                    os.remove(file)
            except:
                pass

        reset_progress(
            enhance_progress,
            enhance_progress_label
        )

    else:

        pause_enhance = False

# =========================================================
# MATCH TAB
# =========================================================
match_tab = tk.Frame(notebook, bg="#1e272e")
notebook.add(match_tab, text="Match & Copy")

header = tk.Label(
    match_tab,
    text="MATCH & COPY",
    font=("Segoe UI", 22, "bold"),
    fg="white",
    bg="#1e272e"
)

header.pack(pady=10)

card = tk.Frame(match_tab, bg="#2f3640")
card.pack(fill="x", padx=20, pady=10)

folder_row(card, "Main Data Folder:", "main")
folder_row(card, "Shortlisted Folder:", "shortlisted")
folder_row(card, "Final Output Folder:", "output")

options_frame = tk.Frame(match_tab, bg="#1e272e")
options_frame.pack(pady=5)

copy_toggle = tk.Checkbutton(
    options_frame,
    text="Copy unmatched shortlisted files",
    variable=copy_unmatched_var,
    bg="#1e272e",
    fg="white",
    selectcolor="#2f3640",
    font=("Segoe UI", 10)
)

copy_toggle.pack()

button_frame = tk.Frame(match_tab, bg="#1e272e")
button_frame.pack(pady=10)

start_btn = tk.Button(
    button_frame,
    text="START MATCH & COPY",
    command=start_match_thread,
    bg="#44bd32",
    fg="white",
    font=("Segoe UI", 11, "bold"),
    relief="flat",
    padx=22,
    pady=10
)

start_btn.pack(side="left", padx=10)

cancel_btn = tk.Button(
    button_frame,
    text="CANCEL",
    command=cancel_match_process,
    bg="#c23616",
    fg="white",
    font=("Segoe UI", 11, "bold"),
    relief="flat",
    padx=22,
    pady=10
)

cancel_btn.pack(side="left", padx=10)

progress = ttk.Progressbar(match_tab, length=620)
progress.pack(pady=8)

progress_label = tk.Label(
    match_tab,
    text="0%",
    fg="white",
    bg="#1e272e"
)

progress_label.pack()

log_box = tk.Text(
    match_tab,
    height=15,
    bg="#2f3640",
    fg="white",
    insertbackground="white"
)

log_box.pack(fill="both", expand=True, padx=20, pady=10)

# =========================================================
# COMPRESS TAB
# =========================================================
compress_tab = tk.Frame(notebook, bg="#1e272e")
notebook.add(compress_tab, text="Compress Images")

compress_header = tk.Label(
    compress_tab,
    text="COMPRESS IMAGES",
    font=("Segoe UI", 22, "bold"),
    fg="white",
    bg="#1e272e"
)

compress_header.pack(pady=10)

compress_card = tk.Frame(compress_tab, bg="#2f3640")
compress_card.pack(fill="x", padx=20, pady=10)

folder_row(compress_card, "Main Data Folder:", "compress_input")
folder_row(compress_card, "Compressed Data Folder:", "compress_output")

quality_frame = tk.Frame(compress_tab, bg="#1e272e")
quality_frame.pack(pady=5)

quality_label = tk.Label(
    quality_frame,
    text="Compression Mode:",
    fg="white",
    bg="#1e272e",
    font=("Segoe UI", 11, "bold")
)

quality_label.pack(side="left", padx=10)

quality_var = tk.StringVar()

quality_dropdown = ttk.Combobox(
    quality_frame,
    textvariable=quality_var,
    state="readonly",
    width=35
)

quality_dropdown["values"] = (
    "High Quality (90%)",
    "Balanced (70%)",
    "Aggressive Compression (50%)",
    "Heavy Compression (30%)"
)

quality_dropdown.current(1)
quality_dropdown.pack(side="left")

compress_button_frame = tk.Frame(
    compress_tab,
    bg="#1e272e"
)

compress_button_frame.pack(pady=10)

compress_btn = tk.Button(
    compress_button_frame,
    text="START COMPRESSION",
    command=start_compression_thread,
    bg="#e1b12c",
    fg="black",
    font=("Segoe UI", 11, "bold"),
    relief="flat",
    padx=22,
    pady=10
)

compress_btn.pack(side="left", padx=10)

compress_cancel_btn = tk.Button(
    compress_button_frame,
    text="CANCEL",
    command=cancel_compress_process,
    bg="#c23616",
    fg="white",
    font=("Segoe UI", 11, "bold"),
    relief="flat",
    padx=22,
    pady=10
)

compress_cancel_btn.pack(side="left", padx=10)

compress_progress = ttk.Progressbar(
    compress_tab,
    length=620
)

compress_progress.pack(pady=8)

compress_progress_label = tk.Label(
    compress_tab,
    text="0%",
    fg="white",
    bg="#1e272e"
)

compress_progress_label.pack()

compress_log_box = tk.Text(
    compress_tab,
    height=15,
    bg="#2f3640",
    fg="white",
    insertbackground="white"
)

compress_log_box.pack(
    fill="both",
    expand=True,
    padx=20,
    pady=10
)

# =========================================================
# AUTO ENHANCE TAB
# =========================================================
enhance_tab = tk.Frame(notebook, bg="#1e272e")
notebook.add(enhance_tab, text="Auto Image Enhance")

enhance_header = tk.Label(
    enhance_tab,
    text="AUTO IMAGE ENHANCE",
    font=("Segoe UI", 22, "bold"),
    fg="white",
    bg="#1e272e"
)

enhance_header.pack(pady=10)

enhance_card = tk.Frame(
    enhance_tab,
    bg="#2f3640"
)

enhance_card.pack(fill="x", padx=20, pady=10)

folder_row(
    enhance_card,
    "Input Image Folder:",
    "enhance_input"
)

folder_row(
    enhance_card,
    "Enhanced Output Folder:",
    "enhance_output"
)

preset_frame = tk.Frame(
    enhance_tab,
    bg="#1e272e"
)

preset_frame.pack(pady=8)

preset_label = tk.Label(
    preset_frame,
    text="Enhancement Style:",
    fg="white",
    bg="#1e272e",
    font=("Segoe UI", 11, "bold")
)

preset_label.pack(side="left", padx=10)

preset_var = tk.StringVar()

preset_dropdown = ttk.Combobox(
    preset_frame,
    textvariable=preset_var,
    state="readonly",
    width=24
)

preset_dropdown["values"] = (
    "Basic",
    "Natural",
    "Aggressive"
)

preset_dropdown.current(1)

preset_dropdown.pack(side="left")

enhance_button_frame = tk.Frame(
    enhance_tab,
    bg="#1e272e"
)

enhance_button_frame.pack(pady=10)

enhance_btn = tk.Button(
    enhance_button_frame,
    text="START AUTO IMAGE ENHANCE",
    command=start_enhance_thread,
    bg="#9c88ff",
    fg="white",
    font=("Segoe UI", 11, "bold"),
    relief="flat",
    padx=22,
    pady=10
)

enhance_btn.pack(side="left", padx=10)

enhance_cancel_btn = tk.Button(
    enhance_button_frame,
    text="CANCEL",
    command=cancel_enhance_process,
    bg="#c23616",
    fg="white",
    font=("Segoe UI", 11, "bold"),
    relief="flat",
    padx=22,
    pady=10
)

enhance_cancel_btn.pack(side="left", padx=10)

enhance_progress = ttk.Progressbar(
    enhance_tab,
    length=620
)

enhance_progress.pack(pady=8)

enhance_progress_label = tk.Label(
    enhance_tab,
    text="0%",
    fg="white",
    bg="#1e272e"
)

enhance_progress_label.pack()

enhance_log_box = tk.Text(
    enhance_tab,
    height=15,
    bg="#2f3640",
    fg="white",
    insertbackground="white"
)

enhance_log_box.pack(
    fill="both",
    expand=True,
    padx=20,
    pady=10
)


# =========================================================
# DUPLICATE FILE FINDER TAB — v1.1
# =========================================================
dup_tab = tk.Frame(notebook, bg="#1e272e")
notebook.add(dup_tab, text="Duplicate Finder")

tk.Label(
    dup_tab,
    text="DUPLICATE FILE FINDER",
    font=("Segoe UI", 22, "bold"),
    fg="white",
    bg="#1e272e"
).pack(pady=10)

dup_card = tk.Frame(dup_tab, bg="#2f3640")
dup_card.pack(fill="x", padx=20, pady=10)

dup_scan_folder = ""

def select_dup_folder(lbl):
    global dup_scan_folder
    folder = filedialog.askdirectory()
    if folder:
        lbl.config(text=folder)
        dup_scan_folder = folder

dup_frame = tk.Frame(dup_card, bg="#2f3640")
dup_frame.pack(fill="x", pady=10, padx=15)

tk.Label(
    dup_frame,
    text="Folder to Scan:",
    width=24,
    anchor="w",
    fg="white",
    bg="#2f3640",
    font=("Segoe UI", 11)
).pack(side="left")

dup_folder_label = tk.Label(
    dup_frame,
    text="No folder selected",
    fg="#dcdde1",
    bg="#2f3640",
    anchor="w",
    font=("Segoe UI", 10)
)
dup_folder_label.pack(side="right", fill="x", expand=True)

tk.Button(
    dup_frame,
    text="Browse",
    command=lambda: select_dup_folder(dup_folder_label),
    bg="#40739e",
    fg="white",
    relief="flat",
    font=("Segoe UI", 10, "bold"),
    padx=12,
    pady=5,
    cursor="hand2"
).pack(side="right", padx=10)

tk.Label(
    dup_tab,
    text="Detects duplicates by matching filename and file size. Tick files you want to delete then click Delete Selected.",
    fg="#7f8fa6",
    bg="#1e272e",
    font=("Segoe UI", 9)
).pack(pady=(0, 5))

dup_btn_frame = tk.Frame(dup_tab, bg="#1e272e")
dup_btn_frame.pack(pady=5)

cancel_dup = False
dup_check_vars = []

def start_dup_thread():
    global cancel_dup
    cancel_dup = False
    threading.Thread(target=run_duplicate_finder, daemon=True).start()

def delete_selected_duplicates():
    if not dup_check_vars:
        messagebox.showinfo("No Results", "Please scan a folder first.")
        return
    selected = [fpath for var, fpath in dup_check_vars if var.get()]
    if not selected:
        messagebox.showinfo("No Selection", "Please tick the files you want to delete.")
        return
    answer = messagebox.askyesno(
        "Delete Duplicates",
        f"Permanently delete {len(selected)} selected file(s)?\nThis cannot be undone."
    )
    if answer:
        deleted = 0
        for fpath in selected:
            try:
                if os.path.exists(fpath):
                    os.remove(fpath)
                    deleted += 1
                    log(f"DELETED: {fpath}", dup_log_box)
            except Exception as e:
                log(f"FAILED: {fpath} | {str(e)}", dup_log_box)
        log(f"\n{deleted} duplicate(s) deleted.", dup_log_box)
        update_status(f"Deleted {deleted} duplicate files")

def run_duplicate_finder():
    global cancel_dup, dup_check_vars
    dup_check_vars = []

    try:
        dup_start_btn.config(state="disabled")

        if not dup_scan_folder:
            update_status("Please select a folder to scan")
            dup_start_btn.config(state="normal")
            return

        dup_log_box.delete("1.0", tk.END)

        for widget in dup_scroll_frame.winfo_children():
            widget.destroy()

        all_files = []
        for root_dir, dirs, files_list in os.walk(dup_scan_folder):
            for f in files_list:
                fpath = os.path.join(root_dir, f)
                try:
                    fsize = os.path.getsize(fpath)
                    all_files.append((f, fsize, fpath))
                except Exception:
                    pass

        total = len(all_files)
        dup_progress["maximum"] = max(total, 1)
        dup_progress["value"] = 0

        seen = {}
        duplicates = []

        for i, (fname, fsize, fpath) in enumerate(all_files, start=1):
            key = f"{fname}_{fsize}"
            if key in seen:
                duplicates.append((fname, fsize, fpath, seen[key]))
            else:
                seen[key] = fpath
            dup_progress["value"] = i
            dup_progress_label.config(text=f"{int(i / total * 100)}%")
            app.update_idletasks()

        if not duplicates:
            log("No duplicates found in this folder.", dup_log_box)
            update_status("No duplicates found")
            dup_start_btn.config(state="normal")
            time.sleep(1)
            reset_progress(dup_progress, dup_progress_label)
            return

        log(f"Found {len(duplicates)} duplicate file(s):\n", dup_log_box)

        for fname, fsize, fpath, original in duplicates:
            size_kb = round(fsize / 1024, 1)
            var = tk.BooleanVar(value=True)
            dup_check_vars.append((var, fpath))

            row = tk.Frame(dup_scroll_frame, bg="#2f3640")
            row.pack(fill="x", padx=5, pady=3)

            tk.Checkbutton(
                row,
                variable=var,
                bg="#2f3640",
                selectcolor="#1e272e",
                activebackground="#2f3640"
            ).pack(side="left")

            info_frame = tk.Frame(row, bg="#2f3640")
            info_frame.pack(side="left", fill="x", expand=True)

            tk.Label(
                info_frame,
                text=f"{fname}  ({size_kb} KB)",
                fg="#dcdde1",
                bg="#2f3640",
                font=("Segoe UI", 9, "bold"),
                anchor="w"
            ).pack(anchor="w")

            tk.Label(
                info_frame,
                text=f"Duplicate: {fpath}",
                fg="#e84118",
                bg="#2f3640",
                font=("Segoe UI", 8),
                anchor="w"
            ).pack(anchor="w")

            tk.Label(
                info_frame,
                text=f"Original:  {original}",
                fg="#44bd32",
                bg="#2f3640",
                font=("Segoe UI", 8),
                anchor="w"
            ).pack(anchor="w")

            tk.Frame(dup_scroll_frame, bg="#353b48", height=1).pack(fill="x", padx=5)

            log(f"DUPLICATE: {fname} ({size_kb} KB)", dup_log_box)
            log(f"  Original  : {original}", dup_log_box)
            log(f"  Duplicate : {fpath}\n", dup_log_box)

        update_status(f"Found {len(duplicates)} duplicate(s) — tick and click Delete Selected")
        time.sleep(1)
        reset_progress(dup_progress, dup_progress_label)
        dup_start_btn.config(state="normal")

    except Exception as e:
        update_status(f"Error: {str(e)}")
        dup_start_btn.config(state="normal")

dup_start_btn = tk.Button(
    dup_btn_frame,
    text="SCAN FOR DUPLICATES",
    command=start_dup_thread,
    bg="#e1b12c",
    fg="black",
    font=("Segoe UI", 11, "bold"),
    relief="flat",
    padx=22,
    pady=10,
    cursor="hand2"
)
dup_start_btn.pack(side="left", padx=10)

tk.Button(
    dup_btn_frame,
    text="DELETE SELECTED",
    command=delete_selected_duplicates,
    bg="#c23616",
    fg="white",
    font=("Segoe UI", 11, "bold"),
    relief="flat",
    padx=22,
    pady=10,
    cursor="hand2"
).pack(side="left", padx=10)

dup_progress = ttk.Progressbar(dup_tab, length=620)
dup_progress.pack(pady=8)

dup_progress_label = tk.Label(
    dup_tab,
    text="0%",
    fg="white",
    bg="#1e272e"
)
dup_progress_label.pack()

# Scrollable duplicate list
dup_list_outer = tk.Frame(dup_tab, bg="#2f3640")
dup_list_outer.pack(fill="both", expand=True, padx=20, pady=(0, 5))

dup_canvas = tk.Canvas(dup_list_outer, bg="#2f3640", highlightthickness=0)
dup_scrollbar = ttk.Scrollbar(dup_list_outer, orient="vertical", command=dup_canvas.yview)
dup_scroll_frame = tk.Frame(dup_canvas, bg="#2f3640")

dup_scroll_frame.bind(
    "<Configure>",
    lambda e: dup_canvas.configure(scrollregion=dup_canvas.bbox("all"))
)

dup_canvas.create_window((0, 0), window=dup_scroll_frame, anchor="nw")
dup_canvas.configure(yscrollcommand=dup_scrollbar.set)
dup_canvas.pack(side="left", fill="both", expand=True)
dup_scrollbar.pack(side="right", fill="y")

dup_log_box = tk.Text(
    dup_tab,
    height=5,
    bg="#2f3640",
    fg="white",
    insertbackground="white"
)
dup_log_box.pack(fill="x", padx=20, pady=(0, 10))

# =========================================================
# LAUNCH — CHECK ACTIVATION BEFORE SHOWING APP
# =========================================================
check_debug()
if is_activated():
    show_splash_and_verify()
else:
    show_activation_window()

# =========================================================
# RUN APP
# =========================================================
app.mainloop()
