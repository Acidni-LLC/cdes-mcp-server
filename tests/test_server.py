"""Tests for the CDES MCP Server.

All tool functions are synchronous and return JSON strings.
"""

from __future__ import annotations

import json

import pytest

from cdes_mcp_server.server import (
    _get_reference,
    _get_schema,
    get_cannabinoid_info,
    get_cdes_overview,
    get_schema,
    get_terpene_info,
    list_cannabinoids,
    list_schemas,
    list_terpenes,
    lookup_terpene_color,
    search_reference_data,
    validate_data,
)


def _j(raw: str) -> dict | list:
    """Parse a JSON string returned by an MCP tool."""
    return json.loads(raw)


# ---------------------------------------------------------------------------
# Schema loading
# ---------------------------------------------------------------------------


class TestSchemaLoading:
    """Verify all bundled schemas load correctly."""

    EXPECTED_SCHEMAS = [
        "strain",
        "terpene-profile",
        "cannabinoid-profile",
        "terpene",
        "coa",
        "rating",
        "rating-aggregate",
    ]

    @pytest.mark.parametrize("name", EXPECTED_SCHEMAS)
    def test_load_schema_success(self, name: str) -> None:
        schema = _get_schema(name)
        assert isinstance(schema, dict)
        assert "$schema" in schema or "$id" in schema

    def test_load_schema_unknown_raises(self) -> None:
        with pytest.raises(FileNotFoundError):
            _get_schema("nonexistent-schema")

    @pytest.mark.parametrize("name", EXPECTED_SCHEMAS)
    def test_schema_has_title(self, name: str) -> None:
        schema = _get_schema(name)
        assert "title" in schema


# ---------------------------------------------------------------------------
# Reference data loading
# ---------------------------------------------------------------------------


class TestReferenceDataLoading:
    """Verify all bundled reference data loads correctly."""

    EXPECTED_REFERENCES = [
        "terpene-library",
        "cannabinoid-library",
        "terpene-colors",
    ]

    @pytest.mark.parametrize("name", EXPECTED_REFERENCES)
    def test_load_reference_success(self, name: str) -> None:
        data = _get_reference(name)
        assert data is not None
        assert isinstance(data, dict)

    def test_load_reference_unknown_raises(self) -> None:
        with pytest.raises(FileNotFoundError):
            _get_reference("nonexistent-reference")

    def test_terpene_library_has_entries(self) -> None:
        data = _get_reference("terpene-library")
        assert len(data.get("terpenes", [])) >= 10

    def test_cannabinoid_library_has_entries(self) -> None:
        data = _get_reference("cannabinoid-library")
        assert len(data.get("cannabinoids", [])) >= 9

    def test_terpene_colors_has_entries(self) -> None:
        data = _get_reference("terpene-colors")
        assert len(data.get("colors", [])) >= 30


# ---------------------------------------------------------------------------
# Tool: list_schemas
# ---------------------------------------------------------------------------


class TestListSchemas:
    def test_returns_all_schemas(self) -> None:
        result = _j(list_schemas())
        assert isinstance(result, list)
        assert len(result) == 7

    def test_schema_entries_have_name_and_title(self) -> None:
        entries = _j(list_schemas())
        for entry in entries:
            assert "name" in entry
            assert "title" in entry


# ---------------------------------------------------------------------------
# Tool: get_schema
# ---------------------------------------------------------------------------


class TestGetSchema:
    def test_get_existing_schema(self) -> None:
        result = _j(get_schema(name="strain"))
        assert "title" in result

    def test_get_nonexistent_schema_raises(self) -> None:
        with pytest.raises(FileNotFoundError):
            get_schema(name="does-not-exist")


# ---------------------------------------------------------------------------
# Tool: validate_data
# ---------------------------------------------------------------------------


