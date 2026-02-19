# =============================================================================
# CDES MCP Server — Multi-stage build
# Stage 1: Fetch latest schemas from upstream repos (cdes-spec, cdes-reference-data)
# Stage 2: Build slim Python image with fresh schemas baked in
# =============================================================================

# ---------------------------------------------------------------------------
# Stage 1 — clone upstream repos for latest schemas & reference data
# ---------------------------------------------------------------------------
FROM alpine/git:latest AS schema-sync

WORKDIR /sync
RUN git clone --depth=1 https://github.com/Acidni-LLC/cdes-spec.git
RUN git clone --depth=1 https://github.com/Acidni-LLC/cdes-reference-data.git

# ---------------------------------------------------------------------------
# Stage 2 — runtime image
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

# Security: non-root user
RUN groupadd --gid 1000 appuser \
    && useradd --uid 1000 --gid 1000 --create-home appuser

WORKDIR /app

# Copy project metadata and source
COPY pyproject.toml README.md LICENSE ./
COPY src/ ./src/

# Overlay fresh schemas from upstream (overwrite bundled copies)
COPY --from=schema-sync /sync/cdes-spec/schemas/v1/ ./src/cdes_mcp_server/schemas/v1/

# Flatten reference data from subdirectories into single reference/ dir
COPY --from=schema-sync /sync/cdes-reference-data/terpenes/ ./src/cdes_mcp_server/reference/
COPY --from=schema-sync /sync/cdes-reference-data/cannabinoids/ ./src/cdes_mcp_server/reference/

# Install package with fresh schemas baked in
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir .

# Ownership
RUN chown -R appuser:appuser /app

USER appuser

# Configuration
ENV MCP_TRANSPORT=sse \
    MCP_HOST=0.0.0.0 \
    MCP_PORT=8000

EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import httpx; r = httpx.get('http://localhost:8000/health', timeout=5); r.raise_for_status()"

CMD ["cdes-mcp-server"]
