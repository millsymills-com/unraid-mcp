"""Curated Unraid system variables model.

Mirrors a curated subset of ``Query.vars`` (``Vars`` type). ``csrfToken`` is a
session secret and is deliberately never modeled or selected (PROTO-012).
"""

from __future__ import annotations

from typing import Literal

from unraid_mcp.models.common import UnraidBaseModel

RegistrationState = Literal[
    "TRIAL",
    "BASIC",
    "PLUS",
    "PRO",
    "STARTER",
    "UNLEASHED",
    "LIFETIME",
    "EEXPIRED",
    "EGUID",
    "EGUID1",
    "ETRIAL",
    "ENOKEYFILE",
    "ENOKEYFILE1",
    "ENOKEYFILE2",
    "ENOFLASH",
    "ENOFLASH1",
    "ENOFLASH2",
    "ENOFLASH3",
    "ENOFLASH4",
    "ENOFLASH5",
    "ENOFLASH6",
    "ENOFLASH7",
    "EBLACKLISTED",
    "EBLACKLISTED1",
    "EBLACKLISTED2",
    "ENOCONN",
]
"""``RegistrationState`` enum (26 variants)."""

RegistrationType = Literal["BASIC", "PLUS", "PRO", "STARTER", "UNLEASHED", "LIFETIME", "INVALID", "TRIAL"]
"""``registrationType`` enum."""


class Vars(UnraidBaseModel):
    """Curated, secret-free subset of Unraid system variables."""

    id: str | None = None
    version: str | None = None
    name: str | None = None
    time_zone: str | None = None
    comment: str | None = None
    workgroup: str | None = None
    domain: str | None = None
    sys_model: str | None = None
    sys_array_slots: int | None = None
    sys_cache_slots: int | None = None
    sys_flash_slots: int | None = None
    use_ssl: bool | None = None
    port: int | None = None
    portssl: int | None = None
    use_ssh: bool | None = None
    portssh: int | None = None
    use_telnet: bool | None = None
    use_ntp: bool | None = None
    ntp_server1: str | None = None
    ntp_server2: str | None = None
    ntp_server3: str | None = None
    ntp_server4: str | None = None
    start_array: bool | None = None
    spindown_delay: str | None = None
    default_format: str | None = None
    default_fs_type: str | None = None
    share_count: int | None = None
    share_smb_count: int | None = None
    share_nfs_count: int | None = None
    share_afp_count: int | None = None
    device_count: int | None = None
    md_num_disks: int | None = None
    md_state: str | None = None
    fs_state: str | None = None
    reg_state: RegistrationState | None = None
    reg_ty: RegistrationType | None = None
    flash_product: str | None = None
    flash_vendor: str | None = None
    config_valid: bool | None = None
    safe_mode: bool | None = None
