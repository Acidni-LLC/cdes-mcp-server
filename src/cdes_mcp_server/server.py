"""CDES MCP Server - Cannabis Data Exchange Standard for AI Agents.

Publicly hosted MCP server exposing all CDES v1 JSON schemas, reference data
libraries, and validation tools.  Automatically syncs with upstream repos
(cdes-spec, cdes-reference-data) to always serve the latest version.

Transport: SSE (public) or stdio (local dev)
Protocol: MCP v1.0 over JSON-RPC 2.0
"""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx
import jsonschema
import referencing
import referencing.jsonschema
import uvicorn
from mcp.server.fastmcp import FastMCP
from mcp.server.sse import SseServerTransport
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse
from starlette.routing import Route

if TYPE_CHECKING:
    from starlette.requests import Request

logger = logging.getLogger(__name__)

__version__ = "1.1.0"

# ---------------------------------------------------------------------------
# GitHub sync configuration
# ---------------------------------------------------------------------------

_GITHUB_RAW_BASE = "https://raw.githubusercontent.com/Acidni-LLC"

_GITHUB_SCHEMA_FILES = [
    "strain",
    "terpene-profile",
    "cannabinoid-profile",
    "terpene",
    "coa",
    "rating",
    "rating-aggregate",
]

_GITHUB_REFERENCE_MAP: dict[str, tuple[str, str]] = {
    "terpene-library": ("terpenes", "terpene-library.json"),
    "cannabinoid-library": ("cannabinoids", "cannabinoid-library.json"),
    "terpene-colors": ("terpenes", "terpene-colors.json"),
    "terpene-library-extended": ("terpenes", "terpene-library-extended.json"),
    "terpene-therapeutics": ("terpenes", "terpene-therapeutics.json"),
    "cannabinoid-therapeutics": ("cannabinoids", "cannabinoid-therapeutics.json"),
}

_last_sync: datetime | None = None

# ---------------------------------------------------------------------------
# Server initialisation
# ---------------------------------------------------------------------------

mcp = FastMCP(
    "cdes-mcp-server",
    instructions=(
        "Cannabis Data Exchange Standard (CDES) MCP Server v1.1.0 — "
        "publicly hosted server providing access to all CDES v1 JSON schemas, "
        "reference data (terpenes, cannabinoids, colors), and validation tools. "
        "Schemas are automatically synced from the official cdes-spec repository."
    ),
)

# ---------------------------------------------------------------------------
# Data loading helpers
# ---------------------------------------------------------------------------

_PACKAGE_DIR = Path(__file__).parent

_SCHEMA_DIR = _PACKAGE_DIR / "schemas" / "v1"
_REFERENCE_DIR = _PACKAGE_DIR / "reference"

# Schema catalog: name -> loaded dict
_SCHEMA_CACHE: dict[str, dict[str, Any]] = {}

# Reference data cache: name -> loaded dict
_REFERENCE_CACHE: dict[str, dict[str, Any]] = {}


def _load_json(path: Path) -> dict[str, Any]:
    """Read and parse a JSON file."""
    return json.loads(path.read_text(encoding="utf-8"))


def _get_schema(name: str) -> dict[str, Any]:
    """Return a cached schema by short name (e.g. 'strain')."""
    if name not in _SCHEMA_CACHE:
        path = _SCHEMA_DIR / f"{name}.json"
        if not path.exists():
            raise FileNotFoundError(f"Schema not found: {name}")
        _SCHEMA_CACHE[name] = _load_json(path)
    return _SCHEMA_CACHE[name]


def _get_reference(name: str) -> dict[str, Any]:
    """Return cached reference data by short name (e.g. 'terpene-library')."""
    if name not in _REFERENCE_CACHE:
        path = _REFERENCE_DIR / f"{name}.json"
        if not path.exists():
            raise FileNotFoundError(f"Reference data not found: {name}")
        _REFERENCE_CACHE[name] = _load_json(path)
    return _REFERENCE_CACHE[name]


def _all_schema_names() -> list[str]:
    """List available schema file stems."""
    return sorted(p.stem for p in _SCHEMA_DIR.glob("*.json"))


