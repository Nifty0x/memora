"""Memora: reference implementation of the Bitemporal Provenance Memory Architecture (BPMA).

Core layer: Memory Events, Claims, the canonical append-only ledger,
versioned transforms, quarantine, and erasure with receipts.

Author: Marko Vidrih. License: MIT. Stdlib only, SQLite backend.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS memory_events (
    id TEXT PRIMARY KEY,
    payload TEXT,
    payload_hash TEXT NOT NULL,
    modality TEXT NOT NULL,
    t_event REAL NOT NULL,
    t_ingested REAL NOT NULL,
    principal_id TEXT,
    principal_kind TEXT,
    model_ref TEXT,
    scope TEXT NOT NULL DEFAULT 'default',
    status TEXT NOT NULL DEFAULT 'active',
    source_event_ids TEXT NOT NULL DEFAULT '[]'
);
CREATE TABLE IF NOT EXISTS claims (
    id TEXT PRIMARY KEY,
    entity TEXT NOT NULL,
    attribute TEXT NOT NULL,
    value TEXT NOT NULL,
    t_valid_from REAL NOT NULL,
    t_valid_to REAL,
    t_ingested REAL NOT NULL,
    source_event_ids TEXT NOT NULL,
    transform_id TEXT NOT NULL,
    transform_version TEXT NOT NULL,
    principal_id TEXT NOT NULL,
    principal_kind TEXT NOT NULL,
    model_ref TEXT,
    scope TEXT NOT NULL DEFAULT 'default',
    supersedes TEXT,
    confirmed_by_human INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS erasure_receipts (
    id TEXT PRIMARY KEY,
    event_id TEXT NOT NULL,
    reason TEXT NOT NULL,
    requested_by TEXT NOT NULL,
    t_erased REAL NOT NULL,
    payload_hash TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_claims_ea ON claims(entity, attribute);
CREATE INDEX IF NOT EXISTS idx_claims_valid ON claims(t_valid_from, t_valid_to);
CREATE INDEX IF NOT EXISTS idx_events_scope ON memory_events(scope, status);
"""


def now() -> float:
    return time.time()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def canonical_hash(obj: Any) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


@dataclass
class Principal:
    id: str
    kind: str            # human | agent | pipeline
    model_ref: Optional[str] = None


@dataclass
class MemoryEvent:
    id: str
    payload: Optional[str]
    payload_hash: str
    modality: str
    t_event: float
    t_ingested: float
    principal_id: Optional[str]
    principal_kind: Optional[str]
    model_ref: Optional[str]
    scope: str
    status: str
    source_event_ids: list = field(default_factory=list)


@dataclass
class Claim:
    id: str
    entity: str
    attribute: str
    value: str
    t_valid_from: float
    t_valid_to: Optional[float]
    t_ingested: float
    source_event_ids: list
    transform_id: str
    transform_version: str
    principal_id: str
    principal_kind: str
    model_ref: Optional[str]
    scope: str
    supersedes: Optional[str]
    confirmed_by_human: bool = False


