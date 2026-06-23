"""UPS (uninterruptible power supply) models.

Mirrors ``Query.upsDevices`` / ``upsDeviceById`` / ``upsConfiguration``.
"""

from __future__ import annotations

from unraid_mcp.models.common import UnraidBaseModel


class UPSBattery(UnraidBaseModel):
    """UPS battery state."""

    charge_level: int | None = None
    estimated_runtime: int | None = None
    health: str | None = None


class UPSPower(UnraidBaseModel):
    """UPS power readings (voltage / load / wattage)."""

    input_voltage: float | None = None
    output_voltage: float | None = None
    load_percentage: int | None = None
    nominal_power: int | None = None
    current_power: float | None = None


class UPSDevice(UnraidBaseModel):
    """A monitored UPS device."""

    id: str | None = None
    name: str | None = None
    model: str | None = None
    status: str | None = None
    battery: UPSBattery | None = None
    power: UPSPower | None = None


class UPSConfiguration(UnraidBaseModel):
    """UPS monitoring service configuration (apcupsd-style)."""

    service: str | None = None
    ups_cable: str | None = None
    custom_ups_cable: str | None = None
    ups_type: str | None = None
    device: str | None = None
    override_ups_capacity: int | None = None
    battery_level: int | None = None
    minutes: int | None = None
    timeout: int | None = None
    kill_ups: str | None = None
    nis_ip: str | None = None
    net_server: str | None = None
    ups_name: str | None = None
    model_name: str | None = None
