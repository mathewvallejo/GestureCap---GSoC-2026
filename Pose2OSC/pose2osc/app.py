"""Tkinter GUI for Pose2OSC.

The GUI is intentionally a thin wrapper around ``pose2osc/cli.py`` so the app
and Terminal use the same enrollment and performance runtime.
"""

from __future__ import annotations

import os
from pathlib import Path
import signal
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from pose2osc.cli import DEFAULT_GENERATED_GESTURES, HAND_CHOICES, default_manifest_path, parse_label_text, project_root
    from pose2osc.manifest import GestureModel, label_style
    from pose2osc.osc import build_osc_route_text, load_manifest_labels
else:
    from .cli import DEFAULT_GENERATED_GESTURES, HAND_CHOICES, default_manifest_path, parse_label_text, project_root
    from .manifest import GestureModel, label_style
    from .osc import build_osc_route_text, load_manifest_labels


APP_BG = "#202528"
PANEL_BG = "#F5F2EC"
FIELD_BG = "#FFFFFF"
TEXT_COLOR = "#182026"
MUTED_COLOR = "#627078"
ACCENT_COLOR = "#009C9C"
ACCENT_DARK = "#007878"
BORDER_COLOR = "#C9D1CC"
DISABLED_BG = "#E2E3DF"
LOG_BG = "#101416"
LOG_FG = "#E8EFED"
MANIFEST_FILETYPES = [("JSON manifests", "*.json"), ("All files", "*.*")]
GRACEFUL_STOP_TIMEOUT_SECONDS = 5.0
FORCE_STOP_TIMEOUT_SECONDS = 2.0


