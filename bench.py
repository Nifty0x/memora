"""Systems micro-benchmarks: append throughput, hybrid query latency,
projection rebuild time, storage growth. Writes bench_results.csv."""
from __future__ import annotations

import csv, os, random, statistics, sys, tempfile, time

sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__))))
from memora.core import Ledger, Principal, RuleClaimExtractor
from memora.projections import LexicalProjection, VectorProjection
from memora.query import Retriever

WORDS = ("deploy price server client meeting decision budget model release "
         "contract review invoice latency memory agent audit column schema "
         "migration index cache token embed graph claim event ledger scope").split()


def synth_payload(rng, i):
    body = " ".join(rng.choice(WORDS) for _ in range(30))
    return f"note {i}: {body}\nentity{i % 500:03d}.attr{i % 5} = value_{i}"


def run(sizes=(1000, 5000, 10000, 25000, 50000), seed=11):
    rows = []
    for n in sizes:
        rng = random.Random(seed)
        path = os.path.join(tempfile.mkdtemp(dir="/dev/shm"), f"bench_{n}.db")
        ledger = Ledger(path)
        agent = Principal("agent.bench", "agent", "llm-a@2026-05")
        ex = RuleClaimExtractor(agent)

        t = time.perf_counter()
        for i in range(n):
            ev = ledger.append_event(synth_payload(rng, i), t_event=1e6 + i,
                                     principal=agent)
            ex.apply(ledger, ev)
        t_ingest = time.perf_counter() - t
        events_per_s = n / t_ingest

        lex, vec = LexicalProjection(), VectorProjection()
        t = time.perf_counter(); lex.build(ledger); t_lex = time.perf_counter() - t
        t = time.perf_counter(); vec.build(ledger); t_vec = time.perf_counter() - t

        r = Retriever(ledger, lex, vec)
        lat = []
        for q in range(50):
            qtext = " ".join(rng.choice(WORDS) for _ in range(4))
            t = time.perf_counter(); r.search(qtext, k=5)
            lat.append((time.perf_counter() - t) * 1000)
        lat_claim = []
        for q in range(200):
            e = f"entity{rng.randrange(500):03d}"
            t = time.perf_counter(); r.answer(e, f"attr{rng.randrange(5)}")
            lat_claim.append((time.perf_counter() - t) * 1000)

        size_mb = os.path.getsize(path) / 1e6
        rows.append({
            "n_events": n,
            "ingest_events_per_s": round(events_per_s, 1),
            "rebuild_lexical_s": round(t_lex, 3),
            "rebuild_vector_s": round(t_vec, 3),
            "search_p50_ms": round(statistics.median(lat), 2),
            "search_p95_ms": round(sorted(lat)[int(len(lat) * 0.95) - 1], 2),
            "claim_lookup_p50_ms": round(statistics.median(lat_claim), 3),
            "db_size_mb": round(size_mb, 2)})
        print(rows[-1], flush=True)
    out = os.path.join(os.path.dirname(__file__), "bench_results.csv")
    exists = os.path.exists(out)
    with open(out, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys())
        if not exists:
            w.writeheader()
        w.writerows(rows)
    print("wrote", out)


if __name__ == "__main__":
    args = [int(a) for a in sys.argv[1:]]
    run(sizes=tuple(args) if args else (1000, 5000, 10000, 25000, 50000))
