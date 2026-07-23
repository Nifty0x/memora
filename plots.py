"""Generate result figures (PDF) for the paper from measured data."""
import csv, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams.update({"font.family": "serif", "font.size": 9,
                     "axes.spines.top": False, "axes.spines.right": False})
HERE = os.path.dirname(os.path.abspath(__file__))
FIGS = os.path.join(os.path.dirname(HERE), "paper", "figures")
os.makedirs(FIGS, exist_ok=True)


def fig_design_space():
    systems = [
        # name, x, y, provenance, label_x, label_y, ha
        ("MemGPT/Letta", 0.15, 0.05, 0.15, 0.17, 0.030, "left"),
        ("Mem0",         0.10, 0.15, 0.30, 0.08, 0.190, "left"),
        ("A-MEM",        0.25, 0.10, 0.15, 0.23, 0.110, "right"),
        ("MIRIX",        0.30, 0.22, 0.25, 0.32, 0.230, "left"),
        ("M3-Agent",     0.40, 0.27, 0.20, 0.42, 0.290, "left"),
        ("Cognee",       0.45, 0.15, 0.35, 0.47, 0.160, "left"),
        ("HippoRAG",     0.55, 0.08, 0.15, 0.57, 0.040, "left"),
        ("Obsidian+git", 0.60, 0.10, 0.45, 0.62, 0.120, "left"),
        ("MemOS",        0.55, 0.45, 0.60, 0.57, 0.470, "left"),
        ("Zep/Graphiti", 0.65, 0.95, 0.50, 0.55, 0.870, "left"),
        ("MemPalace",    0.80, 0.30, 0.35, 0.78, 0.320, "right"),
        ("BPMA (ours)",  0.97, 0.97, 1.00, 0.80, 0.880, "left"),
    ]
    fig, ax = plt.subplots(figsize=(5.6, 3.4))
    xs = [s[1] for s in systems]; ys = [s[2] for s in systems]
    cs = [s[3] for s in systems]
    sc = ax.scatter(xs[:-1], ys[:-1], c=cs[:-1], cmap="viridis", vmin=0, vmax=1,
                    s=55, edgecolors="black", linewidths=0.4, zorder=3)
    ax.scatter([xs[-1]], [ys[-1]], c=[cs[-1]], cmap="viridis", vmin=0, vmax=1,
               s=210, marker="*", edgecolors="black", linewidths=0.6, zorder=4)
    for name, x, y, c, lx, ly, ha in systems:
        ax.annotate(name, (x, y), xytext=(lx, ly), fontsize=7.5, ha=ha)
    cb = fig.colorbar(sc, ax=ax, shrink=0.85)
    cb.set_label("provenance depth (qualitative)", fontsize=8)
    ax.set_xlabel("update discipline (destructive $\\rightarrow$ append-only)")
    ax.set_ylabel("temporal awareness (none $\\rightarrow$ bitemporal)")
    ax.set_xlim(0, 1.05); ax.set_ylim(0, 1.08)
    fig.tight_layout()
    fig.savefig(os.path.join(FIGS, "fig_design_space.pdf"))
    print("fig_design_space.pdf")


def fig_auditeval():
    from memora import auditeval as ae
    timeline, truth = ae.generate()
    ledger, event_of = ae.load_into_memora(timeline)
    store = ae.load_into_baseline(timeline)
    m = ae.score(truth, memora=ledger, event_of=event_of)
    b = ae.score(truth, baseline=store)
    with open(os.path.join(HERE, "auditeval_results.json"), "w") as f:
        json.dump({"memora": m, "baseline": b,
                   "n_pairs": len(truth), "seed": 7}, f, indent=1)
    labels = ["origin", "supersession", "attribution", "belief_at", "contamination"]
    pretty = ["Origin", "Supersession", "Attribution", "Belief-at-time", "Contamination"]
    fig, ax = plt.subplots(figsize=(5.6, 2.7))
    x = range(len(labels)); w = 0.38
    ax.bar([i - w / 2 for i in x], [m[l] for l in labels], w,
           label="Memora (BPMA)", color="#2c7fb8", edgecolor="black", linewidth=0.4)
    ax.bar([i + w / 2 for i in x], [b[l] for l in labels], w,
           label="Destructive-update baseline", color="#d95f0e",
           edgecolor="black", linewidth=0.4)
    for i, l in enumerate(labels):
        ax.text(i - w / 2, m[l] + 2, f"{m[l]:.0f}", ha="center", fontsize=7.5)
        ax.text(i + w / 2, b[l] + 2, f"{b[l]:.1f}", ha="center", fontsize=7.5)
    ax.set_xticks(list(x)); ax.set_xticklabels(pretty, fontsize=8)
    ax.set_ylabel("accuracy (%)"); ax.set_ylim(0, 112)
    ax.legend(fontsize=8, frameon=False, loc="lower center", bbox_to_anchor=(0.5, 1.0), ncol=2)
    fig.tight_layout()
    fig.savefig(os.path.join(FIGS, "fig_auditeval.pdf"))
    print("fig_auditeval.pdf", m, b)


def fig_systems():
    rows = list(csv.DictReader(open(os.path.join(HERE, "bench_results.csv"))))
    n = [int(r["n_events"]) for r in rows]
    fig, axes = plt.subplots(1, 3, figsize=(6.6, 2.3))
    a = axes[0]
    a.plot(n, [float(r["search_p50_ms"]) for r in rows], "o-", ms=3.5, label="hybrid search p50")
    a.plot(n, [float(r["search_p95_ms"]) for r in rows], "s--", ms=3.5, label="hybrid search p95")
    a.plot(n, [float(r["claim_lookup_p50_ms"]) for r in rows], "^-", ms=3.5, label="claim lookup p50")
    a.set_yscale("log"); a.set_xlabel("Memory Events"); a.set_ylabel("latency (ms)")
    a.legend(fontsize=6.5, frameon=False)
    b = axes[1]
    b.plot(n, [float(r["rebuild_lexical_s"]) for r in rows], "o-", ms=3.5, label="lexical rebuild")
    b.plot(n, [float(r["rebuild_vector_s"]) for r in rows], "s--", ms=3.5, label="vector rebuild")
    b.set_xlabel("Memory Events"); b.set_ylabel("full replay time (s)")
    b.legend(fontsize=6.5, frameon=False)
    c = axes[2]
    c.plot(n, [float(r["db_size_mb"]) for r in rows], "o-", ms=3.5, color="#2c7fb8")
    c.set_xlabel("Memory Events"); c.set_ylabel("ledger size (MB)")
    for ax in axes:
        ax.ticklabel_format(axis="x", style="sci", scilimits=(0, 3))
    fig.tight_layout()
    fig.savefig(os.path.join(FIGS, "fig_systems.pdf"))
    print("fig_systems.pdf")


if __name__ == "__main__":
    fig_design_space(); fig_auditeval(); fig_systems()
