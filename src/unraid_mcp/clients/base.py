"""Base GraphQL client with retry, auth, and error mapping."""

from __future__ import annotations

import logging
import re
import time
from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from unraid_mcp.errors import (
    UnraidAuthError,
    UnraidConnectionError,
    UnraidError,
    UnraidGraphQLError,
    UnraidNotFoundError,
    UnraidRateLimitError,
)

logger = logging.getLogger(__name__)

# Match `query Foo { ... }`, `mutation Bar { ... }`, etc. so we can log a
# meaningful operation name even when callers don't set `operationName`.
_OPERATION_NAME_RE = re.compile(r"^\s*(?:query|mutation|subscription)\s+(\w+)")

# Loggers where an operator turning on DEBUG could cause `x-api-key` to be
# emitted verbatim (httpx and its lower-level HTTP engine). We attach a
# redacting filter to these when the client is constructed so the key
# never lands in log output regardless of third-party config.
_REDACTED_LOGGER_NAMES: tuple[str, ...] = ("httpx", "httpcore", "httpcore.http11", "httpcore.connection")


class _ApiKeyRedactingFilter(logging.Filter):
    """Logging filter that replaces occurrences of the Unraid API key with ``***REDACTED***``.

    Attached to third-party loggers in :class:`BaseGraphQLClient` so that
    DEBUG-level httpx / httpcore output (which includes request headers)
    doesn't leak the key even when the caller enables verbose logging.
    """

    def __init__(self, api_key: str) -> None:
        super().__init__(name="unraid_mcp.api_key_redact")
        self._api_key = api_key

    def filter(self, record: logging.LogRecord) -> bool:
        if not self._api_key:
            return True
        try:
            message = record.getMessage()
        except (TypeError, ValueError):
            return True
        if self._api_key in message:
            # Collapse the record to a pre-formatted message so handlers
            # downstream can't re-expand args and pull the key back in.
            record.msg = message.replace(self._api_key, "***REDACTED***")
            record.args = ()
        return True