def _all_reference_names() -> list[str]:
    """List available reference data file stems."""
    return sorted(p.stem for p in _REFERENCE_DIR.glob("*.json"))


def sync_schemas_from_github() -> dict[str, Any]:
    """Fetch latest schemas and reference data from upstream GitHub repos.

    Pulls from Acidni-LLC/cdes-spec (schemas) and
    Acidni-LLC/cdes-reference-data (terpene/cannabinoid libraries).
    Downloaded files are cached in memory and persisted to disk so the
    bundled copy stays current across container restarts.
    """
    global _last_sync  # noqa: PLW0603
    errors: list[str] = []
    schemas_updated = 0
    refs_updated = 0

    try:
        with httpx.Client(timeout=30, follow_redirects=True) as client:
            # -- schemas ------------------------------------------------
            for name in _GITHUB_SCHEMA_FILES:
                url = f"{_GITHUB_RAW_BASE}/cdes-spec/main/schemas/v1/{name}.json"
                try:
                    resp = client.get(url)
                    if resp.is_success:
                        data = resp.json()
                        _SCHEMA_CACHE[name] = data
                        path = _SCHEMA_DIR / f"{name}.json"
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
                        schemas_updated += 1
                    else:
                        errors.append(f"Schema {name}: HTTP {resp.status_code}")
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"Schema {name}: {exc}")

            # -- reference data -----------------------------------------
            for ref_name, (subdir, filename) in _GITHUB_REFERENCE_MAP.items():
                url = f"{_GITHUB_RAW_BASE}/cdes-reference-data/main/{subdir}/{filename}"
                try:
                    resp = client.get(url)
                    if resp.is_success:
                        data = resp.json()
                        _REFERENCE_CACHE[ref_name] = data
                        path = _REFERENCE_DIR / f"{ref_name}.json"
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
                        refs_updated += 1
                    else:
                        errors.append(f"Reference {ref_name}: HTTP {resp.status_code}")
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"Reference {ref_name}: {exc}")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"GitHub sync failed: {exc}")

    _last_sync = datetime.now(tz=UTC)

    summary: dict[str, Any] = {
        "schemas_updated": schemas_updated,
        "references_updated": refs_updated,
        "errors": errors,
        "synced_at": _last_sync.isoformat(),
    }

    if errors:
        logger.warning("GitHub sync completed with errors: %s", errors)
    else:
        logger.info(
            "GitHub sync complete: %d schemas, %d references",
            schemas_updated,
            refs_updated,
        )

    return summary


# ---------------------------------------------------------------------------
# Health endpoint
# ---------------------------------------------------------------------------


async def _health_endpoint(request: Request) -> JSONResponse:  # noqa: ARG001
    """Health check for Azure Container Apps probes."""
    return JSONResponse(
        {
            "status": "healthy",
            "service": "cdes-mcp-server",
            "version": __version__,
            "transport": os.getenv("MCP_TRANSPORT", "sse"),
            "schemas": _all_schema_names(),
            "references": _all_reference_names(),
            "lastSync": _last_sync.isoformat() if _last_sync else None,
        }
    )


# ---------------------------------------------------------------------------
# MCP Resources — schemas
# ---------------------------------------------------------------------------


@mcp.resource("cdes://schemas/v1/{name}")
def schema_resource(name: str) -> str:
    """Return a CDES v1 JSON schema as a resource.

    Available schemas: strain, terpene-profile, cannabinoid-profile,
    terpene, coa, rating, rating-aggregate.
    """
    schema = _get_schema(name)
    return json.dumps(schema, indent=2)


@mcp.resource("cdes://reference/{name}")
def reference_resource(name: str) -> str:
    """Return CDES reference data as a resource.

    Available: terpene-library, cannabinoid-library, terpene-colors.
    """
    data = _get_reference(name)
    return json.dumps(data, indent=2)


# ---------------------------------------------------------------------------
# MCP Tools
# ---------------------------------------------------------------------------


