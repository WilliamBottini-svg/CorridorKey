"""PresetsManager — Save/load inference parameter presets."""

from __future__ import annotations

import json
import logging
import os

import customtkinter as ctk

logger = logging.getLogger("corridorkey.presets")


class PresetsManager(ctk.CTkFrame):
    """UI component for saving and loading named inference presets."""

    def __init__(self, master, presets_dir: str, colors: dict, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self._presets_dir = presets_dir
        self._colors = colors
        self._settings_panel = None  # set via connect_settings()

        os.makedirs(presets_dir, exist_ok=True)

        self.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            self, text="Presets",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=colors["text_bright"],
        ).grid(row=0, column=0, columnspan=3, padx=0, pady=(0, 4), sticky="w")

        self._preset_var = ctk.StringVar(value="Default")
        self._dropdown = ctk.CTkOptionMenu(
            self, variable=self._preset_var,
            values=self._list_presets(),
            font=ctk.CTkFont(size=11),
            fg_color=colors["bg_light"],
            button_color=colors["bg_card"],
            button_hover_color=colors["green"],
            dropdown_fg_color=colors["bg_card"],
            dropdown_hover_color=colors["green"],
            text_color=colors["text"],
            width=120,
        )
        self._dropdown.grid(row=1, column=0, padx=(0, 4), sticky="ew")

        btn_style = dict(
            font=ctk.CTkFont(size=10),
            fg_color=colors["bg_card"],
            hover_color=colors["bg_light"],
            text_color=colors["text"],
            corner_radius=4, height=24,
        )

        self._load_btn = ctk.CTkButton(
            self, text="Load", width=50, command=self._load_preset, **btn_style,
        )
        self._load_btn.grid(row=1, column=1, padx=2)

        self._save_btn = ctk.CTkButton(
            self, text="Save", width=50, command=self._save_preset, **btn_style,
        )
        self._save_btn.grid(row=1, column=2, padx=(2, 0))

    def connect_settings(self, settings_panel):
        """Connect to the SettingsPanel to read/write parameters."""
        self._settings_panel = settings_panel

    def _list_presets(self) -> list[str]:
        names = ["Default"]
        if os.path.isdir(self._presets_dir):
            for f in sorted(os.listdir(self._presets_dir)):
                if f.endswith(".json"):
                    name = os.path.splitext(f)[0]
                    if name not in names:
                        names.append(name)
        return names

    def _refresh_dropdown(self):
        presets = self._list_presets()
        self._dropdown.configure(values=presets)

    def _save_preset(self):
        """Save current settings as a named preset."""
        if not self._settings_panel:
            return

        name = self._preset_var.get().strip()
        if not name or name == "Default":
            # Prompt for a name via simple dialog
            dialog = ctk.CTkInputDialog(
                text="Preset name:", title="Save Preset",
            )
            name = dialog.get_input()
            if not name:
                return

        data = {
            "gamma": self._settings_panel.gamma_var.get(),
            "despill": self._settings_panel.despill_var.get(),
            "despeckle": self._settings_panel.despeckle_var.get(),
            "despeckle_size": self._settings_panel.despeckle_size_var.get(),
            "refiner_scale": self._settings_panel.refiner_var.get(),
            "backend": self._settings_panel.backend_var.get(),
        }

        path = os.path.join(self._presets_dir, f"{name}.json")
        try:
            with open(path, "w") as f:
                json.dump(data, f, indent=2)
            logger.info(f"Preset saved: {name}")
            self._preset_var.set(name)
            self._refresh_dropdown()
        except Exception as exc:
            logger.error(f"Failed to save preset: {exc}")

    def _load_preset(self):
        """Load a preset and apply to settings."""
        if not self._settings_panel:
            return

        name = self._preset_var.get()
        if name == "Default":
            self._apply_defaults()
            return

        path = os.path.join(self._presets_dir, f"{name}.json")
        if not os.path.isfile(path):
            logger.warning(f"Preset file not found: {path}")
            return

        try:
            with open(path) as f:
                data = json.load(f)
            self._apply_preset(data)
            logger.info(f"Preset loaded: {name}")
        except Exception as exc:
            logger.error(f"Failed to load preset: {exc}")

    def _apply_defaults(self):
        if not self._settings_panel:
            return
        sp = self._settings_panel
        sp.gamma_var.set("srgb")
        sp.despill_var.set(1.0)
        sp.despeckle_var.set(True)
        sp.despeckle_size_var.set("400")
        sp.refiner_var.set(1.0)
        sp.backend_var.set("Auto")

    def _apply_preset(self, data: dict):
        if not self._settings_panel:
            return
        sp = self._settings_panel
        if "gamma" in data:
            sp.gamma_var.set(data["gamma"])
        if "despill" in data:
            sp.despill_var.set(data["despill"])
        if "despeckle" in data:
            sp.despeckle_var.set(data["despeckle"])
        if "despeckle_size" in data:
            sp.despeckle_size_var.set(str(data["despeckle_size"]))
        if "refiner_scale" in data:
            sp.refiner_var.set(data["refiner_scale"])
        if "backend" in data:
            sp.backend_var.set(data["backend"])
