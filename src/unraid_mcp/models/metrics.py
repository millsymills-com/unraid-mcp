"""Metrics models: CPU / memory / temperature snapshots.

Mirrors ``Query.metrics`` (``Metrics`` type). ``cpu``/``memory``/``temperature``
are all nullable on the schema, so the top-level fields are ``Optional``. The
unbounded ``TemperatureSensor.history`` array is deliberately not modeled — it
belongs to the streaming subscription, not the snapshot tool.
"""

from __future__ import annotations

from unraid_mcp.models.common import BigInt, UnraidBaseModel


class CpuLoad(UnraidBaseModel):
    """Per-core CPU load (percent fields only)."""

    percent_total: float | None = None


class CpuUtilization(UnraidBaseModel):
    """Aggregate CPU utilization plus per-core load."""

    percent_total: float | None = None
    cpus: list[CpuLoad] | None = None


class MemoryUtilization(UnraidBaseModel):
    """System and swap memory utilization. Byte counts are ``BigInt`` (str)."""

    total: BigInt = None
    used: BigInt = None
    free: BigInt = None
    available: BigInt = None
    active: BigInt = None
    buffcache: BigInt = None
    percent_total: float | None = None
    swap_total: BigInt = None
    swap_used: BigInt = None
    swap_free: BigInt = None
    percent_swap_total: float | None = None


class TemperatureReading(UnraidBaseModel):
    """A single temperature value with unit and status."""

    value: float | None = None
    unit: str | None = None
    timestamp: str | None = None
    status: str | None = None


class TemperatureSensor(UnraidBaseModel):
    """One temperature sensor.

    ``history`` is intentionally omitted — it is unbounded and belongs to the
    streaming subscription, not this snapshot.
    """

    name: str | None = None
    type: str | None = None
    location: str | None = None
    current: TemperatureReading | None = None
    min: TemperatureReading | None = None
    max: TemperatureReading | None = None
    warning: float | None = None
    critical: float | None = None


class TemperatureSummary(UnraidBaseModel):
    """Aggregate temperature summary across all sensors."""

    average: float | None = None
    hottest: TemperatureSensor | None = None
    coolest: TemperatureSensor | None = None
    warning_count: int | None = None
    critical_count: int | None = None


class TemperatureMetrics(UnraidBaseModel):
    """Temperature sensors plus summary."""

    sensors: list[TemperatureSensor] | None = None
    summary: TemperatureSummary | None = None


class Metrics(UnraidBaseModel):
    """Top-level metrics snapshot (``Query.metrics``)."""

    cpu: CpuUtilization | None = None
    memory: MemoryUtilization | None = None
    temperature: TemperatureMetrics | None = None
