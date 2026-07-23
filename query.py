"""Retrieval planner with provenance-carrying results, and the audit query API.

Every retrieval answer ships its chain: Claim -> transform -> source Memory
Events -> principals. Audit queries are first-class, not log archaeology.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .core import Ledger, Claim


@dataclass
class ProvenancedAnswer:
    value: Optional[str]
    claim_id: Optional[str]
    principal_id: Optional[str]
    principal_kind: Optional[str]
    model_ref: Optional[str]
    transform: Optional[str]
    source_event_ids: list
    t_valid_from: Optional[float]
    t_valid_to: Optional[float]
    superseded_value: Optional[str] = None


class Retriever:
    """Hybrid planner: structured claim lookup, then lexical + vector fusion."""

    def __init__(self, ledger: Ledger, lexical, vector):
        self.ledger = ledger
        self.lexical = lexical
        self.vector = vector

    def answer(self, entity: str, attribute: str) -> ProvenancedAnswer:
        """Current-belief lookup with full provenance chain."""
        cs = self.ledger.claims_for(entity, attribute)
        current = next((c for c in cs if c.t_valid_to is None), None)
        if current is None:
            return ProvenancedAnswer(None, None, None, None, None, None, [], None, None)
        prev = self.ledger.get_claim(current.supersedes) if current.supersedes else None
        return ProvenancedAnswer(
            value=current.value, claim_id=current.id,
            principal_id=current.principal_id, principal_kind=current.principal_kind,
            model_ref=current.model_ref,
            transform=f"{current.transform_id}@{current.transform_version}",
            source_event_ids=current.source_event_ids,
            t_valid_from=current.t_valid_from, t_valid_to=current.t_valid_to,
            superseded_value=prev.value if prev else None)

    def search(self, text: str, k: int = 5) -> list:
        """Reciprocal-rank fusion of lexical and vector projections."""
        ranks = {}
        for i, (doc, _) in enumerate(self.lexical.query(text, k * 2)):
            ranks[doc] = ranks.get(doc, 0.0) + 1.0 / (60 + i)
        for i, (doc, _) in enumerate(self.vector.query(text, k * 2)):
            ranks[doc] = ranks.get(doc, 0.0) + 1.0 / (60 + i)
        fused = sorted(ranks.items(), key=lambda x: (-x[1], x[0]))[:k]
        return [(self.ledger.get_event(doc), score) for doc, score in fused]


class Auditor:
    """The five audit query classes of AuditEval."""

    def __init__(self, ledger: Ledger):
        self.ledger = ledger

    def origin(self, entity: str, attribute: str) -> Optional[dict]:
        """Q1: when was this first learned, from whom, with what value?"""
        cs = self.ledger.claims_for(entity, attribute)
        if not cs:
            return None
        first = min(cs, key=lambda c: c.t_valid_from)
        return {"value": first.value, "principal_id": first.principal_id,
                "principal_kind": first.principal_kind, "t": first.t_valid_from,
                "source_event_ids": first.source_event_ids}

    def supersession_chain(self, entity: str, attribute: str) -> list:
        """Q2: full history of values with validity intervals."""
        cs = sorted(self.ledger.claims_for(entity, attribute),
                    key=lambda c: c.t_valid_from)
        return [{"value": c.value, "from": c.t_valid_from, "to": c.t_valid_to,
                 "principal_id": c.principal_id, "claim_id": c.id} for c in cs]

    def attribution(self, entity: str, attribute: str) -> Optional[dict]:
        """Q3: who wrote the current belief: human or agent, which model?"""
        cs = self.ledger.claims_for(entity, attribute)
        current = next((c for c in cs if c.t_valid_to is None), None)
        if current is None:
            return None
        return {"principal_id": current.principal_id,
                "principal_kind": current.principal_kind,
                "model_ref": current.model_ref,
                "transform": f"{current.transform_id}@{current.transform_version}"}

    def belief_at(self, entity: str, attribute: str, t: float) -> Optional[str]:
        """Q4: reconstruct the belief state at world time t."""
        for c in self.ledger.claims_for(entity, attribute):
            if c.t_valid_from <= t and (c.t_valid_to is None or t < c.t_valid_to):
                return c.value
        return None

    def contamination(self, event_id: str) -> list:
        """Q5: which Claims depend on this Memory Event?"""
        return [c.id for c in self.ledger.all_claims()
                if event_id in c.source_event_ids]

    def unconfirmed_agent_claims(self) -> list:
        """Governance sweep: agent-written beliefs never confirmed by a human."""
        return [c.id for c in self.ledger.all_claims()
                if c.principal_kind != "human" and not c.confirmed_by_human
                and c.t_valid_to is None]
