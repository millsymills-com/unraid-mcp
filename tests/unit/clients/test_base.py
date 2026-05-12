"""Tests for the base GraphQL client."""

import logging

import httpx
import pytest
import respx

from unraid_mcp.clients.base import BaseGraphQLClient
from unraid_mcp.errors import (
    UnraidAuthError,
    UnraidConnectionError,
    UnraidError,
    UnraidGraphQLError,
    UnraidNotFoundError,
    UnraidRateLimitError,
)

GRAPHQL_URL = "https://tower.local:443/graphql"


@pytest.fixture
def client():
    return BaseGraphQLClient(
        graphql_url=GRAPHQL_URL,
        api_key="test-api-key",
        verify_ssl=False,
        timeout=5,
        max_retries=2,
    )


class TestQuery:
    @respx.mock
    async def test_query_returns_data(self, client):
        respx.post(GRAPHQL_URL).mock(return_value=httpx.Response(200, json={"data": {"info": {"os": {}}}}))
        result = await client.query("query { info { os { platform } } }")
        assert result == {"info": {"os": {}}}

    @respx.mock
    async def test_api_key_header_included(self, client):
        route = respx.post(GRAPHQL_URL).mock(return_value=httpx.Response(200, json={"data": {"x": 1}}))
        await client.query("query { x }")
        assert route.calls[0].request.headers["x-api-key"] == "test-api-key"

    @respx.mock
    async def test_query_includes_variables(self, client):
        import json

        route = respx.post(GRAPHQL_URL).mock(return_value=httpx.Response(200, json={"data": {"x": 1}}))
        await client.query("query Q($id: ID!) { thing(id: $id) }", variables={"id": "abc"})
        sent = json.loads(route.calls[0].request.content)
        assert sent["query"].startswith("query Q")
        assert sent["variables"] == {"id": "abc"}


class TestMutate:
    @respx.mock
    async def test_mutate_returns_data(self, client):
        respx.post(GRAPHQL_URL).mock(
            return_value=httpx.Response(200, json={"data": {"startArray": {"state": "STARTED"}}})
        )
        result = await client.mutate("mutation { startArray { state } }")
        assert result == {"startArray": {"state": "STARTED"}}


class TestErrorMapping:
    @respx.mock
    async def test_401_raises_auth_error(self, client):
        respx.post(GRAPHQL_URL).mock(return_value=httpx.Response(401, text="Unauthorized"))
        with pytest.raises(UnraidAuthError, match="401"):
            await client.query("query { x }")

    @respx.mock
    async def test_403_raises_auth_error(self, client):
        respx.post(GRAPHQL_URL).mock(return_value=httpx.Response(403, text="Forbidden"))
        with pytest.raises(UnraidAuthError, match="403"):
            await client.query("query { x }")

    @respx.mock
    async def test_404_raises_not_found(self, client):
        respx.post(GRAPHQL_URL).mock(return_value=httpx.Response(404, text="Not Found"))
        with pytest.raises(UnraidNotFoundError, match="404"):
            await client.query("query { x }")

    @respx.mock
    async def test_429_raises_rate_limit(self, client):
        respx.post(GRAPHQL_URL).mock(return_value=httpx.Response(429, text="Too Many Requests"))
        with pytest.raises(UnraidRateLimitError, match="429"):
            await client.query("query { x }")

    @respx.mock
    async def test_500_raises_generic_error(self, client):
        respx.post(GRAPHQL_URL).mock(return_value=httpx.Response(500, text="Internal Server Error"))
        with pytest.raises(UnraidError, match="500"):
            await client.query("query { x }")

    @respx.mock
    async def test_graphql_errors_array_raises_graphql_error(self, client):
        respx.post(GRAPHQL_URL).mock(
            return_value=httpx.Response(
                200,
                json={"errors": [{"message": "Field 'foo' not found"}], "data": None},
            )
        )
        with pytest.raises(UnraidGraphQLError, match="Field 'foo' not found"):
            await client.query("query { foo }")

    @respx.mock
    async def test_graphql_unauthenticated_code_raises_auth_error(self, client):
        respx.post(GRAPHQL_URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "errors": [{"message": "Missing API key", "extensions": {"code": "UNAUTHENTICATED"}}],
                    "data": None,
                },
            )
        )
        with pytest.raises(UnraidAuthError, match="Missing API key"):
            await client.query("query { x }")

    @respx.mock
    async def test_graphql_forbidden_code_raises_auth_error(self, client):
        respx.post(GRAPHQL_URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "errors": [{"message": "Role insufficient", "extensions": {"code": "FORBIDDEN"}}],
                    "data": None,
                },
            )
        )
        with pytest.raises(UnraidAuthError, match="Role insufficient"):
            await client.query("query { x }")

    @respx.mock
    async def test_graphql_not_found_code_raises_not_found_error(self, client):
        respx.post(GRAPHQL_URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "errors": [{"message": "Container abc not found", "extensions": {"code": "NOT_FOUND"}}],
                    "data": None,
                },
            )
        )
        with pytest.raises(UnraidNotFoundError, match="Container abc not found"):
            await client.query("query { x }")

    @respx.mock
    async def test_graphql_unknown_code_falls_back_to_graphql_error(self, client):
        respx.post(GRAPHQL_URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "errors": [{"message": "Internal boom", "extensions": {"code": "INTERNAL_SERVER_ERROR"}}],
                    "data": None,
                },
            )
        )
        with pytest.raises(UnraidGraphQLError, match="Internal boom"):
            await client.query("query { x }")

    @respx.mock
    async def test_missing_data_field_raises_unraid_error(self, client):
        respx.post(GRAPHQL_URL).mock(return_value=httpx.Response(200, json={}))
        with pytest.raises(UnraidError, match="missing 'data' field"):
            await client.query("query { x }")


