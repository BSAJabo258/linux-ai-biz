# The breakthrough lab: making the AI cheaper, faster and smarter

The owner's ask (2026-11-04): not more AI apps, but the engineering underneath. That means
making a small model do a big model's work, spending less on tokens, getting more out of
the RTX 3060, and connecting agents better.

## How an entry gets in (the owner's reference standard, 2026-11-04)

Every entry has these fields. An entry missing any of them is not ranked.

- **Exact name:** as its source writes it. No shortened or guessed names.
- **Primary reference:** the repository, the official documentation or the original paper,
  opened on the date shown. A page that could not be opened is written as such.
- **Evidence status:** one of these four.
  - *documented feature* (the project's own docs say it does this);
  - *experimental research* (a paper or blog reports it);
  - *in BAU* (BAU's own code does it);
  - *unconfirmed* (no primary source found or opened).
- **What the source supports:** quoted, with the setting it was measured in. A number is
  the authors' claim on their hardware, never a promise for the desktop.
- **Licence:** read in the LICENSE file (only free open source, `CLAUDE.md`).
- **Fit:** whether it works on the desktop's hardware and engine, and how it would join BAU.
- **Test:** how BAU would reproduce it before adopting it.

A repository existing does not prove its benchmark, that it runs here, or that it is ready
for real use. Those are separate checks, done in the sandbox and with `bau models lab`.

The weekly open-source watch (`bau scout watch`, `src/bau/data/scout_watch.yaml`) tracks
these projects and searches the same areas for new ones.

## The desktop everything is judged against

- **Hardware:** RTX 3060 with 12 GB, and 16 GB of system memory (`docs/DESKTOP.md`).
- **Engine:** llama.cpp (build b11747), not vLLM.
- **Local model:** the 9B is the boss.

## Reference register (all opened 2026-11-04)

| Exact name | Primary reference | Status | What the source supports (quoted) | Licence |
|---|---|---|---|---|
| Speculative decoding in llama.cpp | [llama.cpp server README](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md) | in BAU (`sudo bau models tune --draft 6`) | lists "Speculative decoding" and draft-model options | MIT |
| Quantized KV cache in llama.cpp | same README | in BAU (`sudo bau models tune --kv q8_0`) | `--cache-type-k` "allowed values: f32, f16, bf16, q8_0, ..." | MIT |
| P-EAGLE: Faster LLM inference with Parallel Speculative Decoding in vLLM | [vLLM blog, "Amazon and NVIDIA Team", 2026-03-13](https://vllm.ai/blog/p-eagle) | experimental research | "up to 1.69x speedup over vanilla EAGLE-3 ... on NVIDIA B200"; "1.05×–1.69× speedup ... on GPT-OSS 20B"; "All experiments are conducted on one NVIDIA B200 (Blackwell) GPU" | n/a (vLLM feature) |
| vLLM Speculators | [vllm-project/speculators](https://github.com/vllm-project/speculators) | documented feature | "A unified library for building, evaluating, and storing speculative decoding algorithms for LLM inference in vLLM" | Apache-2.0 |
| vLLM quantized (FP8) KV cache | [vLLM docs](https://docs.vllm.ai/features/quantization/quantized_kvcache.html) | unconfirmed: the page answered "too many requests" twice | not read | - |
| TRIM: Hybrid Inference via Targeted Stepwise Routing in Multi-Step Reasoning Tasks (Kapoor, Gupta, Chen, Beniwal, Huang, Kumar) | [ICLR 2026 poster](https://www.iclr.cc/virtual/2026/poster/10009916), [arXiv 2601.10245](https://arxiv.org/abs/2601.10245) | experimental research | "match the strong, expensive model's performance using 80% fewer expensive model tokens" (MATH-500); "On harder benchmarks such as AIME, TRIM achieves up to 6x higher cost efficiency" | paper CC BY 4.0 |
| Cache What Lasts: Token Retention for Memory-Bounded KV Cache in LLMs (TRIM-KV; Bui, Sharma, Lamba, Mishra, Ying) | [arXiv 2512.03324v2](https://arxiv.org/abs/2512.03324v2); code [ngocbh/trimkv](https://github.com/ngocbh/trimkv) | experimental research; the ICLR 2026 listing is unconfirmed (the arXiv page names no venue) | "learns each token's intrinsic importance at creation time via a lightweight retention gate" | code Apache-2.0 |
| LLMLingua | [microsoft/LLMLingua](https://github.com/microsoft/LLMLingua) | documented feature | "compress the prompt and KV-Cache, which achieves up to 20x compression with minimal performance loss"; a quantized example needs "<8GB GPU memory" | MIT |
| Model Context Protocol | [modelcontextprotocol/modelcontextprotocol](https://github.com/modelcontextprotocol/modelcontextprotocol), [reference servers](https://github.com/modelcontextprotocol/servers) | in BAU (`src/bau/mcp.py`) | "Specification and documentation for the Model Context Protocol"; "a collection of reference implementations" | MIT; servers Apache-2.0 (new) / MIT (existing) |
| Agent2Agent (A2A) | [a2aproject/A2A](https://github.com/a2aproject/A2A), [spec site](https://a2a-protocol.org/) | documented feature | "an open source project under the Linux Foundation, contributed by Google" | Apache-2.0 |
| Conductor (Microsoft) | [microsoft/conductor](https://github.com/microsoft/conductor) | documented feature | "No LLM in the orchestration loop, no tokens spent deciding what runs next"; its dashboard shows "model, tokens, cost"; local endpoints "Ollama, vLLM, LM Studio". No `budget_usd` setting and no billing caveat appear on its README | MIT |
| Hybrid Computer Use: A Unified Programmatic, Semantic, and Visual Interface for General Agents (HCU; Microsoft Research) | [microsoft/Hybrid-Computer-Use](https://github.com/microsoft/Hybrid-Computer-Use), [arXiv 2610.41432](https://arxiv.org/abs/2610.41432) | documented feature (new: about 10 stars, paper dated 2026-10-30) | "an open-source Model Context Protocol (MCP) server, `computer-use`"; "batch up to 64 actions in one call"; its AX tools "report their effects as AX diffs" | MIT |
| agent-browser (Vercel Labs) | [vercel-labs/agent-browser](https://github.com/vercel-labs/agent-browser) | documented feature | "`snapshot` returns the page as compact text with a ref such as `@e1` for each element"; `agent-browser mcp` | Apache-2.0 |
| Agent Desktop (Vercel Labs) | [vercel-labs/agent-desktop](https://github.com/vercel-labs/agent-desktop) | documented feature | desktop apps "through the OS accessibility tree"; `agent-desktop mcp` (see the repository review) | Apache-2.0 |
| open-computer-use | [iFurySt/open-computer-use](https://github.com/iFurySt/open-computer-use) | documented feature | "an open-source `Computer Use` service wrapped as `MCP`" on "macOS, Linux, and Windows"; its Linux needs are not stated | MIT |

## Ranked for the desktop

### Have already: use them

- **Speculative decoding and the 8-bit KV cache.** Both are in llama.cpp and switched on with
  `sudo bau models tune` (`docs/GPU.md` section 5). Measure each with `bau models lab`.
- **MCP**, **small model first with a strong model when needed** (`pick_model`, workspace
  brains, supervisor takeover), and **steps that need no model** (autopilot, Fanvue feed
  and autopost).

### Test next

1. **Desktop and browser lanes** (roadmap steps 2 and 3).
   - **Desktop:** compare Agent Desktop, Hybrid Computer Use and open-computer-use.
   - **Browser:** compare agent-browser, Browser Use and Playwright MCP.
   - **Measure each:** tokens per task, time, whether it works on the desktop's XFCE, and how
     each action can be gated.
   - HCU's 64-action batches and AX diffs are aimed at fewer calls and fewer tokens. That is a
     claim to measure.
2. **TRIM-style step routing**, built as BAU code, not installed.
   - The local 9B drafts each step, a check marks the risky ones, and only those go to the paid
     model.
   - Measure paid tokens with `bau usage` against answers kept right.
3. **LLMLingua** on BAU's own long prompts (briefing facts, research pages). Measure tokens saved
   against answers kept right.

### Watch

- **A2A:** for when BAU runs across several computers or businesses.
- **Conductor:** BAU's pipelines already run without model calls, and `bau usage` counts tokens
  and cost.
- **TRIM-KV:** needs gates trained for each model, and is not in llama.cpp.
- **vLLM Speculators:** vLLM only.

### Not for this desktop

- **P-EAGLE:** measured on one NVIDIA B200 in vLLM. BAU's MTP draft in llama.cpp is the version
  this desktop can use.
- **vLLM FP8 KV cache:** BAU uses llama.cpp, whose `q8_0` KV cache gives the memory saving here.
  Its hardware support could not be read (see the register).

## Corrections made on 2026-11-04

- **Hybrid Computer Use:** first listed as unconfirmed. Its repository and paper were then found
  and opened.
- **TRIM:** the 80% figure is "80% fewer" on MATH-500, not "up to 80%".
- **TRIM-KV:** its venue is unconfirmed.
- **Two claims from an outside research note are not on the cited pages:** a `budget_usd` setting
  and a billing caveat for Conductor.
- **The vLLM FP8 hardware note is removed:** it came from a search result, not from the page.
