# The graphics card: measure it, then make AI faster on it

For the desktop's NVIDIA card (docs/DESKTOP.md). The rule is the same as for models: find
out what the card is, measure, change one thing, measure again, keep only what is faster
in your own numbers. Nothing here changes the card itself.

## 1. What card is this, exactly?

After `sudo bau-gpu-setup` and a restart:

```bash
bau hw          # the summary
bau hw --full   # every detail
```

It reads, and changes nothing:

- the card's name, memory and free memory, driver and compute level (`nvidia-smi`);
- its exact PCI ID (vendor:device, e.g. `10de:xxxx`) and board ID, read from the system
  even before NVIDIA's driver runs: tools made for particular cards must match this exact
  ID, not just the family;
- temperature, power draw and limit, how busy it is, power state;
- Secure Boot on or off (`mokutil --sb-state`);
- which AI engines and frameworks are present: the stick's llama.cpp, the CUDA build (if
  made), TensorFlow, PyTorch, TensorRT, cuDNN. Found, never started.

Your check report (2026-10-23) says RTX 3060 with 12 GB on the card, 16 GB of system
memory; `bau hw` confirms both on Linux.

## 2. Measure: the model lab

The lab (docs/MODEL-LAB.md) now also records, while it runs, the card's peak memory, its
highest temperature and power draw and how busy it was. Run it several times to see how
much the numbers move between runs:

```bash
bau models lab qwen3.5-9b --run-code --repeat 3
```

With `--repeat` you get the middle value, the lowest and the highest speed, and how many
runs failed. One lucky run never decides.

## 3. A second engine: CUDA (the first thing worth trying)

The stick's model engine (llama.cpp) talks to the card through Vulkan, which works on any
graphics chip. NVIDIA's own CUDA is the other way in, and on NVIDIA cards it is often
faster; whether it is faster on yours is exactly what to measure.

```bash
sudo bau-llm-cuda build          # once: Debian's CUDA tools, about 15 minutes, asks y first
bau models lab qwen3.5-9b --repeat 3                      # the Vulkan engine (baseline)
sudo bau-llm-cuda use cuda
bau models lab qwen3.5-9b --repeat 3 --tag cuda           # the same test on CUDA
bau models compare qwen3.5-9b qwen3.5-9b@cuda
```

Keep whichever is faster with the same right answers. Back to the stick's engine at any
time: `sudo bau-llm-cuda use vulkan`. `sudo bau-llm-cuda status` says which one runs.

How it is built: Debian 13's own `nvidia-cuda-toolkit` 12.4.131 (from Debian's non-free
area, which `bau-gpu-setup` already turned on), the same llama.cpp commit as the stick
(b11747), for your card's compute level only. It goes to `/opt/llama.cpp-cuda`; the
stick's engine in `/opt/llama.cpp` is never touched.

