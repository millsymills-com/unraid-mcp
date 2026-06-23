"""Tests for Phase-1 read methods on UnraidClient.

Exercises the typed query/model path for metrics, UPS, plugins, logs, OIDC,
network/cloud/services/settings/system-time/vars, assignable disks, and rclone.
Also asserts the security-sensitive fields are never selected by the query
constants (PROTO-012).
"""

from __future__ import annotations

import json

import httpx
import pytest
import pytest_asyncio
import respx

from unraid_mcp.clients import unraid as unraid_module
from unraid_mcp.clients.unraid import UnraidClient
from unraid_mcp.errors import UnraidError, UnraidNotFoundError
from unraid_mcp.models.network import ApiKeyHealth

GRAPHQL_URL = "https://tower.local:443/graphql"


@pytest_asyncio.fixture
async def client():
    c = UnraidClient(graphql_url=GRAPHQL_URL, api_key="test-key", timeout=5, max_retries=2)
    yield c
    await c.close()


def _ok(data: dict) -> httpx.Response:
    return httpx.Response(200, json={"data": data})


class TestGetMetrics:
    @respx.mock
    async def test_parses_cpu_memory_temperature(self, client):
        metrics = {
            "cpu": {"percentTotal": 12.5, "cpus": [{"percentTotal": 10.0}, {"percentTotal": 15.0}]},
            "memory": {"total": 1024, "percentTotal": 50.0, "swapTotal": "2048"},
            "temperature": {"summary": {"average": 40.0}, "sensors": [{"name": "Core 0"}]},
        }
        respx.post(GRAPHQL_URL).mock(return_value=_ok({"metrics": metrics}))
        result = await client.get_metrics()
        assert result.cpu is not None
        assert result.cpu.percent_total == 12.5
        assert result.cpu.cpus is not None
        assert [c.percent_total for c in result.cpu.cpus] == [10.0, 15.0]
        # BigInt coercion: numeric and string both land as str.
        assert result.memory is not None
        assert result.memory.total == "1024"
        assert result.memory.swap_total == "2048"

    @respx.mock
    async def test_nullable_sections_normalize(self, client):
        respx.post(GRAPHQL_URL).mock(return_value=_ok({"metrics": {"cpu": None, "memory": None}}))
        result = await client.get_metrics()
        assert result.cpu is None
        assert result.memory is None


class TestUps:
    @respx.mock
    async def test_list_ups_devices(self, client):
        devices = [{"id": "ups1", "name": "Tower UPS", "battery": {"chargeLevel": 100}}]
        respx.post(GRAPHQL_URL).mock(return_value=_ok({"upsDevices": devices}))
        result = await client.list_ups_devices()
        assert result[0].id == "ups1"
        assert result[0].battery is not None
        assert result[0].battery.charge_level == 100

    @respx.mock
    async def test_get_ups_device_found(self, client):
        respx.post(GRAPHQL_URL).mock(return_value=_ok({"upsDeviceById": {"id": "ups1", "name": "Tower"}}))
        result = await client.get_ups_device("ups1")
        assert result.id == "ups1"

    @respx.mock
    async def test_get_ups_device_missing_raises(self, client):
        respx.post(GRAPHQL_URL).mock(return_value=_ok({"upsDeviceById": None}))
        with pytest.raises(UnraidNotFoundError, match="ups-x"):
            await client.get_ups_device("ups-x")

    @respx.mock
    async def test_get_ups_device_non_dict_raises(self, client):
        respx.post(GRAPHQL_URL).mock(return_value=_ok({"upsDeviceById": "garbage"}))
        with pytest.raises(UnraidError, match="upsDeviceById"):
            await client.get_ups_device("ups1")

    @respx.mock
    async def test_ups_configuration_model_name_alias(self, client):
        respx.post(GRAPHQL_URL).mock(
            return_value=_ok({"upsConfiguration": {"service": "enable", "modelName": "APC"}}),
        )
        result = await client.get_ups_configuration()
        assert result.service == "enable"
        assert result.model_name == "APC"


