"""PreviewPanel — Live frame preview with before/after toggle."""

from __future__ import annotations

import logging
import os
from pathlib import Path

import customtkinter as ctk

logger = logging.getLogger("corridorkey.preview")

# Try to import PIL for image display
try:
    from PIL import Image, ImageTk
    HAS_PIL = True
except ImportError:
    HAS_PIL = False
    logger.info("Pillow not available — preview will show placeholders")

# Bytes-per-pixel estimates for output size estimation
_BPP_ESTIMATE = {
    "png": 3,
    "exr": 12,
    "jpg": 0.5,
    "jpeg": 0.5,
    "tiff": 6,
    "tif": 6,
}


class PreviewPanel(ctk.CTkFrame):
    """Shows a live preview of the selected clip's current frame or output."""

    MODES = ("Input", "Matte", "FG", "Comp", "AlphaHint")

    def __init__(self, master, colors: dict, **kwargs):
        super().__init__(master, fg_color=colors["bg_mid"], corner_radius=10, **kwargs)
        self._colors = colors
        self._current_clip = None
        self._current_mode = "Input"
        self._current_frame_index = 0
        self._total_frames = 0
        self._photo_image = None  # prevent GC

        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # Header bar with mode selector
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 4))
        header.grid_columnconfigure(1, weight=1)

        title = ctk.CTkLabel(
            header, text="Preview",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=colors["text_bright"],
        )
        title.grid(row=0, column=0, sticky="w")

        self._mode_var = ctk.StringVar(value="Input")
        mode_seg = ctk.CTkSegmentedButton(
            header, values=list(self.MODES), variable=self._mode_var,
            font=ctk.CTkFont(size=10),
            selected_color=colors["green"], selected_hover_color=colors["green_hover"],
            unselected_color=colors["bg_light"], unselected_hover_color=colors["bg_card"],
            text_color=colors["text_bright"],
            command=self._on_mode_change,
        )
        mode_seg.grid(row=0, column=1, sticky="e")

        # Canvas for image display
        self._canvas = ctk.CTkCanvas(
            self, bg=colors["bg_dark"], highlightthickness=0,
        )
        self._canvas.grid(row=1, column=0, sticky="nsew", padx=8, pady=(4, 4))

        # Placeholder text
        self._placeholder_id = self._canvas.create_text(
            0, 0, text="Select a clip to preview",
            fill=colors["text_dim"], font=("Helvetica", 13),
        )
        self._canvas.bind("<Configure>", self._center_placeholder)

        # Frame scrubber slider
        self._scrubber = ctk.CTkSlider(
            self, from_=0, to=1, number_of_steps=1,
            fg_color=colors["bg_dark"],
            progress_color=colors["green"],
            button_color=colors["text_bright"],
            button_hover_color=colors["green"],
            command=self._on_scrubber_change,
        )
        self._scrubber.grid(row=2, column=0, sticky="ew", padx=12, pady=(2, 2))
        self._scrubber.set(0)
        self._scrubber.grid_remove()  # hidden until a clip is set

        # Frame info label below scrubber: "Frame N of M • 1920×1080"
        self._frame_info_label = ctk.CTkLabel(
            self, text="",
            font=ctk.CTkFont(size=10),
            text_color=colors["text_dim"],
            anchor="w",
        )
        self._frame_info_label.grid(row=3, column=0, sticky="ew", padx=12, pady=(0, 2))

        # Clip info label: "Input: 1920×1080 • 247 frames • ~10s @24fps"
        self._clip_info_label = ctk.CTkLabel(
            self, text="",
            font=ctk.CTkFont(size=10),
            text_color=colors["text_dim"],
            anchor="w",
        )
        self._clip_info_label.grid(row=4, column=0, sticky="ew", padx=12, pady=(0, 2))

        # Output size estimate label: "Output: ~2.1 GB estimated"
        self._output_info_label = ctk.CTkLabel(
            self, text="",
            font=ctk.CTkFont(size=10),
            text_color=colors["text_dim"],
            anchor="w",
        )
        self._output_info_label.grid(row=5, column=0, sticky="ew", padx=12, pady=(0, 8))

    def _center_placeholder(self, event=None):
        w = self._canvas.winfo_width()
        h = self._canvas.winfo_height()
        self._canvas.coords(self._placeholder_id, w // 2, h // 2)

    def _on_mode_change(self, mode: str):
        self._current_mode = mode
        self._refresh_preview()

    def _on_scrubber_change(self, value):
        """Called when the frame scrubber slider is moved."""
        if self._total_frames > 0:
            self._current_frame_index = max(0, min(int(value), self._total_frames - 1))
            self._refresh_preview()

    def set_clip(self, clip):
        """Set the active clip for preview."""
        self._current_clip = clip
        self._current_frame_index = 0
        self._refresh_preview()
        self._update_clip_info()

    def refresh(self):
        """Public refresh — call from processing callbacks to update live preview."""
        self._refresh_preview()

    def set_mode(self, mode: str):
        """Switch the preview mode (e.g. 'AlphaHint', 'Matte', 'Input')."""
        if mode in self.MODES:
            self._mode_var.set(mode)
            self._current_mode = mode
            self._refresh_preview()

    def clear(self):
        """Clear the preview."""
        self._current_clip = None
        self._canvas.delete("preview_img")
        self._canvas.itemconfigure(self._placeholder_id, state="normal")
        self._frame_info_label.configure(text="")
        self._clip_info_label.configure(text="")
        self._output_info_label.configure(text="")

    def _refresh_preview(self):
        """Refresh the displayed image based on current clip and mode."""
        if self._current_clip is None:
            self.clear()
            return

        clip = self._current_clip
        mode = self._current_mode

        frame_path, frame_num, total_frames = self._find_frame(clip, mode)
        self._total_frames = total_frames

        # Update scrubber range and visibility
        if total_frames > 1:
            self._scrubber.configure(to=total_frames - 1, number_of_steps=total_frames - 1)
            self._scrubber.set(self._current_frame_index)
            self._scrubber.grid()
        else:
            self._scrubber.grid_remove()

        if frame_path is None or not HAS_PIL:
            self._canvas.delete("preview_img")
            self._canvas.itemconfigure(self._placeholder_id, state="normal")
            self._frame_info_label.configure(text="")
            return

        try:
            img = Image.open(frame_path)
            img_w, img_h = img.size
            # Fit to canvas size while maintaining aspect ratio
            cw = max(self._canvas.winfo_width(), 100)
            ch = max(self._canvas.winfo_height(), 100)

            # Calculate scale to fit within canvas while preserving aspect ratio
            scale = min(cw / img_w, ch / img_h)
            new_w = max(int(img_w * scale), 1)
            new_h = max(int(img_h * scale), 1)
            img = img.resize((new_w, new_h), Image.LANCZOS)

            self._photo_image = ImageTk.PhotoImage(img)
            self._canvas.delete("preview_img")
            self._canvas.itemconfigure(self._placeholder_id, state="hidden")
            self._canvas.create_image(
                cw // 2, ch // 2, image=self._photo_image,
                anchor="center", tags="preview_img",
            )

            # Update frame info label
            info_parts = []
            if total_frames > 0:
                info_parts.append(f"Frame {frame_num} of {total_frames}")
            info_parts.append(f"{img_w}\u00d7{img_h}")
            self._frame_info_label.configure(text=" \u2022 ".join(info_parts))
        except Exception as exc:
            logger.warning(f"Preview load failed: {exc}")

    def _find_frame(self, clip, mode: str) -> tuple[str | None, int, int]:
        """Find the frame file at _current_frame_index for the given clip and mode.

        Returns (path, frame_number, total_frames) or (None, 0, 0).
        Defaults to the first frame (index 0).
        """
        root = getattr(clip, "root_path", None)
        if not root or not os.path.isdir(root):
            return None, 0, 0

        # Map mode to subdirectory names — never search root_path itself (".")
        # to avoid listing unrelated files from the source/parent directory.
        mode_dirs = {
            "Input": ["Input", "Frames", "Source"],
            "Matte": ["Output/Matte", "Matte", "matte"],
            "FG": ["Output/FG", "FG", "fg", "Foreground"],
            "Comp": ["Output/Comp", "Comp", "comp", "Composite"],
            "AlphaHint": ["AlphaHint", "alphahint"],
        }

        image_exts = (".png", ".jpg", ".jpeg", ".tiff", ".tif", ".exr")

        for subdir in mode_dirs.get(mode, [mode]):
            search_dir = os.path.join(root, subdir)
            if not os.path.isdir(search_dir):
                continue
            image_files = []
            for fname in os.listdir(search_dir):
                ext = os.path.splitext(fname)[1].lower()
                if ext in image_exts:
                    image_files.append(fname)
            if image_files:
                image_files.sort()
                total = len(image_files)
                # Use _current_frame_index, clamped to valid range
                idx = max(0, min(self._current_frame_index, total - 1))
                frame_file = image_files[idx]
                return os.path.join(search_dir, frame_file), idx + 1, total
        return None, 0, 0

    def _update_clip_info(self):
        """Update the clip info and output estimate labels."""
        clip = self._current_clip
        if clip is None:
            self._clip_info_label.configure(text="")
            self._output_info_label.configure(text="")
            return

        # Build input info string
        info_parts = []

        # Try to get resolution from input asset or first frame
        width, height = self._get_clip_resolution(clip)
        if width and height:
            info_parts.append(f"Input: {width}\u00d7{height}")

        # Frame count
        frame_count = getattr(getattr(clip, "input_asset", None), "frame_count", 0) or 0
        if frame_count > 0:
            info_parts.append(f"{frame_count} frames")
            # Estimate duration at 24fps
            duration_s = frame_count / 24.0
            if duration_s >= 60:
                info_parts.append(f"~{duration_s / 60:.1f}m @24fps")
            else:
                info_parts.append(f"~{duration_s:.0f}s @24fps")

        self._clip_info_label.configure(text=" \u2022 ".join(info_parts) if info_parts else "")

        # Estimate output size
        if width and height and frame_count > 0:
            self._update_output_estimate(width, height, frame_count)
        else:
            self._output_info_label.configure(text="")

    def _get_clip_resolution(self, clip) -> tuple[int | None, int | None]:
        """Get the resolution of the clip's input frames."""
        if not HAS_PIL:
            return None, None

        root = getattr(clip, "root_path", None)
        if not root:
            return None, None

        # Check common input directories for a frame — skip root_path itself
        for subdir in ["Input", "Frames", "Source"]:
            search_dir = os.path.join(root, subdir)
            if not os.path.isdir(search_dir):
                continue
            for fname in sorted(os.listdir(search_dir)):
                ext = os.path.splitext(fname)[1].lower()
                if ext in (".png", ".jpg", ".jpeg", ".tiff", ".tif", ".exr"):
                    try:
                        img = Image.open(os.path.join(search_dir, fname))
                        return img.size
                    except Exception:
                        pass
        return None, None

    def _update_output_estimate(self, width: int, height: int, frame_count: int):
        """Estimate output file size based on resolution, frames, and enabled outputs."""
        pixels = width * height
        total_bytes = 0

        # Try to read output settings from parent widget tree
        # Default: assume PNG ~3 bytes/px, EXR ~12 bytes/px
        # We estimate for all 4 output types as a ballpark
        output_types = {
            "fg": ("exr", True),
            "matte": ("exr", True),
            "comp": ("png", True),
            "processed": ("exr", True),
        }

        # Try to find the settings panel to get actual format selections
        try:
            app = self.winfo_toplevel()
            if hasattr(app, "_settings"):
                settings = app._settings
                for name in output_types:
                    enabled = settings.output_vars.get(name, None)
                    fmt_var = settings.format_vars.get(name, None)
                    if enabled is not None and fmt_var is not None:
                        output_types[name] = (fmt_var.get(), enabled.get())
        except Exception:
            pass

        for name, (fmt, enabled) in output_types.items():
            if not enabled:
                continue
            bpp = _BPP_ESTIMATE.get(fmt, 3)
            total_bytes += pixels * bpp * frame_count

        if total_bytes > 0:
            if total_bytes >= 1_073_741_824:
                size_str = f"~{total_bytes / 1_073_741_824:.1f} GB estimated"
            else:
                size_str = f"~{total_bytes / 1_048_576:.0f} MB estimated"
            self._output_info_label.configure(text=f"Output: {size_str}")
        else:
            self._output_info_label.configure(text="")
