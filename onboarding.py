"""OnboardingFlow — First-launch onboarding for CorridorKey (Apple HIG compliant)."""

from __future__ import annotations

import logging
import os

import customtkinter as ctk

logger = logging.getLogger("corridorkey.onboarding")

# Color constants — matches the app's dark VFX aesthetic
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
CLR_BORDER = "#3a3a3a"

_TOTAL_STEPS = 3


class OnboardingFlow:
    """First-launch onboarding flow."""

    MARKER_PATH = os.path.join(os.path.expanduser("~"), ".corridorkey", "onboarding_complete")

    @classmethod
    def needs_onboarding(cls) -> bool:
        return not os.path.isfile(cls.MARKER_PATH)

    @classmethod
    def mark_complete(cls):
        os.makedirs(os.path.dirname(cls.MARKER_PATH), exist_ok=True)
        with open(cls.MARKER_PATH, "w") as f:
            f.write("completed")

    def __init__(self, parent, base_dir: str):
        self._parent = parent
        self._base_dir = base_dir
        self._current_step = 0
        self._dialog: ctk.CTkToplevel | None = None
        self._content_frame: ctk.CTkFrame | None = None
        self._dots: list[ctk.CTkLabel] = []

    def show(self):
        """Create and display the onboarding modal."""
        self._dialog = ctk.CTkToplevel(self._parent)
        self._dialog.title("Welcome to CorridorKey")
        self._dialog.geometry("640x520")
        self._dialog.resizable(False, False)
        self._dialog.configure(fg_color=CLR_BG_DARK)
        self._dialog.transient(self._parent)
        self._dialog.grab_set()

        # Center on screen
        self._dialog.update_idletasks()
        sw = self._dialog.winfo_screenwidth()
        sh = self._dialog.winfo_screenheight()
        x = (sw - 640) // 2
        y = (sh - 520) // 2
        self._dialog.geometry(f"640x520+{x}+{y}")

        # Main layout
        self._dialog.grid_rowconfigure(0, weight=1)
        self._dialog.grid_rowconfigure(1, weight=0)
        self._dialog.grid_columnconfigure(0, weight=1)

        # Content area (swapped per step)
        self._content_frame = ctk.CTkFrame(self._dialog, fg_color="transparent")
        self._content_frame.grid(row=0, column=0, sticky="nsew", padx=24, pady=(24, 8))

        # Bottom bar: dots + nav buttons
        bottom = ctk.CTkFrame(self._dialog, fg_color="transparent", height=48)
        bottom.grid(row=1, column=0, sticky="ew", padx=24, pady=(0, 20))
        bottom.grid_columnconfigure(1, weight=1)

        # Skip button (left)
        self._skip_btn = ctk.CTkButton(
            bottom, text="Skip", width=70, height=32,
            font=ctk.CTkFont(size=12),
            fg_color="transparent", hover_color=CLR_BG_LIGHT,
            text_color=CLR_TEXT_DIM,
            command=self._on_skip,
        )
        self._skip_btn.grid(row=0, column=0, sticky="w")

        # Step dots (center)
        dots_frame = ctk.CTkFrame(bottom, fg_color="transparent")
        dots_frame.grid(row=0, column=1)
        self._dots = []
        for i in range(_TOTAL_STEPS):
            dot = ctk.CTkLabel(
                dots_frame, text="\u2022", width=16,
                font=ctk.CTkFont(size=18),
                text_color=CLR_GREEN if i == 0 else CLR_TEXT_DIM,
            )
            dot.pack(side="left", padx=3)
            self._dots.append(dot)

        # Next/Done button (right)
        self._next_btn = ctk.CTkButton(
            bottom, text="Get Started \u2192", width=140, height=32,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=CLR_GREEN, hover_color=CLR_GREEN_HOVER,
            text_color=CLR_TEXT_BRIGHT,
            command=self._on_next,
        )
        self._next_btn.grid(row=0, column=2, sticky="e")

        self._show_step(0)

    # --- Navigation ---

    def _on_skip(self):
        self.mark_complete()
        self._dialog.destroy()

    def _on_next(self):
        next_step = self._current_step + 1
        if next_step >= _TOTAL_STEPS:
            self.mark_complete()
            self._dialog.destroy()
        else:
            self._show_step(next_step)

    def _show_step(self, step: int):
        self._current_step = step

        # Update dots
        for i, dot in enumerate(self._dots):
            dot.configure(text_color=CLR_GREEN if i == step else CLR_TEXT_DIM)

        # Clear content
        for child in self._content_frame.winfo_children():
            child.destroy()

        # Update button text
        if step == _TOTAL_STEPS - 1:
            self._next_btn.configure(text="Done")
            self._skip_btn.grid_remove()
        elif step == 1:
            self._next_btn.configure(text="Next \u2192")
            self._skip_btn.grid()
        else:
            self._next_btn.configure(text="Get Started \u2192")
            self._skip_btn.grid()

        # Render step
        builders = [self._build_welcome, self._build_system_check, self._build_quick_start]
        builders[step]()

    # --- Step 1: Welcome ---

    def _build_welcome(self):
        f = self._content_frame
        f.grid_columnconfigure(0, weight=1)

        title = ctk.CTkLabel(
            f, text="Welcome to CorridorKey",
            font=ctk.CTkFont(size=26, weight="bold"),
            text_color=CLR_TEXT_BRIGHT,
        )
        title.grid(row=0, column=0, pady=(16, 4))

        subtitle = ctk.CTkLabel(
            f, text="AI-powered green screen keying for professional VFX workflows",
            font=ctk.CTkFont(size=13),
            text_color=CLR_TEXT_DIM,
        )
        subtitle.grid(row=1, column=0, pady=(0, 12))

        desc = ctk.CTkLabel(
            f,
            text=(
                "CorridorKey uses neural networks to produce broadcast-quality keys\n"
                "from green screen footage \u2014 with clean edges, natural hair detail,\n"
                "and automatic despill."
            ),
            font=ctk.CTkFont(size=12),
            text_color=CLR_TEXT,
            justify="center",
        )
        desc.grid(row=2, column=0, pady=(0, 24))

        # Feature highlights
        features = [
            ("Neural Keying", "AI-driven foreground extraction at 2048\u00d72048"),
            ("Smart Alpha", "Guided video matting for alpha hint generation"),
            ("Professional Output", "EXR, PNG, and compositing outputs"),
        ]
        for i, (name, detail) in enumerate(features):
            card = ctk.CTkFrame(f, fg_color=CLR_BG_CARD, corner_radius=8)
            card.grid(row=3 + i, column=0, sticky="ew", pady=4, padx=16)
            card.grid_columnconfigure(1, weight=1)

            label = ctk.CTkLabel(
                card, text=name,
                font=ctk.CTkFont(size=13, weight="bold"),
                text_color=CLR_GREEN,
                anchor="w",
            )
            label.grid(row=0, column=0, padx=(16, 8), pady=10, sticky="w")

            detail_lbl = ctk.CTkLabel(
                card, text=detail,
                font=ctk.CTkFont(size=12),
                text_color=CLR_TEXT,
                anchor="w",
            )
            detail_lbl.grid(row=0, column=1, padx=(0, 16), pady=10, sticky="w")

    # --- Step 2: System Check ---

    def _build_system_check(self):
        f = self._content_frame
        f.grid_columnconfigure(0, weight=1)

        title = ctk.CTkLabel(
            f, text="Checking Your Setup",
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color=CLR_TEXT_BRIGHT,
        )
        title.grid(row=0, column=0, pady=(16, 16))

        checks = self._run_system_checks()

        weights_missing = False
        for i, (label, passed, note) in enumerate(checks):
            row_frame = ctk.CTkFrame(f, fg_color=CLR_BG_MID, corner_radius=6)
            row_frame.grid(row=1 + i, column=0, sticky="ew", pady=3, padx=16)
            row_frame.grid_columnconfigure(1, weight=1)

            icon = "\u2713" if passed else "\u26a0"
            icon_color = CLR_GREEN if passed else "#ffab00"

            icon_lbl = ctk.CTkLabel(
                row_frame, text=icon, width=28,
                font=ctk.CTkFont(size=16),
                text_color=icon_color,
            )
            icon_lbl.grid(row=0, column=0, padx=(12, 4), pady=8)

            text_lbl = ctk.CTkLabel(
                row_frame, text=label,
                font=ctk.CTkFont(size=12),
                text_color=CLR_TEXT,
                anchor="w",
            )
            text_lbl.grid(row=0, column=1, padx=(0, 8), pady=8, sticky="w")

            if note:
                note_lbl = ctk.CTkLabel(
                    row_frame, text=note,
                    font=ctk.CTkFont(size=10),
                    text_color=CLR_TEXT_DIM,
                    anchor="e",
                )
                note_lbl.grid(row=0, column=2, padx=(0, 12), pady=8, sticky="e")

            if "weights" in label.lower() and not passed:
                weights_missing = True

        if weights_missing:
            note = ctk.CTkLabel(
                f,
                text=(
                    "Model weights will be needed before processing.\n"
                    "You can download them from the app."
                ),
                font=ctk.CTkFont(size=11),
                text_color="#ffab00",
                justify="center",
            )
            note.grid(row=1 + len(checks), column=0, pady=(16, 0))

    def _run_system_checks(self) -> list[tuple[str, bool, str]]:
        """Run system checks. Returns list of (label, passed, detail_note)."""
        import sys

        checks: list[tuple[str, bool, str]] = []

        # 1. Python version
        ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        checks.append((f"Python {ver}", True, ""))

        # 2. PyTorch
        torch_ok = False
        torch_note = "not found"
        try:
            import torch
            torch_ok = True
            torch_note = f"v{torch.__version__}"
        except ImportError:
            pass
        checks.append(("PyTorch", torch_ok, torch_note))

        # 3. Apple MPS
        mps_ok = False
        mps_note = "not available"
        if torch_ok:
            try:
                import torch as _t
                if hasattr(_t.backends, "mps") and _t.backends.mps.is_available():
                    mps_ok = True
                    mps_note = "available"
            except Exception:
                pass
        checks.append(("Apple MPS", mps_ok, mps_note))

        # 4. Model weights
        ckpt_dir = os.path.join(self._base_dir, "CorridorKeyModule", "checkpoints")
        weights_ok = False
        for fname in ("CorridorKey.pth", "CorridorKey_v1.0.pth"):
            if os.path.isfile(os.path.join(ckpt_dir, fname)):
                weights_ok = True
                break
        checks.append(("Model weights", weights_ok, "found" if weights_ok else "missing"))

        # 5. Working directory
        projects_dir = os.path.join(os.path.expanduser("~"), "Documents", "CorridorKey", "Projects")
        dir_ok = os.path.isdir(projects_dir)
        if not dir_ok:
            try:
                os.makedirs(projects_dir, exist_ok=True)
                dir_ok = True
            except OSError:
                pass
        checks.append(("Working directory", dir_ok, projects_dir if dir_ok else "could not create"))

        return checks

    # --- Step 3: Quick Start ---

    def _build_quick_start(self):
        f = self._content_frame
        f.grid_columnconfigure(0, weight=1)

        title = ctk.CTkLabel(
            f, text="Your First Key in 3 Steps",
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color=CLR_TEXT_BRIGHT,
        )
        title.grid(row=0, column=0, pady=(16, 20))

        steps = [
            ("1", "Load Clips", "Drop video files or image sequences into the app"),
            ("2", "Generate Hints", "Create alpha hints using GVM or provide your own"),
            ("3", "Process Key", "Run inference to produce clean keyed output"),
        ]

        for i, (num, name, desc) in enumerate(steps):
            card = ctk.CTkFrame(f, fg_color=CLR_BG_MID, corner_radius=8)
            card.grid(row=1 + i, column=0, sticky="ew", pady=6, padx=16)
            card.grid_columnconfigure(2, weight=1)

            num_lbl = ctk.CTkLabel(
                card, text=num, width=36, height=36,
                font=ctk.CTkFont(size=18, weight="bold"),
                text_color=CLR_BG_DARK,
                fg_color=CLR_GREEN,
                corner_radius=18,
            )
            num_lbl.grid(row=0, column=0, padx=(16, 12), pady=14)

            name_lbl = ctk.CTkLabel(
                card, text=name,
                font=ctk.CTkFont(size=14, weight="bold"),
                text_color=CLR_TEXT_BRIGHT,
                anchor="w",
            )
            name_lbl.grid(row=0, column=1, padx=(0, 8), pady=14, sticky="w")

            desc_lbl = ctk.CTkLabel(
                card, text=desc,
                font=ctk.CTkFont(size=12),
                text_color=CLR_TEXT,
                anchor="w",
            )
            desc_lbl.grid(row=0, column=2, padx=(0, 16), pady=14, sticky="w")

        tip = ctk.CTkLabel(
            f,
            text="Tip: Use the 2-second preview mode to test settings before processing full clips.",
            font=ctk.CTkFont(size=11, slant="italic"),
            text_color=CLR_TEXT_DIM,
            justify="center",
        )
        tip.grid(row=4, column=0, pady=(24, 0))