class BaseGraphQLClient:
    """Base client for the Unraid GraphQL API.

    Provides ``query`` and ``mutate`` helpers, retry on transient HTTP errors,
    and consistent mapping from HTTP / GraphQL error shapes to typed exceptions.
    """

    def __init__(
        self,
        graphql_url: str,
        api_key: str,
        *,
        verify_ssl: bool = False,
        timeout: int = 30,
        max_retries: int = 3,
    ) -> None:
        self._graphql_url = graphql_url
        self._api_key = api_key
        self._max_retries = max_retries
        self._client = httpx.AsyncClient(
            headers={
                "x-api-key": api_key,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            verify=verify_ssl,
            timeout=httpx.Timeout(timeout),
        )
        # Install the redaction filter on httpx / httpcore loggers so
        # DEBUG-level dumps don't leak the API key. Each client owns its
        # own filter instance so close() can remove exactly its own.
        self._redact_filter = _ApiKeyRedactingFilter(api_key)
        for name in _REDACTED_LOGGER_NAMES:
            logging.getLogger(name).addFilter(self._redact_filter)

    # ── HTTP / GraphQL helpers ──────────────────────────────────────────

    def _raise_for_status(self, response: httpx.Response) -> None:
        """Map HTTP status codes to typed exceptions."""
        if response.is_success:
            return
        status = response.status_code
        body = response.text[:200]
        if status in (401, 403):
            raise UnraidAuthError(f"HTTP {status}: {body}", status_code=status)
        if status == 404:
            raise UnraidNotFoundError(f"HTTP {status}: {body}", status_code=status)
        if status == 429:
            raise UnraidRateLimitError(f"HTTP {status}: {body}", status_code=status)
        raise UnraidError(f"HTTP {status}: {body}", status_code=status)

    def _parse_json(self, response: httpx.Response) -> dict[str, Any]:
        """Parse JSON response body, wrapping decode errors as UnraidError."""
        try:
            payload = response.json()
        except ValueError as exc:
            body = response.text[:200]
            raise UnraidError(
                f"Invalid JSON in response (HTTP {response.status_code}): {body}",
                status_code=None,
            ) from exc
        if not isinstance(payload, dict):
            raise UnraidError(
                f"Unexpected GraphQL response shape (expected object, got {type(payload).__name__})",
                status_code=None,
            )
        return payload

    def _check_graphql_errors(self, payload: dict[str, Any]) -> None:
        """Raise a typed exception if the response contains an ``errors`` array.

        Routes via ``extensions.code`` on the first error when present:
        ``UNAUTHENTICATED``/``FORBIDDEN`` → :class:`UnraidAuthError`,
        ``NOT_FOUND`` → :class:`UnraidNotFoundError`. Otherwise falls back
        to :class:`UnraidGraphQLError` with concatenated messages.
        """
        errors = payload.get("errors")
        if not errors:
            return
        messages = []
        code: str | None = None
        for err in errors:
            if isinstance(err, dict):
                messages.append(err.get("message", "unknown error"))
                if code is None:
                    extensions = err.get("extensions") or {}
                    if isinstance(extensions, dict):
                        ext_code = extensions.get("code")
                        if isinstance(ext_code, str):
                            code = ext_code
            else:
                messages.append(str(err))
        joined = "; ".join(messages)
        if code in {"UNAUTHENTICATED", "FORBIDDEN"}:
            raise UnraidAuthError(joined)
        if code == "NOT_FOUND":
            raise UnraidNotFoundError(joined)
        raise UnraidGraphQLError(joined)

    @staticmethod
    def _operation_name(payload: dict[str, Any]) -> str:
        """Best-effort extraction of the GraphQL operation name for log lines."""
        explicit = payload.get("operationName")
        if isinstance(explicit, str) and explicit:
            return explicit
        document = payload.get("query")
        if isinstance(document, str):
            match = _OPERATION_NAME_RE.match(document)
            if match:
                return match.group(1)
        return "<anonymous>"

    async def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        """POST a JSON body to the GraphQL endpoint with retry on transient errors."""

        @retry(
            stop=stop_after_attempt(self._max_retries),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            retry=retry_if_exception_type((httpx.ConnectError, httpx.TimeoutException)),
            reraise=True,
        )
        async def _do() -> httpx.Response:
            return await self._client.post(self._graphql_url, json=payload)

        operation = self._operation_name(payload)
        start = time.perf_counter()
        try:
            response = await _do()
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            elapsed_ms = (time.perf_counter() - start) * 1000
            logger.warning("graphql %s failed after %.0fms: %s", operation, elapsed_ms, exc)
            raise UnraidConnectionError(str(exc)) from exc

        elapsed_ms = (time.perf_counter() - start) * 1000
        log_level = logging.WARNING if response.status_code >= 400 else logging.INFO
        logger.log(log_level, "graphql %s -> HTTP %d in %.0fms", operation, response.status_code, elapsed_ms)

        self._raise_for_status(response)
        body = self._parse_json(response)
        self._check_graphql_errors(body)
        return body

    async def query(
        self,
        query: str,
        variables: dict[str, Any] | None = None,
        operation_name: str | None = None,
    ) -> dict[str, Any]:
        """Execute a GraphQL query and return the ``data`` field.

        Raises:
            UnraidAuthError, UnraidNotFoundError, UnraidRateLimitError,
            UnraidConnectionError, UnraidGraphQLError, UnraidError.
        """
        return await self._execute(query, variables, operation_name)

    async def mutate(
        self,
        mutation: str,
        variables: dict[str, Any] | None = None,
        operation_name: str | None = None,
    ) -> dict[str, Any]:
        """Execute a GraphQL mutation. Same semantics as :meth:`query`."""
        return await self._execute(mutation, variables, operation_name)

    async def _execute(
        self,
        document: str,
        variables: dict[str, Any] | None,
        operation_name: str | None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"query": document}
        if variables:
            payload["variables"] = variables
        if operation_name:
            payload["operationName"] = operation_name
        body = await self._post(payload)
        data = body.get("data")
        if data is None:
            raise UnraidError("GraphQL response missing 'data' field")
        if not isinstance(data, dict):
            raise UnraidError(f"Unexpected GraphQL data shape: {type(data).__name__}")
        return data

    # ── Lifecycle ───────────────────────────────────────────────────────

    async def validate_connection(self) -> None:
        """Validate that the API is reachable and authenticated.

        Subclasses should override with a lightweight health-check query and
        let typed ``UnraidError`` subclasses propagate on failure.
        """
        raise NotImplementedError

    async def close(self) -> None:
        """Close the underlying HTTP client and detach the log-redaction filter."""
        for name in _REDACTED_LOGGER_NAMES:
            logging.getLogger(name).removeFilter(self._redact_filter)
        await self._client.aclose()
