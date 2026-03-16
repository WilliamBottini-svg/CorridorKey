#!/usr/bin/env python3
"""CorridorKey — macOS GUI Application.

A polished native macOS GUI for AI-based green screen keying, wrapping
the backend service layer in backend/service.py.

Requires: customtkinter, tkinter (bundled with Python on macOS).
Optional: tkinterdnd2 for native drag-and-drop support.
"""

from __future__ import annotations

import logging
import os
import platform
import subprocess
import sys
import threading
import time
import traceback
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox

import tkinter as tk

import customtkinter as ctk

# ---------------------------------------------------------------------------
# New component imports
# ---------------------------------------------------------------------------
from preview_panel import PreviewPanel
from console_panel import ConsolePanel
from weight_detector import WeightDetector
from presets_manager import PresetsManager
from drop_handler import DropHandler
from notifications import NotificationManager
from thumbnails import ThumbnailCache
from output_config import OutputConfigPanel

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("corridorkey.gui")

# ---------------------------------------------------------------------------
# Project root (matches backend/service.py logic)
# ---------------------------------------------------------------------------
if getattr(sys, "frozen", False):
    BASE_DIR = sys._MEIPASS
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

sys.path.insert(0, BASE_DIR)

# ---------------------------------------------------------------------------
# Color palette — dark theme with green-screen accent
# ---------------------------------------------------------------------------
CLR_BG_DARK = "#1a1a1a"
CLR_BG_MID = "#242424"
CLR_BG_LIGHT = "#2e2e2e"
CLR_BG_CARD = "#333333"
CLR_TEXT = "#e0e0e0"
CLR_TEXT_DIM = "#888888"
CLR_TEXT_BRIGHT = "#ffffff"
CLR_GREEN = "#00c853"
CLR_GREEN_DIM = "#1b5e20"
CLR_GREEN_HOVER = "#00e676"
CLR_ORANGE = "#ff9800"
CLR_RED = "#ef5350"
CLR_BLUE = "#42a5f5"
CLR_YELLOW = "#fdd835"
CLR_BORDER = "#3a3a3a"

# State badge colors (keyed by internal state name)
STATE_COLORS = {
    "EXTRACTING": CLR_BLUE,
    "RAW": CLR_ORANGE,
    "MASKED": CLR_YELLOW,
    "READY": CLR_GREEN,
    "COMPLETE": CLR_GREEN,
    "ERROR": CLR_RED,
}

# User-friendly display names for clip states
STATE_DISPLAY_NAMES = {
    "EXTRACTING": "LOADED",
    "RAW": "NEEDS HINTS",
    "MASKED": "MASKED",
    "READY": "READY TO KEY",
    "COMPLETE": "DONE ✓",
    "ERROR": "ERROR",
}

# Color dictionary for component modules (they don't import module-level constants)
COLORS_DICT = {
    "bg_dark": CLR_BG_DARK,
    "bg_mid": CLR_BG_MID,
    "bg_light": CLR_BG_LIGHT,
    "bg_card": CLR_BG_CARD,
    "text": CLR_TEXT,
    "text_dim": CLR_TEXT_DIM,
    "text_bright": CLR_TEXT_BRIGHT,
    "green": CLR_GREEN,
    "green_dim": CLR_GREEN_DIM,
    "green_hover": CLR_GREEN_HOVER,
    "orange": CLR_ORANGE,
    "red": CLR_RED,
    "blue": CLR_BLUE,
    "yellow": CLR_YELLOW,
    "border": CLR_BORDER,
}


# ---------------------------------------------------------------------------
# Helper: model weights check
# ---------------------------------------------------------------------------
def _weights_path() -> str:
    return os.path.join(BASE_DIR, "CorridorKeyModule", "checkpoints", "CorridorKey.pth")


def _weights_exist() -> bool:
    return os.path.isfile(_weights_path())


def _download_weights(on_status=None) -> bool:
    """Download CorridorKey model weights from HuggingFace."""
    ckpt_dir = os.path.join(BASE_DIR, "CorridorKeyModule", "checkpoints")
    os.makedirs(ckpt_dir, exist_ok=True)
    try:
        from huggingface_hub import hf_hub_download

        if on_status:
            on_status("Downloading model weights (~300 MB)…")
        # HuggingFace file is CorridorKey_v1.0.pth — download then rename
        hf_hub_download(
            repo_id="nikopueringer/CorridorKey_v1.0",
            filename="CorridorKey_v1.0.pth",
            local_dir=ckpt_dir,
        )
        # Rename to CorridorKey.pth (expected by the inference engine)
        downloaded = os.path.join(ckpt_dir, "CorridorKey_v1.0.pth")
        target = os.path.join(ckpt_dir, "CorridorKey.pth")
        if os.path.isfile(downloaded) and not os.path.isfile(target):
            os.rename(downloaded, target)
        return True
    except Exception as exc:
        logger.error(f"Weight download failed: {exc}")
        return False


