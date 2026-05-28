# BrainDrain (V1 Scaffold)

Local-first knowledge agent based on the product docs in this repository.

## What this ships

- Ingestion loop (`/api/ingest`): URL/text -> claim extraction -> relationship reasoning -> SQLite persistence -> cluster recompute.
- Query loop (`/api/query`): multi-angle retrieval -> synthesis memo -> self-evaluation caveats.
- State loop (`/api/state`): cluster-level state summary with conflict/depth/diversity signals.
- Dashboard UI (`/`): ingest, query, card browser, contradiction badges, and state brief.

## Stack

- Next.js (App Router, TypeScript)
- SQLite (`better-sqlite3`)
- Ollama for generation + embeddings
- Mozilla Readability + JSDOM for URL parsing

## Quick start

1. Install dependencies:
```bash
npm install
```

2. Copy env vars:
```bash
cp .env.example .env.local
```

3. Start Ollama and pull models (example):
```bash
ollama pull qwen2.5:14b-instruct
ollama pull nomic-embed-text
```

4. Run app:
```bash
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

## Notes

- DB file defaults to `./data/braindrain.db`.
- If Ollama is unavailable, ingestion/query still run with heuristic fallbacks.
- Current vector retrieval uses in-memory cosine search over stored embeddings (good for V1 scale).

## Next upgrades

- Replace in-memory vector retrieval with `sqlite-vss` or LanceDB.
- Add periodic background job for state assessments and revision history.
- Add explicit belief-revision workflow with user confirmation.