class TestPlugins:
    @respx.mock
    async def test_list_plugins(self, client):
        respx.post(GRAPHQL_URL).mock(
            return_value=_ok({"plugins": [{"name": "dynamix", "version": "1.0", "hasApiModule": True}]}),
        )
        result = await client.list_plugins()
        assert result[0].name == "dynamix"
        assert result[0].has_api_module is True

    @respx.mock
    async def test_list_installed_unraid_plugins_returns_strings(self, client):
        respx.post(GRAPHQL_URL).mock(return_value=_ok({"installedUnraidPlugins": ["a.plg", "b.plg"]}))
        result = await client.list_installed_unraid_plugins()
        assert result == ["a.plg", "b.plg"]

    @respx.mock
    async def test_get_plugin_install_operation_missing_raises(self, client):
        respx.post(GRAPHQL_URL).mock(return_value=_ok({"pluginInstallOperation": None}))
        with pytest.raises(UnraidNotFoundError, match="op-1"):
            await client.get_plugin_install_operation("op-1")

    @respx.mock
    async def test_get_plugin_install_operation_non_dict_raises(self, client):
        respx.post(GRAPHQL_URL).mock(return_value=_ok({"pluginInstallOperation": "garbage"}))
        with pytest.raises(UnraidError, match="pluginInstallOperation"):
            await client.get_plugin_install_operation("op-1")


class TestLogs:
    @respx.mock
    async def test_list_log_files(self, client):
        respx.post(GRAPHQL_URL).mock(return_value=_ok({"logFiles": [{"name": "syslog", "path": "/var/log/syslog"}]}))
        result = await client.list_log_files()
        assert result[0].path == "/var/log/syslog"

    @respx.mock
    async def test_read_log_file_passes_paging_variables(self, client):
        route = respx.post(GRAPHQL_URL).mock(
            return_value=_ok({"logFile": {"path": "/p", "content": "x", "totalLines": 1, "startLine": 5}}),
        )
        result = await client.read_log_file("/p", lines=10, start_line=5)
        assert result.start_line == 5
        sent = json.loads(route.calls.last.request.content)
        assert sent["variables"] == {"path": "/p", "lines": 10, "startLine": 5}


class TestOidc:
    @respx.mock
    async def test_get_sso_status(self, client):
        respx.post(GRAPHQL_URL).mock(return_value=_ok({"isSSOEnabled": True}))
        assert await client.get_sso_status() is True

    @respx.mock
    async def test_get_sso_status_false(self, client):
        respx.post(GRAPHQL_URL).mock(return_value=_ok({"isSSOEnabled": False}))
        assert await client.get_sso_status() is False

    @respx.mock
    async def test_get_sso_status_missing_field_raises(self, client):
        respx.post(GRAPHQL_URL).mock(return_value=_ok({}))
        with pytest.raises(UnraidError, match="isSSOEnabled"):
            await client.get_sso_status()

    @respx.mock
    async def test_get_sso_status_null_raises(self, client):
        respx.post(GRAPHQL_URL).mock(return_value=_ok({"isSSOEnabled": None}))
        with pytest.raises(UnraidError, match="isSSOEnabled"):
            await client.get_sso_status()

    @respx.mock
    async def test_list_public_oidc_providers(self, client):
        respx.post(GRAPHQL_URL).mock(
            return_value=_ok({"publicOidcProviders": [{"id": "google", "name": "Google"}]}),
        )
        result = await client.list_public_oidc_providers()
        assert result[0].id == "google"


class TestSystemExtras:
    @respx.mock
    async def test_get_network(self, client):
        respx.post(GRAPHQL_URL).mock(
            return_value=_ok({"network": {"id": "n1", "accessUrls": [{"type": "LAN", "ipv4": "http://x"}]}}),
        )
        result = await client.get_network()
        assert result.access_urls is not None
        assert result.access_urls[0].ipv4 == "http://x"

    @respx.mock
    async def test_get_cloud_health(self, client):
        respx.post(GRAPHQL_URL).mock(
            return_value=_ok({"cloud": {"error": None, "apiKey": {"valid": True}, "allowedOrigins": ["a"]}}),
        )
        result = await client.get_cloud()
        assert result.api_key is not None
        assert result.api_key.valid is True

    @respx.mock
    async def test_get_system_time(self, client):
        respx.post(GRAPHQL_URL).mock(
            return_value=_ok({"systemTime": {"currentTime": "2026-01-01T00:00:00Z", "useNtp": True}}),
        )
        result = await client.get_system_time()
        assert result.use_ntp is True

    @respx.mock
    async def test_get_vars(self, client):
        respx.post(GRAPHQL_URL).mock(return_value=_ok({"vars": {"version": "6.12", "shareCount": 3}}))
        result = await client.get_vars()
        assert result.version == "6.12"
        assert result.share_count == 3

    @respx.mock
    async def test_list_assignable_disks(self, client):
        respx.post(GRAPHQL_URL).mock(return_value=_ok({"assignableDisks": [{"id": "d1", "name": "new"}]}))
        result = await client.list_assignable_disks()
        assert result[0].id == "d1"

    @respx.mock
    async def test_get_rclone_config_redacts_credentials(self, client):
        rclone = {"remotes": [{"name": "gdrive", "type": "drive"}], "drives": [{"name": "s3"}]}
        respx.post(GRAPHQL_URL).mock(return_value=_ok({"rclone": rclone}))
        result = await client.get_rclone_config()
        assert result.remotes is not None
        assert result.remotes[0].name == "gdrive"
        assert result.drives is not None
        assert result.drives[0].name == "s3"