# ---------------------------------------------------------------------------
# Scrollable clip list item
# ---------------------------------------------------------------------------
class ClipRow(ctk.CTkFrame):
    """A single row in the clip list showing name, state, frames, and progress."""

    def __init__(self, master, clip, on_remove=None, on_selection_change=None, on_retry=None, on_click=None, **kwargs):
        super().__init__(master, fg_color=CLR_BG_CARD, corner_radius=8, **kwargs)
        self.clip = clip
        self._on_remove = on_remove
        self._on_selection_change = on_selection_change
        self._on_retry = on_retry
        self._on_click = on_click
        self.grid_columnconfigure(1, weight=1)

        # State badge
        state_text = clip.state.value
        display_text = STATE_DISPLAY_NAMES.get(state_text, state_text)
        badge_color = STATE_COLORS.get(state_text, CLR_TEXT_DIM)
        self.badge = ctk.CTkLabel(
            self,
            text=f" {display_text} ",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=CLR_BG_DARK,
            fg_color=badge_color,
            corner_radius=4,
            width=100,
        )
        self.badge.grid(row=0, column=0, padx=(10, 6), pady=8, sticky="w")

        # Clip name
        self.name_label = ctk.CTkLabel(
            self,
            text=clip.name,
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=CLR_TEXT_BRIGHT,
            anchor="w",
        )
        self.name_label.grid(row=0, column=1, padx=(4, 4), pady=(8, 2), sticky="w")

        # Frame info
        frame_text = ""
        if clip.input_asset:
            frame_text = f"{clip.input_asset.frame_count} frames"
            if clip.input_asset.asset_type == "video":
                frame_text += "  (video)"
        self.info_label = ctk.CTkLabel(
            self,
            text=frame_text,
            font=ctk.CTkFont(size=11),
            text_color=CLR_TEXT_DIM,
            anchor="w",
        )
        self.info_label.grid(row=1, column=1, padx=(4, 4), pady=(0, 8), sticky="w")

        # Progress bar (hidden by default)
        self.progress_bar = ctk.CTkProgressBar(
            self,
            progress_color=CLR_GREEN,
            fg_color=CLR_BG_MID,
            height=6,
            corner_radius=3,
        )
        self.progress_bar.set(0)
        self.progress_bar.grid(row=2, column=0, columnspan=5, padx=10, pady=(0, 6), sticky="ew")
        self.progress_bar.grid_remove()

        # Progress label
        self.progress_label = ctk.CTkLabel(
            self,
            text="",
            font=ctk.CTkFont(size=10),
            text_color=CLR_TEXT_DIM,
            anchor="e",
        )
        self.progress_label.grid(row=0, column=2, padx=(4, 4), pady=8, sticky="e")

        # Checkbox for selection
        self.selected_var = ctk.BooleanVar(value=True)
        self.checkbox = ctk.CTkCheckBox(
            self,
            text="",
            variable=self.selected_var,
            width=24,
            checkbox_width=18,
            checkbox_height=18,
            fg_color=CLR_GREEN,
            hover_color=CLR_GREEN_HOVER,
            command=self._on_checkbox_toggle,
        )
        self.checkbox.grid(row=0, column=3, padx=(4, 2), pady=8)

        # Per-clip remove button
        self.remove_btn = ctk.CTkButton(
            self,
            text="✕",
            font=ctk.CTkFont(size=11),
            fg_color="transparent",
            hover_color=CLR_RED,
            text_color=CLR_TEXT_DIM,
            corner_radius=4,
            width=24,
            height=24,
            command=self._remove_self,
        )
        self.remove_btn.grid(row=0, column=4, padx=(0, 8), pady=8)

        # Retry button (shown only on ERROR state)
        self._retry_btn = ctk.CTkButton(
            self,
            text="↻ Retry",
            font=ctk.CTkFont(size=11),
            fg_color=CLR_ORANGE,
            hover_color=CLR_YELLOW,
            text_color=CLR_BG_DARK,
            corner_radius=4,
            width=70,
            height=24,
            command=self._on_retry_click,
        )
        self._retry_btn.grid(row=1, column=4, padx=(0, 8), pady=(0, 4))
        self._retry_btn.grid_remove()

        # Right-click context menu
        self.bind("<Button-2>", self._show_context_menu)
        self.bind("<Button-3>", self._show_context_menu)
        for child in self.winfo_children():
            child.bind("<Button-2>", self._show_context_menu)
            child.bind("<Button-3>", self._show_context_menu)

        # Left-click to select this clip for preview
        self.bind("<Button-1>", self._on_row_click)
        for child in self.winfo_children():
            child.bind("<Button-1>", self._on_row_click)

    def _on_row_click(self, event=None):
        if self._on_click:
            self._on_click(self)

    def _on_checkbox_toggle(self):
        if self._on_selection_change:
            self._on_selection_change()

    def _remove_self(self):
        if self._on_remove:
            self._on_remove(self)

    def _show_context_menu(self, event):
        menu = tk.Menu(self, tearoff=0, bg=CLR_BG_CARD, fg=CLR_TEXT,
                       activebackground=CLR_GREEN, activeforeground=CLR_BG_DARK)
        menu.add_command(label="Remove from list", command=self._remove_self)
        menu.add_command(label="Reveal in Finder", command=self._reveal_in_finder)
        menu.add_command(label="Select only this clip", command=self._select_only_this)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _reveal_in_finder(self):
        path = self.clip.root_path
        if path and os.path.isdir(path):
            if platform.system() == "Darwin":
                subprocess.Popen(["open", path])
            elif platform.system() == "Linux":
                subprocess.Popen(["xdg-open", path])
            else:
                subprocess.Popen(["explorer", path])

    def _select_only_this(self):
        # Deselect all siblings, select only this one
        parent = self.master
        for child in parent.winfo_children():
            if isinstance(child, ClipRow):
                child.selected_var.set(child is self)
        if self._on_selection_change:
            self._on_selection_change()

    def show_progress(self, current: int, total: int):
        self.progress_bar.grid()
        if total > 0:
            self.progress_bar.set(current / total)
            self.progress_label.configure(text=f"{current}/{total}")
        else:
            self.progress_bar.set(0)
            self.progress_label.configure(text="")

    def hide_progress(self):
        self.progress_bar.grid_remove()
        self.progress_label.configure(text="")

    def _on_retry_click(self):
        self.update_state("READY")
        if self._on_retry:
            self._on_retry(self)

    def update_state(self, new_state_text: str):
        display_text = STATE_DISPLAY_NAMES.get(new_state_text, new_state_text)
        badge_color = STATE_COLORS.get(new_state_text, CLR_TEXT_DIM)
        self.badge.configure(text=f" {display_text} ", fg_color=badge_color)
        if new_state_text == "ERROR":
            self._retry_btn.grid()
        else:
            self._retry_btn.grid_remove()


# ---------------------------------------------------------------------------
# Collapsible section widget
# ---------------------------------------------------------------------------
class _CollapsibleSection(ctk.CTkFrame):
    """A section with a clickable header that expands/collapses its content."""

    def __init__(self, master, title: str, expanded: bool = True, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.grid_columnconfigure(0, weight=1)

        self._expanded = expanded

        # Header row
        header = ctk.CTkFrame(self, fg_color=CLR_BG_LIGHT, corner_radius=6)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 2))
        header.grid_columnconfigure(0, weight=1)

        self._chevron_label = ctk.CTkLabel(
            header, text="\u25BC" if expanded else "\u25B6",
            font=ctk.CTkFont(size=10), text_color=CLR_TEXT_DIM,
            width=16,
        )
        self._chevron_label.grid(row=0, column=0, padx=(10, 0), pady=6, sticky="w")

        self._title_label = ctk.CTkLabel(
            header, text=title,
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=CLR_TEXT_BRIGHT,
        )
        self._title_label.grid(row=0, column=0, padx=(28, 8), pady=6, sticky="w")

        # Make header clickable
        for widget in (header, self._chevron_label, self._title_label):
            widget.bind("<Button-1>", self._toggle)
            widget.configure(cursor="hand2")

        # Content frame
        self._content = ctk.CTkFrame(self, fg_color="transparent")
        self._content.grid_columnconfigure(0, weight=1)
        if expanded:
            self._content.grid(row=1, column=0, sticky="ew", padx=4, pady=(0, 4))
        # else: hidden

    @property
    def content(self) -> ctk.CTkFrame:
        return self._content

    def _toggle(self, event=None):
        self._expanded = not self._expanded
        self._chevron_label.configure(text="\u25BC" if self._expanded else "\u25B6")
        if self._expanded:
            self._content.grid(row=1, column=0, sticky="ew", padx=4, pady=(0, 4))
        else:
            self._content.grid_remove()


