"""Thumbnails — Thumbnail generator and cache for clip list rows."""

from __future__ import annotations

import hashlib
import logging
import os
import threading

logger = logging.getLogger("corridorkey.thumbnails")

# Try to import PIL
try:
    from PIL import Image, ImageTk
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

THUMB_SIZE = (64, 48)


class ThumbnailCache:
    """Generates and caches thumbnail images for clips."""

    def __init__(self, cache_dir: str):
        self._cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)
        self._memory_cache: dict[str, object] = {}
        self._lock = threading.Lock()

    def get_thumbnail(self, clip, callback=None):
        """Get a thumbnail for a clip. Returns cached version or generates async.

        Args:
            clip: A clip object with root_path attribute.
            callback: Called with (clip, PhotoImage) when thumbnail is ready.
                      If None, returns the cached image or None.
        """
        if not HAS_PIL:
            return None

        root = getattr(clip, "root_path", None)
        if not root:
            return None

        cache_key = self._cache_key(root)

        with self._lock:
            if cache_key in self._memory_cache:
                img = self._memory_cache[cache_key]
                if callback:
                    callback(clip, img)
                return img

        # Check disk cache
        disk_path = os.path.join(self._cache_dir, f"{cache_key}.png")
        if os.path.isfile(disk_path):
            return self._load_and_cache(cache_key, disk_path, clip, callback)

        # Generate in background
        if callback:
            threading.Thread(
                target=self._generate_thumbnail,
                args=(clip, root, cache_key, callback),
                daemon=True,
            ).start()
        return None

    def _cache_key(self, path: str) -> str:
        return hashlib.md5(path.encode()).hexdigest()[:16]

    def _load_and_cache(self, key: str, path: str, clip, callback):
        try:
            img = Image.open(path)
            photo = ImageTk.PhotoImage(img)
            with self._lock:
                self._memory_cache[key] = photo
            if callback:
                callback(clip, photo)
            return photo
        except Exception as exc:
            logger.warning(f"Failed to load cached thumbnail: {exc}")
            return None

    def _generate_thumbnail(self, clip, root_path: str, cache_key: str, callback):
        """Generate a thumbnail from the first frame of the clip."""
        try:
            frame_path = self._find_first_frame(root_path)
            if not frame_path:
                return

            img = Image.open(frame_path)
            img.thumbnail(THUMB_SIZE, Image.LANCZOS)

            # Save to disk cache
            disk_path = os.path.join(self._cache_dir, f"{cache_key}.png")
            img.save(disk_path, "PNG")

            # Convert to PhotoImage (must happen... we store PIL image for thread safety)
            photo = ImageTk.PhotoImage(img)
            with self._lock:
                self._memory_cache[cache_key] = photo

            if callback:
                callback(clip, photo)

        except Exception as exc:
            logger.debug(f"Thumbnail generation failed for {root_path}: {exc}")

    @staticmethod
    def _find_first_frame(root_path: str) -> str | None:
        """Find the first image frame in a clip directory."""
        image_exts = {".png", ".jpg", ".jpeg", ".tiff", ".tif", ".exr"}

        # Look in the root and common subdirectories
        for subdir in [".", "Input", "input"]:
            search_dir = os.path.join(root_path, subdir) if subdir != "." else root_path
            if not os.path.isdir(search_dir):
                continue
            for fname in sorted(os.listdir(search_dir)):
                ext = os.path.splitext(fname)[1].lower()
                if ext in image_exts:
                    return os.path.join(search_dir, fname)
        return None

    def clear_cache(self):
        """Clear the in-memory cache."""
        with self._lock:
            self._memory_cache.clear()
