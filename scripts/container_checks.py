"""Credential-free checks of the built image, never a live Unraid server."""

import asyncio
import importlib.metadata
import json
import os
import re
import ssl
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

import certifi

# Direct and AAA cross-signed chains, including leaves without CT entries.
# https://emudhra.we-have-a-problem.com/ (2026-10-28)
BAD_HOSTS = tuple(
    f"https://{prefix}-emudhra.we-have-a-problem.com/"
    for prefix in ("dv-g3b", "dv-g3b-aaa", "dv-g3b-noct", "dv-g3b-aaa-noct")
)
GOOD_URL = "https://pypi.org/simple/pip/"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def probe(url, context, *, reject):
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=context), NoRedirect()
    )
    try:
        with opener.open(url, timeout=20) as response:
            assert not reject, f"Compromised chain accepted: {url}"
            assert response.status == 200
    except urllib.error.URLError as exc:
        cause = exc.reason
        # Expiry, hostname mismatch, DNS failure and timeout do not establish distrust.
        if reject and isinstance(cause, ssl.SSLCertVerificationError) and cause.verify_code in {20, 21, 23, 28, 50}:
            print(f"Rejected {url}: certificate verification code {cause.verify_code}")
            return
        raise


def version_tuple(value):
    return tuple(int(part) for part in value.split("."))


def trust():
    assert sys.version_info >= (3, 13, 18)
    assert version_tuple(importlib.metadata.version("certifi")) >= (2026, 10, 19)
    uv = subprocess.check_output(["uv", "--version"], text=True).strip()
    assert version_tuple(uv.split()[1]) >= (0, 13, 5)
    # Query the base interpreter, not just the application virtual environment.
    base = json.loads(
        subprocess.check_output(
            [
                "/usr/local/bin/python",
                "-I",
                "-c",
                "import json,pip,pip._vendor.certifi; print(json.dumps([pip.__version__,pip._vendor.certifi.where()]))",
            ],
            text=True,
        )
    )
    assert version_tuple(base[0]) >= (26, 2, 2)
    print(f"Python {sys.version.split()[0]}; {uv}; base pip {base[0]}; certifi {certifi.__version__}")
    print(subprocess.check_output(["dpkg-query", "-W", "ca-certificates"], text=True).strip())
    for label, context in (
        ("system", ssl.create_default_context()),
        ("application certifi", ssl.create_default_context(cafile=certifi.where())),
        ("base pip bundle", ssl.create_default_context(cafile=base[1])),
    ):
        print(f"Testing {label}")
        probe(GOOD_URL, context, reject=False)
        for url in BAD_HOSTS:
            probe(url, context, reject=True)
    # Exercise uv's actual TLS stack; resolving a requirement does not install it.
    with tempfile.TemporaryDirectory() as directory:
        requirements = Path(directory) / "requirements.in"
        requirements.write_text("pip==26.3\n")
        for url in ("https://pypi.org/simple/", *BAD_HOSTS):
            result = subprocess.run(
                [
                    "uv",
                    "pip",
                    "compile",
                    "--no-config",
                    "--no-cache",
                    "--no-progress",
                    "--index-url",
                    url,
                    str(requirements),
                ],
                text=True,
                capture_output=True,
                timeout=90,
                env={**os.environ, "UV_HTTP_RETRIES": "0", "UV_HTTP_TIMEOUT": "20"},
            )
            if url.startswith("https://pypi.org/"):
                assert result.returncode == 0, "uv normal TLS control failed"
            else:
                assert result.returncode != 0 and re.search(
                    r"(?i)(unknownissuer|certificate.*(unknown issuer|revoked|untrusted)|certificaterevoked)",
                    result.stderr,
                ), f"uv distrust not established for {url}: {result.stderr[-600:]}"
                print(f"uv rejected {url} with certificate verification failure")


async def smoke():
    from fastmcp import Client
    from fastmcp.client.transports import StdioTransport

    assert os.getuid() != 0
    assert not os.environ.get("UNRAID_API_KEY")
    transport = StdioTransport(
        command="unraid-mcp",
        env={
            "UNRAID_API_KEY": "",
            "UNRAID_HOST": "unconfigured.invalid",
            "UNRAID_MODE": "readonly",
            "FASTMCP_CHECK_FOR_UPDATES": "off",
        },
        keep_alive=False,
    )
    async with Client(transport) as client:
        tools = await client.list_tools()
        assert tools
        assert "unraid_start_container" not in {tool.name for tool in tools}
        print(f"Credential-free stdio discovery: {len(tools)} tools; write tool hidden")


if __name__ == "__main__":
    if sys.argv[1:] == ["smoke"]:
        asyncio.run(smoke())
    elif sys.argv[1:] == ["trust"]:
        trust()
    else:
        raise SystemExit("Expected smoke or trust")
