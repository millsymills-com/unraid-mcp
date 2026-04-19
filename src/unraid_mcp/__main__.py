"""Entry point for running unraid-mcp as a module."""

from unraid_mcp.server import create_server


def main() -> None:
    """Start the Unraid MCP server."""
    server = create_server()
    server.run()


if __name__ == "__main__":
    main()
