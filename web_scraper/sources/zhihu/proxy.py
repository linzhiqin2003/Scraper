"""Backward compatibility: re-export from core.proxy."""

from ...core.proxy import ProxyInfo, ProxyPoolConfig, ProxyPool

__all__ = ["ProxyInfo", "ProxyPoolConfig", "ProxyPool"]
