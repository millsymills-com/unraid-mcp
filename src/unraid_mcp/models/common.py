"""Shared model types for Unraid GraphQL responses."""

from __future__ import annotations

from pydantic import BaseModel


class UnraidBaseModel(BaseModel):
    """Base model that tolerates unknown fields from the Unraid API."""

    model_config = {"extra": "allow"}