@mcp.tool()
def list_schemas() -> str:
    """List all available CDES v1 schemas with their titles and descriptions.

    Returns a JSON array of objects with name, title, description, and
    required fields for each schema.
    """
    result = []
    for name in _all_schema_names():
        schema = _get_schema(name)
        result.append(
            {
                "name": name,
                "title": schema.get("title", name),
                "description": schema.get("description", ""),
                "schemaId": schema.get("$id", ""),
                "required": schema.get("required", []),
                "propertyCount": len(schema.get("properties", {})),
            }
        )
    return json.dumps(result, indent=2)


@mcp.tool()
def get_schema(name: str) -> str:
    """Get the full CDES v1 JSON schema by name.

    Args:
        name: Schema name — one of: strain, terpene-profile,
              cannabinoid-profile, terpene, coa, rating, rating-aggregate.

    Returns the complete JSON Schema (Draft 2020-12) document.
    """
    schema = _get_schema(name)
    return json.dumps(schema, indent=2)


@mcp.tool()
def validate_data(schema_name: str, data: dict[str, Any]) -> str:
    """Validate a data object against a CDES v1 schema.

    Args:
        schema_name: The schema to validate against (e.g. 'strain', 'coa').
        data: The JSON object to validate.

    Returns a JSON object with 'valid' (bool) and 'errors' (list of
    error messages if invalid).
    """
    schema = _get_schema(schema_name)

    # Build a referencing.Registry so $ref between CDES schemas resolves
    resources: list[tuple[str, referencing.Resource]] = []
    for sn in _all_schema_names():
        s = _get_schema(sn)
        if "$id" in s:
            resources.append((s["$id"], referencing.Resource.from_contents(s)))
    registry = referencing.Registry().with_resources(resources)

    validator = jsonschema.Draft202012Validator(schema, registry=registry)
    errors = sorted(validator.iter_errors(data), key=lambda e: list(e.absolute_path))

    error_messages = []
    for err in errors:
        path = ".".join(str(p) for p in err.absolute_path) or "(root)"
        error_messages.append(
            {
                "path": path,
                "message": err.message,
                "schemaPath": ".".join(str(p) for p in err.absolute_schema_path),
            }
        )

    return json.dumps(
        {
            "valid": len(error_messages) == 0,
            "schemaName": schema_name,
            "errorCount": len(error_messages),
            "errors": error_messages,
        },
        indent=2,
    )


@mcp.tool()
def get_terpene_info(terpene_id: str | None = None, name: str | None = None) -> str:
    """Look up detailed information about a specific terpene.

    Provide either the terpene ID (e.g. 'terpene:myrcene') or the common
    name (e.g. 'Myrcene'). Returns the full terpene record from the
    reference library including aroma, effects, boiling point, and
    natural sources.

    Args:
        terpene_id: CDES terpene identifier (e.g. 'terpene:limonene').
        name: Common name of the terpene (case-insensitive).
    """
    lib = _get_reference("terpene-library")
    for t in lib.get("terpenes", []):
        if terpene_id and t.get("id") == terpene_id:
            return json.dumps(t, indent=2)
        if name and t.get("name", "").lower() == name.lower():
            return json.dumps(t, indent=2)

    available = [t["name"] for t in lib.get("terpenes", [])]
    return json.dumps(
        {
            "error": f"Terpene not found. Search: id={terpene_id}, name={name}",
            "available": available,
        },
        indent=2,
    )


@mcp.tool()
def get_cannabinoid_info(
    cannabinoid_id: str | None = None,
    name: str | None = None,
) -> str:
    """Look up detailed information about a specific cannabinoid.

    Provide either the cannabinoid ID (e.g. 'cannabinoid:thc') or the
    common name (e.g. 'THC'). Returns the full cannabinoid record from
    the reference library.

    Args:
        cannabinoid_id: CDES cannabinoid identifier.
        name: Common name or abbreviation (case-insensitive).
    """
    lib = _get_reference("cannabinoid-library")
    for c in lib.get("cannabinoids", []):
        if cannabinoid_id and c.get("id") == cannabinoid_id:
            return json.dumps(c, indent=2)
        if name and (c.get("name", "").lower() == name.lower() or c.get("fullName", "").lower() == name.lower()):
            return json.dumps(c, indent=2)

    available = [f"{c['name']} ({c.get('fullName', '')})" for c in lib.get("cannabinoids", [])]
    return json.dumps(
        {
            "error": f"Cannabinoid not found. Search: id={cannabinoid_id}, name={name}",
            "available": available,
        },
        indent=2,
    )


