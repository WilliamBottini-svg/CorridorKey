"""ConsolePanel — Collapsible log console that captures Python logging output."""

from __future__ import annotations

import logging
import threading
from collections import deque

import customtkinter as ctk


class _GUILogHandler(logging.Handler):
    """Logging handler that pushes records into a deque for the GUI to consume."""

    def __init__(self, maxlen: int = 2000):
        super().__init__()
        self.records: deque[str] = deque(maxlen=maxlen)
        self._callback = None
        self._lock = threading.Lock()

    def set_callback(self, cb):
        self._callback = cb

    def emit(self, record):
        with self._lock:
            try:
                msg = self.format(record)
                self.records.append(msg)
                if self._callback:
                    self._callback(msg)
            except Exception:
                self.handleError(record)


class ConsolePanel(ctk.CTkFrame):
    """Collapsible console panel that shows application log output."""

    def __init__(self, master, colors: dict, **kwargs):
        super().__init__(master, fg_color=colors["bg_mid"], corner_radius=8, **kwargs)
        self._colors = colors
        self._expanded = False

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # Toggle header bar
        self._header = ctk.CTkFrame(self, fg_color="transparent", height=28)
        self._header.grid(row=0, column=0, sticky="ew")
        self._header.grid_columnconfigure(1, weight=1)

        self._toggle_btn = ctk.CTkButton(
            self._header, text="▶ Console", width=100, height=24,
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color="transparent", hover_color=colors["bg_light"],
            text_color=colors["text_dim"], anchor="w",
            command=self.toggle,
        )
        self._toggle_btn.grid(row=0, column=0, padx=8, pady=2, sticky="w")

        self._clear_btn = ctk.CTkButton(
            self._header, text="Clear", width=50, height=20,
            font=ctk.CTkFont(size=10),
            fg_color="transparent", hover_color=colors["bg_light"],
            text_color=colors["text_dim"],
            command=self.clear_log,
        )
        self._clear_btn.grid(row=0, column=1, padx=4, pady=2, sticky="e")

        # Text area (hidden by default)
        self._textbox = ctk.CTkTextbox(
            self, fg_color=colors["bg_dark"],
            text_color=colors["text_dim"],
            font=ctk.CTkFont(family="Courier", size=11),
            height=150, state="disabled",
            scrollbar_button_color=colors["bg_light"],
        )

        # Set up logging handler
        self._handler = _GUILogHandler()
        self._handler.setFormatter(
            logging.Formatter("%(asctime)s  %(levelname)-8s  %(name)s — %(message)s", datefmt="%H:%M:%S")
        )

    def attach_to_root_logger(self):
        """Attach the GUI log handler to the root logger."""
        root = logging.getLogger()
        root.addHandler(self._handler)
        self._handler.set_callback(self._on_log_message)

    def detach_from_root_logger(self):
        """Remove the GUI log handler."""
        root = logging.getLogger()
        root.removeHandler(self._handler)
        self._handler.set_callback(None)

    def toggle(self):
        """Toggle console expanded/collapsed."""
        self._expanded = not self._expanded
        if self._expanded:
            self._textbox.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
            self._toggle_btn.configure(text="▼ Console")
        else:
            self._textbox.grid_remove()
            self._toggle_btn.configure(text="▶ Console")

    def clear_log(self):
        """Clear the console output."""
        self._textbox.configure(state="normal")
        self._textbox.delete("1.0", "end")
        self._textbox.configure(state="disabled")
        self._handler.records.clear()

    def expand(self):
        """Expand the console panel if it is currently collapsed."""
        if not self._expanded:
            self.toggle()

    def _on_log_message(self, msg: str):
        """Called from the logging handler (may be from any thread)."""
        try:
            self._textbox.after(0, lambda: self._append_line(msg))
            # Auto-expand on errors
            if "ERROR" in msg or "CRITICAL" in msg:
                self._textbox.after(0, self.expand)
        except Exception:
            pass

    def _append_line(self, msg: str):
        self._textbox.configure(state="normal")
        self._textbox.insert("end", msg + "\n")
        self._textbox.see("end")
        self._textbox.configure(state="disabled")