class TestValidateData:
    def test_valid_strain(self) -> None:
        data = {"id": "strain-001", "name": "Blue Dream", "type": "hybrid"}
        result = _j(validate_data(schema_name="strain", data=data))
        assert result["valid"] is True

    def test_invalid_strain_missing_required(self) -> None:
        data = {"id": "strain-001"}  # missing name, type
        result = _j(validate_data(schema_name="strain", data=data))
        assert result["valid"] is False
        assert result["errorCount"] > 0

    def test_invalid_strain_bad_type_enum(self) -> None:
        data = {"id": "s1", "name": "Test", "type": "not-a-real-type"}
        result = _j(validate_data(schema_name="strain", data=data))
        assert result["valid"] is False

    def test_validate_unknown_schema_raises(self) -> None:
        with pytest.raises(FileNotFoundError):
            validate_data(schema_name="fake", data={"a": 1})


# ---------------------------------------------------------------------------
# Tool: get_terpene_info / get_cannabinoid_info
# ---------------------------------------------------------------------------


class TestTerpeneInfo:
    def test_get_by_name(self) -> None:
        result = _j(get_terpene_info(name="myrcene"))
        assert "name" in result
        assert result["name"].lower() == "myrcene"

    def test_get_by_id(self) -> None:
        result = _j(get_terpene_info(terpene_id="terpene:myrcene"))
        assert "id" in result

    def test_not_found(self) -> None:
        result = _j(get_terpene_info(name="unobtanium"))
        assert "error" in result


class TestCannabinoidInfo:
    def test_get_by_name(self) -> None:
        result = _j(get_cannabinoid_info(name="THC"))
        assert "name" in result

    def test_not_found(self) -> None:
        result = _j(get_cannabinoid_info(name="unobtanium"))
        assert "error" in result


# ---------------------------------------------------------------------------
# Tool: lookup_terpene_color
# ---------------------------------------------------------------------------


class TestLookupTerpeneColor:
    def test_known_terpene(self) -> None:
        result = _j(lookup_terpene_color(terpene_name="myrcene"))
        # Should contain color data (hex, rgb, etc.) or a match
        assert isinstance(result, dict)

    def test_unknown_terpene(self) -> None:
        result = _j(lookup_terpene_color(terpene_name="unobtanium"))
        assert "error" in result or "hex" in result  # may return default


# ---------------------------------------------------------------------------
# Tool: list_terpenes / list_cannabinoids
# ---------------------------------------------------------------------------


class TestListTerpenes:
    def test_returns_list(self) -> None:
        result = _j(list_terpenes())
        assert isinstance(result, list)
        assert len(result) >= 10

    def test_terpene_entries_have_id_and_name(self) -> None:
        entries = _j(list_terpenes())
        for entry in entries:
            assert "id" in entry
            assert "name" in entry


class TestListCannabinoids:
    def test_returns_list(self) -> None:
        result = _j(list_cannabinoids())
        assert isinstance(result, list)
        assert len(result) >= 9

    def test_cannabinoid_entries_have_id_and_name(self) -> None:
        entries = _j(list_cannabinoids())
        for entry in entries:
            assert "id" in entry
            assert "name" in entry


# ---------------------------------------------------------------------------
# Tool: search_reference_data
# ---------------------------------------------------------------------------


class TestSearchReferenceData:
    def test_search_finds_myrcene(self) -> None:
        result = _j(search_reference_data(query="myrcene"))
        assert "results" in result
        assert len(result["results"]) > 0

    def test_search_no_results(self) -> None:
        result = _j(search_reference_data(query="xyzzy_unlikely_match_12345"))
        assert "results" in result
        assert len(result["results"]) == 0


# ---------------------------------------------------------------------------
# Tool: get_cdes_overview
# ---------------------------------------------------------------------------


class TestGetCdesOverview:
    def test_returns_overview(self) -> None:
        result = _j(get_cdes_overview())
        assert "standard" in result
        assert "schemas" in result
        assert "referenceDataSets" in result

    def test_overview_has_links(self) -> None:
        result = _j(get_cdes_overview())
        assert "links" in result
        assert "specification" in result["links"]
        assert "mcpServer" in result["links"]
