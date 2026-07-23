"""Destructive-update baseline: the extract-then-update pattern used by
current extraction pipelines (ADD / UPDATE / DELETE against a mutable store).

Given the same inputs as Memora, it keeps only the latest value per
(entity, attribute) plus a last-writer field. It is not a strawman: it gets
the same extractor and is allowed to answer every audit query as well as its
data model permits."""
from __future__ import annotations


class DestructiveStore:
    def __init__(self):
        self.facts = {}   # (entity, attribute) -> dict

    def upsert(self, entity, attribute, value, t, principal_id, principal_kind):
        self.facts[(entity, attribute)] = {
            "value": value, "updated_at": t,
            "principal_id": principal_id, "principal_kind": principal_kind}

    def delete(self, entity, attribute):
        self.facts.pop((entity, attribute), None)

    # ---- audit interface (best effort under this data model) ----

    def origin(self, entity, attribute):
        f = self.facts.get((entity, attribute))
        if f is None:
            return None
        # Only the last write survives; it must stand in for the origin.
        return {"value": f["value"], "principal_id": f["principal_id"],
                "principal_kind": f["principal_kind"], "t": f["updated_at"]}

    def supersession_chain(self, entity, attribute):
        f = self.facts.get((entity, attribute))
        return [{"value": f["value"], "from": f["updated_at"], "to": None}] if f else []

    def attribution(self, entity, attribute):
        f = self.facts.get((entity, attribute))
        if f is None:
            return None
        return {"principal_id": f["principal_id"],
                "principal_kind": f["principal_kind"]}

    def belief_at(self, entity, attribute, t):
        f = self.facts.get((entity, attribute))
        if f is None:
            return None
        # No history: can only answer with the current value.
        return f["value"]

    def contamination(self, event_id):
        return []  # no lineage recorded
