# ADR 0002: Split Structured Facts From Research Prose

## Status

Accepted

## Context

Finance Hub needs deterministic facts for reconciliation, prices, metrics, strategy versions, and
deployment arithmetic. It also needs prose-heavy research artifacts such as theses, cited briefs, and
decision narratives.

## Decision

Use SQLite for structured facts and relationships. Use Markdown for research thinking and portable
prose artifacts. SQLite may store relative note paths, but prose bodies should not become opaque text
blobs in the database.

## Consequences

Tools can validate, query, and compose structured data deterministically, while agents can draft and
revise research material in ordinary files. Generated readouts are derived artifacts, not independent
sources of truth.
