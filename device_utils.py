"""Centralized cross-platform device selection for CorridorKey.

Also applies MPS-specific environment tweaks (TIMM_FUSED_ATTN, etc.)
**before** any ML library is first imported, so that the flags take effect.
"""

import logging
import os

logger = logging.getLogger(__name__)

DEVICE_ENV_VAR = "CORRIDORKEY_DEVICE"
VALID_DEVICES = ("auto", "cuda", "mps", "cpu")

_mps_env_configured = False  # guard so we only log once


def _configure_mps_environment() -> None:
    """Set environment variables that make MPS inference safer.

    Must be called **before** ``import timm`` / first use of SDPA so that
    the flags are picked up at module-init time.

    What this does and why:

    TIMM_FUSED_ATTN=0
        Tells timm to use the manual attention path (matmul → softmax →
        matmul) instead of ``F.scaled_dot_product_attention``.  The MPS
        SDPA backend has a history of correctness issues:
        • Out-of-bounds memory access at seq-len ≥ 1024  (pytorch#174861)
        • Wrong output shape when value-dim ≠ query-dim  (pytorch#176767)
        • Regression on non-contiguous query tensors      (pytorch#163597)
        Disabling fused attention sidesteps all of these with negligible
        performance cost during inference.

    PYTORCH_ENABLE_MPS_FALLBACK is intentionally NOT set — it only catches
    ``NotImplementedError`` and misses silent correctness bugs, which are
    the real threat.  All ops used by CorridorKey are already implemented
    on MPS, so the flag provides no benefit.
    """
    global _mps_env_configured
    if _mps_env_configured:
        return
    _mps_env_configured = True

    tweaks: list[str] = []

    # --- Disable SDPA in timm (Hiera attention) ---------------------
    if "TIMM_FUSED_ATTN" not in os.environ:
        os.environ["TIMM_FUSED_ATTN"] = "0"
        tweaks.append("TIMM_FUSED_ATTN=0  (disable SDPA — MPS correctness safeguard)")
    else:
        tweaks.append(f"TIMM_FUSED_ATTN={os.environ['TIMM_FUSED_ATTN']}  (user override)")

    if tweaks:
        logger.info("MPS environment configured:")
        for t in tweaks:
            logger.info("  • %s", t)


def is_rocm_system() -> bool:
    """Detect if the system has AMD ROCm available (without importing torch).

    Checks: /opt/rocm (Linux), HIP_PATH env var (Windows), HIP_VISIBLE_DEVICES
    (any platform), CORRIDORKEY_ROCM=1 (explicit opt-in for cases where
    auto-detection fails, e.g. pip-installed ROCm on Windows).
    """
    return (
        os.path.exists("/opt/rocm")
        or os.environ.get("HIP_PATH") is not None
        or os.environ.get("HIP_VISIBLE_DEVICES") is not None
        or os.environ.get("CORRIDORKEY_ROCM") == "1"
    )


def setup_rocm_env() -> None:
    """Set ROCm environment variables and apply optional patches.

    Must be called before importing torch so that env vars are visible to
    PyTorch's initialization. This module intentionally avoids importing
    torch at module level to make that possible. Safe to call on non-ROCm
    systems (no-op).
    """
    if not is_rocm_system():
        return
    os.environ.setdefault("TORCH_ROCM_AOTRITON_ENABLE_EXPERIMENTAL", "1")
    os.environ.setdefault("MIOPEN_FIND_MODE", "2")
    # Level 4 = suppress info/debug but keep warnings and errors visible
    os.environ.setdefault("MIOPEN_LOG_LEVEL", "4")
    # Enable GTT (system RAM as GPU overflow) on Linux for 16GB cards.
    # pytorch-rocm-gtt must be installed separately: pip install pytorch-rocm-gtt
    try:
        import pytorch_rocm_gtt

        pytorch_rocm_gtt.patch()
    except ImportError:
        pass  # not installed — expected on most systems
    except Exception:
        logger.warning("pytorch-rocm-gtt is installed but patch() failed", exc_info=True)


def detect_best_device() -> str:
    """Auto-detect best available device: CUDA > MPS > CPU."""
    import torch

    if torch.cuda.is_available():
        device = "cuda"
    elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        device = "mps"
        _configure_mps_environment()
    else:
        device = "cpu"
    logger.info("Auto-selected device: %s", device)
    return device


def resolve_device(requested: str | None = None) -> str:
    """Resolve device from explicit request > env var > auto-detect.

    Args:
        requested: Device string from CLI arg. None or "auto" triggers
                   env var lookup then auto-detection.

    Returns:
        Validated device string ("cuda", "mps", or "cpu").

    Raises:
        RuntimeError: If the requested backend is unavailable.
    """
    import torch

    # CLI arg takes priority, then env var, then auto
    device = requested
    if device is None or device == "auto":
        device = os.environ.get(DEVICE_ENV_VAR, "auto")

    if device == "auto":
        return detect_best_device()

    device = device.lower()
    if device not in VALID_DEVICES:
        raise RuntimeError(f"Unknown device '{device}'. Valid options: {', '.join(VALID_DEVICES)}")

    # Validate the explicit request
    if device == "cuda":
        if not torch.cuda.is_available():
            raise RuntimeError(
                "CUDA requested but torch.cuda.is_available() is False. Install a CUDA-enabled PyTorch build."
            )
    elif device == "mps":
        if not hasattr(torch.backends, "mps"):
            raise RuntimeError(
                "MPS requested but this PyTorch build has no MPS support. Install PyTorch >= 1.12 with MPS backend."
            )
        if not torch.backends.mps.is_available():
            raise RuntimeError(
                "MPS requested but not available on this machine. Requires Apple Silicon (M1+) with macOS 12.3+."
            )
        _configure_mps_environment()

    return device


def clear_device_cache(device) -> None:
    """Clear GPU memory cache if applicable (no-op for CPU)."""
    import torch

    device_type = device.type if isinstance(device, torch.device) else device
    if device_type == "cuda":
        torch.cuda.empty_cache()
    elif device_type == "mps":
        torch.mps.empty_cache()
