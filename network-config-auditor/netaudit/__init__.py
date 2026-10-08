"""Offline, evidence-based network configuration auditing."""

__version__ = "0.2.3"

from .parser import parse_config
from .rules import audit

__all__ = ["parse_config", "audit", "__version__"]
