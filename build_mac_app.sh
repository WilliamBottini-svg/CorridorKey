#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────
# build_mac_app.sh — Build CorridorKey.app for macOS using PyInstaller
#
# This script:
#   1. Ensures uv and the venv are set up
#   2. Installs PyInstaller + GUI dependencies
#   3. Builds a macOS .app bundle (dist/CorridorKey.app)
#
# Model weights are NOT bundled (too large). The app will download them
# on first launch.
# ──────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()  { echo -e "${GREEN}[build]${NC} $*"; }
warn()  { echo -e "${YELLOW}[build]${NC} $*"; }
error() { echo -e "${RED}[build]${NC} $*" >&2; }

# ── Step 1: Ensure uv is available ─────────────────────────────────
if ! command -v uv &>/dev/null; then
    info "Installing uv package manager..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi

info "Using uv: $(uv --version)"

# ── Step 2: Sync project dependencies ──────────────────────────────
info "Syncing project dependencies..."
uv sync

# ── Step 3: Install build dependencies ─────────────────────────────
info "Installing PyInstaller and GUI dependencies..."
uv pip install pyinstaller customtkinter

# Try to install tkinterdnd2 (optional — drag-and-drop support)
if uv pip install tkinterdnd2 2>/dev/null; then
    info "tkinterdnd2 installed (drag-and-drop enabled)"
else
    warn "tkinterdnd2 not available — drag-and-drop will use file dialog fallback"
fi

# ── Step 4: Locate customtkinter for bundling ──────────────────────
CTK_PATH=$(uv run python -c "import customtkinter; import os; print(os.path.dirname(customtkinter.__file__))")
info "customtkinter located at: $CTK_PATH"

# ── Step 5: Build with PyInstaller ─────────────────────────────────
info "Building CorridorKey.app..."

# Use the .spec file if present, otherwise build from scratch
if [ -f "CorridorKey.spec" ]; then
    info "Using CorridorKey.spec"
    uv run pyinstaller CorridorKey.spec --noconfirm
else
    warn "CorridorKey.spec not found, building with command-line options"
    uv run pyinstaller \
        --name "CorridorKey" \
        --windowed \
        --onedir \
        --noconfirm \
        --clean \
        --add-data "backend:backend" \
        --add-data "CorridorKeyModule:CorridorKeyModule" \
        --add-data "device_utils.py:." \
        --add-data "${CTK_PATH}:customtkinter" \
        --hidden-import "backend" \
        --hidden-import "backend.service" \
        --hidden-import "backend.clip_state" \
        --hidden-import "backend.errors" \
        --hidden-import "backend.frame_io" \
        --hidden-import "backend.job_queue" \
        --hidden-import "backend.validators" \
        --hidden-import "backend.natural_sort" \
        --hidden-import "backend.project" \
        --hidden-import "customtkinter" \
        --hidden-import "PIL" \
        --hidden-import "cv2" \
        --hidden-import "numpy" \
        --hidden-import "torch" \
        --hidden-import "huggingface_hub" \
        --exclude-module "matplotlib" \
        --exclude-module "notebook" \
        --exclude-module "pytest" \
        --icon "assets/CorridorKey.iconset" \
        --osx-bundle-identifier "com.corridordigital.corridorkey" \
        corridorkey_gui.py
fi

# ── Step 6: Report results ─────────────────────────────────────────
APP_PATH="dist/CorridorKey.app"
if [ -d "$APP_PATH" ]; then
    APP_SIZE=$(du -sh "$APP_PATH" | cut -f1)
    info "Build successful!"
    info "App bundle: $APP_PATH ($APP_SIZE)"
    info ""
    info "Note: Model weights are NOT included in the bundle."
    info "On first launch, the app will offer to download them (~300 MB)."
    info ""
    info "To test: open $APP_PATH"
else
    error "Build failed — dist/CorridorKey.app not found"
    exit 1
fi