# ---------------------------------------------------------------------------
# Settings panel
# ---------------------------------------------------------------------------
class SettingsPanel(ctk.CTkFrame):
    """Settings panel with collapsible sections for inference parameters and output config."""

    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color=CLR_BG_MID, corner_radius=10, **kwargs)
        self.grid_columnconfigure(0, weight=1)

        row = 0

        # Header
        header = ctk.CTkLabel(
            self,
            text="Settings",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=CLR_TEXT_BRIGHT,
        )
        header.grid(row=row, column=0, padx=16, pady=(12, 8), sticky="w")
        row += 1

        # ===== Section 1: Inference Parameters (expanded by default) =====
        inference_section = _CollapsibleSection(self, "Inference", expanded=True)
        inference_section.grid(row=row, column=0, padx=8, pady=(0, 2), sticky="ew")
        row += 1
        inf = inference_section.content

        # --- Gamma ---
        ctk.CTkLabel(
            inf, text="Input Gamma", font=ctk.CTkFont(size=12), text_color=CLR_TEXT,
        ).grid(row=0, column=0, padx=8, pady=(6, 2), sticky="w")

        self.gamma_var = ctk.StringVar(value="srgb")
        gamma_frame = ctk.CTkFrame(inf, fg_color="transparent")
        gamma_frame.grid(row=1, column=0, padx=8, pady=(0, 6), sticky="w")
        ctk.CTkRadioButton(
            gamma_frame, text="sRGB", variable=self.gamma_var, value="srgb",
            font=ctk.CTkFont(size=11), text_color=CLR_TEXT, fg_color=CLR_GREEN,
            hover_color=CLR_GREEN_HOVER,
        ).pack(side="left", padx=(0, 12))
        ctk.CTkRadioButton(
            gamma_frame, text="Linear", variable=self.gamma_var, value="linear",
            font=ctk.CTkFont(size=11), text_color=CLR_TEXT, fg_color=CLR_GREEN,
            hover_color=CLR_GREEN_HOVER,
        ).pack(side="left")

        # --- Despill Strength ---
        ctk.CTkLabel(
            inf, text="Despill Strength", font=ctk.CTkFont(size=12), text_color=CLR_TEXT,
        ).grid(row=2, column=0, padx=8, pady=(6, 2), sticky="w")

        self.despill_var = ctk.DoubleVar(value=1.0)
        despill_frame = ctk.CTkFrame(inf, fg_color="transparent")
        despill_frame.grid(row=3, column=0, padx=8, pady=(0, 2), sticky="ew")
        despill_frame.grid_columnconfigure(0, weight=1)
        self.despill_slider = ctk.CTkSlider(
            despill_frame, from_=0.0, to=1.0, variable=self.despill_var,
            button_color=CLR_GREEN, button_hover_color=CLR_GREEN_HOVER,
            progress_color=CLR_GREEN_DIM, fg_color=CLR_BG_LIGHT,
            command=self._on_despill_change,
        )
        self.despill_slider.grid(row=0, column=0, padx=(0, 8), sticky="ew")
        self.despill_value_label = ctk.CTkLabel(
            despill_frame, text="1.00", font=ctk.CTkFont(size=11), text_color=CLR_TEXT_DIM, width=36,
        )
        self.despill_value_label.grid(row=0, column=1)

        self.despill_desc_label = ctk.CTkLabel(
            inf, text="Full green removal",
            font=ctk.CTkFont(size=10, slant="italic"), text_color=CLR_TEXT_DIM,
        )
        self.despill_desc_label.grid(row=4, column=0, padx=8, pady=(0, 4), sticky="w")

        # --- Auto-Despeckle ---
        self.despeckle_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            inf, text="Auto-Despeckle", variable=self.despeckle_var,
            font=ctk.CTkFont(size=12), text_color=CLR_TEXT,
            fg_color=CLR_GREEN, hover_color=CLR_GREEN_HOVER,
            command=self._on_despeckle_toggle,
        ).grid(row=5, column=0, padx=8, pady=(6, 2), sticky="w")

        despeckle_size_frame = ctk.CTkFrame(inf, fg_color="transparent")
        despeckle_size_frame.grid(row=6, column=0, padx=8, pady=(0, 6), sticky="w")
        ctk.CTkLabel(
            despeckle_size_frame, text="Size threshold:", font=ctk.CTkFont(size=11), text_color=CLR_TEXT_DIM,
        ).pack(side="left", padx=(0, 6))
        self.despeckle_size_var = ctk.StringVar(value="400")
        self.despeckle_size_entry = ctk.CTkEntry(
            despeckle_size_frame, textvariable=self.despeckle_size_var, width=60,
            font=ctk.CTkFont(size=11), fg_color=CLR_BG_LIGHT, border_color=CLR_BORDER,
            text_color=CLR_TEXT,
        )
        self.despeckle_size_entry.pack(side="left")

        # --- Refiner Scale ---
        ctk.CTkLabel(
            inf, text="Refiner Scale", font=ctk.CTkFont(size=12), text_color=CLR_TEXT,
        ).grid(row=7, column=0, padx=8, pady=(6, 2), sticky="w")

        self.refiner_var = ctk.DoubleVar(value=1.0)
        refiner_frame = ctk.CTkFrame(inf, fg_color="transparent")
        refiner_frame.grid(row=8, column=0, padx=8, pady=(0, 2), sticky="ew")
        refiner_frame.grid_columnconfigure(0, weight=1)
        self.refiner_slider = ctk.CTkSlider(
            refiner_frame, from_=0.5, to=2.0, variable=self.refiner_var,
            button_color=CLR_GREEN, button_hover_color=CLR_GREEN_HOVER,
            progress_color=CLR_GREEN_DIM, fg_color=CLR_BG_LIGHT,
            command=self._on_refiner_change,
        )
        self.refiner_slider.grid(row=0, column=0, padx=(0, 8), sticky="ew")
        self.refiner_value_label = ctk.CTkLabel(
            refiner_frame, text="1.00", font=ctk.CTkFont(size=11), text_color=CLR_TEXT_DIM, width=36,
        )
        self.refiner_value_label.grid(row=0, column=1)

        self.refiner_desc_label = ctk.CTkLabel(
            inf, text="Balanced edge detail",
            font=ctk.CTkFont(size=10, slant="italic"), text_color=CLR_TEXT_DIM,
        )
        self.refiner_desc_label.grid(row=9, column=0, padx=8, pady=(0, 4), sticky="w")

        # ===== Section 2: Output Formats (collapsed by default) =====
        output_section = _CollapsibleSection(self, "Output Formats", expanded=False)
        output_section.grid(row=row, column=0, padx=8, pady=(0, 2), sticky="ew")
        row += 1
        out = output_section.content

        self.output_vars = {}
        self.format_vars = {}
        for i, (output_name, default_fmt) in enumerate([("FG", "exr"), ("Matte", "exr"), ("Comp", "png"), ("Processed", "exr")]):
            oframe = ctk.CTkFrame(out, fg_color="transparent")
            oframe.grid(row=i, column=0, padx=8, pady=2, sticky="ew")
            oframe.grid_columnconfigure(1, weight=1)

            var = ctk.BooleanVar(value=True)
            self.output_vars[output_name.lower()] = var
            ctk.CTkCheckBox(
                oframe, text=output_name, variable=var,
                font=ctk.CTkFont(size=11), text_color=CLR_TEXT,
                fg_color=CLR_GREEN, hover_color=CLR_GREEN_HOVER,
                width=24, checkbox_width=16, checkbox_height=16,
            ).grid(row=0, column=0, sticky="w")

            fmt_var = ctk.StringVar(value=default_fmt)
            self.format_vars[output_name.lower()] = fmt_var
            ctk.CTkSegmentedButton(
                oframe, values=["exr", "png"], variable=fmt_var,
                font=ctk.CTkFont(size=10),
                selected_color=CLR_GREEN, selected_hover_color=CLR_GREEN_HOVER,
                unselected_color=CLR_BG_LIGHT, unselected_hover_color=CLR_BG_CARD,
                text_color=CLR_TEXT_BRIGHT, text_color_disabled=CLR_TEXT_DIM,
                height=24,
            ).grid(row=0, column=1, padx=(8, 0), sticky="e")

        # ===== Section 3: Backend (collapsed by default) =====
        backend_section = _CollapsibleSection(self, "Backend", expanded=False)
        backend_section.grid(row=row, column=0, padx=8, pady=(0, 8), sticky="ew")
        row += 1
        bk = backend_section.content

        self.backend_var = ctk.StringVar(value="Auto")
        ctk.CTkSegmentedButton(
            bk, values=["Auto", "Torch", "MLX"], variable=self.backend_var,
            font=ctk.CTkFont(size=11),
            selected_color=CLR_GREEN, selected_hover_color=CLR_GREEN_HOVER,
            unselected_color=CLR_BG_LIGHT, unselected_hover_color=CLR_BG_CARD,
            text_color=CLR_TEXT_BRIGHT, text_color_disabled=CLR_TEXT_DIM,
        ).grid(row=0, column=0, padx=8, pady=(4, 8), sticky="ew")

    def _on_despill_change(self, value):
        self.despill_value_label.configure(text=f"{value:.2f}")
        if value < 0.05:
            desc = "No green removal"
        elif value < 0.4:
            desc = "Light green removal"
        elif value < 0.7:
            desc = "Moderate green removal"
        else:
            desc = "Full green removal"
        self.despill_desc_label.configure(text=desc)

    def _on_refiner_change(self, value):
        self.refiner_value_label.configure(text=f"{value:.2f}")
        if value < 0.8:
            desc = "Softer edges"
        elif value < 1.3:
            desc = "Balanced edge detail"
        else:
            desc = "Enhanced edge detail (slower)"
        self.refiner_desc_label.configure(text=desc)

    def _on_despeckle_toggle(self):
        state = "normal" if self.despeckle_var.get() else "disabled"
        self.despeckle_size_entry.configure(state=state)

    def get_inference_params(self):
        from backend.service import InferenceParams

        try:
            despeckle_size = int(self.despeckle_size_var.get())
        except ValueError:
            despeckle_size = 400
        return InferenceParams(
            input_is_linear=(self.gamma_var.get() == "linear"),
            despill_strength=self.despill_var.get(),
            auto_despeckle=self.despeckle_var.get(),
            despeckle_size=despeckle_size,
            refiner_scale=self.refiner_var.get(),
        )

    def get_output_config(self):
        from backend.service import OutputConfig

        return OutputConfig(
            fg_enabled=self.output_vars["fg"].get(),
            fg_format=self.format_vars["fg"].get(),
            matte_enabled=self.output_vars["matte"].get(),
            matte_format=self.format_vars["matte"].get(),
            comp_enabled=self.output_vars["comp"].get(),
            comp_format=self.format_vars["comp"].get(),
            processed_enabled=self.output_vars["processed"].get(),
            processed_format=self.format_vars["processed"].get(),
        )