class TestErrorBodyTruncation:
    """HTTP / JSON error bodies must keep enough context to identify the failure (#80)."""

    @respx.mock
    async def test_error_body_under_limit_is_not_truncated(self, client):
        body = '{"errors":[{"message":"Cannot query field \\"dockerContainers\\" on type \\"Query\\"."}]}'
        respx.post(GRAPHQL_URL).mock(return_value=httpx.Response(400, text=body))
        with pytest.raises(UnraidError) as exc_info:
            await client.query("query { x }")
        assert "dockerContainers" in str(exc_info.value)
        assert "truncated" not in str(exc_info.value)

    @respx.mock
    async def test_error_body_over_limit_is_truncated_with_marker(self, client, caplog):
        long_body = "x" * 5000
        respx.post(GRAPHQL_URL).mock(return_value=httpx.Response(500, text=long_body))
        with (
            caplog.at_level("DEBUG", logger="unraid_mcp.clients.base"),
            pytest.raises(UnraidError) as exc_info,
        ):
            await client.query("query { x }")
        message = str(exc_info.value)
        assert "[truncated, 5000 bytes total" in message
        assert len(message) < 5000
        debug_lines = [r for r in caplog.records if r.levelname == "DEBUG" and "full error body" in r.message]
        assert debug_lines, "expected a DEBUG line with the full body"
        assert long_body in debug_lines[0].message

    @respx.mock
    async def test_invalid_json_truncates_and_logs_full_body(self, client, caplog):
        long_body = "not json " * 500
        respx.post(GRAPHQL_URL).mock(
            return_value=httpx.Response(200, content=long_body.encode(), headers={"content-type": "application/json"})
        )
        with (
            caplog.at_level("DEBUG", logger="unraid_mcp.clients.base"),
            pytest.raises(UnraidError, match="Invalid JSON") as exc_info,
        ):
            await client.query("query { x }")
        message = str(exc_info.value)
        assert "[truncated" in message
        debug_lines = [r for r in caplog.records if r.levelname == "DEBUG" and "Invalid JSON full body" in r.message]
        assert debug_lines, "expected a DEBUG line with the full invalid-JSON body"


