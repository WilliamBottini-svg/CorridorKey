"""Notifications — Toast-style notification system for the GUI."""

from __future__ import annotations

import logging
from collections import deque

import customtkinter as ctk

logger = logging.getLogger("corridorkey.notifications")


class _Toast(ctk.CTkFrame):
    """A single toast notification widget."""

    LEVEL_COLORS = {
        "info": "#42a5f5",
        "success": "#00c853",
        "warning": "#ff9800",
        "error": "#ef5350",
    }

    def __init__(self, master, message: str, level: str, colors: dict,
                 on_dismiss=None, **kwargs):
        bg = colors.get("bg_card", "#333333")
        super().__init__(master, fg_color=bg, corner_radius=8, **kwargs)
        self._on_dismiss = on_dismiss

        accent = self.LEVEL_COLORS.get(level, colors.get("text_dim", "#888888"))

        self.grid_columnconfigure(1, weight=1)

        # Color accent bar
        bar = ctk.CTkFrame(self, fg_color=accent, width=4, corner_radius=2)
        bar.grid(row=0, column=0, sticky="ns", padx=(6, 4), pady=6)

        # Message text
        msg_label = ctk.CTkLabel(
            self, text=message,
            font=ctk.CTkFont(size=12),
            text_color=colors.get("text", "#e0e0e0"),
            anchor="w", wraplength=280,
        )
        msg_label.grid(row=0, column=1, padx=(4, 8), pady=8, sticky="w")

        # Close button
        close_btn = ctk.CTkButton(
            self, text="✕", width=20, height=20,
            font=ctk.CTkFont(size=10),
            fg_color="transparent",
            hover_color=colors.get("bg_light", "#2e2e2e"),
            text_color=colors.get("text_dim", "#888888"),
            command=self._dismiss,
        )
        close_btn.grid(row=0, column=2, padx=(0, 6), pady=4)

    def _dismiss(self):
        if self._on_dismiss:
            self._on_dismiss(self)


class NotificationManager:
    """Manages toast notifications in the top-right corner of the app."""

    MAX_VISIBLE = 5
    DEFAULT_DURATION_MS = 5000

    def __init__(self, root_widget, colors: dict):
        self._root = root_widget
        self._colors = colors
        self._toasts: deque[_Toast] = deque()

        # Container frame positioned in top-right
        self._container = ctk.CTkFrame(root_widget, fg_color="transparent")
        self._container.place(relx=1.0, rely=0.0, anchor="ne", x=-20, y=60)

    def notify(self, message: str, level: str = "info", duration_ms: int | None = None):
        """Show a toast notification.

        Args:
            message: The notification text.
            level: One of 'info', 'success', 'warning', 'error'.
            duration_ms: Auto-dismiss time in ms. None uses the default.
        """
        if duration_ms is None:
            duration_ms = self.DEFAULT_DURATION_MS

        toast = _Toast(
            self._container, message=message, level=level,
            colors=self._colors, on_dismiss=self._remove_toast,
        )
        self._toasts.append(toast)

        # Trim old toasts if exceeding max
        while len(self._toasts) > self.MAX_VISIBLE:
            old = self._toasts.popleft()
            old.destroy()

        self._relayout()

        # Auto-dismiss
        if duration_ms > 0:
            toast.after(duration_ms, lambda: self._remove_toast(toast))

        logger.debug(f"Notification [{level}]: {message}")

    def _remove_toast(self, toast: _Toast):
        """Remove a toast from the display."""
        if toast in self._toasts:
            self._toasts.remove(toast)
            toast.destroy()
            self._relayout()

    def _relayout(self):
        """Re-pack all visible toasts."""
        for widget in self._container.winfo_children():
            widget.pack_forget()
        for toast in self._toasts:
            toast.pack(pady=(0, 4), fill="x")

    def clear_all(self):
        """Dismiss all notifications."""
        for toast in list(self._toasts):
            toast.destroy()
        self._toasts.clear()
