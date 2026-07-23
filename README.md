# Memora

Reference implementation of the Bitemporal Provenance Memory Architecture (BPMA).

Paper: "Who Knew What, When, and Why: A Replayable, Bitemporal Memory Substrate
for AI Agents" (Marko Vidrih, 2026).

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

[Read the paper (PDF)](paper/BPMA_paper.pdf) - "Who Knew What, When, and Why: A Replayable, Bitemporal Memory Substrate for AI Agents" (Marko Vidrih, 2026). arXiv submission pending.