class TestMalformedJson:
    @respx.mock
    async def test_invalid_json_raises_unraid_error(self, client):
        respx.post(GRAPHQL_URL).mock(
            return_value=httpx.Response(200, content=b"not json", headers={"content-type": "application/json"})
        )
        with pytest.raises(UnraidError, match="Invalid JSON") as exc_info:
            await client.query("query { x }")
        assert exc_info.value.status_code is None

    @respx.mock
    async def test_array_top_level_raises_unraid_error(self, client):
        respx.post(GRAPHQL_URL).mock(return_value=httpx.Response(200, json=[]))
        with pytest.raises(UnraidError, match="Unexpected GraphQL response shape"):
            await client.query("query { x }")


class TestRetry:
    @respx.mock
    async def test_retries_on_connect_error_then_succeeds(self, client):
        route = respx.post(GRAPHQL_URL)
        route.side_effect = [
            httpx.ConnectError("Connection refused"),
            httpx.Response(200, json={"data": {"ok": True}}),
        ]
        result = await client.query("query { ok }")
        assert result == {"ok": True}
        assert route.call_count == 2

    @respx.mock
    async def test_raises_connection_error_after_retries_exhausted(self, client):
        respx.post(GRAPHQL_URL).mock(side_effect=httpx.ConnectError("Connection refused"))
        with pytest.raises(UnraidConnectionError, match="Connection refused"):
            await client.query("query { x }")

    @respx.mock
    async def test_no_retry_on_auth_error(self, client):
        route = respx.post(GRAPHQL_URL).mock(return_value=httpx.Response(401, text="Unauthorized"))
        with pytest.raises(UnraidAuthError):
            await client.query("query { x }")
        assert route.call_count == 1

    @respx.mock
    async def test_retry_emits_warning_log(self, client, caplog):
        route = respx.post(GRAPHQL_URL)
        route.side_effect = [
            httpx.ConnectError("Connection refused"),
            httpx.Response(200, json={"data": {"ok": True}}),
        ]
        with caplog.at_level("WARNING", logger="unraid_mcp.clients.base"):
            await client.query("query { ok }")
        retry_lines = [r for r in caplog.records if r.levelname == "WARNING" and "Retrying" in r.message]
        assert retry_lines, f"expected a tenacity 'Retrying' WARNING line, got: {[r.message for r in caplog.records]}"
        assert "ConnectError" in retry_lines[0].message


class TestClose:
    async def test_close_calls_aclose(self, client):
        await client.close()
        assert client._client.is_closed


class TestApiKeyRedaction:
    """API-key redaction filter protects against leaking the key via httpx DEBUG logs."""

    async def test_key_is_redacted_in_httpx_logger_output(self, client, caplog):
        # Simulate an httpcore DEBUG log line that includes the request headers.
        raw_key = client._api_key.get_secret_value()
        with caplog.at_level("DEBUG", logger="httpcore.http11"):
            logging.getLogger("httpcore.http11").debug(
                "send_request_headers.started request=%s",
                f"Request(headers={{'x-api-key': '{raw_key}'}})",
            )
        messages = [r.getMessage() for r in caplog.records]
        assert all(raw_key not in m for m in messages), f"API key leaked in log: {messages}"
        assert any("***REDACTED***" in m for m in messages)

    async def test_non_matching_log_lines_pass_through(self, client, caplog):  # noqa: ARG002 — fixture installs the filter
        with caplog.at_level("DEBUG", logger="httpx"):
            logging.getLogger("httpx").debug("some unrelated log line")
        messages = [r.getMessage() for r in caplog.records]
        assert any("some unrelated log line" in m for m in messages)

    async def test_close_detaches_filter(self, client):
        logger_under_test = logging.getLogger("httpx")
        assert client._redact_filter in logger_under_test.filters
        await client.close()
        assert client._redact_filter not in logger_under_test.filters

    async def test_multiple_clients_have_independent_filters(self):
        client_a = BaseGraphQLClient(
            graphql_url="https://a.example/graphql",
            api_key="key-aaaaaaaaaaaa",
        )
        client_b = BaseGraphQLClient(
            graphql_url="https://b.example/graphql",
            api_key="key-bbbbbbbbbbbb",
        )
        try:
            assert client_a._redact_filter is not client_b._redact_filter
            httpx_logger = logging.getLogger("httpx")
            assert client_a._redact_filter in httpx_logger.filters
            assert client_b._redact_filter in httpx_logger.filters
        finally:
            await client_a.close()
            await client_b.close()


