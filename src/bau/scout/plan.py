"""Turn one capability request into a research spectrum: several distinct searches.

The same capability hides under different names ("synthetic customers", "consumer
behaviour simulation", "AI personas"), so one query finds one corner of it. The plan is
deterministic (keyword facets below); an approved model may add a few more phrasings,
which are cleaned and tagged as the model's so a report can tell them apart.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

STOP = set("""a an and any are as at be best build can do does find for from get good help
helps how i in into is it its me my need of on or our that the their them these this to
tool tools use using want way we what which with would you your open source opensource
github repo repos repository repositories project projects library libraries something
""".split())

# Facet: a pattern in the request -> other names the same capability goes by.
FACETS: list[tuple[str, str, list[str]]] = [
    ("customers", r"customer|consumer|persona|buyer|shopper|user research|synthetic user",
     ["synthetic customer personas", "consumer behavior simulation",
      "synthetic users product testing", "customer interview automation llm"]),
    ("simulation", r"simulat|virtual (company|people|person)|sandbox world",
     ["agent based simulation llm", "multi agent market simulation",
      "generative agents simulation"]),
    ("business", r"business|market|startup|idea|validat|strategy|pricing",
     ["market research agent", "business idea validation llm",
      "business strategy simulation"]),
    ("agents", r"\bagents?\b|orchestrat|autonomous|crew|swarm",
     ["multi agent framework", "agent orchestration python"]),
    ("coding", r"\bcod(e|ing)\b|software engineer|developer|refactor|pull request",
     ["ai coding agent", "repository code understanding llm"]),
    ("memory", r"memory|remember|knowledge|retriev|\brag\b|notes|second brain",
     ["llm long term memory", "retrieval augmented generation local"]),
    ("video", r"video|animation|animate|film|clip|shorts",
     ["ai video generation open source", "text to video pipeline"]),
    ("image", r"image|picture|illustrat|thumbnail|art\b",
     ["text to image local", "image generation pipeline"]),
    ("audio", r"audio|voice|speech|tts|podcast|narrat",
     ["text to speech open source", "speech recognition local"]),
    ("music", r"music|song|beat|melod|soundtrack",
     ["music generation open source", "audio processing python"]),
    ("browser", r"browser|web automation|scrap|computer use|click",
     ["browser automation agent", "computer use agent"]),
    ("schedule", r"schedul|calendar|booking|appointment|messag|email|crm",
     ["workflow automation self hosted", "scheduling automation open source"]),
    ("research", r"research|extract|summar|paper|document|pdf",
     ["research automation agent", "information extraction llm"]),
    ("inference", r"model serving|inference|local model|llm server|run models",
     ["local llm inference server", "openai compatible server"]),
    ("testing", r"\btest|debug|evaluat|benchmark|observab|monitor",
     ["llm evaluation framework", "llm observability open source"]),
]


@dataclass
class Query:
    q: str
    origin: str                      # request | facet:<name> | model


@dataclass
class Plan:
    request: str
    keywords: list[str]
    facets: list[str]
    queries: list[Query] = field(default_factory=list)

    def public(self) -> dict[str, Any]:
        return {"request": self.request, "keywords": self.keywords, "facets": self.facets,
                "queries": [q.__dict__ for q in self.queries]}


def keywords(text: str) -> list[str]:
    words = re.findall(r"[a-z0-9][a-z0-9+#.-]*", text.lower())
    seen: list[str] = []
    for w in words:
        w = w.strip(".-")
        if len(w) > 1 and w not in STOP and w not in seen:
            seen.append(w)
    return seen


def clean(q: str) -> str:
    """A search phrase is plain words only: no qualifiers (user:, org:), no operators."""
    q = re.sub(r"\b\w+:\S*", " ", q.lower())
    q = re.sub(r"[^a-z0-9 +#.-]", " ", q)
    return re.sub(r"\s+", " ", q).strip()[:80]


def plan(request: str, max_queries: int = 8, provider: Any = None) -> Plan:
    kw = keywords(request)
    if not kw:
        raise ValueError("say what capability you are looking for")
    hit = [(name, alts) for name, rx, alts in FACETS if re.search(rx, request, re.I)]
    p = Plan(request, kw, [n for n, _ in hit])
    out: list[Query] = [Query(" ".join(kw[:6]), "request")]
    # Interleave facets so a small budget still covers every angle once.
    for i in range(max(len(a) for _, a in hit) if hit else 0):
        for name, alts in hit:
            if i < len(alts):
                out.append(Query(alts[i], f"facet:{name}"))
    if provider is not None:
        out[1:1] = [Query(q, "model") for q in model_queries(request, provider)]
    seen: set[str] = set()
    for q in out:
        c = clean(q.q)
        if c and c not in seen:
            seen.add(c)
            p.queries.append(Query(c, q.origin))
        if len(p.queries) >= max_queries:
            break
    return p


def model_queries(request: str, provider: Any, n: int = 4) -> list[str]:
    """Up to n extra phrasings from an approved model. Its reply is data: one search
    phrase per line, cleaned; anything else is dropped."""
    try:
        r = provider.complete(
            "You write GitHub repository search phrases. Reply with one short phrase per "
            "line, 2 to 6 plain words, no numbering, no qualifiers, nothing else.",
            [{"role": "user", "content": f"Different ways people name this capability: "
                                         f"{request[:300]}"}], max_tokens=200)
    except Exception:  # a model that fails never stops a search
        return []
    lines = [clean(x.lstrip("-*0123456789. ")) for x in (r.text or "").splitlines()]
    return [x for x in lines if 2 <= len(x.split()) <= 6][:n]
