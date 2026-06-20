# Finance-Only Repo Conversion TODO

**Status:** complete
**Request:** convert the former multi-hub scaffold into a finance-focused installable package while preserving the request-scoped docs layout.

## Decisions

- Keep the shared CLI/MCP/tool-registry runtime pattern.
- Remove the multiple-hub framing from code and packaging.
- Use a polished `src/finance_hub/` package layout.
- Preserve `docs/requests/finance/**` as the home for specs, plans, TODOs, and design docs.
- Keep `notes/finance-corpus/**` as finance source material.
- Remove inactive non-finance hubs and non-finance note corpora from this repo.
- Treat the sibling `projects/finance-hub` repository as legacy/reference material, not the canonical architecture.

## Checklist

- [x] Move CLI, MCP, registry, and runtime helpers under `src/finance_hub/`.
- [x] Create finance domain package placeholders for ingestion, market data, research, and strategy.
- [x] Update package metadata and console scripts for `finance` and `finance-mcp`.
- [x] Remove inactive `hubs/*` packages and non-finance note corpora.
- [x] Add root README explaining the finance-only package shape.
- [x] Run import/CLI smoke checks.
- [x] Commit the migration.

## Follow-Up Work

- Implement the first real finance slice under `src/finance_hub/ingestion`.
- Add focused tests under `tests/` as finance behavior lands.
- Decide whether to rename the sibling legacy repo outside this migration.
