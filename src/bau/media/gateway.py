"""Media gateway (spec §57): one interface, swappable adapters (spec §112).

Every output - whatever adapter made it - gets a provenance record and a
disclosure label before anything else can touch it (spec §14). Machine-readable
marking is only claimed when it really happened: a C2PA manifest signed by
``c2patool`` when installed, otherwise the sidecar + embedded metadata are
recorded honestly as *not* a standards-based marking.

Adapters:
* FFmpegAdapter      - local editing: render, clip, caption, concat, upscale, audio.
* HTTPMediaAdapter   - a generation service (e.g. Open-Generative-AI) reached over
                       HTTP. Refuses to run unless its registry record is APPROVED or
                       ACTIVE, i.e. it passed Sentinel (spec §37, §56).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import shutil
import subprocess
import urllib.request
from dataclasses import asdict
from pathlib import Path
from typing import Any

from ..disclosure import Provenance

VERBS = ["generate_image", "generate_video", "generate_audio", "generate_music",
         "generate_voice", "lip_sync", "create_scene", "create_storyboard", "create_character",
         "create_clip", "upscale", "caption", "render"]
MEDIA_TYPE = {"generate_image": "image", "generate_video": "video", "generate_audio": "audio",
              "generate_music": "audio", "generate_voice": "audio", "lip_sync": "video",
              "create_scene": "image", "create_storyboard": "image",
              "create_character": "image", "create_clip": "video", "upscale": "image",
              "caption": "video", "render": "video"}


class MediaError(RuntimeError):
    pass


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class FFmpegAdapter:
    name = "ffmpeg"
    generative = False

    def __init__(self, binary: str | None = None, runner: Any = None):
        self.binary = binary or shutil.which("ffmpeg") or "ffmpeg"
        self.run_cmd = runner or (lambda cmd: subprocess.run(cmd, check=True,
                                                             capture_output=True))

    def command(self, verb: str, out: Path, **kw: Any) -> list[str]:
        b = [self.binary, "-y", "-hide_banner", "-loglevel", "error"]
        meta = ["-metadata", f"comment={kw.get('label', '')}"] if kw.get("label") else []
        if verb == "create_clip":
            return b + ["-ss", str(kw["start"]), "-to", str(kw["end"]), "-i", str(kw["src"]),
                        "-c", "copy", *meta, str(out)]
        if verb == "caption":
            return b + ["-i", str(kw["src"]), "-vf", f"subtitles={kw['subtitles']}", *meta,
                        str(out)]
        if verb == "upscale":
            return b + ["-i", str(kw["src"]), "-vf",
                        f"scale=iw*{kw.get('factor', 2)}:ih*{kw.get('factor', 2)}:flags=lanczos",
                        *meta, str(out)]
        if verb == "render":
            # concat demuxer list of segments + optional audio master track
            cmd = b + ["-f", "concat", "-safe", "0", "-i", str(kw["concat_list"])]
            if kw.get("audio"):
                cmd += ["-i", str(kw["audio"]), "-map", "0:v", "-map", "1:a", "-shortest"]
            return cmd + ["-c:v", "libx264", "-pix_fmt", "yuv420p", *meta, str(out)]
        raise MediaError(f"ffmpeg adapter does not implement {verb}")

    def run(self, verb: str, out: Path, **kw: Any) -> Path:
        self.run_cmd(self.command(verb, out, **kw))
        return out


class HTTPMediaAdapter:
    generative = True

    def __init__(self, name: str, base_url: str, registry_status: str,
                 endpoints: dict[str, str], opener: Any = None, timeout: int = 900):
        if registry_status not in ("APPROVED", "ACTIVE"):
            raise MediaError(f"{name} is {registry_status}: it must pass Sentinel and be "
                             "APPROVED before it may generate anything")
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.endpoints = endpoints
        self._open = opener or urllib.request.urlopen
        self.timeout = timeout

    def run(self, verb: str, out: Path, **kw: Any) -> Path:
        ep = self.endpoints.get(verb)
        if not ep:
            raise MediaError(f"{self.name} has no endpoint for {verb}")
        body = json.dumps({k: v for k, v in kw.items() if k != "label"}).encode()
        req = urllib.request.Request(self.base_url + ep, data=body,
                                     headers={"Content-Type": "application/json"})
        with self._open(req, timeout=self.timeout) as r:
            out.write_bytes(r.read())
        return out


class MediaGateway:
    def __init__(self, adapters: dict[str, Any], c2pa_tool: str | None = None,
                 c2pa_manifest: Path | None = None):
        self.adapters = adapters
        self.c2pa_tool = c2pa_tool if c2pa_tool is not None else shutil.which("c2patool")
        self.c2pa_manifest = c2pa_manifest

    def _mark(self, out: Path) -> bool:
        """Embed a C2PA manifest when the tool and a signing manifest are configured."""
        if not (self.c2pa_tool and self.c2pa_manifest and self.c2pa_manifest.exists()):
            return False
        signed = out.with_suffix(".c2pa" + out.suffix)
        r = subprocess.run([self.c2pa_tool, str(out), "-m", str(self.c2pa_manifest), "-o",
                            str(signed), "-f"], capture_output=True, check=False)
        if r.returncode != 0 or not signed.exists():
            return False
        signed.replace(out)
        return True

    def produce(self, verb: str, adapter: str, out: Path, job_id: str, model_id: str,
                source_material: list[str] | None = None, likeness_used: bool = False,
                voice_clone: bool = False, consent_status: str = "not_required",
                human_contribution: list[str] | None = None,
                input_had_provenance_marking: bool = False, **kw: Any) -> Provenance:
        if verb not in VERBS:
            raise MediaError(f"unknown media verb {verb}")
        if (likeness_used or voice_clone) and consent_status != "granted":
            raise MediaError("likeness/voice of a real person needs granted consent (spec §16)")
        a = self.adapters[adapter]
        generated = bool(getattr(a, "generative", False))
        prov = Provenance(
            artifact_id=out.stem, media_type=MEDIA_TYPE[verb], ai_generated=generated,
            ai_assisted=not generated, human_authored=False,
            human_modified=bool(human_contribution), model_id=model_id if generated else None,
            provider=adapter, generation_timestamp=dt.datetime.now(dt.UTC).isoformat(),
            generation_job=job_id, source_material=source_material or [],
            synthetic_media=generated and MEDIA_TYPE[verb] != "text",
            likeness_used=likeness_used, voice_clone=voice_clone,
            consent_status=consent_status,
            input_had_provenance_marking=input_had_provenance_marking,
            human_contribution=human_contribution or [])
        label = prov.suggested_label()
        out.parent.mkdir(parents=True, exist_ok=True)
        a.run(verb, out, label=label or "", **kw)
        prov.machine_readable_marking = self._mark(out) if out.exists() else False
        prov.visible_disclosure_text = label
        sidecar = out.with_suffix(out.suffix + ".provenance.json")
        doc = asdict(prov)
        if out.exists():
            doc["artifact_sha256"] = sha256_file(out)
        doc["marking_note"] = ("C2PA manifest embedded" if prov.machine_readable_marking
                               else "sidecar + metadata only - NOT a standards-based marking")
        sidecar.write_text(json.dumps(doc, indent=2))
        return prov
