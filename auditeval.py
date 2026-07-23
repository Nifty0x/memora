"""AuditEval: a benchmark for provenance queries over agent memory.

Generator builds synthetic multi-principal revision histories with known
ground truth; scorer runs the five audit query classes against any system
exposing the audit interface. Deterministic under a fixed seed.
"""
from __future__ import annotations

import random

from .core import Ledger, Principal, RuleClaimExtractor
from .query import Auditor
from .baseline import DestructiveStore

QUERY_CLASSES = ["origin", "supersession", "attribution", "belief_at", "contamination"]


def generate(seed=7, n_entities=40, n_attrs=3, max_revisions=4):
    """Returns (timeline, ground_truth). timeline: list of revision dicts."""
    rng = random.Random(seed)
    principals = [
        {"id": "marko", "kind": "human", "model_ref": None},
        {"id": "agent.support", "kind": "agent", "model_ref": "llm-a@2026-05"},
        {"id": "agent.research", "kind": "agent", "model_ref": "llm-b@2026-06"},
    ]
    timeline = []
    t = 1_000_000.0
    for e in range(n_entities):
        for a in range(n_attrs):
            entity, attr = f"entity{e:03d}", f"attr{a}"
            for rev in range(rng.randint(1, max_revisions)):
                t += rng.uniform(10, 1000)
                p = rng.choice(principals)
                timeline.append({
                    "entity": entity, "attribute": attr,
                    "value": f"v{rev}_{entity}_{attr}", "rev": rev,
                    "t": t, "principal": p})
    truth = {}
    by_ea = {}
    for item in timeline:
        by_ea.setdefault((item["entity"], item["attribute"]), []).append(item)
    for ea, revs in by_ea.items():
        revs = sorted(revs, key=lambda x: x["t"])
        truth[ea] = revs
    return timeline, truth


def load_into_memora(timeline):
    ledger = Ledger()
    event_of = {}
    for item in timeline:
        p = Principal(**item["principal"])
        ev = ledger.append_event(
            payload=f'{item["entity"]}.{item["attribute"]} = {item["value"]}',
            t_event=item["t"], principal=p)
        RuleClaimExtractor(p).apply(ledger, ev)
        event_of[(item["entity"], item["attribute"], item["rev"])] = ev.id
    return ledger, event_of


def load_into_baseline(timeline):
    store = DestructiveStore()
    for item in timeline:
        store.upsert(item["entity"], item["attribute"], item["value"],
                     item["t"], item["principal"]["id"], item["principal"]["kind"])
    return store


def score(truth, memora=None, baseline=None, event_of=None, seed=7):
    """Score one system. Returns {query_class: accuracy}."""
    rng = random.Random(seed + 1)
    aud = Auditor(memora) if memora else None
    results = {q: [0, 0] for q in QUERY_CLASSES}

    for (entity, attr), revs in truth.items():
        first, last = revs[0], revs[-1]

        # Q1 origin: first value and first principal
        got = aud.origin(entity, attr) if aud else baseline.origin(entity, attr)
        ok = bool(got) and got["value"] == first["value"] and \
            got["principal_id"] == first["principal"]["id"]
        results["origin"][0] += int(ok); results["origin"][1] += 1

        # Q2 supersession: full chain of values in order
        chain = (aud.supersession_chain(entity, attr) if aud
                 else baseline.supersession_chain(entity, attr))
        ok = [c["value"] for c in chain] == [r["value"] for r in revs]
        results["supersession"][0] += int(ok); results["supersession"][1] += 1

        # Q3 attribution: current principal id + kind
        got = aud.attribution(entity, attr) if aud else baseline.attribution(entity, attr)
        ok = bool(got) and got["principal_id"] == last["principal"]["id"] and \
            got["principal_kind"] == last["principal"]["kind"]
        results["attribution"][0] += int(ok); results["attribution"][1] += 1

        # Q4 belief_at: value at a random instant inside each interval
        for i, r in enumerate(revs):
            t_end = revs[i + 1]["t"] if i + 1 < len(revs) else r["t"] + 10_000
            t_probe = rng.uniform(r["t"] + 1e-6, t_end - 1e-6)
            got = (aud.belief_at(entity, attr, t_probe) if aud
                   else baseline.belief_at(entity, attr, t_probe))
            results["belief_at"][0] += int(got == r["value"])
            results["belief_at"][1] += 1

        # Q5 contamination: claims derived from the event of revision 0
        if memora is not None:
            ev_id = event_of[(entity, attr, 0)]
            deps = aud.contamination(ev_id)
            claims0 = [c for c in memora.claims_for(entity, attr)
                       if c.value == first["value"]]
            ok = len(deps) == 1 and claims0 and deps[0] == claims0[0].id
        else:
            ok = bool(baseline.contamination("ev_unknown"))
        results["contamination"][0] += int(ok); results["contamination"][1] += 1

    return {q: round(100.0 * c / t, 1) for q, (c, t) in results.items()}


if __name__ == "__main__":
    timeline, truth = generate()
    ledger, event_of = load_into_memora(timeline)
    store = load_into_baseline(timeline)
    m = score(truth, memora=ledger, event_of=event_of)
    b = score(truth, baseline=store)
    print("n_queries per class computed over", len(truth), "entity-attribute pairs")
    print("Memora   :", m)
    print("Baseline :", b)
