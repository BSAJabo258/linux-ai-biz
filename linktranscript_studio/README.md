# LinkTranscript Studio

A small, standalone local web app for collecting transcripts from a batch of media URLs or files into one document.

## Requirements

- Python 3.11+
- `pip install -r requirements.txt`
- FFmpeg for audio extraction when captions are unavailable

The app tries captions first using `yt-dlp`. If none are available, it uses Faster Whisper locally. Some sources require a URL accessible without login; the app does not accept cookies or bypass access controls. Only submit material you are allowed to access and process.

## Run

```bash
python -m venv .venv
. .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:8766. Paste one URL per line. Optional file uploads can be added in the form. Results are assembled in memory and can be downloaded as Markdown, plain text, or JSON. The first local Whisper run downloads its model.

## Notes

Processing is sequential. Captions are preferred; when local speech recognition is needed, the `base` Whisper model is used by default (`WHISPER_MODEL` can select another Faster Whisper model). Failed sources are included in the report with an error. This is an initial utility, not a guarantee that every platform permits automated access.

## Import transcripts into Jarvis

After adding Jarvis's `src` directory to the Python environment (for example,
by installing the repository in editable mode), import the collection into the
configured `BAU_HOME` with:

```bash
python linktranscript_studio/import_to_jarvis.py
```

The importer adds one searchable `video_transcript` memory record per source,
preserves its URL, and marks the automatic transcript `UNKNOWN` so it is not
mistaken for verified fact. Sources already in memory are skipped when you run
the importer again. It also updates the `Transcript Collection Research for
Jarvis` note in Jarvis's Second Brain from `jarvis_research.md`.

Set `BAU_HOME` to the intended Jarvis data directory before importing if it
differs from the active environment. Jarvis can then retrieve transcript
passages through its normal memory recall tools.
