"""Model errors (plan §6.1: the model raises only on structurally
impossible states, never on contract rules — those belong to validation)."""

from __future__ import annotations

__all__ = ["ModelError"]


class ModelError(Exception):
    """Base class for canonical-model construction errors."""
