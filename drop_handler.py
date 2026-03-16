"""DropHandler — Enhanced drag-and-drop with visual feedback."""

from __future__ import annotations

import logging
import os
import re

import customtkinter as ctk

logger = logging.getLogger("corridorkey.drop")

# Supported video extensions
VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".mxf", ".webm"}


class DropHandler:
    """Manages drag-and-drop with visual feedback on a target widget."""

    def __init__(self, zone_widget: ctk.CTkFrame, colors: dict, on_drop_paths=None):
        self._zone = zone_widget
        self._colors = colors
        self._on_drop_paths = on_drop_paths
        self._original_border_color = colors.get("border", "#3a3a3a")
        self._overlay_label = None
        self._dnd_available = False

        self._setup_dnd()

    @property
    def is_dnd_available(self) -> bool:
        """Whether drag-and-drop is available (tkinterdnd2 loaded successfully)."""
        return self._dnd_available

    def _setup_dnd(self):
        """Try to register tkinterdnd2 drag-and-drop on the zone."""
        try:
            import tkinterdnd2
            self._zone.drop_target_register(tkinterdnd2.DND_FILES)
            self._zone.dnd_bind("<<DropEnter>>", self._on_drag_enter)
            self._zone.dnd_bind("<<DropLeave>>", self._on_drag_leave)
            self._zone.dnd_bind("<<Drop>>", self._on_drop)
            self._dnd_available = True
            logger.info("DropHandler: tkinterdnd2 drag-and-drop enabled with visual feedback")
        except (ImportError, Exception) as e:
            logger.info(f"DropHandler: tkinterdnd2 not available ({e}), file dialog fallback only")

    def _on_drag_enter(self, event=None):
        """Highlight the drop zone when files are dragged over."""
        try:
            self._zone.configure(border_color=self._colors["green"])
            if self._overlay_label is None:
                self._overlay_label = ctk.CTkLabel(
                    self._zone, text="Drop files here",
                    font=ctk.CTkFont(size=16, weight="bold"),
                    text_color=self._colors["green"],
                    fg_color=self._colors["bg_dark"],
                    corner_radius=8,
                )
            self._overlay_label.place(relx=0.5, rely=0.5, anchor="center")
        except Exception:
            pass

    def _on_drag_leave(self, event=None):
        """Reset the drop zone appearance."""
        try:
            self._zone.configure(border_color=self._original_border_color)
            if self._overlay_label:
                self._overlay_label.place_forget()
        except Exception:
            pass

    def _on_drop(self, event):
        """Handle the drop event, parsing multiple paths."""
        self._on_drag_leave()
        paths = self._parse_drop_data(event.data)
        if paths and self._on_drop_paths:
            self._on_drop_paths(paths)

    @staticmethod
    def _parse_drop_data(raw: str) -> list[str]:
        """Parse tkdnd drop data into a list of file paths."""
        paths = []
        if "{" in raw:
            paths = re.findall(r"\{([^}]+)\}", raw)
            remaining = re.sub(r"\{[^}]+\}", "", raw).strip()
            if remaining:
                paths.extend(remaining.split())
        else:
            paths = raw.split()

        # Filter to existing paths
        return [p for p in paths if os.path.exists(p)]

    @staticmethod
    def filter_video_files(paths: list[str]) -> list[str]:
        """Filter a list of paths to only video files."""
        result = []
        for p in paths:
            if os.path.isfile(p):
                ext = os.path.splitext(p)[1].lower()
                if ext in VIDEO_EXTENSIONS:
                    result.append(p)
            elif os.path.isdir(p):
                result.append(p)
        return result
