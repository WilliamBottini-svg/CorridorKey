"""OutputConfig — Extended output configuration panel."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk

logger = logging.getLogger("corridorkey.output_config")

# Persistent config path
_CONFIG_DIR = os.path.expanduser("~/.corridorkey")
_CONFIG_PATH = os.path.join(_CONFIG_DIR, "config.json")

# Common resolution presets
RESOLUTION_PRESETS = {
    "Original": None,
    "4K (3840\u00d72160)": (3840, 2160),
    "1080p (1920\u00d71080)": (1920, 1080),
    "720p (1280\u00d7720)": (1280, 720),
    "480p (854\u00d7480)": (854, 480),
}

CODEC_OPTIONS = ["Auto", "ProRes 422", "ProRes 4444", "H.264", "H.265"]

QUALITY_PRESETS = {"Low": 0.3, "Medium": 0.6, "High": 0.85, "Lossless": 1.0}


def _load_config() -> dict:
    """Load persistent config from ~/.corridorkey/config.json."""
    try:
        if os.path.isfile(_CONFIG_PATH):
            with open(_CONFIG_PATH, "r") as f:
                return json.load(f)
    except Exception as exc:
        logger.warning(f"Failed to load config: {exc}")
    return {}


def _save_config(cfg: dict):
    """Save persistent config to ~/.corridorkey/config.json."""
    try:
        os.makedirs(_CONFIG_DIR, exist_ok=True)
        with open(_CONFIG_PATH, "w") as f:
            json.dump(cfg, f, indent=2)
    except Exception as exc:
        logger.warning(f"Failed to save config: {exc}")


class OutputConfigPanel(ctk.CTkFrame):
    """Extended output configuration with resolution, codec, and quality options."""

    def __init__(self, master, colors: dict, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self._colors = colors

        self.grid_columnconfigure(0, weight=1)
        row = 0

        # Header
        ctk.CTkLabel(
            self, text="Output Config",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=colors["text_bright"],
        ).grid(row=row, column=0, padx=0, pady=(0, 6), sticky="w")
        row += 1

        # --- Projects Location picker (at top) ---
        ctk.CTkLabel(
            self, text="Projects Location",
            font=ctk.CTkFont(size=11), text_color=colors["text"],
        ).grid(row=row, column=0, pady=(4, 2), sticky="w")
        row += 1

        # Load saved projects location from config
        cfg = _load_config()
        saved_dir = cfg.get("projects_root", cfg.get("output_dir", ""))
        # Apply saved location to backend on startup
        if saved_dir:
            self._sync_projects_root(saved_dir)

        self._output_dir_var = ctk.StringVar(value=saved_dir)

        dir_frame = ctk.CTkFrame(self, fg_color="transparent")
        dir_frame.grid(row=row, column=0, sticky="ew", pady=(0, 6))
        dir_frame.grid_columnconfigure(0, weight=1)

        self._dir_display = ctk.CTkLabel(
            dir_frame,
            text=self._format_dir_display(saved_dir),
            font=ctk.CTkFont(size=10),
            text_color=colors["text_dim"],
            anchor="w",
        )
        self._dir_display.grid(row=0, column=0, sticky="ew", padx=(0, 4))

        btn_frame = ctk.CTkFrame(dir_frame, fg_color="transparent")
        btn_frame.grid(row=1, column=0, sticky="w", pady=(2, 0))

        ctk.CTkButton(
            btn_frame, text="Browse\u2026", width=70, height=22,
            font=ctk.CTkFont(size=10),
            fg_color=colors["bg_light"], hover_color=colors["bg_card"],
            text_color=colors["text"],
            corner_radius=4,
            command=self._browse_output_dir,
        ).pack(side="left", padx=(0, 4))

        ctk.CTkButton(
            btn_frame, text="Reset", width=50, height=22,
            font=ctk.CTkFont(size=10),
            fg_color=colors["bg_light"], hover_color=colors["bg_card"],
            text_color=colors["text_dim"],
            corner_radius=4,
            command=self._reset_output_dir,
        ).pack(side="left")

        row += 1

        # Separator
        ctk.CTkFrame(self, fg_color=colors.get("border", "#3a3a3a"), height=1).grid(
            row=row, column=0, sticky="ew", pady=6,
        )
        row += 1

        # Resolution preset
        ctk.CTkLabel(
            self, text="Resolution",
            font=ctk.CTkFont(size=11), text_color=colors["text"],
        ).grid(row=row, column=0, pady=(4, 2), sticky="w")
        row += 1

        self.resolution_var = ctk.StringVar(value="Original")
        self._res_menu = ctk.CTkOptionMenu(
            self, variable=self.resolution_var,
            values=list(RESOLUTION_PRESETS.keys()),
            font=ctk.CTkFont(size=11),
            fg_color=colors["bg_light"],
            button_color=colors["bg_card"],
            button_hover_color=colors["green"],
            dropdown_fg_color=colors["bg_card"],
            dropdown_hover_color=colors["green"],
            text_color=colors["text"],
        )
        self._res_menu.grid(row=row, column=0, sticky="ew", pady=(0, 6))
        row += 1

        # Codec selection
        ctk.CTkLabel(
            self, text="Video Codec",
            font=ctk.CTkFont(size=11), text_color=colors["text"],
        ).grid(row=row, column=0, pady=(4, 2), sticky="w")
        row += 1

        self.codec_var = ctk.StringVar(value="Auto")
        self._codec_menu = ctk.CTkOptionMenu(
            self, variable=self.codec_var,
            values=CODEC_OPTIONS,
            font=ctk.CTkFont(size=11),
            fg_color=colors["bg_light"],
            button_color=colors["bg_card"],
            button_hover_color=colors["green"],
            dropdown_fg_color=colors["bg_card"],
            dropdown_hover_color=colors["green"],
            text_color=colors["text"],
        )
        self._codec_menu.grid(row=row, column=0, sticky="ew", pady=(0, 6))
        row += 1

        # Quality slider
        ctk.CTkLabel(
            self, text="Quality",
            font=ctk.CTkFont(size=11), text_color=colors["text"],
        ).grid(row=row, column=0, pady=(4, 2), sticky="w")
        row += 1

        quality_frame = ctk.CTkFrame(self, fg_color="transparent")
        quality_frame.grid(row=row, column=0, sticky="ew", pady=(0, 6))
        quality_frame.grid_columnconfigure(0, weight=1)

        self.quality_var = ctk.DoubleVar(value=0.85)
        self._quality_slider = ctk.CTkSlider(
            quality_frame, from_=0.1, to=1.0, variable=self.quality_var,
            button_color=colors["green"], button_hover_color=colors["green_hover"],
            progress_color=colors["green_dim"], fg_color=colors["bg_light"],
            command=self._on_quality_change,
        )
        self._quality_slider.grid(row=0, column=0, padx=(0, 8), sticky="ew")

        self._quality_label = ctk.CTkLabel(
            quality_frame, text="High",
            font=ctk.CTkFont(size=10), text_color=colors["text_dim"], width=60,
        )
        self._quality_label.grid(row=0, column=1)
        row += 1

        # Auto-stitch to MP4
        self.auto_stitch_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            self, text="Auto-stitch to MP4",
            variable=self.auto_stitch_var,
            font=ctk.CTkFont(size=11), text_color=colors["text"],
            fg_color=colors["green"], hover_color=colors["green_hover"],
            width=24, checkbox_width=16, checkbox_height=16,
        ).grid(row=row, column=0, pady=(4, 2), sticky="w")
        row += 1

        # Skip existing frames (resume partial renders)
        saved_skip = cfg.get("skip_existing", False)
        self.skip_existing_var = ctk.BooleanVar(value=saved_skip)
        ctk.CTkCheckBox(
            self, text="Resume partial renders",
            variable=self.skip_existing_var,
            font=ctk.CTkFont(size=11), text_color=colors["text"],
            fg_color=colors["green"], hover_color=colors["green_hover"],
            width=24, checkbox_width=16, checkbox_height=16,
            command=self._on_skip_existing_change,
        ).grid(row=row, column=0, pady=(4, 2), sticky="w")

    def _format_dir_display(self, path: str) -> str:
        if not path:
            return "~/Documents/CorridorKey/Projects/"
        # Shorten home directory
        home = os.path.expanduser("~")
        if path.startswith(home):
            return "~" + path[len(home):]
        return path

    def _browse_output_dir(self):
        path = filedialog.askdirectory(title="Select projects directory")
        if path:
            self._output_dir_var.set(path)
            self._dir_display.configure(text=self._format_dir_display(path))
            # Persist and update backend
            cfg = _load_config()
            cfg["projects_root"] = path
            _save_config(cfg)
            self._sync_projects_root(path)

    def _reset_output_dir(self):
        self._output_dir_var.set("")
        self._dir_display.configure(text=self._format_dir_display(""))
        # Persist and reset backend
        cfg = _load_config()
        cfg.pop("projects_root", None)
        _save_config(cfg)
        self._sync_projects_root(None)

    @staticmethod
    def _sync_projects_root(path: str | None):
        """Tell the backend where to create new projects."""
        try:
            from backend.project import set_projects_root
            set_projects_root(path)
        except Exception:
            pass  # backend not available yet

    def _on_quality_change(self, value):
        # Find closest named preset
        closest_name = "Custom"
        closest_dist = float("inf")
        for name, val in QUALITY_PRESETS.items():
            dist = abs(value - val)
            if dist < closest_dist:
                closest_dist = dist
                closest_name = name
        if closest_dist > 0.1:
            closest_name = f"{value:.0%}"
        self._quality_label.configure(text=closest_name)

    def get_output_dir(self) -> str | None:
        """Return the custom output directory, or None for default."""
        d = self._output_dir_var.get()
        return d if d else None

    def get_resolution(self) -> tuple[int, int] | None:
        """Return the selected resolution or None for original."""
        return RESOLUTION_PRESETS.get(self.resolution_var.get())

    def get_codec(self) -> str:
        return self.codec_var.get()

    def get_quality(self) -> float:
        return self.quality_var.get()

    def get_auto_stitch(self) -> bool:
        return self.auto_stitch_var.get()

    def get_skip_existing(self) -> bool:
        return self.skip_existing_var.get()

    def _on_skip_existing_change(self):
        cfg = _load_config()
        cfg["skip_existing"] = self.skip_existing_var.get()
        _save_config(cfg)
