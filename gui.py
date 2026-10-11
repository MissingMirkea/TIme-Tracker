import os
import sys
import time
import ctypes
import tkinter as tk
from tkinter import ttk
from database import create_database, get_summary, log_activity
from tracker import get_active_window_title, get_system_sleep_time


def resource_path(relative_path: str) -> str:
    """Gets absolute path to resources, working both in dev mode and inside PyInstaller .exe."""
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


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
        self.start_time = 0.0
        self.last_check_time = 0.0
        self.sleep_time = 0.0

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
            show="headings",
            selectmode="browse",
            style="Treeview",
        )
        self.tree.heading("app", text="Application Name")
        self.tree.heading("window_title", text="Window Title")
        self.tree.heading("time", text="Total Time Spent")
        self.tree.column("app", width=180, anchor=tk.W)
        self.tree.column("window_title", width=380, anchor=tk.W)
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
        for app_name, window_title, total_seconds in summary_data:
            self.tree.insert(
                "",
                tk.END,
                values=(
                    app_name,
                    window_title,
                    self.format_time(total_seconds),
                ),
            )

    def start_tracking(self):
        if not self.is_tracking:
            sleep_time = get_system_sleep_time()
            current_app, current_title = get_active_window_title()

            self.is_tracking = True
            self.btn_start.config(state=tk.DISABLED)
            self.btn_stop.config(state=tk.NORMAL)
            self.status_label.config(text="Status: TRACKING...")

            self.current_app = current_app
            self.current_title = current_title
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
                log_activity(self.current_app, self.current_title, duration)

            self.refresh_table()

    def track_loop(self):
        if not self.is_tracking:
            return

        current_sleep_time = get_system_sleep_time()
        if current_sleep_time - self.sleep_time >= 0.5:
            self.stop_tracking(end_time=self.last_check_time)
            return

        self.sleep_time = current_sleep_time
        new_app, new_title = get_active_window_title()
        now = time.time()

        if new_title != self.current_title or new_app != self.current_app:
            duration = now - self.start_time

            log_activity(self.current_app, self.current_title, duration)
            self.refresh_table()

            self.current_app = new_app
            self.current_title = new_title
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
    root = tk.Tk()
    app = TimeTrackerGUI(root)
    root.mainloop()
