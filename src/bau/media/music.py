"""Music video factory timing (spec §58): the real audio is the master clock.

Pure-Python analysis of a WAV file (other formats are converted with ffmpeg
first): energy envelope, onsets, tempo (autocorrelation), beat grid, sections,
drops and pauses. ``edit_decision_list`` then places cuts on beats and scene
changes on section boundaries - never a generic video unrelated to the song.
"""

from __future__ import annotations

import array
import math
import shutil
import subprocess
import tempfile
import wave
from pathlib import Path
from typing import Any

HOP = 512           # samples per analysis frame at the working rate
WORK_RATE = 11025   # downsample target for speed


def _read_mono(path: Path) -> tuple[list[float], int]:
    with wave.open(str(path), "rb") as w:
        ch, width, rate, n = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
        raw = w.readframes(n)
    if width != 2:
        raise ValueError("only 16-bit PCM WAV is supported (convert with ffmpeg)")
    samples = array.array("h", raw)
    step = max(1, rate // WORK_RATE)
    mono = []
    for i in range(0, len(samples) - ch + 1, ch * step):
        mono.append(sum(samples[i:i + ch]) / (ch * 32768.0))
    return mono, rate // step


def to_wav(path: Path) -> Path:
    if path.suffix.lower() == ".wav":
        return path
    ff = shutil.which("ffmpeg")
    if not ff:
        raise ValueError("ffmpeg is required to analyse non-WAV audio")
    out = Path(tempfile.mkdtemp()) / (path.stem + ".wav")
    subprocess.run([ff, "-y", "-loglevel", "error", "-i", str(path), "-ac", "1", "-ar",
                    str(WORK_RATE), "-sample_fmt", "s16", str(out)], check=True)
    return out


def analyze(path: Path) -> dict[str, Any]:
    mono, rate = _read_mono(to_wav(path))
    if not mono:
        raise ValueError("empty audio")
    frame_t = HOP / rate
    energy = []
    for i in range(0, len(mono) - HOP + 1, HOP):
        seg = mono[i:i + HOP]
        energy.append(math.sqrt(sum(x * x for x in seg) / HOP))
    duration = len(mono) / rate
    if len(energy) < 8:
        return {"duration_s": round(duration, 3), "tempo_bpm": None, "beats": [],
                "sections": [], "drops": [], "pauses": []}
    # Onset strength: positive energy change, normalised.
    onset = [max(0.0, energy[i] - energy[i - 1]) for i in range(1, len(energy))]
    onset.insert(0, 0.0)
    peak = max(onset) or 1.0
    onset = [o / peak for o in onset]
    # Tempo by autocorrelation over 60-200 BPM.
    best_lag, best = None, 0.0
    for bpm in range(60, 201):
        lag = round(60 / bpm / frame_t)
        if lag < 1 or lag >= len(onset) // 2:
            continue
        s = sum(onset[i] * onset[i - lag] for i in range(lag, len(onset)))
        if s > best:
            best, best_lag = s, lag
    tempo = round(60 / (best_lag * frame_t), 1) if best_lag else None
    beats: list[float] = []
    if best_lag:
        # Phase: the offset within one period with the strongest onsets.
        phase = max(range(best_lag), key=lambda p: sum(onset[p::best_lag]))
        beats = [round(i * frame_t, 3) for i in range(phase, len(onset), best_lag)]
    # Sections: split where the 4-second smoothed energy changes markedly.
    win = max(1, round(4 / frame_t))
    smooth = [sum(energy[max(0, i - win):i + 1]) / (i + 1 - max(0, i - win))
              for i in range(len(energy))]
    mean_e = sum(energy) / len(energy)
    sections, start = [], 0
    for i in range(win, len(smooth), win):
        if abs(smooth[i] - smooth[i - win]) > 0.35 * (mean_e or 1e-9):
            sections.append({"start": round(start * frame_t, 2), "end": round(i * frame_t, 2),
                             "energy": round(sum(energy[start:i]) / max(1, i - start), 4)})
            start = i
    sections.append({"start": round(start * frame_t, 2), "end": round(duration, 2),
                     "energy": round(sum(energy[start:]) / max(1, len(energy) - start), 4)})
    drops = [round(i * frame_t, 2) for i in range(win, len(smooth))
             if smooth[i] > 1.8 * smooth[i - win] and energy[i] > mean_e]
    dedup_drops: list[float] = []
    for d in drops:
        if not dedup_drops or d - dedup_drops[-1] > 4:
            dedup_drops.append(d)
    quiet = 0.15 * mean_e
    pauses, run_start = [], None
    for i, e in enumerate(energy):
        if e < quiet and run_start is None:
            run_start = i
        elif e >= quiet and run_start is not None:
            if (i - run_start) * frame_t >= 0.5:
                pauses.append({"start": round(run_start * frame_t, 2),
                               "end": round(i * frame_t, 2)})
            run_start = None
    return {"duration_s": round(duration, 3), "tempo_bpm": tempo, "beats": beats,
            "sections": sections, "drops": dedup_drops, "pauses": pauses,
            "frame_seconds": round(frame_t, 5)}


def edit_decision_list(analysis: dict[str, Any], scenes: list[str],
                       beats_per_cut: int = 4) -> list[dict[str, Any]]:
    """Cuts land on beats; the scene changes at each section boundary; drops get a hard cut."""
    if not scenes:
        raise ValueError("need at least one scene")
    beats = analysis["beats"] or [i * 0.5 for i in range(int(analysis["duration_s"] * 2))]
    cut_points = beats[::max(1, beats_per_cut)]
    boundaries = [s["start"] for s in analysis["sections"]] + analysis["drops"]
    cut_points = sorted(set(round(c, 3) for c in cut_points + boundaries if c >= 0))
    if not cut_points or cut_points[0] > 0:
        cut_points.insert(0, 0.0)
    cut_points.append(analysis["duration_s"])
    sections = analysis["sections"] or [{"start": 0, "end": analysis["duration_s"]}]
    edl = []
    for a, b in zip(cut_points, cut_points[1:], strict=False):
        if b - a < 0.05:
            continue
        sec = next((i for i, s in enumerate(sections) if s["start"] <= a < s["end"]),
                   len(sections) - 1)
        edl.append({"start": round(a, 3), "end": round(b, 3), "section": sec,
                    "scene": scenes[sec % len(scenes)],
                    "hard_cut": any(abs(a - d) < 0.05 for d in analysis["drops"])})
    return edl
