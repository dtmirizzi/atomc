"""Built-in kernel registration.

Importing this module imports the adapter modules (which are dependency-free) but never the
hardware engines themselves. Call :func:`register_builtin_kernels` / :func:`create_registry` to
wire the four optional kernels into a :class:`DefaultKernelRegistry`.
"""

from __future__ import annotations

from atomcd.kernel_protocol import KernelFactory
from atomcd.kernels.atopile import AtopileKernel
from atomcd.kernels.kiutils import KiutilsKernel
from atomcd.kernels.ocp import OcpKernel
from atomcd.kernels.registry import DefaultKernelRegistry
from atomcd.kernels.renode import RenodeKernel

BUILTIN_KERNELS: dict[str, KernelFactory] = {
    "atopile": AtopileKernel,
    "kiutils": KiutilsKernel,
    "ocp": OcpKernel,
    "renode": RenodeKernel,
}


def register_builtin_kernels(registry: DefaultKernelRegistry) -> DefaultKernelRegistry:
    """Register every built-in kernel factory (idempotent)."""
    for name, factory in BUILTIN_KERNELS.items():
        registry.register(name, factory)
    return registry


def create_registry() -> DefaultKernelRegistry:
    """Return a registry with all built-in (lazy, optional) kernels registered."""
    return register_builtin_kernels(DefaultKernelRegistry())


__all__ = ["BUILTIN_KERNELS", "create_registry", "register_builtin_kernels"]
