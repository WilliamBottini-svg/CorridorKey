"""Unit tests for device_utils — cross-platform device selection.

Tests cover all code paths in detect_best_device(), resolve_device(),
and clear_device_cache() using monkeypatch to mock hardware availability.
No GPU required.
"""

import os
from unittest.mock import MagicMock

import pytest
import torch

import device_utils
from device_utils import (
    DEVICE_ENV_VAR,
    _configure_mps_environment,
    clear_device_cache,
    detect_best_device,
    resolve_device,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _patch_gpu(monkeypatch, *, cuda=False, mps=False):
    """Mock CUDA and MPS availability flags."""
    monkeypatch.setattr(torch.cuda, "is_available", lambda: cuda)
    # MPS lives behind torch.backends.mps; ensure the attr path exists
    mps_backend = MagicMock()
    mps_backend.is_available = MagicMock(return_value=mps)
    monkeypatch.setattr(torch.backends, "mps", mps_backend)
    # Reset the once-only guard so each test starts clean
    monkeypatch.setattr(device_utils, "_mps_env_configured", False)


# ---------------------------------------------------------------------------
# detect_best_device
# ---------------------------------------------------------------------------


class TestDetectBestDevice:
    """Priority chain: CUDA > MPS > CPU."""

    def test_returns_cuda_when_available(self, monkeypatch):
        _patch_gpu(monkeypatch, cuda=True, mps=True)
        assert detect_best_device() == "cuda"

    def test_returns_mps_when_no_cuda(self, monkeypatch):
        _patch_gpu(monkeypatch, cuda=False, mps=True)
        assert detect_best_device() == "mps"

    def test_returns_cpu_when_nothing(self, monkeypatch):
        _patch_gpu(monkeypatch, cuda=False, mps=False)
        assert detect_best_device() == "cpu"


# ---------------------------------------------------------------------------
# resolve_device
# ---------------------------------------------------------------------------


class TestResolveDevice:
    """Priority chain: CLI arg > env var > auto-detect."""

    # --- auto-detect path ---

    def test_none_triggers_auto_detect(self, monkeypatch):
        _patch_gpu(monkeypatch, cuda=False, mps=False)
        monkeypatch.delenv(DEVICE_ENV_VAR, raising=False)
        assert resolve_device(None) == "cpu"

    def test_auto_string_triggers_auto_detect(self, monkeypatch):
        _patch_gpu(monkeypatch, cuda=True)
        monkeypatch.delenv(DEVICE_ENV_VAR, raising=False)
        assert resolve_device("auto") == "cuda"

    # --- env var fallback ---

    def test_env_var_used_when_no_cli_arg(self, monkeypatch):
        _patch_gpu(monkeypatch, cuda=True, mps=True)
        monkeypatch.setenv(DEVICE_ENV_VAR, "cpu")
        assert resolve_device(None) == "cpu"

    def test_env_var_auto_triggers_detect(self, monkeypatch):
        _patch_gpu(monkeypatch, cuda=False, mps=True)
        monkeypatch.setenv(DEVICE_ENV_VAR, "auto")
        assert resolve_device(None) == "mps"

    # --- CLI arg overrides env var ---

    def test_cli_arg_overrides_env_var(self, monkeypatch):
        _patch_gpu(monkeypatch, cuda=True, mps=True)
        monkeypatch.setenv(DEVICE_ENV_VAR, "mps")
        assert resolve_device("cuda") == "cuda"

    # --- explicit valid devices ---

    def test_explicit_cuda(self, monkeypatch):
        _patch_gpu(monkeypatch, cuda=True)
        assert resolve_device("cuda") == "cuda"

    def test_explicit_mps(self, monkeypatch):
        _patch_gpu(monkeypatch, mps=True)
        assert resolve_device("mps") == "mps"

    def test_explicit_cpu(self, monkeypatch):
        assert resolve_device("cpu") == "cpu"

    def test_case_insensitive(self, monkeypatch):
        assert resolve_device("CPU") == "cpu"

    # --- unavailable backend errors ---

    def test_cuda_unavailable_raises(self, monkeypatch):
        _patch_gpu(monkeypatch, cuda=False)
        with pytest.raises(RuntimeError, match="CUDA requested"):
            resolve_device("cuda")

    def test_mps_no_backend_raises(self, monkeypatch):
        # Simulate PyTorch build without MPS module in torch.backends
        _patch_gpu(monkeypatch, cuda=False, mps=False)
        # Replace torch.backends with an object that lacks "mps" entirely
        fake_backends = type("Backends", (), {})()
        monkeypatch.setattr(torch, "backends", fake_backends)
        with pytest.raises(RuntimeError, match="no MPS support"):
            resolve_device("mps")

    def test_mps_unavailable_raises(self, monkeypatch):
        _patch_gpu(monkeypatch, cuda=False, mps=False)
        with pytest.raises(RuntimeError, match="not available on this machine"):
            resolve_device("mps")

    # --- invalid device string ---

    def test_invalid_device_raises(self, monkeypatch):
        with pytest.raises(RuntimeError, match="Unknown device"):
            resolve_device("tpu")


# ---------------------------------------------------------------------------
# _configure_mps_environment
# ---------------------------------------------------------------------------


class TestConfigureMpsEnvironment:
    """MPS env tweaks are applied exactly once and respect user overrides."""

    def test_sets_timm_fused_attn(self, monkeypatch):
        monkeypatch.setattr(device_utils, "_mps_env_configured", False)
        monkeypatch.delenv("TIMM_FUSED_ATTN", raising=False)
        _configure_mps_environment()
        assert os.environ.get("TIMM_FUSED_ATTN") == "0"

    def test_respects_user_override(self, monkeypatch):
        monkeypatch.setattr(device_utils, "_mps_env_configured", False)
        monkeypatch.setenv("TIMM_FUSED_ATTN", "1")
        _configure_mps_environment()
        assert os.environ["TIMM_FUSED_ATTN"] == "1"  # not overwritten

    def test_runs_only_once(self, monkeypatch):
        monkeypatch.setattr(device_utils, "_mps_env_configured", False)
        monkeypatch.delenv("TIMM_FUSED_ATTN", raising=False)
        _configure_mps_environment()
        # Manually set a different value; second call should NOT overwrite
        os.environ["TIMM_FUSED_ATTN"] = "999"
        _configure_mps_environment()
        assert os.environ["TIMM_FUSED_ATTN"] == "999"  # guard prevented re-run

    def test_detect_best_device_triggers_on_mps(self, monkeypatch):
        _patch_gpu(monkeypatch, cuda=False, mps=True)
        monkeypatch.delenv("TIMM_FUSED_ATTN", raising=False)
        detect_best_device()
        assert os.environ.get("TIMM_FUSED_ATTN") == "0"

    def test_resolve_device_explicit_mps_triggers(self, monkeypatch):
        _patch_gpu(monkeypatch, mps=True)
        monkeypatch.delenv("TIMM_FUSED_ATTN", raising=False)
        resolve_device("mps")
        assert os.environ.get("TIMM_FUSED_ATTN") == "0"

    def test_cuda_does_not_trigger(self, monkeypatch):
        _patch_gpu(monkeypatch, cuda=True)
        monkeypatch.delenv("TIMM_FUSED_ATTN", raising=False)
        resolve_device("cuda")
        assert "TIMM_FUSED_ATTN" not in os.environ

    def test_cpu_does_not_trigger(self, monkeypatch):
        _patch_gpu(monkeypatch, cuda=False, mps=False)
        monkeypatch.delenv("TIMM_FUSED_ATTN", raising=False)
        resolve_device("cpu")
        assert "TIMM_FUSED_ATTN" not in os.environ


# ---------------------------------------------------------------------------
# clear_device_cache
# ---------------------------------------------------------------------------


class TestClearDeviceCache:
    """Dispatches to correct backend cache clear."""

    def test_cuda_clears_cache(self, monkeypatch):
        mock_empty = MagicMock()
        monkeypatch.setattr(torch.cuda, "empty_cache", mock_empty)
        clear_device_cache("cuda")
        mock_empty.assert_called_once()

    def test_mps_clears_cache(self, monkeypatch):
        mock_empty = MagicMock()
        monkeypatch.setattr(torch.mps, "empty_cache", mock_empty)
        clear_device_cache("mps")
        mock_empty.assert_called_once()

    def test_cpu_is_noop(self):
        # Should not raise
        clear_device_cache("cpu")

    def test_accepts_torch_device_object(self, monkeypatch):
        mock_empty = MagicMock()
        monkeypatch.setattr(torch.cuda, "empty_cache", mock_empty)
        clear_device_cache(torch.device("cuda"))
        mock_empty.assert_called_once()

    def test_accepts_mps_device_object(self, monkeypatch):
        mock_empty = MagicMock()
        monkeypatch.setattr(torch.mps, "empty_cache", mock_empty)
        clear_device_cache(torch.device("mps"))
        mock_empty.assert_called_once()
