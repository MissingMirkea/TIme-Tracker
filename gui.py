import base64
import ctypes
import os
import shutil
import struct
import sys
import time
import winreg
import zlib
import tkinter as tk
from tkinter import ttk
from ctypes import wintypes
from database import create_database, get_summary, log_activity
from tracker import get_active_window_info, get_system_sleep_time


def resource_path(relative_path: str) -> str:
    """Gets absolute path to resources, working both in dev mode and inside PyInstaller .exe."""
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


def _resolve_executable_path(app_name: str, executable_path: str) -> str:
    if executable_path and os.path.isfile(executable_path):
        return executable_path

    executable_name = os.path.basename(executable_path or app_name)
    path = shutil.which(executable_name)
    if path:
        return path

    registry_path = (
        "Software\\Microsoft\\Windows\\CurrentVersion\\App Paths\\"
        + executable_name
    )
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY, 0):
            try:
                with winreg.OpenKey(
                    hive, registry_path, 0, winreg.KEY_READ | view
                ) as key:
                    path, _ = winreg.QueryValueEx(key, None)
                if os.path.isfile(path):
                    return path
            except OSError:
                continue
    return ""


def _png_chunk(chunk_type: bytes, data: bytes) -> bytes:
    chunk = chunk_type + data
    return (
        struct.pack(">I", len(data))
        + chunk
        + struct.pack(">I", zlib.crc32(chunk) & 0xFFFFFFFF)
    )


