"""Minimal local batch transcript web app. Optional engines are loaded on demand."""
from __future__ import annotations

import html
import json
import os
import tempfile
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HOST, PORT = "127.0.0.1", int(os.environ.get("PORT", "8766"))
MAX_UPLOAD = 500 * 1024 * 1024
_whisper = None
_whisper_lock = threading.Lock()


def transcribe_url(url: str) -> dict:
    try:
        import yt_dlp
    except ImportError as exc:
        raise RuntimeError("Install dependencies from requirements.txt first") from exc
    with tempfile.TemporaryDirectory(prefix="linktranscript-") as td:
        base = str(Path(td) / "media")
        opts = {
            "quiet": True, "no_warnings": True, "noprogress": True,
            "socket_timeout": 20, "retries": 1, "fragment_retries": 1,
            "outtmpl": base + ".%(ext)s", "writesubtitles": True,
            "writeautomaticsub": True, "subtitleslangs": ["en", "en-US", "en.*"],
            "skip_download": True,
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            title = info.get("title") or url
            subtitles = info.get("subtitles") or {}
            automatic = info.get("automatic_captions") or {}
            # Manual English subtitles first, then English auto-captions; manual tracks in
            # other languages must not hide automatic English ones.
            candidates = [
                track for tracks in (subtitles, automatic)
                for lang, choices in tracks.items()
                if lang == "en" or lang.startswith("en-")
                for track in choices
            ]
            if candidates:
                sub = next(
                    (s for s in candidates if s.get("ext") in {"vtt", "srt"}),
                    candidates[0],
                )
                raw = ydl.urlopen(sub["url"]).read().decode("utf-8", "replace")
                text = _subtitle_text(raw)
                if text.strip():
                    return {"source": url, "title": title, "method": "captions", "text": text}
        # Download only audio after metadata/caption lookup found no usable captions.
        opts.update({
            "skip_download": False,
            "format": "bestaudio/best",
            "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "wav"}],
        })
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get("title") or url
        audio = next(
            (p for p in Path(td).glob("media.*")
             if p.suffix.lower() in {".wav", ".m4a", ".mp3", ".opus"}),
            None,
        )
        if not audio:
            raise RuntimeError(
                "Audio download did not produce a supported file; check that FFmpeg is installed"
            )
        return {
            "source": url, "title": title, "method": "Faster Whisper",
            "text": transcribe_file(audio),
        }


def transcribe_file(path: Path) -> str:
    global _whisper
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError("Install faster-whisper from requirements.txt") from exc
    # PyAV 19 removed this keyword while Faster Whisper still supplies it.
    # Drop only that unsupported option so newer PyAV releases keep working.
    import av
    av_open = av.open
    if not getattr(av_open, "_linktranscript_compatible", False):
        def compatible_open(*args, **kwargs):
            kwargs.pop("metadata_errors", None)
            return av_open(*args, **kwargs)
        compatible_open._linktranscript_compatible = True
        av.open = compatible_open
    with _whisper_lock:
        if _whisper is None:
            _whisper = WhisperModel(
                os.environ.get("WHISPER_MODEL", "base"),
                device="cpu",
                compute_type="int8",
            )
    segments, _ = _whisper.transcribe(str(path), vad_filter=True)
    return "\n".join(f"[{s.start:0.1f}s] {s.text.strip()}" for s in segments)


def _subtitle_text(raw: str) -> str:
    # Handle VTT/SRT cues and discard markup, cue numbers and timestamps.
    import re
    lines = []
    for line in raw.replace("\r", "").splitlines():
        line = line.strip()
        ignored_prefixes = ("WEBVTT", "NOTE", "Kind:", "Language:")
        if (
            not line
            or line.startswith(ignored_prefixes)
            or "-->" in line
            or line.isdigit()
        ):
            continue
        line = re.sub(r"<[^>]*>", "", line)
        if line and (not lines or line != lines[-1]):
            lines.append(line)
    return "\n".join(lines)


def transcribe_upload(name: str, data: bytes) -> dict:
    suffix = Path(name).suffix or ".bin"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        f.write(data)
        path = Path(f.name)
    try:
        if suffix.lower() in {".txt", ".md", ".vtt", ".srt"}:
            text = path.read_text("utf-8", errors="replace")
            if suffix.lower() in {".vtt", ".srt"}:
                text = _subtitle_text(text)
            method = "uploaded transcript/captions"
        else:
            text, method = transcribe_file(path), "Faster Whisper"
        return {"source": name, "title": name, "method": method, "text": text}
    finally:
        path.unlink(missing_ok=True)


PAGE = '''<!doctype html>
<meta charset="utf-8">
<title>LinkTranscript Studio</title>
<style>
body { font: 16px system-ui; max-width: 900px; margin: 3rem auto; padding: 0 1rem; color: #17212b }
textarea { width: 100%; height: 180px }
button { padding: .7rem 1.1rem; background: #146c5a; color: white; border: 0;
  border-radius: 5px; font-size: 1rem }
input { margin: 1rem 0 }
.note { color: #555 }
</style>
<h1>LinkTranscript Studio</h1>
<p>Paste URLs, one per line, and optionally add audio, video, caption, or transcript files.</p>
<form method="post" enctype="multipart/form-data">
<textarea name="urls" placeholder="https://..."></textarea><br>
<label>Files <input type="file" name="files" multiple></label><br>
<button>Transcribe everything</button></form>
<p class="note">Runs locally. Captions are preferred; audio uses local Faster Whisper.
Source access restrictions still apply.</p>'''


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.respond(200, PAGE.encode(), "text/html; charset=utf-8")

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        if length > MAX_UPLOAD + 10_000_000:
            self.respond(413, b"Request too large")
            return
        body = self.rfile.read(length)
        # stdlib email parser handles multipart without framework dependencies.
        from email.parser import BytesParser
        from email.policy import default
        headers = (
            f"Content-Type: {self.headers.get('Content-Type')}\r\n"
            "MIME-Version: 1.0\r\n\r\n"
        )
        msg = BytesParser(policy=default).parsebytes(headers.encode() + body)
        fields, uploads = {}, []
        for part in msg.iter_parts():
            name = part.get_param("name", header="content-disposition")
            payload = part.get_payload(decode=True) or b""
            filename = part.get_filename()
            if filename:
                if len(payload) > MAX_UPLOAD:
                    self.respond(413, b"A file exceeds the 500 MB limit")
                    return
                uploads.append((Path(filename).name, payload))
            elif name:
                fields[name] = payload.decode("utf-8", "replace")
        records = []
        urls = [u.strip() for u in fields.get("urls", "").splitlines() if u.strip()]
        for source, job in [(u, lambda u=u: transcribe_url(u)) for u in urls]:
            records.append(self.run_one(source, job))
        for filename, data in uploads:
            def job(name=filename, payload=data):
                return transcribe_upload(name, payload)

            records.append(self.run_one(filename, job))
        self.show_results(records)

    def run_one(self, source, job):
        try:
            return job()
        except Exception as exc:
            return {
                "source": source, "title": source, "method": "failed",
                "text": "", "error": str(exc),
            }

    def show_results(self, records):
        md = "\n\n".join(
            f"## {r['title']}\n\nSource: {r['source']}  \nMethod: {r['method']}\n"
            + (f"\nError: {r['error']}" if r.get("error") else f"\n\n{r['text']}")
            for r in records
        )
        data = json.dumps(records, ensure_ascii=False, indent=2)
        succeeded = sum(not record.get("error") for record in records)
        failed = sum(bool(record.get("error")) for record in records)
        content = (
            "<h1>Batch results</h1><p>"
            f"{succeeded} succeeded; {failed} failed."
            "</p><p><a href='/download.md'>Markdown</a> · "
            "<a href='/download.txt'>Text</a> · "
            "<a href='/download.json'>JSON</a></p><ol>"
        )
        content += "".join(
            f"<li>{html.escape(record['title'])}: "
            f"{html.escape(record['method'])}"
            + (f" — {html.escape(record['error'])}" if record.get("error") else "")
            + "</li>"
            for record in records
        ) + "</ol><p><a href='/'>New batch</a></p>"
        self.server.results = {"md": md.encode(), "txt": md.encode(), "json": data.encode()}
        page = PAGE.replace("<h1>LinkTranscript Studio</h1>", content)
        self.respond(200, page.encode(), "text/html; charset=utf-8")

    def respond(self, code, payload, ctype="text/plain; charset=utf-8"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *_):
        pass


def main():
    class AppHandler(Handler):
        def do_GET(self):
            path = urllib.parse.urlsplit(self.path).path
            if path.startswith("/download."):
                kind = path.rsplit(".", 1)[-1]
                content = getattr(self.server, "results", {}).get(kind)
                if content is None:
                    self.respond(404, b"No batch results yet")
                else:
                    self.send_response(200)
                    self.send_header("Content-Type", "application/octet-stream")
                    self.send_header(
                        "Content-Disposition",
                        f"attachment; filename=transcripts.{kind}",
                    )
                    self.end_headers()
                    self.wfile.write(content)
            else:
                super().do_GET()
    server = ThreadingHTTPServer((HOST, PORT), AppHandler)
    server.results = {}
    print(f"LinkTranscript Studio listening at http://{HOST}:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