@mcp.tool()
def lookup_terpene_color(terpene_name: str) -> str:
    """Get the standardized WCAG 2.1 AA-compliant color for a terpene.

    Used for consistent data visualization across CDES-compliant
    applications. Returns hex and RGB values.

    Args:
        terpene_name: Terpene key name (e.g. 'myrcene', 'limonene').
    """
    colors = _get_reference("terpene-colors")
    for entry in colors.get("colors", []):
        if entry.get("terpene", "").lower() == terpene_name.lower():
            return json.dumps(entry, indent=2)

    available = [c["terpene"] for c in colors.get("colors", [])]
    return json.dumps(
        {
            "error": f"Terpene color not found: {terpene_name}",
            "available": available,
        },
        indent=2,
    )


@mcp.tool()
def list_terpenes() -> str:
    """List all terpenes in the CDES reference library.

    Returns a summary array with id, name, category, aroma, and boiling
    point for each terpene.
    """
    lib = _get_reference("terpene-library")
    result = [
        {
            "id": t.get("id"),
            "name": t.get("name"),
            "casNumber": t.get("casNumber"),
            "category": t.get("category"),
            "aroma": t.get("aroma", []),
            "boilingPoint": t.get("boilingPoint"),
        }
        for t in lib.get("terpenes", [])
    ]
    return json.dumps(result, indent=2)


@mcp.tool()
def list_cannabinoids() -> str:
    """List all cannabinoids in the CDES reference library.

    Returns a summary array with id, name, psychoactive status, color,
    and primary effects for each cannabinoid.
    """
    lib = _get_reference("cannabinoid-library")
    result = [
        {
            "id": c.get("id"),
            "name": c.get("name"),
            "fullName": c.get("fullName"),
            "psychoactive": c.get("psychoactive"),
            "color": c.get("color"),
            "effects": c.get("effects", []),
        }
        for c in lib.get("cannabinoids", [])
    ]
    return json.dumps(result, indent=2)


@mcp.tool()
def search_reference_data(query: str) -> str:
    """Search across all CDES reference data for a term.

    Searches terpene names, aromas, effects, natural sources,
    cannabinoid names, and descriptions. Case-insensitive.

    Args:
        query: The search term (e.g. 'citrus', 'pain', 'anti-inflammatory').
    """
    q = query.lower()
    results: list[dict[str, Any]] = []

    # Search terpenes
    lib = _get_reference("terpene-library")
    for t in lib.get("terpenes", []):
        searchable = json.dumps(t).lower()
        if q in searchable:
            results.append(
                {
                    "type": "terpene",
                    "id": t.get("id"),
                    "name": t.get("name"),
                    "matchContext": _extract_match_context(t, q),
                }
            )

    # Search cannabinoids
    clib = _get_reference("cannabinoid-library")
    for c in clib.get("cannabinoids", []):
        searchable = json.dumps(c).lower()
        if q in searchable:
            results.append(
                {
                    "type": "cannabinoid",
                    "id": c.get("id"),
                    "name": c.get("name"),
                    "matchContext": _extract_match_context(c, q),
                }
            )

    return json.dumps(
        {
            "query": query,
            "resultCount": len(results),
            "results": results,
        },
        indent=2,
    )


def _extract_match_context(obj: dict[str, Any], query: str) -> str:
    """Find which fields match the query for context."""
    q = query.lower()
    matches = []
    for key, val in obj.items():
        val_str = json.dumps(val).lower()
        if q in val_str:
            matches.append(key)
    return f"Matched in: {', '.join(matches)}"