def _extract_executable_icon(executable_path: str) -> bytes | None:
    class ShellFileInfo(ctypes.Structure):
        _fields_ = [
            ("hIcon", wintypes.HANDLE),
            ("iIcon", ctypes.c_int),
            ("dwAttributes", wintypes.DWORD),
            ("szDisplayName", wintypes.WCHAR * 260),
            ("szTypeName", wintypes.WCHAR * 80),
        ]

    class BitmapInfoHeader(ctypes.Structure):
        _fields_ = [
            ("biSize", wintypes.DWORD),
            ("biWidth", ctypes.c_long),
            ("biHeight", ctypes.c_long),
            ("biPlanes", wintypes.WORD),
            ("biBitCount", wintypes.WORD),
            ("biCompression", wintypes.DWORD),
            ("biSizeImage", wintypes.DWORD),
            ("biXPelsPerMeter", ctypes.c_long),
            ("biYPelsPerMeter", ctypes.c_long),
            ("biClrUsed", wintypes.DWORD),
            ("biClrImportant", wintypes.DWORD),
        ]

    class BitmapInfo(ctypes.Structure):
        _fields_ = [("bmiHeader", BitmapInfoHeader)]

    width = height = 20
    file_info = ShellFileInfo()
    shell_get_file_info = ctypes.windll.shell32.SHGetFileInfoW
    shell_get_file_info.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        ctypes.POINTER(ShellFileInfo),
        wintypes.UINT,
        wintypes.UINT,
    ]
    shell_get_file_info.restype = ctypes.c_size_t
    if not shell_get_file_info(
        executable_path,
        0,
        ctypes.byref(file_info),
        ctypes.sizeof(file_info),
        0x100,
    ) or not file_info.hIcon:
        return None

    gdi32 = ctypes.windll.gdi32
    user32 = ctypes.windll.user32
    user32.GetDC.argtypes = [wintypes.HWND]
    user32.GetDC.restype = wintypes.HDC
    user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
    user32.ReleaseDC.restype = ctypes.c_int
    user32.DrawIconEx.argtypes = [
        wintypes.HDC,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.UINT,
        wintypes.HANDLE,
        wintypes.UINT,
    ]
    user32.DrawIconEx.restype = wintypes.BOOL
    user32.DestroyIcon.argtypes = [wintypes.HANDLE]
    user32.DestroyIcon.restype = wintypes.BOOL
    gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
    gdi32.CreateCompatibleDC.restype = wintypes.HDC
    gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HANDLE]
    gdi32.SelectObject.restype = wintypes.HANDLE
    gdi32.DeleteObject.argtypes = [wintypes.HANDLE]
    gdi32.DeleteObject.restype = wintypes.BOOL
    gdi32.DeleteDC.argtypes = [wintypes.HDC]
    gdi32.DeleteDC.restype = wintypes.BOOL
    screen_dc = user32.GetDC(None)
    memory_dc = None
    bitmap = None
    old_bitmap = None
    try:
        memory_dc = gdi32.CreateCompatibleDC(screen_dc)
        if not memory_dc:
            return None

        bitmap_info = BitmapInfo(
            BitmapInfoHeader(
                ctypes.sizeof(BitmapInfoHeader),
                width,
                -height,
                1,
                32,
                0,
                width * height * 4,
                0,
                0,
                0,
                0,
            )
        )
        pixel_data = ctypes.c_void_p()
        gdi32.CreateDIBSection.argtypes = [
            wintypes.HDC,
            ctypes.POINTER(BitmapInfo),
            wintypes.UINT,
            ctypes.POINTER(ctypes.c_void_p),
            wintypes.HANDLE,
            wintypes.DWORD,
        ]
        gdi32.CreateDIBSection.restype = wintypes.HANDLE
        bitmap = gdi32.CreateDIBSection(
            memory_dc,
            ctypes.byref(bitmap_info),
            0,
            ctypes.byref(pixel_data),
            None,
            0,
        )
        if not bitmap or not pixel_data.value:
            return None

        old_bitmap = gdi32.SelectObject(memory_dc, bitmap)
        ctypes.memset(pixel_data, 255, width * height * 4)
        if not user32.DrawIconEx(
            memory_dc, 0, 0, file_info.hIcon, width, height, 0, None, 3
        ):
            return None

        bgra = ctypes.string_at(pixel_data, width * height * 4)
        rgba = bytearray(width * height * 4)
        for offset in range(0, len(bgra), 4):
            rgba[offset : offset + 4] = bytes(
                (bgra[offset + 2], bgra[offset + 1], bgra[offset], 255)
            )

        scanlines = b"".join(
            b"\0" + rgba[row * width * 4 : (row + 1) * width * 4]
            for row in range(height)
        )
        return (
            b"\x89PNG\r\n\x1a\n"
            + _png_chunk(
                b"IHDR", struct.pack(">2I5B", width, height, 8, 6, 0, 0, 0)
            )
            + _png_chunk(b"IDAT", zlib.compress(scanlines))
            + _png_chunk(b"IEND", b"")
        )
    finally:
        if old_bitmap:
            gdi32.SelectObject(memory_dc, old_bitmap)
        if bitmap:
            gdi32.DeleteObject(bitmap)
        if memory_dc:
            gdi32.DeleteDC(memory_dc)
        if screen_dc:
            user32.ReleaseDC(None, screen_dc)
        ctypes.windll.user32.DestroyIcon(file_info.hIcon)


