# The breakthrough lab: making the AI cheaper, faster and smarter

The owner's ask (2026-11-04): not more AI apps, but the engineering underneath. That means
making a small model do a big model's work, spending less on tokens, getting more out of
the RTX 3060, and connecting agents better.

Every item below was looked up on 2026-11-04 on its own page (links given). Each one is
marked as one of:

- **have**: already in BAU;
- **test next**: worth a sandbox test now;
- **watch**: real, but not needed yet;
- **not for this hardware**: built for data-centre GPUs or another engine;
- **not confirmed**: no official page found under that name.

Published numbers are the authors' own claims, measured on their setups, not on the
desktop. Only a test on the desktop counts (`bau models lab`).

The weekly open-source watch (`bau scout watch`, `src/bau/data/scout_watch.yaml`) now
tracks these projects and searches for new ones in the same areas. That keeps the lab
updated by itself.

## The desktop this is judged against

- **Hardware:** RTX 3060 with 12 GB, and 16 GB of system memory (`docs/DESKTOP.md`).
- **Engine:** llama.cpp (build b11747), not vLLM.
- **Local model:** the 9B is the boss.

Techniques built for vLLM or for newer cards (FP8 needs Hopper or later for native
conversion, per vLLM's own docs) do not carry over automatically.

## Ranked

### Have already

| Technique | Where in BAU | Note |
|---|---|---|
| Speculative decoding: a draft guesses ahead, the model checks | `sudo bau models tune --draft 6` (the 9B's built-in MTP draft head), `docs/GPU.md` section 5 | llama.cpp's own server README lists "Speculative decoding" and draft-model options |
| Smaller KV cache (the model's working memory at 8 bits, about half the memory) | `sudo bau models tune --kv q8_0` | llama.cpp: `--cache-type-k` / `--cache-type-v` accept `q8_0`. This is the same saving vLLM's FP8 KV cache gives, on an engine and card BAU has |
| Tools through one standard | the MCP client, `src/bau/mcp.py` | each tool gets its own permission and no keys |
| Small model first, strong model when needed | online hosted models first with the local model as backup (`pick_model`); workspace stages marked `small` or `strong`; the supervisor hands a stuck job to the strong model | what is missing is a check on each step, see TRIM below |
| Steps that need no model at all | the autopilot's scans, the Fanvue feed and autopost, the week of posts | nothing to add |

### Test next

1. **[Agent Browser](https://github.com/vercel-labs/agent-browser)** (vercel-labs,
   Apache-2.0).
   - A browser driver: `snapshot` returns the page "as compact text with a ref such as `@e1`
     for each element", and `agent-browser mcp` serves it over MCP.
   - It comes from the same team and uses the same ref design as Agent Desktop. That means
     far fewer tokens than screenshots.
   - It needs Node, Rust, and Chrome for Testing.
   - **It joins the browser lane test** (roadmap step 3) next to Browser Use and Playwright
     MCP. It may beat both, because it has no agent loop of its own.
2. **TRIM, step-by-step routing**
   ([ICLR 2026 poster](https://www.iclr.cc/virtual/2026/poster/10009916),
   [paper](https://arxiv.org/pdf/2601.10245)).
   - A cheap model does the reasoning. A step checker (a "process reward model") picks out
     the "critical steps that cause solution failure", and only those go to the strong
     model.
   - The authors report matching top models with "up to 80% fewer expensive tokens" and up
     to 6x cost efficiency on AIME. Those are their benchmarks, not ours.
   - **For BAU, this is a pattern to build, not a package to install.** The local 9B drafts
     each step, a check marks the risky ones, and only those go to the paid model. Measure
     with `bau usage`.
3. **[LLMLingua](https://github.com/microsoft/LLMLingua)** (Microsoft, MIT,
   `pip install llmlingua`).
   - It compresses long prompts before they are sent. The authors claim "up to 20x
     compression with minimal performance loss".
   - It runs a small model of its own; one quantized example needs "<8GB GPU memory".
   - **Test:** BAU's own long prompts (briefing facts, research pages). Measure the tokens
     saved against the answers kept right.

### Watch

- **[A2A](https://github.com/a2aproject/A2A)**, agent-to-agent protocol (Apache-2.0, Linux
  Foundation, "contributed by Google"). It lets separately built agents talk to each other.
  It matters when BAU runs across several computers or businesses; not needed for one
  desktop yet.
- **[Microsoft Conductor](https://github.com/microsoft/conductor)** (MIT). YAML multi-agent
  workflows with "no tokens spent deciding what runs next", and MCP steps with "zero prompt
  tokens".
  - Its dashboard shows each step's "model, tokens, cost".
  - It can use local endpoints ("Ollama, vLLM, LM Studio"), routed through its Copilot
    provider setting.
  - BAU's own pipelines already run without model calls, and `bau usage` counts tokens and
    cost, so the idea is kept and a second orchestrator is not added. Revisit if BAU needs
    YAML workflows that people other than the owner write.
- **[Open Computer Use](https://github.com/iFurySt/open-computer-use)** (iFurySt, MIT).
  "An open-source Computer Use service wrapped as MCP" for "macOS, Linux, and Windows"; its
  Linux needs are not stated. A second candidate for the desktop lane next to Agent Desktop.
- **[TRIM-KV](https://arxiv.org/abs/2512.03324v2)** (ICLR 2026, code at
  [ngocbh/trimkv](https://github.com/ngocbh/trimkv), Apache-2.0). It learns which parts of
  the model's working memory to keep. It needs small gates trained for each model and is
  not in llama.cpp, so it is research for now.

### Not for this hardware

- **P-EAGLE** ([vLLM blog](https://vllm.ai/blog/p-eagle)).
  - The "up to 1.69x over EAGLE-3" figure is on NVIDIA B200 data-centre GPUs, with
    specific models (GPT-OSS 20B; Qwen3-Coder 30B in FP8).
  - AWS's own SageMaker table shows about 1.12x to 1.22x at low concurrency.
  - It runs in vLLM, not llama.cpp. BAU's MTP draft (above) is the version this desktop
    can use.
- **vLLM FP8 KV cache**
  ([vLLM docs](https://docs.vllm.ai/features/quantization/quantized_kvcache.html)).
  - It runs in vLLM, and native FP8 conversion is for newer GPUs.
  - The same memory saving on this desktop is llama.cpp's `q8_0` KV cache, which BAU has.

### Not confirmed

- **"Hybrid Computer Use", "batches up to 64 actions per call":** no project under that name
  was found. The closest match is Clawdcursor (accessibility tree plus screenshots, with a
  batch tool). No maximum batch size was found, and its licence is not read. It stays off
  the list until an official page is given.

## The order

1. The browser lane test (roadmap step 3) adds **Agent Browser** to the comparison.
2. **TRIM-style step routing** becomes its own roadmap item after the browser lane. It needs
   BAU's usage meter, the supervisor and a step checker: all BAU code, no new package.
3. **LLMLingua** gets a sandbox test on BAU's own prompts.
4. Everything under "watch" stays in the weekly watch until a need appears.

## The rules that come with every item

- Only free open source (`CLAUDE.md`).
- Every link opened before it is written here.
- Claims kept apart from tests.
- Nothing installed without a sandbox test and the owner's yes.