# ---------------------------------------------------------------------------
# Frame range selector (preview renders)
# ---------------------------------------------------------------------------
class FrameRangeSelector(ctk.CTkFrame):
    """Segmented control for choosing All Frames / Preview (2 s) / Custom range."""

    MODES = ("All Frames", "Preview (2s)", "Custom")

    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)

        self._mode_var = tk.StringVar(value=self.MODES[0])
        self._fps = 24.0  # updated externally when clips are loaded

        # Segmented button row
        seg = ctk.CTkSegmentedButton(
            self,
            values=list(self.MODES),
            variable=self._mode_var,
            command=self._on_mode_changed,
            font=ctk.CTkFont(size=11),
            fg_color=CLR_BG_CARD,
            selected_color=CLR_GREEN_DIM,
            selected_hover_color=CLR_GREEN,
            unselected_color=CLR_BG_CARD,
            unselected_hover_color=CLR_BG_LIGHT,
            text_color=CLR_TEXT,
        )
        seg.pack(side="left", padx=(0, 8))

        # Custom start/end entries (hidden by default)
        self._custom_frame = ctk.CTkFrame(self, fg_color="transparent")

        ctk.CTkLabel(
            self._custom_frame, text="Start:", font=ctk.CTkFont(size=11),
            text_color=CLR_TEXT_DIM,
        ).pack(side="left", padx=(0, 2))
        self._start_entry = ctk.CTkEntry(
            self._custom_frame, width=60, height=26,
            font=ctk.CTkFont(size=11),
            fg_color=CLR_BG_CARD, text_color=CLR_TEXT,
        )
        self._start_entry.insert(0, "0")
        self._start_entry.pack(side="left", padx=(0, 6))

        ctk.CTkLabel(
            self._custom_frame, text="End:", font=ctk.CTkFont(size=11),
            text_color=CLR_TEXT_DIM,
        ).pack(side="left", padx=(0, 2))
        self._end_entry = ctk.CTkEntry(
            self._custom_frame, width=60, height=26,
            font=ctk.CTkFont(size=11),
            fg_color=CLR_BG_CARD, text_color=CLR_TEXT,
        )
        self._end_entry.insert(0, "48")
        self._end_entry.pack(side="left", padx=(0, 6))

        # Info label (frame count / duration)
        self._info_label = ctk.CTkLabel(
            self, text="", font=ctk.CTkFont(size=10, slant="italic"),
            text_color=CLR_TEXT_DIM,
        )
        self._info_label.pack(side="left", padx=(4, 0))

        self._on_mode_changed(self.MODES[0])

    def set_fps(self, fps: float):
        self._fps = fps if fps > 0 else 24.0

    def _on_mode_changed(self, mode: str):
        if mode == "Custom":
            self._custom_frame.pack(side="left", padx=(0, 4))
        else:
            self._custom_frame.pack_forget()
        self._update_info()

    def _update_info(self):
        rng = self.get_frame_range()
        if rng is None:
            self._info_label.configure(text="all frames")
        else:
            start, end = rng
            count = max(end - start, 0)
            dur = count / self._fps if self._fps else 0
            self._info_label.configure(text=f"{count} frames ({dur:.1f}s)")

    def get_frame_range(self) -> tuple[int, int] | None:
        """Return (start, end) frame indices, or None for all frames."""
        mode = self._mode_var.get()
        if mode == self.MODES[0]:  # All Frames
            return None
        if mode == self.MODES[1]:  # Preview (2s)
            count = int(self._fps * 2)
            return (0, count)
        # Custom
        try:
            start = int(self._start_entry.get())
        except ValueError:
            start = 0
        try:
            end = int(self._end_entry.get())
        except ValueError:
            end = start + int(self._fps * 2)
        return (max(start, 0), max(end, start))