class TimeTrackerGUI:

    def __init__(self, root):
        self.root = root
        self.root.title("Time Tracker")
        self.root.geometry("800x520")
        self.root.minsize(650, 400)

        # Set Window Icon if app_icon.ico exists in project directory
        icon_path = resource_path("app_icon.ico")
        if os.path.exists(icon_path):
            self.root.iconbitmap(icon_path)

        # Guarantee database exists
        create_database()

        # State tracking
        self.is_tracking = False
        self.current_app = ""
        self.current_title = ""
        self.current_executable_path = ""
        self.start_time = 0.0
        self.last_check_time = 0.0
        self.sleep_time = 0.0
        self.app_images: dict[str, tk.PhotoImage | None] = {}

        # Apply visual theme
        self._configure_styles()

        # Build UI
        self._build_ui()
        self.refresh_table()

    def _configure_styles(self):
        """Sets up custom fonts, colors, and button styles using ttk."""
        self.style = ttk.Style()
        self.style.theme_use("clam")

        BG_COLOR = "#F8FAFC"
        CARD_BG = "#FFFFFF"
        TEXT_PRIMARY = "#0F172A"
        ACCENT_GREEN = "#16A34A"
        ACCENT_RED = "#DC2626"

        self.root.configure(bg=BG_COLOR)

        self.style.configure("Main.TFrame", background=BG_COLOR)
        self.style.configure("Card.TFrame", background=CARD_BG, relief="flat")

        self.style.configure(
            "Header.TLabel",
            background=CARD_BG,
            foreground=TEXT_PRIMARY,
            font=("Segoe UI", 11, "bold"),
        )

        # Table Styling
        self.style.configure(
            "Treeview",
            background="#FFFFFF",
            foreground=TEXT_PRIMARY,
            fieldbackground="#FFFFFF",
            rowheight=28,
            font=("Segoe UI", 9),
            bordercolor="#E2E8F0",
            borderwidth=1,
        )
        self.style.configure(
            "Treeview.Heading",
            background="#F1F5F9",
            foreground=TEXT_PRIMARY,
            font=("Segoe UI", 10, "bold"),
            padding=6,
        )
        self.style.map(
            "Treeview", background=[("selected", "#E2E8F0")], foreground=[]
        )

        # Button Styles
        self.style.configure(
            "Start.TButton",
            font=("Segoe UI", 10, "bold"),
            background="GREEN",
            foreground="white",
            padding=6,
        )
        self.style.map("Start.TButton", background=[("active", "#15803D")])

        self.style.configure(
            "Stop.TButton",
            font=("Segoe UI", 10, "bold"),
            background="RED",
            foreground="white",
            padding=6,
        )
        self.style.map("Stop.TButton", background=[("active", "#B91C1C")])

    def _build_ui(self):
        main_container = ttk.Frame(self.root, style="Main.TFrame", padding=15)
        main_container.pack(fill=tk.BOTH, expand=True)

        # Top Control Card
        control_card = ttk.Frame(
            main_container, style="Card.TFrame", padding=15
        )
        control_card.pack(fill=tk.X, pady=(0, 15))

        self.status_label = ttk.Label(
            control_card, text="Status: STOPPED", style="Header.TLabel"
        )
        self.status_label.pack(side=tk.LEFT, padx=5)

        self.btn_stop = ttk.Button(
            control_card,
            text="Stop",
            style="Stop.TButton",
            command=self.stop_tracking,
            state=tk.DISABLED,
        )
        self.btn_stop.pack(side=tk.RIGHT, padx=5)

        self.btn_start = ttk.Button(
            control_card,
            text="Start",
            style="Start.TButton",
            command=self.start_tracking,
        )
        self.btn_start.pack(side=tk.RIGHT, padx=5)

        # Summary Table Card
        table_card = ttk.Frame(main_container, style="Card.TFrame", padding=15)
        table_card.pack(fill=tk.BOTH, expand=True)

        columns = ("app", "window_title", "time")
        self.tree = ttk.Treeview(
            table_card,
            columns=columns,
            show="tree headings",
            selectmode="browse",
            style="Treeview",
        )
        self.tree.heading("#0", text="Icon")
        self.tree.column(
            "#0", width=60, minwidth=40, anchor=tk.CENTER, stretch=False
        )
        self.tree.heading("app", text="Application Name")
        self.tree.heading("window_title", text="Window Title")
        self.tree.heading("time", text="Total Time Spent")
        self.tree.column("app", width=170, anchor=tk.W)
        self.tree.column("window_title", width=300, anchor=tk.W)
        self.tree.column("time", width=140, anchor=tk.E)

        scrollbar = ttk.Scrollbar(
            table_card, orient=tk.VERTICAL, command=self.tree.yview
        )
        self.tree.configure(yscrollcommand=scrollbar.set)

        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    def format_time(self, seconds: float) -> str:
        """Converts raw seconds into a readable format (e.g. 1h 23m 45s)."""
        seconds = int(seconds)
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60

        if hours > 0:
            return f"{hours}h {minutes}m {secs}s"
        elif minutes > 0:
            return f"{minutes}m {secs}s"
        else:
            return f"{secs}s"

    def refresh_table(self):
        """Reloads summary data from SQLite into the GUI table."""
        for row in self.tree.get_children():
            self.tree.delete(row)

        summary_data = get_summary()
        for app_name, window_title, total_seconds, executable_path in summary_data:
            image = self._get_app_image(app_name, executable_path)
            item_options = {
                "values": (
                    app_name,
                    window_title,
                    self.format_time(total_seconds),
                )
            }
            if image is not None:
                item_options["image"] = image
            self.tree.insert(
                "",
                tk.END,
                **item_options,
            )

    def _get_app_image(
        self, app_name: str, executable_path: str
    ) -> tk.PhotoImage | None:
        cache_key = executable_path.casefold() or app_name.casefold()
        if cache_key not in self.app_images:
            image = None
            resolved_path = _resolve_executable_path(app_name, executable_path)
            if resolved_path:
                try:
                    image_data = _extract_executable_icon(resolved_path)
                    if image_data:
                        image = tk.PhotoImage(
                            master=self.root,
                            data=base64.b64encode(image_data).decode("ascii"),
                            format="png",
                        )
                except (OSError, tk.TclError):
                    image = None
            self.app_images[cache_key] = image
        return self.app_images[cache_key]

    def start_tracking(self):
        if not self.is_tracking:
            sleep_time = get_system_sleep_time()
            current_app, current_title, executable_path = get_active_window_info()

            self.is_tracking = True
            self.btn_start.config(state=tk.DISABLED)
            self.btn_stop.config(state=tk.NORMAL)
            self.status_label.config(text="Status: TRACKING...")

            self.current_app = current_app
            self.current_title = current_title
            self.current_executable_path = executable_path
            self.start_time = time.time()
            self.last_check_time = self.start_time
            self.sleep_time = sleep_time

            self.root.after(1000, self.track_loop)

    def stop_tracking(self, end_time=None):
        if self.is_tracking:
            self.is_tracking = False
            self.btn_start.config(state=tk.NORMAL)
            self.btn_stop.config(state=tk.DISABLED)
            stopped_for_sleep = end_time is not None
            status = (
                "Status: STOPPED (SLEEP DETECTED)"
                if stopped_for_sleep
                else "Status: STOPPED"
            )
            self.status_label.config(text=status)

            if self.start_time > 0:
                stop_time = end_time if stopped_for_sleep else time.time()
                duration = max(0.0, stop_time - self.start_time)
                log_activity(
                    self.current_app,
                    self.current_title,
                    duration,
                    self.current_executable_path,
                )

            self.refresh_table()

    def track_loop(self):
        if not self.is_tracking:
            return

        current_sleep_time = get_system_sleep_time()
        if current_sleep_time - self.sleep_time >= 0.5:
            self.stop_tracking(end_time=self.last_check_time)
            return

        self.sleep_time = current_sleep_time
        new_app, new_title, executable_path = get_active_window_info()
        now = time.time()

        if (
            new_title != self.current_title
            or new_app != self.current_app
            or executable_path != self.current_executable_path
        ):
            duration = now - self.start_time

            log_activity(
                self.current_app,
                self.current_title,
                duration,
                self.current_executable_path,
            )
            self.refresh_table()

            self.current_app = new_app
            self.current_title = new_title
            self.current_executable_path = executable_path
            self.start_time = now

        self.last_check_time = now
        self.root.after(1000, self.track_loop)


if __name__ == "__main__":
 # Force Windows to assign a unique Taskbar ID to this application
    my_app_id = "timetracker.desktop.app.1.0"
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(my_app_id)

    root = tk.Tk()
    app = TimeTrackerGUI(root)
    root.mainloop()