class Ledger:
    """Canonical, append-only event record with bitemporal claims on top."""

    def __init__(self, path: str = ":memory:"):
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)

    # ---------- Layer 1: capture ----------

    def append_event(
        self,
        payload: str,
        modality: str = "text",
        t_event: Optional[float] = None,
        principal: Optional[Principal] = None,
        scope: str = "default",
        source_event_ids: Optional[list] = None,
    ) -> MemoryEvent:
        """Append a Memory Event. Writes without a principal are quarantined,
        never silently admitted (injection defense)."""
        t_ing = now()
        ev = MemoryEvent(
            id=new_id("ev"),
            payload=payload,
            payload_hash=hashlib.sha256(payload.encode()).hexdigest(),
            modality=modality,
            t_event=t_event if t_event is not None else t_ing,
            t_ingested=t_ing,
            principal_id=principal.id if principal else None,
            principal_kind=principal.kind if principal else None,
            model_ref=principal.model_ref if principal else None,
            scope=scope,
            status="active" if principal else "quarantined",
            source_event_ids=source_event_ids or [],
        )
        self.db.execute(
            "INSERT INTO memory_events VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (ev.id, ev.payload, ev.payload_hash, ev.modality, ev.t_event,
             ev.t_ingested, ev.principal_id, ev.principal_kind, ev.model_ref,
             ev.scope, ev.status, json.dumps(ev.source_event_ids)),
        )
        self.db.commit()
        return ev

    # ---------- Layer 2: bitemporal claims ----------

    def assert_claim(
        self,
        entity: str,
        attribute: str,
        value: str,
        t_valid_from: float,
        source_event_ids: list,
        transform_id: str,
        transform_version: str,
        principal: Principal,
        scope: str = "default",
    ) -> Claim:
        """Record a Claim. If an open claim exists for (entity, attribute),
        close its validity interval and link supersession. Nothing is deleted."""
        cur = self.db.execute(
            "SELECT id FROM claims WHERE entity=? AND attribute=? AND scope=? "
            "AND t_valid_to IS NULL ORDER BY t_valid_from DESC LIMIT 1",
            (entity, attribute, scope),
        )
        row = cur.fetchone()
        supersedes = row["id"] if row else None
        if supersedes:
            self.db.execute(
                "UPDATE claims SET t_valid_to=? WHERE id=?", (t_valid_from, supersedes)
            )
        c = Claim(
            id=new_id("cl"), entity=entity, attribute=attribute, value=value,
            t_valid_from=t_valid_from, t_valid_to=None, t_ingested=now(),
            source_event_ids=source_event_ids, transform_id=transform_id,
            transform_version=transform_version, principal_id=principal.id,
            principal_kind=principal.kind, model_ref=principal.model_ref,
            scope=scope, supersedes=supersedes,
        )
        self.db.execute(
            "INSERT INTO claims VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (c.id, c.entity, c.attribute, c.value, c.t_valid_from, c.t_valid_to,
             c.t_ingested, json.dumps(c.source_event_ids), c.transform_id,
             c.transform_version, c.principal_id, c.principal_kind, c.model_ref,
             c.scope, c.supersedes, int(c.confirmed_by_human)),
        )
        self.db.commit()
        return c

    # ---------- reads ----------

    def events(self, scope: Optional[str] = None, status: str = "active") -> list:
        q = "SELECT * FROM memory_events WHERE status=?"
        args = [status]
        if scope:
            q += " AND scope=?"
            args.append(scope)
        q += " ORDER BY t_ingested"
        return [self._row_to_event(r) for r in self.db.execute(q, args)]

    def get_event(self, event_id: str) -> Optional[MemoryEvent]:
        r = self.db.execute("SELECT * FROM memory_events WHERE id=?", (event_id,)).fetchone()
        return self._row_to_event(r) if r else None

    def get_claim(self, claim_id: str) -> Optional[Claim]:
        r = self.db.execute("SELECT * FROM claims WHERE id=?", (claim_id,)).fetchone()
        return self._row_to_claim(r) if r else None

    def claims_for(self, entity: str, attribute: Optional[str] = None) -> list:
        if attribute:
            rows = self.db.execute(
                "SELECT * FROM claims WHERE entity=? AND attribute=? ORDER BY t_valid_from",
                (entity, attribute))
        else:
            rows = self.db.execute(
                "SELECT * FROM claims WHERE entity=? ORDER BY t_valid_from", (entity,))
        return [self._row_to_claim(r) for r in rows]

    def all_claims(self) -> list:
        rows = self.db.execute("SELECT * FROM claims ORDER BY t_ingested")
        return [self._row_to_claim(r) for r in rows]

    # ---------- erasure with receipts (Layer 6) ----------

    def erase_event(self, event_id: str, reason: str, requested_by: str) -> str:
        """Right-to-erasure: destroy payload, keep hash, lineage, and a receipt."""
        ev = self.get_event(event_id)
        if ev is None:
            raise KeyError(event_id)
        self.db.execute(
            "UPDATE memory_events SET payload=NULL, status='erased' WHERE id=?",
            (event_id,))
        rid = new_id("er")
        self.db.execute(
            "INSERT INTO erasure_receipts VALUES (?,?,?,?,?,?)",
            (rid, event_id, reason, requested_by, now(), ev.payload_hash))
        self.db.commit()
        return rid

    def approve_quarantined(self, event_id: str, principal: Principal) -> None:
        self.db.execute(
            "UPDATE memory_events SET status='active', principal_id=?, principal_kind=?, "
            "model_ref=? WHERE id=? AND status='quarantined'",
            (principal.id, principal.kind, principal.model_ref, event_id))
        self.db.commit()

    def quarantined(self) -> list:
        rows = self.db.execute("SELECT * FROM memory_events WHERE status='quarantined'")
        return [self._row_to_event(r) for r in rows]

    def stats(self) -> dict:
        e = self.db.execute("SELECT COUNT(*) c FROM memory_events").fetchone()["c"]
        c = self.db.execute("SELECT COUNT(*) c FROM claims").fetchone()["c"]
        r = self.db.execute("SELECT COUNT(*) c FROM erasure_receipts").fetchone()["c"]
        return {"events": e, "claims": c, "erasure_receipts": r}

    # ---------- helpers ----------

    @staticmethod
    def _row_to_event(r: sqlite3.Row) -> MemoryEvent:
        d = dict(r)
        d["source_event_ids"] = json.loads(d["source_event_ids"])
        return MemoryEvent(**d)

    @staticmethod
    def _row_to_claim(r: sqlite3.Row) -> Claim:
        d = dict(r)
        d["source_event_ids"] = json.loads(d["source_event_ids"])
        d["confirmed_by_human"] = bool(d["confirmed_by_human"])
        return Claim(**d)


class Transform:
    """A named, versioned, deterministic derivation step. Rerunning transform
    version v over the same ledger prefix reproduces identical Claims."""

    id = "transform.base"
    version = "0.0"

    def apply(self, ledger: Ledger, event: MemoryEvent) -> list:
        raise NotImplementedError


class RuleClaimExtractor(Transform):
    """Deterministic extractor for structured statements of the form
    'entity.attribute = value'. Stands in for an LLM extractor; the interface
    is identical and the transform id and version are logged either way."""

    id = "transform.claim_extract.rule"
    version = "1.0"

    def __init__(self, principal: Principal):
        self.principal = principal

    def apply(self, ledger: Ledger, event: MemoryEvent) -> list:
        out = []
        if not event.payload:
            return out
        for line in event.payload.splitlines():
            line = line.strip()
            if "=" in line and "." in line.split("=")[0]:
                left, value = line.split("=", 1)
                entity, attribute = left.strip().rsplit(".", 1)
                out.append(ledger.assert_claim(
                    entity=entity.strip(), attribute=attribute.strip(),
                    value=value.strip(), t_valid_from=event.t_event,
                    source_event_ids=[event.id], transform_id=self.id,
                    transform_version=self.version, principal=self.principal,
                    scope=event.scope))
        return out