# ---------------------------------------------------------------------------
# Main application window
# ---------------------------------------------------------------------------
class CorridorKeyApp(ctk.CTk):
    """Main application window."""

    def __init__(self):
        super().__init__()

        # Window setup
        self.title("CorridorKey")
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        win_w = min(max(int(screen_w * 0.75), 1100), 1800)
        win_h = min(max(int(screen_h * 0.75), 780), 1200)
        self.geometry(f"{win_w}x{win_h}")
        self.minsize(900, 600)
        self.configure(fg_color=CLR_BG_DARK)

        # Set window icon (shows in Dock / title bar on macOS)
        icon_path = os.path.join(BASE_DIR, "assets", "icon.png")
        if os.path.isfile(icon_path):
            try:
                from PIL import Image, ImageTk
                icon_img = Image.open(icon_path).resize((128, 128), Image.LANCZOS)
                self._app_icon = ImageTk.PhotoImage(icon_img)
                self.iconphoto(True, self._app_icon)
            except Exception:
                pass  # Non-critical — icon just won't show

        # State
        self._service = None
        self._clips: list = []
        self._clip_rows: list[ClipRow] = []
        self._working = False
        self._cancel_flag = threading.Event()
        self._worker_thread: threading.Thread | None = None
        self._device_str = "detecting…"
        self._clips_dir: str | None = None
        self._start_time: float = 0

        # --- New component instances ---
        self._weight_detector = WeightDetector(BASE_DIR, COLORS_DICT)
        self._thumbnail_cache = ThumbnailCache(
            os.path.join(os.path.expanduser("~"), ".corridorkey", "thumbnails")
        )
        self._notification_mgr: NotificationManager | None = None

        # Layout
        self._build_ui()

        # Keyboard shortcuts
        self._bind_shortcuts()

        # Attach console log handler after UI is built
        self._console_panel.attach_to_root_logger()

        # Graceful window-close handling
        self.protocol("WM_DELETE_WINDOW", self._on_quit)

        # Check weights on startup
        self.after(300, self._startup_checks)

    # ----- UI Construction -----

    def _build_ui(self):
        # Rows: 0=top bar, 1=drop zone, 2=workdir label, 3=clip toolbar,
        #        4=workflow stepper, 5=next-action banner, 6=content,
        #        7=console, 8=bottom bar
        self.grid_rowconfigure(6, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # === Menu bar ===
        self._build_menu_bar()

        # === Top bar ===
        self._build_top_bar()

        # === Drop zone ===
        self._build_drop_zone()

        # === Working directory display ===
        self._build_workdir_display()

        # === Clip list toolbar ===
        self._build_clip_toolbar()

        # === Workflow stepper (3-step indicator) ===
        self._build_workflow_stepper()

        # === Next-action banner ===
        self._build_next_action_banner()

        # === Main content area (clip list + preview + settings) ===
        content = ctk.CTkFrame(self, fg_color="transparent")
        content.grid(row=6, column=0, sticky="nsew", padx=0, pady=0)
        content.grid_rowconfigure(0, weight=1)
        content.grid_columnconfigure(0, weight=1)   # clip list ~25%
        content.grid_columnconfigure(1, weight=2)   # preview ~50%
        content.grid_columnconfigure(2, weight=1, minsize=280)  # settings ~25%

        # Clip list (scrollable) — left pane
        self._clip_list_frame = ctk.CTkScrollableFrame(
            content,
            fg_color=CLR_BG_DARK,
            scrollbar_button_color=CLR_BG_LIGHT,
            scrollbar_button_hover_color=CLR_BG_CARD,
        )
        self._clip_list_frame.grid(row=0, column=0, sticky="nsew", padx=(16, 4), pady=(0, 8))
        self._clip_list_frame.grid_columnconfigure(0, weight=1)

        # Empty state label
        self._empty_label = ctk.CTkLabel(
            self._clip_list_frame,
            text="No clips loaded.\nDrop footage above or click Browse.",
            font=ctk.CTkFont(size=13),
            text_color=CLR_TEXT_DIM,
        )
        self._empty_label.grid(row=0, column=0, pady=40)

        # Preview panel — center pane
        self._preview_panel = PreviewPanel(content, colors=COLORS_DICT)
        self._preview_panel.grid(row=0, column=1, sticky="nsew", padx=4, pady=(0, 8))

        # Settings + output config — right pane
        right_pane = ctk.CTkScrollableFrame(
            content,
            fg_color=CLR_BG_DARK,
            scrollbar_button_color=CLR_BG_LIGHT,
            scrollbar_button_hover_color=CLR_BG_CARD,
        )
        right_pane.grid(row=0, column=2, sticky="nsew", padx=(4, 16), pady=(0, 8))
        right_pane.grid_columnconfigure(0, weight=1)

        self._settings_panel = SettingsPanel(right_pane)
        self._settings_panel.grid(row=0, column=0, sticky="ew", pady=(0, 8))

        self._output_config = OutputConfigPanel(right_pane, colors=COLORS_DICT)
        self._output_config.grid(row=1, column=0, sticky="ew", pady=(0, 8))

        # Presets manager
        self._presets_mgr = PresetsManager(
            right_pane, presets_dir=self._presets_dir, colors=COLORS_DICT,
        )
        self._presets_mgr.grid(row=2, column=0, sticky="ew")
        self._presets_mgr.connect_settings(self._settings_panel)

        # === Console panel ===
        self._console_panel = ConsolePanel(self, colors=COLORS_DICT)
        self._console_panel.grid(row=7, column=0, sticky="ew", padx=16, pady=(0, 4))

        # === Bottom bar ===
        self._build_bottom_bar()

    def _build_top_bar(self):
        top_bar = ctk.CTkFrame(self, fg_color=CLR_BG_MID, corner_radius=0, height=44)
        top_bar.grid(row=0, column=0, sticky="ew")
        top_bar.grid_columnconfigure(1, weight=1)
        top_bar.grid_propagate(False)

        # Logo / app name
        logo_lbl = ctk.CTkLabel(
            top_bar,
            text="  CorridorKey",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=CLR_GREEN,
        )
        logo_lbl.grid(row=0, column=0, padx=(16, 8), sticky="w")

        # Device / status label (center)
        self._status_label = ctk.CTkLabel(
            top_bar,
            text="",
            font=ctk.CTkFont(size=11),
            text_color=CLR_TEXT_DIM,
        )
        self._status_label.grid(row=0, column=1, sticky="")

        # Right-side controls — compact icon buttons only
        right_controls = ctk.CTkFrame(top_bar, fg_color="transparent")
        right_controls.grid(row=0, column=2, padx=(8, 12), sticky="e")

        # Notification bell
        self._notif_btn = ctk.CTkButton(
            right_controls,
            text="\U0001f514",
            font=ctk.CTkFont(size=14),
            width=32,
            height=32,
            fg_color="transparent",
            hover_color=CLR_BG_CARD,
            corner_radius=8,
            command=self._toggle_notification_panel,
        )
        self._notif_btn.pack(side="left", padx=(0, 4))

        # Settings gear button
        gear_btn = ctk.CTkButton(
            right_controls,
            text="\u2699",
            font=ctk.CTkFont(size=16),
            width=32,
            height=32,
            fg_color="transparent",
            hover_color=CLR_BG_CARD,
            corner_radius=8,
            command=self._open_preferences,
        )
        gear_btn.pack(side="left")

        # Presets manager — placed in settings pane instead, create reference for later
        _presets_dir = os.path.join(os.path.expanduser("~"), "Documents", "CorridorKey", "Presets")
        self._presets_dir = _presets_dir

    def _build_drop_zone(self):
        """Build the drag-and-drop zone at the top of the window."""
        drop_frame = ctk.CTkFrame(
            self,
            fg_color=CLR_BG_MID,
            corner_radius=12,
            border_width=2,
            border_color=CLR_BORDER,
            height=90,
        )
        drop_frame.grid(row=1, column=0, sticky="ew", padx=16, pady=(8, 4))
        drop_frame.grid_propagate(False)
        drop_frame.grid_columnconfigure(0, weight=1)
        drop_frame.grid_rowconfigure(0, weight=1)

        self._drop_label = ctk.CTkLabel(
            drop_frame,
            text="⬇  Drop image sequences or video files here  ⬇",
            font=ctk.CTkFont(size=14),
            text_color=CLR_TEXT_DIM,
        )
        self._drop_label.grid(row=0, column=0, sticky="")

        # Attach drag-and-drop handler to drop zone frame
        self._drop_handler = DropHandler(drop_frame, COLORS_DICT, self._on_drop)

        # Adjust drop zone text based on drag-and-drop availability
        if not self._drop_handler.is_dnd_available:
            self._drop_label.configure(text="Click Browse to add image sequences or video files")

    def _build_workdir_display(self):
        workdir_frame = ctk.CTkFrame(self, fg_color="transparent")
        workdir_frame.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 2))
        workdir_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            workdir_frame,
            text="Working dir:",
            font=ctk.CTkFont(size=11),
            text_color=CLR_TEXT_DIM,
        ).grid(row=0, column=0, sticky="w")

        self._workdir_label = ctk.CTkLabel(
            workdir_frame,
            text="(not set)",
            font=ctk.CTkFont(size=11),
            text_color=CLR_TEXT,
            anchor="w",
        )
        self._workdir_label.grid(row=0, column=1, padx=(6, 0), sticky="ew")

        ctk.CTkButton(
            workdir_frame,
            text="Change…",
            font=ctk.CTkFont(size=10),
            fg_color="transparent",
            hover_color=CLR_BG_CARD,
            text_color=CLR_BLUE,
            width=60,
            height=20,
            command=self._choose_work_dir,
        ).grid(row=0, column=2, padx=(4, 0), sticky="e")

    def _build_clip_toolbar(self):
        toolbar = ctk.CTkFrame(self, fg_color="transparent")
        toolbar.grid(row=3, column=0, sticky="ew", padx=16, pady=(4, 2))

        # Browse button
        browse_btn = ctk.CTkButton(
            toolbar,
            text="Browse…",
            font=ctk.CTkFont(size=12),
            fg_color=CLR_BG_CARD,
            hover_color=CLR_BG_LIGHT,
            text_color=CLR_TEXT,
            corner_radius=8,
            height=32,
            width=90,
            command=self._browse_clips,
        )
        browse_btn.pack(side="left", padx=(0, 6))

        # Clear all
        clear_btn = ctk.CTkButton(
            toolbar,
            text="Clear All",
            font=ctk.CTkFont(size=12),
            fg_color="transparent",
            hover_color=CLR_BG_CARD,
            text_color=CLR_TEXT_DIM,
            corner_radius=8,
            height=32,
            width=80,
            command=self._clear_clips,
        )
        clear_btn.pack(side="left", padx=(0, 6))

        # Select all / deselect all
        sel_all_btn = ctk.CTkButton(
            toolbar,
            text="Select All",
            font=ctk.CTkFont(size=11),
            fg_color="transparent",
            hover_color=CLR_BG_CARD,
            text_color=CLR_TEXT_DIM,
            corner_radius=8,
            height=28,
            width=76,
            command=self._select_all_clips,
        )
        sel_all_btn.pack(side="left", padx=(0, 2))

        desel_all_btn = ctk.CTkButton(
            toolbar,
            text="Deselect All",
            font=ctk.CTkFont(size=11),
            fg_color="transparent",
            hover_color=CLR_BG_CARD,
            text_color=CLR_TEXT_DIM,
            corner_radius=8,
            height=28,
            width=90,
            command=self._deselect_all_clips,
        )
        desel_all_btn.pack(side="left", padx=(0, 6))

        # Clip count label
        self._clip_count_label = ctk.CTkLabel(
            toolbar,
            text="0 clips",
            font=ctk.CTkFont(size=11),
            text_color=CLR_TEXT_DIM,
        )
        self._clip_count_label.pack(side="left", padx=(4, 0))

        # Frame range selector (right-aligned)
        self._frame_range_selector = FrameRangeSelector(toolbar)
        self._frame_range_selector.pack(side="right", padx=(0, 0))

    def _build_workflow_stepper(self):
        """3-step indicator: Load → Set Hints → Key."""
        stepper = ctk.CTkFrame(self, fg_color="transparent")
        stepper.grid(row=4, column=0, sticky="ew", padx=16, pady=(4, 2))

        steps = [
            ("1", "Load Clips"),
            ("2", "Set Hints"),
            ("3", "Run Keying"),
        ]
        self._step_labels: list[ctk.CTkLabel] = []

        for i, (num, label) in enumerate(steps):
            step_frame = ctk.CTkFrame(stepper, fg_color="transparent")
            step_frame.pack(side="left", padx=(0, 12))

            num_lbl = ctk.CTkLabel(
                step_frame,
                text=num,
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color=CLR_BG_DARK,
                fg_color=CLR_TEXT_DIM,
                corner_radius=10,
                width=22,
                height=22,
            )
            num_lbl.pack(side="left", padx=(0, 4))

            lbl = ctk.CTkLabel(
                step_frame,
                text=label,
                font=ctk.CTkFont(size=12),
                text_color=CLR_TEXT_DIM,
            )
            lbl.pack(side="left")
            self._step_labels.append((num_lbl, lbl))

            if i < len(steps) - 1:
                ctk.CTkLabel(
                    stepper, text="›",
                    font=ctk.CTkFont(size=14), text_color=CLR_TEXT_DIM,
                ).pack(side="left", padx=(0, 12))

    def _build_next_action_banner(self):
        """A highlighted banner prompting the user for the next action."""
        self._next_action_frame = ctk.CTkFrame(
            self, fg_color=CLR_GREEN_DIM, corner_radius=8,
        )
        self._next_action_frame.grid(row=5, column=0, sticky="ew", padx=16, pady=(2, 4))
        self._next_action_frame.grid_columnconfigure(0, weight=1)

        self._next_action_label = ctk.CTkLabel(
            self._next_action_frame,
            text="→ Drop or Browse to load image sequences / video clips",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=CLR_GREEN,
            anchor="w",
        )
        self._next_action_label.grid(row=0, column=0, padx=14, pady=6, sticky="w")

    def _build_bottom_bar(self):
        bottom_bar = ctk.CTkFrame(self, fg_color=CLR_BG_MID, corner_radius=0, height=56)
        bottom_bar.grid(row=8, column=0, sticky="ew")
        bottom_bar.grid_columnconfigure(1, weight=1)
        bottom_bar.grid_propagate(False)

        # Run button
        self._run_btn = ctk.CTkButton(
            bottom_bar,
            text="▶  Run Keying",
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color=CLR_GREEN,
            hover_color=CLR_GREEN_HOVER,
            text_color=CLR_BG_DARK,
            corner_radius=10,
            height=40,
            width=160,
            command=self._start_keying,
        )
        self._run_btn.grid(row=0, column=0, padx=(16, 8), pady=8)

        # Cancel button
        self._cancel_btn = ctk.CTkButton(
            bottom_bar,
            text="◼  Cancel",
            font=ctk.CTkFont(size=13),
            fg_color=CLR_RED,
            hover_color="#c62828",
            text_color=CLR_TEXT_BRIGHT,
            corner_radius=10,
            height=40,
            width=120,
            command=self._cancel_keying,
            state="disabled",
        )
        self._cancel_btn.grid(row=0, column=1, padx=(0, 8), pady=8, sticky="w")

        # Timer label
        self._timer_label = ctk.CTkLabel(
            bottom_bar,
            text="",
            font=ctk.CTkFont(size=11),
            text_color=CLR_TEXT_DIM,
        )
        self._timer_label.grid(row=0, column=1, pady=8, sticky="e", padx=(0, 16))

        # Overall progress bar
        self._progress_bar = ctk.CTkProgressBar(
            bottom_bar,
            progress_color=CLR_GREEN,
            fg_color=CLR_BG_LIGHT,
            height=6,
            corner_radius=3,
        )
        self._progress_bar.set(0)
        self._progress_bar.grid(row=1, column=0, columnspan=3, padx=16, pady=(0, 8), sticky="ew")
        self._progress_bar.grid_remove()

    def _build_menu_bar(self):
        menubar = tk.Menu(self)

        # App menu (macOS shows this as the app name)
        app_menu = tk.Menu(menubar, tearoff=0)
        app_menu.add_command(label="About CorridorKey", command=self._show_about)
        app_menu.add_separator()
        app_menu.add_command(label="Quit CorridorKey", command=self._on_quit, accelerator="Cmd+Q")
        menubar.add_cascade(label="CorridorKey", menu=app_menu)

        # File menu
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Open Files\u2026", command=self._browse_clips, accelerator="Cmd+O")
        file_menu.add_command(label="Choose Working Directory\u2026", command=self._choose_work_dir)
        file_menu.add_separator()
        file_menu.add_command(label="Clear All Clips", command=self._clear_clips)
        menubar.add_cascade(label="File", menu=file_menu)

        # Process menu
        process_menu = tk.Menu(menubar, tearoff=0)
        process_menu.add_command(label="Run Keying", command=self._start_keying, accelerator="Cmd+Return")
        process_menu.add_command(label="Cancel", command=self._cancel_keying, accelerator="Escape")
        menubar.add_cascade(label="Process", menu=process_menu)

        # View menu
        view_menu = tk.Menu(menubar, tearoff=0)
        view_menu.add_command(label="Toggle Console", command=lambda: self._console_panel.toggle(), accelerator="Cmd+L")
        menubar.add_cascade(label="View", menu=view_menu)

        # Help menu
        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="CorridorKey Help", command=self._show_help)
        help_menu.add_command(label="GitHub Repository", command=lambda: webbrowser.open("https://github.com/nikopueringer/CorridorKey"))
        menubar.add_cascade(label="Help", menu=help_menu)

        self.config(menu=menubar)

    def _show_about(self):
        about_win = ctk.CTkToplevel(self)
        about_win.title("About CorridorKey")
        about_win.geometry("360x220")
        about_win.configure(fg_color=CLR_BG_DARK)
        about_win.grab_set()
        about_win.resizable(False, False)

        ctk.CTkLabel(
            about_win, text="CorridorKey",
            font=ctk.CTkFont(size=20, weight="bold"), text_color=CLR_GREEN,
        ).pack(pady=(24, 4))
        ctk.CTkLabel(
            about_win, text="Version 1.0.0",
            font=ctk.CTkFont(size=12), text_color=CLR_TEXT_DIM,
        ).pack(pady=(0, 8))
        ctk.CTkLabel(
            about_win, text="AI-powered green screen keying\nfor professional VFX workflows",
            font=ctk.CTkFont(size=12), text_color=CLR_TEXT, justify="center",
        ).pack(pady=(0, 16))
        ctk.CTkButton(
            about_win, text="OK", command=about_win.destroy,
            fg_color=CLR_BG_CARD, hover_color=CLR_BG_LIGHT, width=80,
        ).pack(pady=(0, 16))

    def _show_help(self):
        webbrowser.open("https://github.com/nikopueringer/CorridorKey#readme")

    # ----- Keyboard shortcuts -----

    def _bind_shortcuts(self):
        self.bind("<Command-o>", lambda e: self._browse_clips())
        self.bind("<Command-Return>", lambda e: self._start_keying())
        self.bind("<Escape>", lambda e: self._cancel_keying())
        self.bind("<Command-a>", lambda e: self._select_all_clips())
        self.bind("<Command-d>", lambda e: self._deselect_all_clips())
        self.bind("<Command-Delete>", lambda e: self._clear_clips())
        self.bind("<Command-l>", lambda e: self._console_panel.toggle())

    # ----- Startup -----

    def _startup_checks(self):
        """Run startup checks: onboarding (first launch), then weights + device."""
        # Onboarding — first launch only (Apple HIG: show once, skippable)
        onboarding_marker = os.path.join(
            os.path.expanduser("~"), ".corridorkey", "onboarding_complete"
        )
        if not os.path.isfile(onboarding_marker):
            try:
                from onboarding import OnboardingFlow
                flow = OnboardingFlow(self, BASE_DIR)
                flow.show()
            except ImportError:
                logger.info("Onboarding module not found, skipping onboarding")

        # Weights check
        if not _weights_exist():
            self._weight_detector.show(
                parent=self,
                on_download=self._do_download_weights,
                on_locate=self._do_locate_weights,
            )
        else:
            self._detect_device_async()

    def _detect_device_async(self):
        def _detect():
            try:
                import torch
                if torch.backends.mps.is_available():
                    device = "Apple MPS"
                elif torch.cuda.is_available():
                    device = f"CUDA ({torch.cuda.get_device_name(0)})"
                else:
                    device = "CPU"
            except Exception:
                device = "Unknown"
            self._device_str = device
            self.after(0, lambda: self._status_label.configure(
                text=f"Device: {device}"
            ))

        t = threading.Thread(target=_detect, daemon=True)
        t.start()

    def _do_download_weights(self):
        def _dl():
            ok = _download_weights(on_status=lambda msg: self.after(0, lambda: self._status_label.configure(text=msg)))
            if ok:
                self.after(0, lambda: self._status_label.configure(text="Weights ready."))
                self.after(0, self._detect_device_async)
            else:
                self.after(0, lambda: messagebox.showerror("Download Failed",
                    "Could not download model weights.\n"
                    "Please download manually from HuggingFace and place in:\n" +
                    _weights_path()))
        threading.Thread(target=_dl, daemon=True).start()

    def _do_locate_weights(self):
        path = filedialog.askopenfilename(
            title="Locate CorridorKey.pth",
            filetypes=[("PyTorch weights", "*.pth"), ("All files", "*.*")],
        )
        if path:
            target = _weights_path()
            os.makedirs(os.path.dirname(target), exist_ok=True)
            try:
                import shutil
                shutil.copy2(path, target)
                self._status_label.configure(text="Weights located.")
                self._detect_device_async()
            except Exception as e:
                messagebox.showerror("Error", f"Could not copy weights: {e}")

    # ----- Clip management -----

    def _browse_clips(self):
        paths = filedialog.askopenfilenames(
            title="Select image sequences or video files",
            filetypes=[
                ("Supported media", "*.mov *.mp4 *.avi *.mkv *.png *.jpg *.jpeg *.exr *.tiff *.tif"),
                ("All files", "*.*"),
            ],
        )
        if paths:
            self._load_paths(list(paths))

    def _on_drop(self, paths: list[str]):
        """Called by DropHandler when files/folders are dropped."""
        self._load_paths(paths)

    def _load_paths(self, paths: list[str]):
        """Import a list of file / folder paths as clips."""
        from backend.service import CorridorKeyService

        if self._service is None:
            self._service = CorridorKeyService()
            self._service.detect_device()

        last_clip = None
        for path in paths:
            try:
                clip = self._service.import_clip(path)
                self._clips.append(clip)
                row = ClipRow(
                    self._clip_list_frame,
                    clip,
                    on_remove=self._remove_clip_row,
                    on_selection_change=self._update_clip_count,
                    on_click=self._on_clip_row_click,
                )
                row.grid(
                    row=len(self._clip_rows),
                    column=0,
                    sticky="ew",
                    padx=4,
                    pady=(0, 4),
                )
                self._clip_rows.append(row)
                last_clip = clip
            except Exception as e:
                logger.error(f"Failed to load {path}: {e}")
                messagebox.showerror("Import Error", f"Failed to load:\n{path}\n\n{e}")

        # Show the last loaded clip in the preview panel
        if last_clip is not None:
            self._preview_panel.set_clip(last_clip)

        self._update_clip_count()
        self._update_empty_state()
        self._update_workflow_step()
        self._refresh_next_action()

    def _remove_clip_row(self, row: ClipRow):
        if not messagebox.askyesno("Remove Clip", f"Remove '{row.clip.name}' from the list?"):
            return
        idx = self._clip_rows.index(row)
        self._clips.pop(idx)
        self._clip_rows.pop(idx)
        row.destroy()
        # Re-grid remaining rows
        for i, r in enumerate(self._clip_rows):
            r.grid(row=i)
        self._update_clip_count()
        self._update_empty_state()
        self._update_workflow_step()
        self._refresh_next_action()

    def _clear_clips(self):
        for row in self._clip_rows:
            row.destroy()
        self._clips.clear()
        self._clip_rows.clear()
        self._update_clip_count()
        self._update_empty_state()
        self._update_workflow_step()
        self._refresh_next_action()

    def _select_all_clips(self):
        for row in self._clip_rows:
            row.selected_var.set(True)
        self._update_clip_count()

    def _deselect_all_clips(self):
        for row in self._clip_rows:
            row.selected_var.set(False)
        self._update_clip_count()

    def _update_clip_count(self):
        total = len(self._clip_rows)
        selected = sum(1 for r in self._clip_rows if r.selected_var.get())
        self._clip_count_label.configure(text=f"{selected}/{total} clips")

    def _update_empty_state(self):
        if self._clip_rows:
            self._empty_label.grid_remove()
        else:
            self._empty_label.grid()

    # ----- Workflow stepper -----

    def _update_workflow_step(self):
        """Highlight the current workflow step."""
        step = 0  # default: Load
        if self._clips:
            step = 1  # Set Hints
            if any(c.state.value in ("READY", "MASKED") for c in self._clips):
                step = 2  # Key
        for i, (num_lbl, txt_lbl) in enumerate(self._step_labels):
            if i == step:
                num_lbl.configure(fg_color=CLR_GREEN, text_color=CLR_BG_DARK)
                txt_lbl.configure(text_color=CLR_GREEN)
            else:
                num_lbl.configure(fg_color=CLR_TEXT_DIM, text_color=CLR_BG_DARK)
                txt_lbl.configure(text_color=CLR_TEXT_DIM)

    def _refresh_next_action(self):
        """Update the next-action banner based on current state."""
        if not self._clips:
            msg = "→ Drop or Browse to load image sequences / video clips"
            self._next_action_frame.configure(fg_color=CLR_GREEN_DIM)
        elif not any(c.state.value in ("READY", "MASKED") for c in self._clips):
            msg = "→ Adjust color hints in the Preview panel, then Run Keying"
            self._next_action_frame.configure(fg_color="#3e2723")
        else:
            msg = "→ Press Run Keying (⌘↩) to process selected clips"
            self._next_action_frame.configure(fg_color="#1a3a1a")
        self._next_action_label.configure(text=msg)

    # ----- Clip row click → preview -----

    def _on_clip_row_click(self, row: ClipRow):
        """When a clip row is clicked, show it in the preview panel."""
        self._preview_panel.set_clip(row.clip)

    # ----- Preferences / Settings -----

    def _open_preferences(self):
        """Open a preferences / about dialog."""
        prefs_win = ctk.CTkToplevel(self)
        prefs_win.title("Preferences")
        prefs_win.geometry("400x300")
        prefs_win.configure(fg_color=CLR_BG_DARK)
        prefs_win.grab_set()

        ctk.CTkLabel(
            prefs_win,
            text="CorridorKey Preferences",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=CLR_TEXT_BRIGHT,
        ).pack(pady=(20, 10))

        ctk.CTkLabel(
            prefs_win,
            text="Version 1.0.0 — macOS GUI",
            font=ctk.CTkFont(size=12),
            text_color=CLR_TEXT_DIM,
        ).pack(pady=(0, 20))

        ctk.CTkLabel(
            prefs_win,
            text="Theme:",
            font=ctk.CTkFont(size=12),
            text_color=CLR_TEXT,
        ).pack()
        theme_seg = ctk.CTkSegmentedButton(
            prefs_win,
            values=["Dark", "Light", "System"],
            command=lambda v: ctk.set_appearance_mode(v.lower()),
        )
        theme_seg.set("Dark")
        theme_seg.pack(pady=6)

        ctk.CTkButton(
            prefs_win,
            text="Close",
            command=prefs_win.destroy,
            fg_color=CLR_BG_CARD,
            hover_color=CLR_BG_LIGHT,
        ).pack(pady=20)

    # ----- Notification panel -----

    def _toggle_notification_panel(self):
        if self._notification_mgr is None:
            self._notification_mgr = NotificationManager(self, colors=COLORS_DICT)
        self._notification_mgr.clear_all()

    # ----- Working directory -----

    def _choose_work_dir(self):
        chosen = filedialog.askdirectory(title="Choose Working Directory")
        if chosen:
            self._clips_dir = chosen
            self._workdir_label.configure(text=chosen)

    # ----- Keying process -----

    def _start_keying(self):
        selected_clips = [c for c, r in zip(self._clips, self._clip_rows) if r.selected_var.get()]
        if not selected_clips:
            messagebox.showwarning("No Clips Selected", "Please select at least one clip to process.")
            return

        if not _weights_exist():
            messagebox.showerror("Missing Weights",
                "Model weights not found. Please download or locate them via the startup dialog.")
            return

        if self._working:
            return

        self._working = True
        self._cancel_flag.clear()
        self._run_btn.configure(state="disabled")
        self._cancel_btn.configure(state="normal")
        self._progress_bar.grid()
        self._progress_bar.set(0)
        self._start_time = time.time()
        self._update_timer()

        params = self._settings_panel.get_inference_params()
        output_config = self._settings_panel.get_output_config()
        frame_range = self._frame_range_selector.get_frame_range()
        out_dir = self._clips_dir or ""

        self._worker_thread = threading.Thread(
            target=self._keying_worker,
            args=(selected_clips, params, output_config, frame_range, out_dir),
            daemon=True,
        )
        self._worker_thread.start()

    def _cancel_keying(self):
        if self._working:
            self._cancel_flag.set()
            self._status_label.configure(text="Cancelling…")

    def _keying_worker(self, clips, params, output_config, frame_range, out_dir):
        from backend.clip_state import ClipState
        from backend.service import CorridorKeyService

        total = len(clips)
        if self._service is None:
            self._service = CorridorKeyService()
            self._service.detect_device()
        service = self._service

        # Show model loading indicator
        self.after(0, lambda: self._status_label.configure(text="Loading inference engine\u2026"))
        self.after(0, lambda: self._progress_bar.configure(mode="indeterminate"))
        self.after(0, lambda: self._progress_bar.start())
        _first_frame_done = [False]

        for idx, clip in enumerate(clips):
            if self._cancel_flag.is_set():
                break

            clip_row = next((r for r in self._clip_rows if r.clip is clip), None)

            def on_progress(current: int, total_frames: int, clip_ref=clip, row_ref=clip_row):
                if not _first_frame_done[0]:
                    _first_frame_done[0] = True
                    self.after(0, lambda: self._progress_bar.stop())
                    self.after(0, lambda: self._progress_bar.configure(mode="determinate"))
                    self.after(0, lambda: self._status_label.configure(text="Processing\u2026"))
                self.after(0, lambda: (
                    row_ref.show_progress(current, total_frames) if row_ref else None,
                    self._progress_bar.set(
                        (clips.index(clip_ref) + current / max(total_frames, 1)) / len(clips)
                    ),
                ))

            self.after(0, lambda r=clip_row, s="EXTRACTING": r.update_state(s) if r else None)

            try:
                clip_out_dir = out_dir or os.path.join(
                    os.path.dirname(clip.root_path), "corridorkey_output"
                )
                def _progress_adapter(clip_name, current_frame, total_frames,
                                     _clip=clip, _row=clip_row):
                    on_progress(current_frame, total_frames, clip_ref=_clip, row_ref=_row)

                # Auto-run GVM for RAW clips (generates AlphaHint, transitions RAW → READY)
                if clip.state == ClipState.RAW:
                    self.after(0, lambda r=clip_row: (
                        r.update_state("RAW") if r else None,
                        self._status_label.configure(text="Generating alpha (GVM)\u2026"),
                    ))
                    service.run_gvm(
                        clip,
                        on_progress=_progress_adapter,
                    )

                # Compute skip_stems for resume support
                skip_stems = clip.completed_stems() if self._output_config.get_skip_existing() else None

                service.run_inference(
                    clip,
                    params,
                    on_progress=_progress_adapter,
                    skip_stems=skip_stems,
                    output_config=output_config,
                    frame_range=frame_range,
                )
                self.after(0, lambda r=clip_row: r.update_state("COMPLETE") if r else None)
                self.after(0, lambda r=clip_row: r.hide_progress() if r else None)
            except Exception as e:
                logger.error(f"Clip processing failed: {e}\n{traceback.format_exc()}")
                self.after(0, lambda r=clip_row: r.update_state("ERROR") if r else None)
                self.after(0, lambda r=clip_row: r.hide_progress() if r else None)

            overall = (idx + 1) / total
            self.after(0, lambda v=overall: self._progress_bar.set(v))

        self.after(0, self._on_keying_done)

    def _on_keying_done(self):
        self._working = False
        self._run_btn.configure(state="normal")
        self._cancel_btn.configure(state="disabled")
        self._progress_bar.grid_remove()
        if self._cancel_flag.is_set():
            self._status_label.configure(text="Cancelled.")
        else:
            self._status_label.configure(text="Keying complete.")
            if self._notification_mgr:
                self._notification_mgr.notify("All selected clips have been processed.", level="success")

    # ----- Timer -----

    def _update_timer(self):
        if not self._working:
            return
        elapsed = time.time() - self._start_time
        mins = int(elapsed // 60)
        secs = int(elapsed % 60)
        self._timer_label.configure(text=f"Elapsed: {mins:02d}:{secs:02d}")
        self.after(1000, self._update_timer)

    # ----- Window close -----

    def _on_quit(self):
        if self._working:
            if not messagebox.askyesno(
                "Quit",
                "Keying is in progress. Quit anyway?",
                icon="warning",
            ):
                return
            self._cancel_flag.set()
            if self._worker_thread and self._worker_thread.is_alive():
                self._worker_thread.join(timeout=3.0)
        self.destroy()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main():
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("green")
    app = CorridorKeyApp()
    app.mainloop()


if __name__ == "__main__":
    main()
