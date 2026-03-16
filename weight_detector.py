"""WeightDetector — Automatic model weight detection with status indicator."""

from __future__ import annotations

import logging
import os
import threading

import customtkinter as ctk

logger = logging.getLogger("corridorkey.weights")


class WeightDetector:
    """Monitors the checkpoints directory for model weight files and provides status."""

    WEIGHT_FILENAMES = ("CorridorKey.pth", "CorridorKey_v1.0.pth")

    def __init__(self, base_dir: str, colors: dict):
        self._base_dir = base_dir
        self._colors = colors
        self._ckpt_dir = os.path.join(base_dir, "CorridorKeyModule", "checkpoints")
        self._found = False
        self._weight_path: str | None = None
        self._on_found_callbacks: list = []
        self._on_missing_callbacks: list = []
        self._status_label: ctk.CTkLabel | None = None

    @property
    def found(self) -> bool:
        return self._found

    @property
    def weight_path(self) -> str | None:
        return self._weight_path

    def on_found(self, callback):
        """Register a callback for when weights are found."""
        self._on_found_callbacks.append(callback)

    def on_missing(self, callback):
        """Register a callback for when weights are missing."""
        self._on_missing_callbacks.append(callback)

    def create_indicator(self, master) -> ctk.CTkLabel:
        """Create and return a status indicator label for the top bar."""
        self._status_label = ctk.CTkLabel(
            master, text="⏳ Weights: checking…",
            font=ctk.CTkFont(size=11),
            text_color=self._colors["text_dim"],
        )
        return self._status_label

    def check(self):
        """Check for weight files (call from any thread). Updates status on main thread."""
        self._found = False
        self._weight_path = None

        for fname in self.WEIGHT_FILENAMES:
            path = os.path.join(self._ckpt_dir, fname)
            if os.path.isfile(path):
                self._found = True
                self._weight_path = path
                break

        if self._found:
            self._update_status("✓ Weights: found", self._colors["green"])
            for cb in self._on_found_callbacks:
                cb(self._weight_path)
        else:
            self._update_status("✗ Weights: missing", self._colors["red"])
            for cb in self._on_missing_callbacks:
                cb()

    def check_async(self, root_widget):
        """Run check in a background thread, updating status via root_widget.after()."""
        def _run():
            self.check()
        threading.Thread(target=_run, daemon=True).start()

    def _update_status(self, text: str, color: str):
        if self._status_label:
            try:
                self._status_label.after(0, lambda: self._status_label.configure(
                    text=text, text_color=color,
                ))
            except Exception:
                pass

    def show(self, parent, on_download=None, on_locate=None):
        """Show a dialog for downloading or locating model weights.

        Args:
            parent: Parent widget for the dialog.
            on_download: Callback when user clicks Download.
            on_locate: Callback when user clicks Locate.
        """
        dialog = ctk.CTkToplevel(parent)
        dialog.title("Model Weights")
        dialog.geometry("440x220")
        dialog.resizable(False, False)
        dialog.configure(fg_color=self._colors["bg_dark"])
        dialog.transient(parent)
        dialog.grab_set()

        title = ctk.CTkLabel(
            dialog, text="Model Weights Required",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=self._colors["text_bright"],
        )
        title.pack(pady=(20, 8))

        if self._found:
            status_text = f"Weights found: {os.path.basename(self._weight_path)}"
            status_color = self._colors["green"]
        else:
            status_text = "No model weights found in checkpoints directory."
            status_color = self._colors.get("red", "#ff4444")

        status = ctk.CTkLabel(
            dialog, text=status_text,
            font=ctk.CTkFont(size=12),
            text_color=status_color,
        )
        status.pack(pady=(0, 16))

        btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_frame.pack(pady=(0, 20))

        if on_download:
            dl_btn = ctk.CTkButton(
                btn_frame, text="Download Weights",
                fg_color=self._colors["green"],
                hover_color=self._colors.get("green_hover", self._colors["green"]),
                text_color=self._colors.get("text_bright", "#ffffff"),
                command=lambda: (dialog.destroy(), on_download()),
            )
            dl_btn.pack(side="left", padx=8)

        if on_locate:
            loc_btn = ctk.CTkButton(
                btn_frame, text="Locate on Disk",
                fg_color=self._colors.get("bg_light", "#3a3a3a"),
                hover_color=self._colors.get("bg_card", "#444444"),
                text_color=self._colors.get("text_bright", "#ffffff"),
                command=lambda: (dialog.destroy(), on_locate()),
            )
            loc_btn.pack(side="left", padx=8)

        close_btn = ctk.CTkButton(
            btn_frame, text="Close",
            fg_color=self._colors.get("bg_light", "#3a3a3a"),
            hover_color=self._colors.get("bg_card", "#444444"),
            text_color=self._colors.get("text_dim", "#888888"),
            command=dialog.destroy,
        )
        close_btn.pack(side="left", padx=8)

    def weights_exist(self) -> bool:
        """Compatibility helper matching the old _weights_exist() signature."""
        if self._weight_path is None:
            self.check()
        return self._found

    def weights_path(self) -> str:
        """Compatibility helper matching the old _weights_path() signature."""
        return os.path.join(self._ckpt_dir, "CorridorKey.pth")
