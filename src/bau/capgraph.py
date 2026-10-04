"""Capability graph and legal-change impact analysis (spec §43, §94).

Nodes: regulations, policies, gate domains, mission types, factories, capabilities,
models, agents, providers. Edges are derived from the live registries, so the
graph is never a hand-drawn diagram that drifts. ``impact(reg_id)`` answers
"this law changed - what does it touch?"
"""

from __future__ import annotations

from collections import defaultdict, deque
from typing import Any

RELATIONS = {"DEPENDS_ON", "REQUIRES", "PROVIDES", "REPLACES", "CONFLICTS_WITH",
             "FALLBACK_FOR", "LICENSED_BY", "OWNED_BY", "USES_DATA_FROM", "GENERATES",
             "PUBLISHES_TO", "IMPLEMENTS", "GATES", "USES"}


class Graph:
    def __init__(self) -> None:
        self.out: dict[str, set[tuple[str, str]]] = defaultdict(set)
        self.inc: dict[str, set[tuple[str, str]]] = defaultdict(set)

    def edge(self, a: str, rel: str, b: str) -> None:
        if rel not in RELATIONS:
            raise ValueError(f"unknown relation {rel}")
        self.out[a].add((rel, b))
        self.inc[b].add((rel, a))

    def dependents(self, node: str) -> list[str]:
        """Everything that (transitively) depends on node."""
        seen, q = set(), deque([node])
        while q:
            n = q.popleft()
            for _, src in self.inc.get(n, ()):
                if src not in seen:
                    seen.add(src)
                    q.append(src)
        return sorted(seen)

    def to_dict(self) -> dict[str, Any]:
        return {a: sorted(f"{r} {b}" for r, b in es) for a, es in sorted(self.out.items())}


def build(engine: Any, missions: dict[str, Any], factories: dict[str, Any],
          capabilities: dict[str, dict[str, Any]] | None = None) -> Graph:
    g = Graph()
    for p in engine.policies:
        for r in p.regs:
            g.edge(f"policy:{p.id}", "IMPLEMENTS", f"reg:{r}")
        g.edge(f"domain:{p.domain}", "DEPENDS_ON", f"policy:{p.id}")
    for name, mt in missions.items():
        for d in mt.get("requires", []):
            g.edge(f"mission:{name}", "REQUIRES", f"domain:{d}")
        for c in mt.get("capabilities", []):
            g.edge(f"mission:{name}", "USES", f"capability:{c}")
    for name, f in factories.items():
        g.edge(f"factory:{name}", "DEPENDS_ON", f"mission:{f['mission_type']}")
        for st in f["stages"]:
            if st["type"] == "gate":
                g.edge(f"factory:{name}", "REQUIRES", f"domain:{st['domain']}")
            if st.get("capability"):
                g.edge(f"factory:{name}", "USES", f"capability:{st['capability']}")
    for kind, recs in (capabilities or {}).items():
        for key, rec in recs.items():
            node = f"{kind}:{key}"
            if kind == "model" and rec.get("provider"):
                g.edge(node, "DEPENDS_ON", f"provider:{rec['provider']}")
                g.edge(node, "LICENSED_BY", f"license:{rec.get('license')}")
            if kind == "agent":
                g.edge(node, "USES", f"model:{rec.get('model')}")
                for t in rec.get("tools", []):
                    g.edge(node, "USES", f"capability:{t}")
    return g


def impact(g: Graph, reg_id: str) -> dict[str, list[str]]:
    deps = g.dependents(f"reg:{reg_id}")
    out: dict[str, list[str]] = defaultdict(list)
    for d in deps:
        kind, name = d.split(":", 1)
        out[kind].append(name)
    return dict(out)
