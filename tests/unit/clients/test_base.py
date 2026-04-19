"""Tests for the base GraphQL client."""

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
    async def test_missing_data_field_raises_unraid_error(self, client):
        respx.post(GRAPHQL_URL).mock(return_value=httpx.Response(200, json={}))
        with pytest.raises(UnraidError, match="missing 'data' field"):
            await client.query("query { x }")


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


class TestClose:
    async def test_close_calls_aclose(self, client):
        await client.close()
        assert client._client.is_closed
