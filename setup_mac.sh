#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────
# setup_mac.sh — One-click setup for running CorridorKey from source
#
# What this script does:
#   1. Installs uv if not already present
#   2. Syncs project dependencies (uv sync)
#   3. Installs GUI dependencies (customtkinter)
#   4. Downloads CorridorKey model weights from HuggingFace (~300 MB)
#   5. Optionally installs the MLX backend for Apple Silicon
#   6. Launches the GUI
# ──────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
RED='\033[0;31m'
BOLD='\033[1m'
NC='\033[0m'

info()  { echo -e "${GREEN}[setup]${NC} $*"; }
warn()  { echo -e "${YELLOW}[setup]${NC} $*"; }
step()  { echo -e "${CYAN}${BOLD}==>${NC} $*"; }
error() { echo -e "${RED}[setup]${NC} $*" >&2; }

echo ""
echo -e "${GREEN}${BOLD}  CorridorKey — macOS Setup${NC}"
echo -e "  AI-based green screen keying"
echo ""

# ── Step 1: Install uv ────────────────────────────────────────────
step "Checking for uv package manager..."
if command -v uv &>/dev/null; then
    info "uv found: $(uv --version)"
else
    info "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
    if ! command -v uv &>/dev/null; then
        error "Failed to install uv. Please install manually: https://docs.astral.sh/uv/"
        exit 1
    fi
    info "uv installed: $(uv --version)"
fi

# ── Step 2: Sync dependencies ─────────────────────────────────────
step "Syncing project dependencies..."
uv sync
info "Dependencies synced"

# ── Step 3: Install GUI dependencies ──────────────────────────────
step "Installing GUI packages..."
uv pip install customtkinter
# tkinterdnd2 is optional — enables native drag-and-drop
if uv pip install tkinterdnd2 2>/dev/null; then
    info "tkinterdnd2 installed (native drag-and-drop enabled)"
else
    warn "tkinterdnd2 not available — file dialog will be used for importing"
fi
info "GUI packages installed"

# ── Step 4: Download model weights ────────────────────────────────
CKPT_DIR="$SCRIPT_DIR/CorridorKeyModule/checkpoints"
CKPT_FILE="$CKPT_DIR/CorridorKey.pth"

step "Checking model weights..."
if [ -f "$CKPT_FILE" ]; then
    info "Model weights found at $CKPT_FILE"
else
    info "Downloading CorridorKey model weights (~300 MB)..."
    mkdir -p "$CKPT_DIR"

    # The HuggingFace file is named CorridorKey_v1.0.pth — download then rename
    HF_FILENAME="CorridorKey_v1.0.pth"

    # Try huggingface-hub CLI first, fall back to Python API
    if uv run huggingface-cli download \
        nikopueringer/CorridorKey_v1.0 \
        "$HF_FILENAME" \
        --local-dir "$CKPT_DIR" 2>/dev/null; then
        info "Model weights downloaded successfully"
    else
        warn "huggingface-cli failed, trying Python API..."
        uv run python -c "
from huggingface_hub import hf_hub_download
hf_hub_download(
    repo_id='nikopueringer/CorridorKey_v1.0',
    filename='CorridorKey_v1.0.pth',
    local_dir='$CKPT_DIR',
)
print('Download complete')
"
    fi

    # Rename to CorridorKey.pth (expected by the inference engine)
    if [ -f "$CKPT_DIR/$HF_FILENAME" ] && [ ! -f "$CKPT_FILE" ]; then
        mv "$CKPT_DIR/$HF_FILENAME" "$CKPT_FILE"
        info "Renamed $HF_FILENAME → CorridorKey.pth"
    fi

    if [ -f "$CKPT_FILE" ]; then
        FILE_SIZE=$(du -h "$CKPT_FILE" | cut -f1)
        info "Model weights ready ($FILE_SIZE)"
    else
        error "Weight download failed. You can download manually from:"
        error "  https://huggingface.co/nikopueringer/CorridorKey_v1.0"
        error "Download CorridorKey_v1.0.pth, rename to CorridorKey.pth, and place in: $CKPT_DIR/"
    fi
fi

# ── Step 5: Optionally install MLX backend ────────────────────────
# MLX is Apple Silicon only and provides faster inference on M-series chips
ARCH=$(uname -m)
if [ "$ARCH" = "arm64" ]; then
    echo ""
    step "Apple Silicon detected"
    echo -e "  The MLX backend can provide faster inference on M-series chips."
    echo -n "  Install MLX backend? [y/N] "
    read -r INSTALL_MLX

    if [[ "$INSTALL_MLX" =~ ^[Yy]$ ]]; then
        info "Installing corridorkey-mlx..."
        if uv pip install "corridorkey-mlx@git+https://github.com/nikopueringer/corridorkey-mlx.git" 2>/dev/null; then
            info "MLX backend installed"

            # Download MLX weights if not present (hosted on GitHub Releases, not HuggingFace)
            MLX_WEIGHTS="$CKPT_DIR/corridorkey_mlx.safetensors"
            if [ ! -f "$MLX_WEIGHTS" ]; then
                info "Downloading MLX model weights from GitHub Releases..."
                MLX_URL="https://github.com/nikopueringer/corridorkey-mlx/releases/download/v1.0.0/corridorkey_mlx.safetensors"
                if curl -L --progress-bar -o "$MLX_WEIGHTS" "$MLX_URL"; then
                    FILE_SIZE=$(du -h "$MLX_WEIGHTS" | cut -f1)
                    info "MLX weights downloaded ($FILE_SIZE)"
                else
                    rm -f "$MLX_WEIGHTS"
                    warn "MLX weights download failed — MLX backend may not work"
                fi
            fi
        else
            warn "MLX installation failed — the Torch/MPS backend will be used instead"
        fi
    else
        info "Skipping MLX (Torch/MPS backend will be used)"
    fi
fi

# ── Step 6: Set macOS environment variables ───────────────────────
export PYTORCH_ENABLE_MPS_FALLBACK=1

# ── Step 7: Launch ────────────────────────────────────────────────
echo ""
step "Setup complete! Launching CorridorKey..."
echo ""
exec uv run python corridorkey_gui.py
