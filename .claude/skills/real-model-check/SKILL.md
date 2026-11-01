---
name: real-model-check
description: Prove Jarvis works on a REAL local model, not only in tests. Starts the stick's own llama.cpp with the laptop's model, runs Jarvis in a fresh empty home, asks the owner's everyday questions and grades what he did (tools used, notes on disk, audit chain). Use before telling the owner Jarvis "works", after any change to assistant.py, the gateway, tools, prompts or models, and for "test it for real", "does it actually work".
---

# Real-model check

Unit tests use a scripted model. They cannot catch a real small model doing the wrong
thing. On 2026-11-01 this check caught three things the 824 unit tests missed: Jarvis said
"I've saved that" but saved nothing, he invented a "4 calls remaining" limit, and he never
found the creator tool. Run it before telling the owner that Jarvis works.

## 1. Start the real model (127.0.0.1 only)

Use the stick's own build and the laptop's boss model, the way `bau-llm.service` runs them.
The stick image's llama-server needs `LD_LIBRARY_PATH=/opt/llama.cpp`.

```bash
docker run -d --name bau-llm-test --network host -e LD_LIBRARY_PATH=/opt/llama.cpp \
  -v /path/to/models:/models:ro <stick image> /opt/llama.cpp/llama-server \
  -m /models/Qwen3.5-4B-Q4_K_M.gguf --host 127.0.0.1 --port 8080 --jinja -c 16384 \
  --alias qwen3.5-4b -t 3
curl -s 127.0.0.1:8080/health          # wait for {"status":"ok"}
```

The model file is pinned by SHA-256 in `src/bau/data/registry_defaults.yaml`
(`qwen3.5-4b`). On the owner's laptop the server is already running: skip this step.

## 2. Run the check

```bash
python3 .claude/skills/real-model-check/run.py            # or: run.py MODEL_ID
```

It makes a fresh home, runs the owner's one setup step (`bau creator init`), asks seven
everyday questions and grades each one on what Jarvis did. It prints PASS or FAIL per
check and exits 1 if any check failed. Expect 20 to 90 seconds per answer on 3 CPU cores.

## 3. Report honestly

- Paste the PASS/FAIL lines and the seconds per answer into the PR and to the owner.
- A FAIL is a bug to fix, test-first: write a unit test from the transcript that fails,
  fix it, then run this check again.
- Never approve the model to make the check pass. The script builds the model straight
  from its record, and approval stays the owner's (`bau set-status`).
- Stop the server afterwards: `docker rm -f bau-llm-test`.
