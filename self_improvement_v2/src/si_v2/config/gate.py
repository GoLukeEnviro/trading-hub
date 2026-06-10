"""Environment gate — guards real adapter instantiation behind env vars.

All real adapter base classes call ``require_env_enabled`` during
``__init__``, ensuring they cannot be instantiated without the correct
environment variable being set to ``"1"`` (case-sensitive).

Typical usage::

    from si_v2.config.gate import require_env_enabled

    class RealDockerAdapter(RealAdapterBase):
        def __init__(self, ...) -> None:
            require_env_enabled(SI_V2_ENABLE_REAL_ADAPTERS, self.__class__.__name__)
            ...
"""

from __future__ import annotations

import os

#: Default gate flag for real adapters. Set ``SI_V2_ENABLE_REAL_ADAPTERS=1``
#: in the environment to allow real adapter instantiation.
SI_V2_ENABLE_REAL_ADAPTERS: str = "SI_V2_ENABLE_REAL_ADAPTERS"


def check_env_enabled(flag_name: str, default: bool = False) -> bool:
    """Check whether *flag_name* is set to ``"1"`` in ``os.environ``.

    Only the literal string ``"1"`` is considered enabled. ``"0"``,
    ``"true"``, ``"yes"``, or absence all return the default.

    Args:
        flag_name: Environment variable name to check.
        default: Value returned when the variable is absent or not ``"1"``.

    Returns:
        ``True`` only if ``os.environ[flag_name] == "1"``; otherwise
        *default*.
    """
    val = os.environ.get(flag_name)
    if val is None:
        return default
    return val == "1"


def require_env_enabled(flag_name: str, component: str) -> None:
    """Require *flag_name* to be ``"1"`` in ``os.environ``, or raise.

    Args:
        flag_name: Environment variable name to check.
        component: Human-readable component name for the error message.

    Raises:
        RuntimeError: If *flag_name* is not set to ``"1"``.
    """
    if not check_env_enabled(flag_name):
        msg = (
            f"{component} requires environment variable {flag_name}=1. "
            f"Current value: {os.environ.get(flag_name, '<not set>')!r}. "
            "Set the variable to '1' and try again."
        )
        raise RuntimeError(msg)