Tested 2026-10-27, in a clean Debian 13: the build works (14 minutes on 4 cores) and needs
`libcudart.so.12` and `libcublas.so.12` (from the toolkit) and `libcuda.so.1` (from
NVIDIA's driver). Not tested: running on your card (the test machine has no graphics card).

## 4. Other ways to make models faster, ranked

| # | What | Why | Status |
|---|---|---|---|
| 1 | Measure the baseline (section 2) | nothing else can be judged without it | ready |
| 2 | CUDA engine (section 3) | NVIDIA's own path; often faster than Vulkan on NVIDIA | ready to try |
| 3 | The right model size for 12 GB (docs/MODEL-LAB.md) | a model that fits on the card whole is many times faster than one spilling into memory | ready: Qwen3.8-27B 2-bit and 3-bit to test |
| 4 | Context length | the 9B is set to 16K words of context; less leaves more room, more costs memory | change only after a lab run shows the need |
| 5 | Guessing ahead: the 9B with its own draft head (MTP, section 5) | can speed up writing; the answers stay the model's own | ready to try on the card |
| 6 | Smaller KV cache (`--kv q8_0`, section 5) | half the memory for the model's working notes, for longer prompts | only if long prompts run out of card memory |
| 7 | Other engines: ExLlamaV3, vLLM | made for NVIDIA cards; need PyTorch and their own model formats | watch list; not before 1-3 show where time goes |

Not on the list, and why: making a smaller model from a big one (distillation) is a
training job for the model's makers, BAU downloads their results (the 4B, the 9B);
serving many people at once (continuous batching) and splitting one model over several
cards (tensor and pipeline parallelism) are for servers with many users or many cards,
and the desktop has one owner and one card. Quantization (the 4-bit files) and the KV
cache are already in use.

## 5. Faster writing: guessing ahead (MTP) and a smaller KV cache

**Guessing ahead (speculative decoding).** A model writes one word-piece at a time. A
small extra layer can guess the next few, and the model then checks all the guesses in
one step: the right ones are kept, the first wrong one is thrown away. The answer is
exactly what the model would have written; only the speed changes. Qwen3.5 has that
extra layer (MTP, "multi-token prediction"); unsloth publishes files that keep it
(`unsloth/Qwen3.5-9B-MTP-GGUF`), and the stick's llama.cpp runs it.

```bash
bau models fetch qwen3.5-9b-mtp                 # 5.9 GB, checked against its SHA-256
sudo bau models use qwen3.5-9b-mtp
bau models lab qwen3.5-9b-mtp --repeat 3
bau models compare qwen3.5-9b qwen3.5-9b-mtp    # same scores? faster?
```

How far it guesses ahead is one setting: 3 to start. Try others and measure each:

```bash
sudo bau models tune --draft 6
bau models lab qwen3.5-9b-mtp --repeat 3 --tag draft6
bau models compare qwen3.5-9b-mtp qwen3.5-9b-mtp@draft6
```

`sudo bau models tune --draft off` turns guessing off without changing the file.

Measured here (2026-10-27, the 4B version, the stick's llama.cpp b11747, 3 processor
threads, no card), words per second:

| | Free prose | A list of numbers | Code |
|---|---|---|---|
| Plain 4B | 6.0 | 6.0 | 6.1 |
| MTP file, guessing off | 5.9 | 5.8 | 5.8 |
| Guessing 1 ahead | 5.8 | 6.8 | 7.0 |
| Guessing 2 ahead | 5.2 | 7.5 | 6.9 |
| Guessing 3 ahead | 4.5 | 9.4 | 7.9 |
| Guessing 6 ahead (unsloth's suggestion) | 2.8 | 9.0 | 6.1 |

The whole lab on the MTP 4B (guessing 3 ahead) gave the same scores as the plain 4B
(reasoning 9 of 10, tools, JSON, coding and long prompts all right: meets the bar), but
took 10 minutes instead of 6 and the first word came after 1.9 s instead of 1.3 s.

So: on a processor, guessing pays on predictable text (lists, code, forms) and costs on
free prose, where most guesses are wrong (about 1 in 5 kept at 6 ahead). The laptop keeps
the plain 4B. On the card, checking guesses costs much less time, which is why it is
worth measuring there; unsloth says about 1.5 to 2 times faster (their claim, not
measured here). Unsloth's README also says MTP serves one conversation at a time
(`-np 1`), which BAU sets.

**A smaller KV cache.** While it reads and writes, the model keeps working notes for
every word-piece in the conversation (the KV cache). By default they are stored at
16 bits; `q8_0` stores them at 8 bits, half the memory, with a very small loss of
precision.

```bash
sudo bau models tune --kv q8_0
bau models lab qwen3.5-9b --tag kv8
bau models compare qwen3.5-9b qwen3.5-9b@kv8
```

Measured here (the 4B, 16K context): the same speed (6.0 words per second) and its KV
cache went from 512 MB to 272 MB. The 4B keeps these notes in only 8 of its layers, so
the saving is small at the stick's 8K context (the 9B not measured yet).
Use it only when long prompts run out of card memory; `sudo bau models tune --kv f16`
goes back. `sudo bau models tune --reset` forgets every tune setting.

The tune settings live in `/etc/bau/llm-tune.env` and stay when you change the model.
Only these settings exist; a model's own settings (the MTP files' `server_env`) are
checked against a short list, so no file can move the server off this computer.

## 6. TensorFlow: not installed, on purpose


Nothing in BAU uses TensorFlow today: the local models run in llama.cpp. TensorFlow would
add several GB and its own CUDA libraries for no workload. It is installed only when a
real BAU job needs it, and then kept apart from the model engine.

Two kinds of "quantization" that are not the same thing:

| | TensorFlow / Keras (Model Optimization Toolkit) | Language models in BAU (llama.cpp) |
|---|---|---|
| For | TensorFlow models (vision, small networks) | large language models |
| Formats | SavedModel, TFLite (int8, float16), pruned models | GGUF (Q2-Q8, IQ, UD); elsewhere EXL3, AWQ, GPTQ, FP8, NVFP4, MXFP4 |
| How it is made | post-training quantization, quantization-aware training, pruning, in Python | converted once by the model's publisher (e.g. unsloth); BAU downloads the file pinned by SHA-256 |
| Runs in | TensorFlow / TFLite | llama.cpp (Vulkan or CUDA) |

A file of one kind does not work in the other. Watched: github.com/tensorflow/model-optimization,
tensorflow.org/guide/gpu, tensorflow.org/model_optimization.

## 7. "GPU unlock" projects: reviewed, not used

Four repositories claim to unlock faster tensor math on GeForce cards:
github.com/Zagitta/gpu-unlock (the original) and three forks,
github.com/SpeechlessPanda/gpu-unlock, github.com/JustAResearcher/gpu-unlock-ada and
github.com/miounet11/gpuunlock. Read on 2026-10-27 (commits 6081407, ba8604b, d28c485 and
3a251b7), downloaded to a closed folder and only read, never built or run.

What was found:

- All four are one Linux kernel module (GPL-2.0) that runs at start-up before NVIDIA's
  driver. It relies on a flaw in NVIDIA's own signed start-up firmware, and uses firmware
  taken from a newer NVIDIA driver than Debian's. Installing it changes the start-up
  configuration; the screen goes blank while it runs.
- They list nine device IDs of the RTX 3060's chip family (GA106). None publishes a test
  on a GA106 card: the measured gains are on other cards (RTX 3090 Ti, 4090, 4070 Ti
  SUPER, 3050).
- The gain is for one kind of math (16-bit inputs adding up in 32-bit). The one
  quantized-model inference test those projects published showed no gain, and BAU's
  local models are quantized (GGUF). Writing words is limited mostly by memory speed,
  which this does not change.

Decision: BAU does not install, build or activate any of them. The risk to the computer
is real and the benefit for BAU's work is not shown; sections 2-4 are where the measured
speed comes from.

## Tested so far (2026-10-27)

- Tests: `tests/test_machine.py` (card ID, temperature, power, Secure Boot, unknown values
  from an older driver), `tests/test_model_lab.py` (temperature, power and load sampled;
  `--repeat` range; `--tag` kept apart), `tests/test_llm_cuda.py` (nothing without y;
  the stick's commit and the card's level; refused on the live stick, without the driver,
  without sudo; switching and back). Removing the commit check makes its test fail.
- The CUDA build in a clean Debian 13 (above). The systemd rule that the engine file wins
  over the service's own settings, read in systemd.exec(5) of Debian 13's systemd 257.
- The field names `bau hw` asks nvidia-smi for are in Debian 13's nvidia-smi 550.163.01.
- Speed settings (section 5): `tests/test_llm_speed.py` (an MTP model starts with its
  draft head on; a model record cannot set anything outside the short list, e.g. the
  address; tune keeps, changes and resets its settings and refuses anything else; the
  service reads the tune file last). Removing either check makes its test fail. In the
  stick's llama.cpp b11747: the MTP draft ran (its log shows the accepted guesses), q8_0
  cache, guessing off and a draft length on a plain model all start and answer right.
- Not yet on your desktop: nothing here has run on the RTX 3060 itself.
