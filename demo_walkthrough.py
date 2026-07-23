"""End-to-end walkthrough (paper Section 7.6): a meeting recording enters,
a decision is extracted, later corrected by a human, audited, and the raw
recording is erased with a receipt while lineage survives."""
from __future__ import annotations

import sys, time

sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__))))
from memora.core import Ledger, Principal, RuleClaimExtractor
from memora.projections import LexicalProjection, VectorProjection
from memora.query import Retriever, Auditor


def main():
    ledger = Ledger()
    human = Principal("marko", "human")
    agent = Principal("agent.notetaker", "agent", "llm-a@2026-05")

    t0 = time.time() - 86400 * 30  # meeting a month ago

    # 1. capture: audio event + transcript (multimodal pair, linked lineage)
    audio = ledger.append_event("[audio bytes ref: s3://meetings/2026-06-23.wav]",
                                modality="audio", t_event=t0, principal=human)
    transcript = ledger.append_event(
        "Meeting notes: pricing discussion.\nacme_deal.price = 40 EUR",
        modality="text", t_event=t0, principal=agent,
        source_event_ids=[audio.id])

    # 2. consolidation: agent transform extracts a Claim
    RuleClaimExtractor(agent).apply(ledger, transcript)

    # 3. correction two weeks later, by a human this time
    t1 = t0 + 86400 * 14
    corr = ledger.append_event("Correction after call.\nacme_deal.price = 45 EUR",
                               modality="text", t_event=t1, principal=human)
    RuleClaimExtractor(human).apply(ledger, corr)

    # 4. projections + provenance-carrying retrieval
    lex, vec = LexicalProjection(), VectorProjection()
    lex.build(ledger); vec.build(ledger)
    r = Retriever(ledger, lex, vec)
    ans = r.answer("acme_deal", "price")
    print("Q: what is the Acme price?")
    print(f"A: {ans.value} (was {ans.superseded_value}), written by "
          f"{ans.principal_id}/{ans.principal_kind}, transform {ans.transform}, "
          f"sources {ans.source_event_ids}")

    # 5. audit queries
    aud = Auditor(ledger)
    print("origin        :", aud.origin("acme_deal", "price"))
    print("chain         :", [(c["value"], c["principal_id"])
                              for c in aud.supersession_chain("acme_deal", "price")])
    print("belief mid-way:", aud.belief_at("acme_deal", "price", t0 + 86400 * 7))
    print("contamination :", aud.contamination(transcript.id))
    print("unconfirmed   :", aud.unconfirmed_agent_claims())

    # 6. injection attempt: unattributed write is quarantined
    ledger.append_event("acme_deal.price = 1 EUR", principal=None)
    print("quarantined   :", len(ledger.quarantined()), "event(s)")

    # 7. erasure with receipt; lineage survives
    receipt = ledger.erase_event(audio.id, "GDPR request", "marko")
    print("erasure       :", receipt, "| event payload now:",
          ledger.get_event(audio.id).payload, "| hash kept:",
          ledger.get_event(audio.id).payload_hash[:12])

    # 8. replay determinism
    h1 = lex.build(ledger); h2 = lex.build(ledger)
    v1 = vec.build(ledger); v2 = vec.build(ledger)
    print("replay        : lexical", h1 == h2, "| vector", v1 == v2)
    print("ledger stats  :", ledger.stats())


if __name__ == "__main__":
    main()