class TestObservability:
    """Per-request log lines (timing, status, operation name)."""

    @respx.mock
    async def test_logs_operation_and_timing_on_success(self, client, caplog):
        respx.post(GRAPHQL_URL).mock(return_value=httpx.Response(200, json={"data": {"info": {}}}))
        with caplog.at_level("INFO", logger="unraid_mcp.clients.base"):
            await client.query("query Info { info { os { platform } } }")
        info_lines = [r for r in caplog.records if r.levelname == "INFO" and "graphql Info" in r.message]
        assert info_lines, f"expected an 'graphql Info' INFO line, got: {[r.message for r in caplog.records]}"
        assert "HTTP 200" in info_lines[0].message
        assert "ms" in info_lines[0].message

    @respx.mock
    async def test_warns_on_http_error(self, client, caplog):
        respx.post(GRAPHQL_URL).mock(return_value=httpx.Response(500, text="oops"))
        with (
            caplog.at_level("WARNING", logger="unraid_mcp.clients.base"),
            pytest.raises(UnraidError),
        ):
            await client.query("query Info { x }")
        warn_lines = [r for r in caplog.records if r.levelname == "WARNING"]
        assert warn_lines, "expected a WARNING for HTTP 500"
        assert "HTTP 500" in warn_lines[0].message

    @respx.mock
    async def test_anonymous_query_logs_anonymous(self, client, caplog):
        respx.post(GRAPHQL_URL).mock(return_value=httpx.Response(200, json={"data": {"x": 1}}))
        with caplog.at_level("INFO", logger="unraid_mcp.clients.base"):
            await client.query("{ x }")
        assert any("graphql <anonymous>" in r.message for r in caplog.records)

    @respx.mock
    async def test_explicit_operation_name_wins(self, client, caplog):
        respx.post(GRAPHQL_URL).mock(return_value=httpx.Response(200, json={"data": {"x": 1}}))
        with caplog.at_level("INFO", logger="unraid_mcp.clients.base"):
            await client.query("query InternalName { x }", operation_name="ExplicitName")
        assert any("graphql ExplicitName" in r.message for r in caplog.records)
        assert not any("graphql InternalName" in r.message for r in caplog.records)


class TestRepr:
    """`__repr__` must never contain the raw API key (#77)."""

    async def test_repr_elides_api_key(self):
        secret = "SUPER-SECRET-API-KEY-abc123xyz456"
        client = BaseGraphQLClient(graphql_url=GRAPHQL_URL, api_key=secret)
        try:
            rendered = repr(client)
            assert secret not in rendered
            assert "<redacted>" in rendered
            assert GRAPHQL_URL in rendered
        finally:
            await client.close()

    async def test_repr_redacts_secretstr_input(self):
        from pydantic import SecretStr

        secret = "SUPER-SECRET-API-KEY-abc123xyz456"
        client = BaseGraphQLClient(graphql_url=GRAPHQL_URL, api_key=SecretStr(secret))
        try:
            assert secret not in repr(client)
        finally:
            await client.close()


class TestSslVerificationWarning:
    """Emit a warning at construction time when SSL verification is disabled (#77)."""

    async def test_warns_when_verify_ssl_false(self, caplog):
        with caplog.at_level("WARNING", logger="unraid_mcp.clients.base"):
            client = BaseGraphQLClient(graphql_url=GRAPHQL_URL, api_key="k", verify_ssl=False)
            await client.close()
        assert any("SSL verification disabled" in rec.message for rec in caplog.records)

    async def test_no_warning_when_verify_ssl_true(self, caplog):
        with caplog.at_level("WARNING", logger="unraid_mcp.clients.base"):
            client = BaseGraphQLClient(graphql_url=GRAPHQL_URL, api_key="k", verify_ssl=True)
            await client.close()
        assert not any("SSL verification disabled" in rec.message for rec in caplog.records)