@mcp.tool()
def get_cdes_overview() -> str:
    """Get a comprehensive overview of the Cannabis Data Exchange Standard.

    Returns information about CDES including version, available schemas,
    reference data sets, licensing, and links to documentation.
    """
    schemas = []
    for name in _all_schema_names():
        s = _get_schema(name)
        schemas.append(
            {
                "name": name,
                "title": s.get("title", ""),
                "description": s.get("description", ""),
                "required": s.get("required", []),
            }
        )

    reference_sets = []
    for name in _all_reference_names():
        r = _get_reference(name)
        reference_sets.append(
            {
                "name": name,
                "description": r.get("description", ""),
                "version": r.get("version", ""),
                "license": r.get("license", ""),
            }
        )

    return json.dumps(
        {
            "standard": "Cannabis Data Exchange Standard (CDES)",
            "specVersion": "1.0.0",
            "serverVersion": __version__,
            "publicEndpoint": "https://cdes-mcp.acidni.net/sse",
            "schemaVersion": "JSON Schema Draft 2020-12",
            "baseUri": "https://schemas.terprint.com/cdes/v1/",
            "website": "https://www.cdes.world",
            "publisher": "Acidni LLC / Terprint",
            "licenses": {
                "code": "Apache-2.0",
                "specifications": "CC-BY-4.0",
                "referenceData": "CC0-1.0",
            },
            "schemas": schemas,
            "referenceDataSets": reference_sets,
            "links": {
                "specification": "https://github.com/Acidni-LLC/cdes-spec",
                "pythonSdk": "https://github.com/Acidni-LLC/cdes-sdk-python",
                "referenceData": "https://github.com/Acidni-LLC/cdes-reference-data",
                "mcpServer": "https://github.com/Acidni-LLC/cdes-mcp-server",
            },
            "tools": [
                "list_schemas",
                "get_schema",
                "validate_data",
                "get_terpene_info",
                "get_cannabinoid_info",
                "lookup_terpene_color",
                "list_terpenes",
                "list_cannabinoids",
                "search_reference_data",
                "get_cdes_overview",
            ],
        },
        indent=2,
    )


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


async def _run_sse_server(host: str, port: int) -> None:
    """Run SSE server with /health endpoint and CORS."""
    sse_transport = SseServerTransport("/messages/")

    async def handle_sse(request: Request) -> None:
        async with sse_transport.connect_sse(
            request.scope,
            request.receive,
            request._send,  # noqa: SLF001
        ) as (read_stream, write_stream):
            await mcp._mcp_server.run(  # noqa: SLF001
                read_stream,
                write_stream,
                mcp._mcp_server.create_initialization_options(),  # noqa: SLF001
            )

    app = Starlette(
        routes=[
            Route("/health", _health_endpoint),
            Route("/sse", handle_sse),
            Route("/messages/", sse_transport.handle_post_message, methods=["POST"]),
        ],
        middleware=[
            Middleware(
                CORSMiddleware,
                allow_origins=["*"],
                allow_methods=["GET", "POST"],
                allow_headers=["*"],
            ),
        ],
    )

    config = uvicorn.Config(app, host=host, port=port, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()


def main() -> None:
    """Run the CDES MCP server.

    Transport is controlled by ``MCP_TRANSPORT`` env var:

    * ``sse``   (default) — public SSE server with ``/health`` endpoint
    * ``stdio`` — local stdio for MCP client development
    """
    transport = os.getenv("MCP_TRANSPORT", "sse")

    if transport == "stdio":
        mcp.run(transport="stdio")
    else:
        logging.basicConfig(level=logging.INFO)
        logger.info("Syncing schemas from GitHub on startup...")
        result = sync_schemas_from_github()
        logger.info("Sync result: %s", result)

        host = os.getenv("MCP_HOST", "0.0.0.0")  # noqa: S104
        port = int(os.getenv("MCP_PORT", "8000"))
        logger.info("Starting CDES MCP Server (SSE) on %s:%d", host, port)

        import anyio

        anyio.run(_run_sse_server, host, port)


if __name__ == "__main__":
    main()
