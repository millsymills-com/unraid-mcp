"""Base GraphQL client with retry, auth, and error mapping."""

from __future__ import annotations

import logging
import re
import time
from typing import Any

import httpx
from pydantic import SecretStr
from tenacity import (
    before_sleep_log,
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
    UnraidValidationError,
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
        api_key: SecretStr | str,
        *,
        verify_ssl: bool = True,
        timeout: int = 30,
        max_retries: int = 3,
    ) -> None:
        self._graphql_url = graphql_url
        # Wrap plain strings so the value can never escape via __repr__ /
        # model_dump on whatever ends up holding a reference to the client.
        self._api_key: SecretStr = api_key if isinstance(api_key, SecretStr) else SecretStr(api_key)
        self._max_retries = max_retries
        if not verify_ssl:
            logger.warning(
                "SSL verification disabled — only safe on trusted networks. Set UNRAID_VERIFY_SSL=true to enable.",
            )
        key_value = self._api_key.get_secret_value()
        self._client = httpx.AsyncClient(
            headers={
                "x-api-key": key_value,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            verify=verify_ssl,
            timeout=httpx.Timeout(timeout),
        )
        # Install the redaction filter on httpx / httpcore loggers so
        # DEBUG-level dumps don't leak the API key. Each client owns its
        # own filter instance so close() can remove exactly its own.
        self._redact_filter = _ApiKeyRedactingFilter(key_value)
        for name in _REDACTED_LOGGER_NAMES:
            logging.getLogger(name).addFilter(self._redact_filter)

    def __repr__(self) -> str:
        return f"{type(self).__name__}(graphql_url={self._graphql_url!r}, api_key=<redacted>)"

    # ── HTTP / GraphQL helpers ──────────────────────────────────────────

    # Truncate raw HTTP error bodies in exception messages so a multi-KB
    # validation error doesn't dominate logs while still leaving room for
    # GraphQL error payloads (which routinely exceed the previous 200-byte
    # cap, hiding the failing field name in the truncated tail).
    _ERROR_BODY_LIMIT = 2000

    def _truncate_body(self, body: str) -> str:
        if len(body) <= self._ERROR_BODY_LIMIT:
            return body
        return f"{body[: self._ERROR_BODY_LIMIT]}… [truncated, {len(body)} bytes total; see DEBUG log for full body]"

    def _raise_for_status(self, response: httpx.Response) -> None:
        """Map HTTP status codes to typed exceptions."""
        if response.is_success:
            return
        status = response.status_code
        full_body = response.text
        if len(full_body) > self._ERROR_BODY_LIMIT:
            logger.debug("HTTP %d full error body: %s", status, full_body)
        body = self._truncate_body(full_body)
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
            full_body = response.text
            if len(full_body) > self._ERROR_BODY_LIMIT:
                logger.debug("Invalid JSON full body (HTTP %d): %s", response.status_code, full_body)
            body = self._truncate_body(full_body)
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

    @staticmethod
    def _extract_error_fields(
        errors: list[Any],
    ) -> tuple[list[str], list[dict[str, Any]], str | None, list[Any] | None, list[dict[str, Any]] | None]:
        """Pull messages, raw entries, and the first-seen code/path/locations from a GraphQL errors list."""
        messages: list[str] = []
        structured: list[dict[str, Any]] = []
        code: str | None = None
        path: list[Any] | None = None
        locations: list[dict[str, Any]] | None = None
        for err in errors:
            if not isinstance(err, dict):
                messages.append(str(err))
                structured.append({"message": str(err)})
                continue
            messages.append(str(err.get("message", "unknown error")))
            structured.append(err)
            if code is None:
                extensions = err.get("extensions") or {}
                ext_code = extensions.get("code") if isinstance(extensions, dict) else None
                if isinstance(ext_code, str):
                    code = ext_code
            if path is None and isinstance(err.get("path"), list):
                path = list(err["path"])
            if locations is None and isinstance(err.get("locations"), list):
                locations = [loc for loc in err["locations"] if isinstance(loc, dict)]
        return messages, structured, code, path, locations

    def _check_graphql_errors(self, payload: dict[str, Any]) -> None:
        """Raise a typed exception if the response contains an ``errors`` array.

        Captures the structured fields the GraphQL spec guarantees on the
        first error: ``extensions.code`` (used for routing), ``path``, and
        ``locations``. Routes via ``extensions.code`` when present:
        ``UNAUTHENTICATED``/``FORBIDDEN`` → :class:`UnraidAuthError`,
        ``NOT_FOUND`` → :class:`UnraidNotFoundError`,
        ``GRAPHQL_VALIDATION_FAILED`` → :class:`UnraidValidationError`.
        Otherwise falls back to :class:`UnraidGraphQLError` with the raw
        errors list, code, path, and locations preserved on the exception
        so callers (logs, metrics, error mappers) can branch on them.
        """
        errors = payload.get("errors")
        if not errors or not isinstance(errors, list):
            return
        messages, structured, code, path, locations = self._extract_error_fields(errors)
        joined = "; ".join(messages)
        if code in {"UNAUTHENTICATED", "FORBIDDEN"}:
            raise UnraidAuthError(joined)
        if code == "NOT_FOUND":
            raise UnraidNotFoundError(joined)
        exc_type: type[UnraidGraphQLError] = (
            UnraidValidationError if code == "GRAPHQL_VALIDATION_FAILED" else UnraidGraphQLError
        )
        raise exc_type(
            joined,
            code=code,
            errors=structured,
            path=path,
            locations=locations,
        )

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
            before_sleep=before_sleep_log(logger, logging.WARNING),
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
