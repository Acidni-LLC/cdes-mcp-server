# CDES MCP Server

**Cannabis Data Exchange Standard — Model Context Protocol Server**

[![License: Apache-2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![MCP](https://img.shields.io/badge/MCP-v1.0-green.svg)](https://modelcontextprotocol.io)

A public MCP server that exposes the [Cannabis Data Exchange Standard (CDES)](https://www.cdes.world) v1 JSON schemas, reference data libraries, and validation tools to AI agents and MCP-compatible clients.

## What is CDES?

The **Cannabis Data Exchange Standard** is an open-source data standard for the cannabis industry, providing:

- **7 JSON Schemas** — Strain, Terpene Profile, Cannabinoid Profile, Terpene, Certificate of Analysis (COA), Rating, Rating Aggregate
- **3 Reference Data Sets** — Terpene Library (10 terpenes), Cannabinoid Library (9 cannabinoids), Terpene Color Palette (30 WCAG 2.1 AA colors)
- **Validation Tools** — Validate any cannabis data object against CDES schemas

## Quick Start

### Install from Source

```bash
git clone https://github.com/Acidni-LLC/cdes-mcp-server.git
cd cdes-mcp-server
pip install -e .
```

### Install from PyPI *(coming soon)*

```bash
pip install cdes-mcp-server
```

### Run Standalone

```bash
cdes-mcp-server
```

The server communicates over **stdio** transport (JSON-RPC 2.0).

## MCP Client Configuration

### Claude Desktop

Add to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "cdes": {
      "command": "cdes-mcp-server",
      "args": []
    }
  }
}
```

### VS Code (GitHub Copilot)

Add to `.vscode/mcp.json` in your project:

```json
{
  "mcpServers": {
    "cdes": {
      "command": "cdes-mcp-server",
      "args": []
    }
  }
}
```

### Cursor / Windsurf

```json
{
  "mcpServers": {
    "cdes": {
      "command": "cdes-mcp-server"
    }
  }
}
```

## Available Tools

| Tool | Description |
|------|-------------|
| `list_schemas` | List all CDES v1 schemas with titles, descriptions, and required fields |
| `get_schema` | Get the full JSON Schema document by name |
| `validate_data` | Validate a data object against any CDES schema |
| `get_terpene_info` | Look up detailed terpene information by ID or name |
| `get_cannabinoid_info` | Look up detailed cannabinoid information by ID or name |
| `lookup_terpene_color` | Get standardized WCAG 2.1 AA color for a terpene |
| `list_terpenes` | List all terpenes with summary data |
| `list_cannabinoids` | List all cannabinoids with summary data |
| `search_reference_data` | Full-text search across all reference data |
| `get_cdes_overview` | Comprehensive CDES standard overview |

## Available Resources

| URI | Description |
|-----|-------------|
| `cdes://schemas/v1/strain` | Strain schema |
| `cdes://schemas/v1/terpene-profile` | Terpene Profile schema |
| `cdes://schemas/v1/cannabinoid-profile` | Cannabinoid Profile schema |
| `cdes://schemas/v1/terpene` | Terpene definition schema |
| `cdes://schemas/v1/coa` | Certificate of Analysis schema |
| `cdes://schemas/v1/rating` | User Rating schema (CX extension) |
| `cdes://schemas/v1/rating-aggregate` | Rating Aggregate schema |
| `cdes://reference/terpene-library` | Terpene reference library (10 terpenes) |
| `cdes://reference/cannabinoid-library` | Cannabinoid reference library (9 cannabinoids) |
| `cdes://reference/terpene-colors` | Terpene color palette (30 colors) |

## Example Interactions

### List all schemas

```
> Use the CDES server to list all available schemas

The CDES standard includes 7 schemas:
1. Strain — cannabis strain definition with type, effects, flavors
2. Terpene Profile — 21 named terpene measurements
3. Cannabinoid Profile — 13 cannabinoid measurements with computed totals
4. Terpene — individual terpene definition with CAS number, effects
5. COA — Certificate of Analysis with lab info, safety tests
6. Rating — user rating/review (CX extension)
7. Rating Aggregate — aggregated rating statistics
```

### Validate data

```
> Validate this strain data against the CDES schema:
> {"id": "strain-001", "name": "Blue Dream", "type": "hybrid"}

✅ Valid! The data conforms to the CDES v1 strain schema.
```

### Look up a terpene

```
> What is Myrcene? Use the CDES terpene library.

Myrcene (CAS: 123-35-3) is a monoterpene with an earthy, musky, herbal
aroma. It's the most common terpene in cannabis (~40% of strains).
Boiling point: 168°C. Key effects: relaxing, sedating, anti-inflammatory.
Found in mango, hops, lemongrass, and thyme.
```

## Schema Structure

All schemas follow **JSON Schema Draft 2020-12** with base URI:

```
https://schemas.terprint.com/cdes/v1/
```

### Schema Relationships

```
strain.json
├── $ref → terpene-profile.json
├── $ref → cannabinoid-profile.json
└── enums: type, effects, flavors, difficulty

coa.json
├── $ref → terpene-profile.json
├── $ref → cannabinoid-profile.json
└── safetyTests: microbials, pesticides, heavyMetals, ...

terpene-profile.json
└── $defs/terpeneValue: number | {value, loq, lod, ...}

rating.json → rating-aggregate.json (computed)
```

## Reference Data Licensing

| Data Set | License | Description |
|----------|---------|-------------|
| Terpene Library | CC0-1.0 | 10 common cannabis terpenes with full metadata |
| Cannabinoid Library | CC0-1.0 | 9 cannabinoids with colors, effects, CAS numbers |
| Terpene Colors | CC0-1.0 | 30 WCAG 2.1 AA-compliant visualization colors |

## Development

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Lint
ruff check src/
ruff format src/
```

## Related Projects

| Project | Description |
|---------|-------------|
| [cdes-spec](https://github.com/Acidni-LLC/cdes-spec) | CDES specification and JSON schemas |
| [cdes-sdk-python](https://github.com/Acidni-LLC/cdes-sdk-python) | Python SDK for CDES (Pydantic models) |
| [cdes-reference-data](https://github.com/Acidni-LLC/cdes-reference-data) | Reference data (terpenes, cannabinoids) |
| [cdes.world](https://www.cdes.world) | CDES documentation website |

## License

- **Code:** [Apache 2.0](LICENSE)
- **Schemas:** [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)
- **Reference Data:** [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/)

---

*Built by [Acidni LLC](https://www.acidni.com) — Powering the cannabis data ecosystem.*
