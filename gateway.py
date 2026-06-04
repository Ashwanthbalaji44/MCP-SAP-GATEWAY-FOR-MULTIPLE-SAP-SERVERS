"""
SAP MCP Gateway
Connects Claude to multiple SAP systems via mcp-abap-adt.

Usage:
    py gateway.py                 → stdio mode (for Claude Desktop)
    py gateway.py --http          → HTTP mode on port 8080
    py gateway.py --http --port 9000
"""

import os
import sys
import argparse
import asyncio
from pathlib import Path
from dotenv import load_dotenv
from fastmcp import FastMCP, Client
from fastmcp.client.transports import StdioTransport
from fastmcp.server import create_proxy

# ─── Configuration ────────────────────────────────────────────────────────────

load_dotenv()

# Path to the mcp-abap-adt server (override with MCP_ABAP_ADT_PATH env var)
MCP_ABAP_ADT_PATH = os.environ.get(
    "MCP_ABAP_ADT_PATH",
    "mcp-abap-adt/dist/index.js"
)

# Define your SAP systems here
# Format: "namespace": ("HOST_VAR", "USER_VAR", "PASS_VAR", "CLIENT_VAR")
SAP_SYSTEMS = {
    "sap_dev": ("SAP_DEV_HOST", "SAP_DEV_USER", "SAP_DEV_PASS", "SAP_DEV_CLIENT"),
    "sap_ids": ("SAP_IDS_HOST", "SAP_IDS_USER", "SAP_IDS_PASS", "SAP_IDS_CLIENT"),
    # add more here as needed
}

# ─── Security Checks ──────────────────────────────────────────────────────────

def validate_environment() -> None:
    """Fail fast if anything is misconfigured."""
    # Check mcp-abap-adt exists
    if not Path(MCP_ABAP_ADT_PATH).is_file():
        print(f"❌ mcp-abap-adt not found at: {MCP_ABAP_ADT_PATH}", file=sys.stderr)
        print(f"   Set MCP_ABAP_ADT_PATH in .env to override", file=sys.stderr)
        sys.exit(1)

    # Check all required env vars are present
    missing = []
    for name, vars_needed in SAP_SYSTEMS.items():
        for var in vars_needed:
            if not os.environ.get(var):
                missing.append(f"{var}  (for {name})")

    if missing:
        print("❌ Missing environment variables in .env:", file=sys.stderr)
        for m in missing:
            print(f"   - {m}", file=sys.stderr)
        sys.exit(1)

# ─── Backend Connection ───────────────────────────────────────────────────────

def make_sap_client(sap_url: str, username: str, password: str, client_id: str) -> Client:
    """Spawn an mcp-abap-adt subprocess with credentials passed via env vars."""
    transport = StdioTransport(
        command="node",
        args=[MCP_ABAP_ADT_PATH],
        env={
            # SAP credentials for this specific subprocess
            "SAP_URL":      sap_url,
            "SAP_USERNAME": username,
            "SAP_PASSWORD": password,
            "SAP_CLIENT":   client_id,
            # System paths Node needs on Windows
            "PATH":         os.environ.get("PATH", ""),
            "USERPROFILE":  os.environ.get("USERPROFILE", ""),
            "APPDATA":      os.environ.get("APPDATA", ""),
            "TEMP":         os.environ.get("TEMP", ""),
            "SYSTEMROOT":   os.environ.get("SYSTEMROOT", ""),
        }
    )
    return Client(transport)


def build_backends() -> dict[str, Client]:
    """Create one client per SAP system."""
    backends = {}
    for name, (host_var, user_var, pass_var, client_var) in SAP_SYSTEMS.items():
        backends[name] = make_sap_client(
            sap_url=   os.environ[host_var],
            username=  os.environ[user_var],
            password=  os.environ[pass_var],
            client_id= os.environ[client_var],
        )
    return backends

# ─── Gateway Assembly ─────────────────────────────────────────────────────────

def build_gateway():
    backends = build_backends()
    gateway = FastMCP("sap-gateway")
    for name, client in backends.items():
        sub = create_proxy(client, name=name)
        gateway.mount(sub, namespace=name)
    return gateway, backends

# ─── Health Check ─────────────────────────────────────────────────────────────

async def check_backends(backends: dict[str, Client]) -> None:
    """Test each SAP system is reachable on startup."""
    for name, client in backends.items():
        try:
            async with client:
                tools = await client.list_tools()
                print(f"✅ {name}: {len(tools)} tools available", file=sys.stderr)
        except Exception as e:
            print(f"❌ {name}: FAILED — {e}", file=sys.stderr)

# ─── Entry Point ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="SAP MCP Gateway")
    parser.add_argument("--http", action="store_true",
                        help="Run as HTTP server (default is stdio for Claude Desktop)")
    parser.add_argument("--host", default="127.0.0.1",
                        help="Host to bind HTTP server (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8080,
                        help="Port for HTTP server (default: 8080)")
    parser.add_argument("--skip-check", action="store_true",
                        help="Skip backend health check on startup")
    args = parser.parse_args()

    # Security & config validation
    validate_environment()

    # Build the gateway
    gateway, backends = build_gateway()

    # Run health check unless skipped
    if not args.skip_check:
        asyncio.run(check_backends(backends))

    # Run in selected mode
    if args.http:
        print(f"🚀 HTTP mode: http://{args.host}:{args.port}/mcp", file=sys.stderr)
        gateway.run(transport="http", host=args.host, port=args.port)
    else:
        print("🚀 stdio mode (for Claude Desktop)", file=sys.stderr)
        gateway.run(transport="stdio")


if __name__ == "__main__":
    main()
