# Memora

Reference implementation of the Bitemporal Provenance Memory Architecture (BPMA).

Paper: "Who Knew What, When, and Why: A Replayable, Bitemporal Memory Substrate for AI Agents" (Marko Vidrih, 2026).

## Overview

The problem: AI agent memory systems (Mem0, MemGPT, A-MEM, Zep, etc.) all store facts by overwriting or paraphrasing them. None can answer "who told the agent this, when, and what did it believe before." That's a liability the moment agents make real decisions.

The fix (BPMA): never overwrite anything. Every input becomes a permanent, append-only Memory Event with an author (human or agent, model version included) and a timestamp. Facts extracted from those events (Claims) get validity windows, so old beliefs stay queryable instead of vanishing. Everything else, search indexes, summaries, graphs, is rebuilt from that log on demand and can be thrown away and regenerated without losing anything.

Memora: the working code that proves it. Benchmarked against a normal "just keep the latest value" store: Memora answers 100% of "who knew what, when" questions; the normal approach answers 0 to 38% on anything requiring history.

## Use cases

- Enterprise AI agents (support, sales, ops) where you need to prove why an agent said or did something, audit and compliance requirement, not a nice-to-have.
- Multi-agent systems where several agents and humans write to shared memory and you need to know whose input caused what.
- Any agent that corrects itself over time (price changes, contract terms, customer preferences) and needs to reconstruct "what did we believe last month" without the record.
- Regulated environments (GDPR, EU AI Act) needing both the right to erasure and a defensible audit trail, the erasure-with-receipt mechanism does both at once.
- Long-running coding or research agents where you want to trace a bad output back to the exact source that poisoned it (the contamination query).

Dependency-free Python over SQLite. Modules map to BPMA layers:

- `core.py`: Memory Events, Claims, append-only ledger, quarantine, erasure receipts, versioned transforms
- `projections.py`: lexical (BM25-style) and sparse vector projections with replay state hashes
- `query.py`: hybrid retriever with provenance-carrying answers; the five-class audit API
- `baseline.py`: destructive-update comparator used in the paper
- `auditeval.py`: AuditEval generator and scorer (seeded, deterministic)
- `demo_walkthrough.py`, `bench.py`, `plots.py`: paper artifacts

Reproduce every number in the paper:

    python3 -m memora.auditeval
    python3 memora/demo_walkthrough.py
    python3 memora/bench.py
    python3 memora/plots.py

License: MIT

## Paper

[Read the paper (PDF)](paper/BPMA_Vidrih_2026.pdf) - "Who Knew What, When, and Why: A Replayable, Bitemporal Memory Substrate for AI Agents" (Marko Vidrih, 2026).

Published on Zenodo: https://doi.org/10.5281/zenodo.21654959

## Citing

    @article{vidrih2026bpma,
      title  = {Who Knew What, When, and Why: A Replayable, Bitemporal
                Memory Substrate for AI Agents},
      author = {Vidrih, Marko},
      year   = {2026},
      doi    = {10.5281/zenodo.21654959}
    }