class TestNonNullRootDriftRaises:
    """#248: schema-non-null roots raise on null instead of fabricating ``{}``."""

    @pytest.mark.parametrize(
        ("key", "method"),
        [
            ("cloud", "get_cloud"),
            ("network", "get_network"),
            ("rclone", "get_rclone_config"),
            ("upsConfiguration", "get_ups_configuration"),
            ("metrics", "get_metrics"),
            ("display", "get_display_settings"),
            ("settings", "get_api_settings"),
            ("systemTime", "get_system_time"),
            ("vars", "get_vars"),
            ("info", "get_info"),
            ("array", "get_array"),
            ("vms", "list_vms"),
            ("me", "get_me"),
            ("notifications", "list_notifications"),
            ("flash", "get_flash"),
            ("connect", "get_connect"),
            ("docker", "list_containers"),
            ("docker", "list_docker_networks"),
        ],
    )
    @respx.mock
    async def test_null_non_null_root_raises(self, client, key, method):
        respx.post(GRAPHQL_URL).mock(return_value=_ok({key: None}))
        with pytest.raises(UnraidError, match=key):
            await getattr(client, method)()

    @respx.mock
    async def test_null_log_file_root_raises(self, client):
        respx.post(GRAPHQL_URL).mock(return_value=_ok({"logFile": None}))
        with pytest.raises(UnraidError, match="logFile"):
            await client.read_log_file("/var/log/syslog")

    @respx.mock
    async def test_nullable_list_root_normalizes_to_empty(self, client):
        respx.post(GRAPHQL_URL).mock(return_value=_ok({"services": None}))
        assert await client.list_services() == []


class TestUnknownEnumTolerance:
    """#255: an enum variant absent from the schema snapshot passes through as a
    plain string instead of raising ``ValidationError`` and failing the tool."""

    @respx.mock
    async def test_unknown_temperature_enum_passes_through(self, client):
        metrics = {
            "temperature": {
                "sensors": [{"name": "Core 0", "type": "QUANTUM", "current": {"unit": "PLANCK", "status": "MELTING"}}],
            },
        }
        respx.post(GRAPHQL_URL).mock(return_value=_ok({"metrics": metrics}))
        result = await client.get_metrics()
        assert result.temperature is not None
        assert result.temperature.sensors is not None
        sensor = result.temperature.sensors[0]
        assert sensor.type == "QUANTUM"
        assert sensor.current is not None
        assert sensor.current.unit == "PLANCK"
        assert sensor.current.status == "MELTING"

    @respx.mock
    async def test_unknown_registration_state_passes_through(self, client):
        respx.post(GRAPHQL_URL).mock(return_value=_ok({"vars": {"regState": "EFUTUREVARIANT", "regTy": "QUANTUM"}}))
        result = await client.get_vars()
        assert result.reg_state == "EFUTUREVARIANT"
        assert result.reg_ty == "QUANTUM"


class TestSecurityOmissions:
    """PROTO-012: secret-bearing fields are never selected by the queries."""

    def test_vars_query_omits_csrf_token(self):
        assert "csrfToken" not in unraid_module.QUERY_VARS

    def test_vars_query_omits_nan_prone_cache_slots(self):
        # #260: the server emits NaN for sysCacheSlots, which fails the whole
        # vars read; it must never be selected.
        assert "sysCacheSlots" not in unraid_module.QUERY_VARS

    def test_cloud_apikey_model_has_no_key_material(self):
        assert set(ApiKeyHealth.model_fields) == {"valid", "error"}
        assert "clientSecret" not in unraid_module.QUERY_CLOUD

    def test_rclone_query_omits_parameters_and_config(self):
        assert "parameters" not in unraid_module.QUERY_RCLONE_CONFIG
        assert "config" not in unraid_module.QUERY_RCLONE_CONFIG

    def test_rclone_query_omits_null_prone_drives(self):
        # #261: the server returns null for the non-null ``drives`` field,
        # failing the whole rclone read; it must never be selected.
        assert "drives" not in unraid_module.QUERY_RCLONE_CONFIG

    def test_display_query_omits_base64(self):
        assert "base64" not in unraid_module.QUERY_DISPLAY

    def test_metrics_query_omits_sensor_history(self):
        assert "history" not in unraid_module.QUERY_METRICS

    def test_no_oidc_provider_query_selects_client_secret(self):
        assert "clientSecret" not in unraid_module.QUERY_PUBLIC_OIDC_PROVIDERS