def stop_pose2osc_process(process: subprocess.Popen[str], log) -> int | None:
    """Ask a child Pose2OSC session to stop before forcing it closed."""

    if process.poll() is not None:
        return process.returncode

    log("Stopping active Pose2OSC session\n")
    try:
        if os.name == "nt":
            process.terminate()
        else:
            process.send_signal(signal.SIGINT)
    except OSError:
        return process.poll()

    try:
        return process.wait(timeout=GRACEFUL_STOP_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        log("Pose2OSC did not stop cleanly; forcing it to close\n")
        process.terminate()

    try:
        return process.wait(timeout=FORCE_STOP_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        process.kill()
        return process.wait(timeout=FORCE_STOP_TIMEOUT_SECONDS)


def manifest_dialog_settings(current_text: str, *, title: str) -> dict[str, object]:
    current = Path(current_text or default_manifest_path()).expanduser()
    initial_dir = current.parent if current.name else Path(default_manifest_path()).parent
    if not initial_dir.exists():
        initial_dir = project_root() / "models"
    if not initial_dir.exists():
        initial_dir = project_root()
    return {
        "title": title,
        "initialdir": str(initial_dir),
        "initialfile": current.name or "gestures.json",
        "defaultextension": ".json",
        "filetypes": MANIFEST_FILETYPES,
    }


class Pose2OSCApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Pose2OSC")
        self.geometry("1040x760")
        self.minsize(900, 660)
        self.process: subprocess.Popen[str] | None = None
        self.reader_thread: threading.Thread | None = None
        self.log_queue: queue.Queue[str] = queue.Queue()

        self._build_variables()
        self._configure_style()
        self._build_ui()
        self._sync_label_source()
        self._sync_primary_button()
        self._refresh_manifest_summary()

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(100, self._poll_log_queue)
        self.after(300, self._poll_process)

    def _build_variables(self) -> None:
        self.manifest_var = tk.StringVar(value=default_manifest_path())
        self.camera_var = tk.StringVar(value="0")
        self.hand_var = tk.StringVar(value="Auto")
        self.correct_handedness_var = tk.BooleanVar(value=True)
        self.preview_var = tk.BooleanVar(value=True)
        self.width_var = tk.StringVar(value="")
        self.height_var = tk.StringVar(value="")

        self.generated_var = tk.BooleanVar(value=True)
        self.labels_var = tk.StringVar(value="gesture_1")
        self.gesture_count_var = tk.StringVar(value=str(DEFAULT_GENERATED_GESTURES))
        self.start_index_var = tk.StringVar(value="1")
        self.seconds_var = tk.StringVar(value="2.0")
        self.capture_frames_var = tk.StringVar(value="45")
        self.target_captures_var = tk.StringVar(value="5")
        self.max_samples_var = tk.StringVar(value="64")
        self.timed_var = tk.BooleanVar(value=False)
        self.replace_var = tk.BooleanVar(value=False)

        self.host_var = tk.StringVar(value="127.0.0.1")
        self.port_var = tk.StringVar(value="9000")
        self.split_axes_var = tk.BooleanVar(value=False)
        self.landmark_vectors_var = tk.BooleanVar(value=True)
        self.send_unknown_var = tk.BooleanVar(value=False)
        self.show_routes_var = tk.BooleanVar(value=False)
        self.enter_frames_var = tk.StringVar(value="1")
        self.exit_frames_var = tk.StringVar(value="1")
        self.switch_frames_var = tk.StringVar(value="1")

        self.status_var = tk.StringVar(value="Idle")
        self.summary_var = tk.StringVar(value="")
        self.generated_var.trace_add("write", lambda *_: self._sync_label_source())

    def _configure_style(self) -> None:
        self.configure(background=APP_BG)
        self.style = ttk.Style(self)
        if "clam" in self.style.theme_names():
            self.style.theme_use("clam")
        self.style.configure("Root.TFrame", background=APP_BG)
        self.style.configure("Header.TFrame", background=APP_BG)
        self.style.configure("TFrame", background=PANEL_BG)
        self.style.configure("TLabel", background=PANEL_BG, foreground=TEXT_COLOR)
        self.style.configure("Header.TLabel", background=APP_BG, foreground="#F8F5EF", font=("TkDefaultFont", 20, "bold"))
        self.style.configure("Subheader.TLabel", background=APP_BG, foreground="#B7C5C3", font=("TkDefaultFont", 10))
        self.style.configure("Subtle.TLabel", background=PANEL_BG, foreground=MUTED_COLOR)
        self.style.configure("Field.TLabel", background=PANEL_BG, foreground=MUTED_COLOR, font=("TkDefaultFont", 10))
        self.style.configure("TLabelframe", background=PANEL_BG, bordercolor=BORDER_COLOR, lightcolor=BORDER_COLOR, darkcolor=BORDER_COLOR, relief="solid")
        self.style.configure("TLabelframe.Label", background=PANEL_BG, foreground=TEXT_COLOR, font=("TkDefaultFont", 11, "bold"))
        self.style.configure("TEntry", fieldbackground=FIELD_BG, foreground=TEXT_COLOR, insertcolor=TEXT_COLOR)
        self.style.map("TEntry", fieldbackground=[("disabled", DISABLED_BG), ("readonly", DISABLED_BG)], foreground=[("disabled", MUTED_COLOR)])
        self.style.configure("TCombobox", fieldbackground=FIELD_BG, foreground=TEXT_COLOR)
        self.style.configure("TCheckbutton", background=PANEL_BG, foreground=TEXT_COLOR)
        self.style.configure("TRadiobutton", background=PANEL_BG, foreground=TEXT_COLOR)
        self.style.configure("TNotebook", background=APP_BG, borderwidth=0)
        self.style.configure("TNotebook.Tab", background="#DDE5E2", foreground=TEXT_COLOR, padding=(16, 8))
        self.style.map("TNotebook.Tab", background=[("selected", PANEL_BG)], foreground=[("selected", ACCENT_DARK)])
        self.style.configure("TButton", background="#E1E7E4", foreground=TEXT_COLOR, padding=(12, 7))
        self.style.map("TButton", background=[("active", "#D4DFDB")])
        self.style.configure("Primary.TButton", background=ACCENT_COLOR, foreground="#FFFFFF", font=("TkDefaultFont", 11, "bold"), padding=(14, 8))
        self.style.map("Primary.TButton", background=[("active", ACCENT_DARK)])
        self.style.configure("Status.TLabel", background=APP_BG, foreground="#75D4CA")
        self.style.configure("Treeview", background=FIELD_BG, fieldbackground=FIELD_BG, foreground=TEXT_COLOR)
        self.style.configure("Treeview.Heading", background="#DDE5E2", foreground=TEXT_COLOR)

    def _build_ui(self) -> None:
        root = ttk.Frame(self, padding=18, style="Root.TFrame")
        root.grid(row=0, column=0, sticky="nsew")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(2, weight=1)

        header = ttk.Frame(root, style="Header.TFrame")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="Pose2OSC", style="Header.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(header, text="Gesture enrollment and OSC performance launcher", style="Subheader.TLabel").grid(row=1, column=0, sticky="w", pady=(2, 0))
        ttk.Label(header, textvariable=self.status_var, style="Status.TLabel").grid(row=0, column=1, rowspan=2, sticky="e")

        self._build_common_panel(root).grid(row=1, column=0, sticky="ew", pady=(0, 12))

        body = ttk.Frame(root, style="Root.TFrame")
        body.grid(row=2, column=0, sticky="nsew")
        body.columnconfigure(0, weight=3)
        body.columnconfigure(1, weight=2)
        body.rowconfigure(0, weight=1)

        left = ttk.Frame(body, style="Root.TFrame")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        left.columnconfigure(0, weight=1)
        left.rowconfigure(0, weight=1)

        self.notebook = ttk.Notebook(left)
        self.notebook.grid(row=0, column=0, sticky="nsew")
        self.notebook.bind("<<NotebookTabChanged>>", lambda _: self._sync_primary_button())
        self._build_enroll_tab()
        self._build_performance_tab()

        self._build_action_bar(left).grid(row=1, column=0, sticky="ew", pady=(12, 0))
        self.routes_panel = self._build_routes_panel(left)
        self.routes_panel.grid(row=2, column=0, sticky="nsew", pady=(12, 0))
        self.routes_panel.grid_remove()
        self._build_manifest_panel(body).grid(row=0, column=1, sticky="nsew")
        self._build_log_panel(root).grid(row=3, column=0, sticky="nsew", pady=(12, 0))
        root.rowconfigure(3, weight=1)

    def _build_common_panel(self, parent: ttk.Frame) -> ttk.LabelFrame:
        panel = ttk.LabelFrame(parent, text="Session")
        panel.columnconfigure(0, weight=1)

        manifest = ttk.Frame(panel)
        manifest.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 6))
        manifest.columnconfigure(0, weight=1)
        ttk.Label(manifest, text="Manifest file", style="Field.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 3))
        ttk.Entry(manifest, textvariable=self.manifest_var).grid(row=1, column=0, sticky="ew", padx=(0, 8))
        ttk.Button(manifest, text="Load", command=self._load_manifest).grid(row=1, column=1, sticky="e", padx=(0, 6))
        ttk.Button(manifest, text="New", command=self._new_manifest).grid(row=1, column=2, sticky="e")

        controls = ttk.Frame(panel)
        controls.grid(row=1, column=0, sticky="ew", padx=4, pady=(0, 10))
        for column in range(6):
            controls.columnconfigure(column, weight=1)
        self._add_labeled_entry(controls, "Camera", self.camera_var, 0, 0, width=8)
        self._add_labeled_combobox(controls, "Hand", self.hand_var, HAND_CHOICES, 0, 1, width=12)
        self._add_labeled_entry(controls, "Width", self.width_var, 0, 2, width=8)
        self._add_labeled_entry(controls, "Height", self.height_var, 0, 3, width=8)
        toggles = ttk.Frame(controls)
        toggles.grid(row=0, column=4, columnspan=2, sticky="nsew", padx=8, pady=8)
        ttk.Checkbutton(toggles, text="Correct handedness", variable=self.correct_handedness_var).grid(row=0, column=0, sticky="w", pady=(20, 4))
        ttk.Checkbutton(toggles, text="Preview window", variable=self.preview_var).grid(row=1, column=0, sticky="w")
        return panel

    def _build_enroll_tab(self) -> None:
        tab = ttk.Frame(self.notebook, padding=14)
        tab.columnconfigure(0, weight=1)
        self.notebook.add(tab, text="Set Gesture")

        source = ttk.LabelFrame(tab, text="Gestures")
        source.grid(row=0, column=0, sticky="ew")
        source.columnconfigure(1, weight=1)
        ttk.Radiobutton(source, text="Generated", variable=self.generated_var, value=True).grid(row=0, column=0, sticky="w", padx=10, pady=(10, 6))
        generated_frame = ttk.Frame(source)
        generated_frame.grid(row=0, column=1, sticky="ew", pady=(8, 4))
        self.gesture_count_entry = self._add_labeled_entry(generated_frame, "Count", self.gesture_count_var, 0, 0, width=8)
        self.start_index_entry = self._add_labeled_entry(generated_frame, "Start number", self.start_index_var, 0, 1, width=10)

        ttk.Radiobutton(source, text="Labels", variable=self.generated_var, value=False).grid(row=1, column=0, sticky="w", padx=10, pady=(6, 10))
        label_frame = ttk.Frame(source)
        label_frame.grid(row=1, column=1, sticky="ew", padx=(0, 10), pady=(4, 10))
        label_frame.columnconfigure(0, weight=1)
        ttk.Label(label_frame, text="Custom labels", style="Field.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 3))
        self.labels_entry = ttk.Entry(label_frame, textvariable=self.labels_var)
        self.labels_entry.grid(row=1, column=0, sticky="ew")

        capture = ttk.LabelFrame(tab, text="Capture")
        capture.grid(row=1, column=0, sticky="ew", pady=(12, 0))
        for column in range(4):
            capture.columnconfigure(column, weight=1)
        self._add_labeled_entry(capture, "Seconds", self.seconds_var, 0, 0, width=10)
        self._add_labeled_entry(capture, "Frames per capture", self.capture_frames_var, 0, 1, width=12)
        self._add_labeled_entry(capture, "Target captures", self.target_captures_var, 0, 2, width=12)
        self._add_labeled_entry(capture, "Max samples", self.max_samples_var, 0, 3, width=12)
        ttk.Checkbutton(capture, text="Timed capture", variable=self.timed_var).grid(row=1, column=0, columnspan=2, sticky="w", padx=12, pady=(2, 12))
        ttk.Checkbutton(capture, text="Replace existing samples", variable=self.replace_var).grid(row=1, column=2, columnspan=2, sticky="w", padx=12, pady=(2, 12))

    def _build_performance_tab(self) -> None:
        tab = ttk.Frame(self.notebook, padding=14)
        tab.columnconfigure(0, weight=1)
        self.notebook.add(tab, text="Performance")

        osc = ttk.LabelFrame(tab, text="OSC")
        osc.grid(row=0, column=0, sticky="ew")
        for column in range(4):
            osc.columnconfigure(column, weight=1)
        self._add_labeled_entry(osc, "OSC host", self.host_var, 0, 0, width=18)
        self._add_labeled_entry(osc, "OSC port", self.port_var, 0, 1, width=10)
        ttk.Checkbutton(osc, text="Split axes", variable=self.split_axes_var, command=self._refresh_osc_routes).grid(row=1, column=0, sticky="w", padx=12, pady=(2, 10))
        ttk.Checkbutton(osc, text="Landmark vectors", variable=self.landmark_vectors_var, command=self._refresh_osc_routes).grid(row=1, column=1, sticky="w", padx=12, pady=(2, 10))
        ttk.Checkbutton(osc, text="Unknown predictions", variable=self.send_unknown_var, command=self._refresh_osc_routes).grid(row=1, column=2, sticky="w", padx=12, pady=(2, 10))
        ttk.Checkbutton(osc, text="Show OSC routes", variable=self.show_routes_var, command=self._sync_routes_panel).grid(row=1, column=3, sticky="w", padx=12, pady=(2, 10))

        state = ttk.LabelFrame(tab, text="State")
        state.grid(row=1, column=0, sticky="ew", pady=(12, 0))
        for column in range(3):
            state.columnconfigure(column, weight=1)
        self._add_labeled_entry(state, "Enter frames", self.enter_frames_var, 0, 0, width=10)
        self._add_labeled_entry(state, "Exit frames", self.exit_frames_var, 0, 1, width=10)
        self._add_labeled_entry(state, "Switch frames", self.switch_frames_var, 0, 2, width=10)

    def _build_action_bar(self, parent: ttk.Frame) -> ttk.Frame:
        bar = ttk.Frame(parent)
        bar.columnconfigure(0, weight=1)
        self.primary_button = ttk.Button(bar, text="Start", style="Primary.TButton", command=self._start_selected_mode)
        self.primary_button.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.stop_button = ttk.Button(bar, text="Stop", command=self._stop_process, state="disabled")
        self.stop_button.grid(row=0, column=1, sticky="ew")
        return bar

    def _build_manifest_panel(self, parent: ttk.Frame) -> ttk.LabelFrame:
        panel = ttk.LabelFrame(parent, text="Manifest")
        panel.columnconfigure(0, weight=1)
        panel.rowconfigure(1, weight=1)
        ttk.Label(panel, textvariable=self.summary_var, style="Subtle.TLabel").grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 6))
        columns = ("label", "display", "samples", "hands", "threshold")
        self.manifest_tree = ttk.Treeview(panel, columns=columns, show="headings", height=8)
        headings = {"label": "Label", "display": "Display", "samples": "Samples", "hands": "Hands", "threshold": "Threshold"}
        widths = {"label": 100, "display": 120, "samples": 70, "hands": 90, "threshold": 80}
        for column in columns:
            self.manifest_tree.heading(column, text=headings[column])
            self.manifest_tree.column(column, width=widths[column], anchor="w")
        self.manifest_tree.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 8))
        ttk.Button(panel, text="Refresh", command=self._refresh_manifest_summary).grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 10))
        return panel

    def _build_log_panel(self, parent: ttk.Frame) -> ttk.LabelFrame:
        panel = ttk.LabelFrame(parent, text="Output")
        panel.columnconfigure(0, weight=1)
        panel.rowconfigure(0, weight=1)
        self.log_text = tk.Text(panel, height=8, wrap="word", state="disabled", background=LOG_BG, foreground=LOG_FG, insertbackground=LOG_FG, borderwidth=0, padx=10, pady=8)
        self.log_text.grid(row=0, column=0, sticky="nsew", padx=(10, 0), pady=10)
        scrollbar = ttk.Scrollbar(panel, orient="vertical", command=self.log_text.yview)
        scrollbar.grid(row=0, column=1, sticky="ns", padx=(0, 10), pady=10)
        self.log_text.configure(yscrollcommand=scrollbar.set)
        return panel

    def _build_routes_panel(self, parent: ttk.Frame) -> ttk.LabelFrame:
        panel = ttk.LabelFrame(parent, text="OSC Routes")
        panel.columnconfigure(0, weight=1)
        panel.rowconfigure(0, weight=1)
        self.routes_text = tk.Text(panel, height=12, wrap="word", state="disabled", background=FIELD_BG, foreground=TEXT_COLOR, insertbackground=TEXT_COLOR, borderwidth=0, padx=10, pady=8)
        self.routes_text.grid(row=0, column=0, sticky="nsew", padx=(10, 0), pady=10)
        scrollbar = ttk.Scrollbar(panel, orient="vertical", command=self.routes_text.yview)
        scrollbar.grid(row=0, column=1, sticky="ns", padx=(0, 10), pady=10)
        self.routes_text.configure(yscrollcommand=scrollbar.set)
        return panel

    def _add_labeled_entry(self, parent: ttk.Frame, label: str, variable: tk.StringVar, row: int, column: int, *, width: int = 12) -> ttk.Entry:
        field = ttk.Frame(parent)
        field.grid(row=row, column=column, sticky="ew", padx=8, pady=8)
        field.columnconfigure(0, weight=1, minsize=max(80, width * 9))
        ttk.Label(field, text=label, style="Field.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 3))
        entry = ttk.Entry(field, textvariable=variable, width=width)
        entry.grid(row=1, column=0, sticky="ew")
        return entry

    def _add_labeled_combobox(self, parent: ttk.Frame, label: str, variable: tk.StringVar, values: tuple[str, ...], row: int, column: int, *, width: int = 12) -> ttk.Combobox:
        field = ttk.Frame(parent)
        field.grid(row=row, column=column, sticky="ew", padx=8, pady=8)
        field.columnconfigure(0, weight=1, minsize=max(80, width * 9))
        ttk.Label(field, text=label, style="Field.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 3))
        combo = ttk.Combobox(field, textvariable=variable, values=values, state="readonly", width=width)
        combo.grid(row=1, column=0, sticky="ew")
        return combo

    def _load_manifest(self) -> None:
        selected = filedialog.askopenfilename(**manifest_dialog_settings(self.manifest_var.get(), title="Load Gesture Manifest"))
        if selected:
            self.manifest_var.set(selected)
            self._refresh_manifest_summary()
            self._refresh_osc_routes()

    def _new_manifest(self) -> None:
        selected = filedialog.asksaveasfilename(**manifest_dialog_settings(self.manifest_var.get(), title="New Gesture Manifest"))
        if selected:
            self.manifest_var.set(selected)
            self._refresh_manifest_summary()
            self._refresh_osc_routes()

    def _sync_routes_panel(self) -> None:
        if self.show_routes_var.get():
            self.routes_panel.grid()
            self._refresh_osc_routes()
        else:
            self.routes_panel.grid_remove()

    def _refresh_osc_routes(self) -> None:
        if not hasattr(self, "routes_text"):
            return
        text = build_osc_route_text(
            load_manifest_labels(self.manifest_var.get()),
            send_landmark_vectors=self.landmark_vectors_var.get(),
            split_axes=self.split_axes_var.get(),
            send_unknown_predictions=self.send_unknown_var.get(),
        )
        self.routes_text.configure(state="normal")
        self.routes_text.delete("1.0", "end")
        self.routes_text.insert("1.0", text)
        self.routes_text.configure(state="disabled")

    def _sync_label_source(self) -> None:
        generated = self.generated_var.get()
        for widget in (self.gesture_count_entry, self.start_index_entry):
            widget.configure(state="normal" if generated else "disabled")
        self.labels_entry.configure(state="disabled" if generated else "normal")

    def _sync_primary_button(self) -> None:
        self.primary_button.configure(text="Start Set Gesture" if self._selected_mode() == "enroll" else "Start Performance")

    def _selected_mode(self) -> str:
        return "enroll" if self.notebook.index(self.notebook.select()) == 0 else "performance"

    def _start_selected_mode(self) -> None:
        mode = self._selected_mode()
        try:
            command = self._build_command(mode)
        except ValueError as exc:
            messagebox.showerror("Pose2OSC", str(exc))
            return
        if self.process and self.process.poll() is None:
            self._stop_process()
        self._start_process(command, "Set Gesture" if mode == "enroll" else "Performance")

    def _build_command(self, mode: str) -> list[str]:
        command = [sys.executable, str(project_root() / "pose2osc" / "cli.py")]
        if mode == "enroll":
            command.append("enroll")
            command.extend(["--manifest", self.manifest_var.get().strip()])
            if self.generated_var.get():
                command.extend(["--generated", str(self._read_int(self.gesture_count_var, "Gesture count"))])
                command.extend(["--start-index", str(self._read_int(self.start_index_var, "Start index"))])
            else:
                labels = parse_label_text(self.labels_var.get())
                if not labels:
                    raise ValueError("Add at least one gesture label.")
                for label in labels:
                    command.extend(["--label", label])
            command.extend(["--seconds", str(self._read_float(self.seconds_var, "Seconds"))])
            command.extend(["--capture-frames", str(self._read_int(self.capture_frames_var, "Capture frames"))])
            command.extend(["--target-captures", str(self._read_int(self.target_captures_var, "Target captures"))])
            command.extend(["--max-samples", str(self._read_int(self.max_samples_var, "Max samples"))])
            if self.timed_var.get():
                command.append("--timed")
            if self.replace_var.get():
                command.append("--replace")
        else:
            command.append("perform")
            command.extend(["--manifest", self.manifest_var.get().strip()])
            command.extend(["--host", self.host_var.get().strip()])
            command.extend(["--port", str(self._read_int(self.port_var, "OSC port"))])
            command.extend(["--enter-frames", str(self._read_int(self.enter_frames_var, "Enter frames"))])
            command.extend(["--exit-frames", str(self._read_int(self.exit_frames_var, "Exit frames"))])
            command.extend(["--switch-frames", str(self._read_int(self.switch_frames_var, "Switch frames"))])
            if self.split_axes_var.get():
                command.append("--split-axes")
            if not self.landmark_vectors_var.get():
                command.append("--no-landmark-vectors")
            if self.send_unknown_var.get():
                command.append("--send-unknown")

        command.extend(["--camera", str(self._read_int(self.camera_var, "Camera index", minimum=0))])
        command.extend(["--hand", self.hand_var.get()])
        width = self._read_optional_int(self.width_var, "Width")
        height = self._read_optional_int(self.height_var, "Height")
        if width is not None:
            command.extend(["--width", str(width)])
        if height is not None:
            command.extend(["--height", str(height)])
        if not self.correct_handedness_var.get():
            command.append("--no-correct-handedness")
        if not self.preview_var.get():
            command.append("--no-preview")
        return command

    def _start_process(self, command: list[str], label: str) -> None:
        self.log_queue = queue.Queue()
        try:
            root = str(project_root())
            env = os.environ.copy()
            existing_pythonpath = env.get("PYTHONPATH")
            env["PYTHONPATH"] = root if not existing_pythonpath else root + os.pathsep + existing_pythonpath
            env["PYTHONUNBUFFERED"] = "1"
            env["POSE2OSC_PARENT_PID"] = str(os.getpid())
            self.process = subprocess.Popen(command, cwd=root, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        except OSError as exc:
            messagebox.showerror("Pose2OSC", str(exc))
            self.process = None
            return
        self.status_var.set(f"Running {label}")
        self.stop_button.configure(state="normal")
        self._append_log("$ " + " ".join(command) + "\n")
        self.reader_thread = threading.Thread(target=self._read_process_output, args=(self.process,), daemon=True)
        self.reader_thread.start()

    def _read_process_output(self, process: subprocess.Popen[str]) -> None:
        if process.stdout is None:
            return
        for line in process.stdout:
            self.log_queue.put(line)

    def _poll_log_queue(self) -> None:
        while True:
            try:
                line = self.log_queue.get_nowait()
            except queue.Empty:
                break
            self._append_log(line)
        self.after(100, self._poll_log_queue)

    def _poll_process(self) -> None:
        if self.process is not None and self.process.poll() is not None:
            return_code = self.process.returncode
            self.process.wait(timeout=0.1)
            self._append_log(f"Session ended with code {return_code}\n")
            self.process = None
            self.stop_button.configure(state="disabled")
            self.status_var.set("Idle")
            self._refresh_manifest_summary()
            self._refresh_osc_routes()
        self.after(300, self._poll_process)

    def _stop_process(self) -> None:
        if self.process is None or self.process.poll() is not None:
            self.process = None
            self.stop_button.configure(state="disabled")
            self.status_var.set("Idle")
            return
        process = self.process
        return_code = stop_pose2osc_process(process, self._append_log)
        if return_code is not None:
            self._append_log(f"Session ended with code {return_code}\n")
        self.process = None
        self.stop_button.configure(state="disabled")
        self.status_var.set("Idle")
        self._refresh_manifest_summary()
        self._refresh_osc_routes()

    def _append_log(self, text: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", text)
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _refresh_manifest_summary(self) -> None:
        for row in self.manifest_tree.get_children():
            self.manifest_tree.delete(row)
        path = Path(self.manifest_var.get()).expanduser()
        if not path.exists():
            self.summary_var.set("No manifest yet")
            return
        try:
            model = GestureModel.load(path)
        except (OSError, ValueError, KeyError) as exc:
            self.summary_var.set(f"Could not read manifest: {exc}")
            return
        self.summary_var.set(f"{len(model.labels)} labels, {len(model.samples)} samples")
        for label in model.labels:
            metadata = model.label_metadata.get(label, {})
            style = label_style(label, metadata)
            hand_modes = metadata.get("hand_modes") or {}
            hand_text = ", ".join(f"{hand}:{count}" for hand, count in sorted(hand_modes.items()))
            threshold = model.thresholds.get(label)
            threshold_text = "" if threshold is None else f"{threshold:0.3f}"
            self.manifest_tree.insert("", "end", values=(label, style.display_label, metadata.get("sample_count", ""), hand_text, threshold_text))

    def _read_int(self, variable: tk.StringVar, label: str, *, minimum: int | None = 1) -> int:
        text = variable.get().strip()
        try:
            value = int(text)
        except ValueError as exc:
            raise ValueError(f"{label} must be a whole number.") from exc
        if minimum is not None and value < minimum:
            raise ValueError(f"{label} must be at least {minimum}.")
        return value

    def _read_optional_int(self, variable: tk.StringVar, label: str) -> int | None:
        if not variable.get().strip():
            return None
        return self._read_int(variable, label)

    def _read_float(self, variable: tk.StringVar, label: str) -> float:
        text = variable.get().strip()
        try:
            return float(text)
        except ValueError as exc:
            raise ValueError(f"{label} must be a number.") from exc

    def _on_close(self) -> None:
        self._stop_process()
        self.destroy()


def main() -> int:
    app = Pose2OSCApp()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
