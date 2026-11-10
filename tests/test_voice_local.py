"""Jarvis's own voice on this computer: Voice uses the bau-voice service (Kokoro speaks,
faster-whisper listens, 127.0.0.1:8767) when the owner chose `speak: local` / `listen: local`.
Restored 2026-11-10: the code was on an unmerged branch (967f9d7), so main turned the mic off
for an owner whose config already said `listen: local`. No real models, no network."""
import json
import os
import threading
import urllib.error
import urllib.request

from bau.assistant import Voice, save_config


class FakeResp:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return self.body


def test_local_voice_speaks_and_listens_on_this_computer_only(tmp_path, monkeypatch):
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    assert not Voice(tmp_path).available and not Voice(tmp_path).can_listen   # nothing chosen
    save_config(tmp_path, speak="local", listen="local", local_voice="bm_lewis")
    sent = []

    def opener(req, timeout=0):
        sent.append(req)
        return FakeResp(b'{"text": "status please"}' if req.full_url.endswith("/listen")
                        else b"RIFF-wav")
    v = Voice(tmp_path, opener=opener)
    assert v.available and v.can_listen
    assert v.speak("Good morning") == b"RIFF-wav" and v.speak("Good morning") == b"RIFF-wav"
    assert len(sent) == 1                                          # second from the cache
    assert sent[0].full_url == "http://127.0.0.1:8767/speak"
    assert json.loads(sent[0].data) == {"text": "Good morning", "voice": "bm_lewis"}
    assert v.listen(b"webm-bytes", "audio/webm;codecs=opus") == "status please"
    assert sent[1].full_url == "http://127.0.0.1:8767/listen" and sent[1].data == b"webm-bytes"
    assert all("Xi-api-key" not in r.headers for r in sent)        # no key leaves the machine


def test_local_voice_stopped_falls_back_to_the_browser(tmp_path, monkeypatch):
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    save_config(tmp_path, speak="local", listen="local")

    def opener(req, timeout=0):
        raise urllib.error.URLError("connection refused")
    v = Voice(tmp_path, opener=opener)
    assert v.speak("hi") is None and v.listen(b"x") is None        # page uses its own voice


def test_jarvis_serves_local_audio_as_wav(tmp_path, monkeypatch):
    from test_assistant import make

    from bau.ui.jarvis_server import serve
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    save_config(tmp_path, speak="local")
    v = Voice(tmp_path, opener=lambda req, timeout=0: FakeResp(b"RIFF....WAVE"))
    srv, key = serve(make(tmp_path), v, 0, key="k123")
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{srv.server_address[1]}/api/tts",
                                     data=b'{"text": "hello"}', headers={
                                         "X-Jarvis-Key": "k123",
                                         "Content-Type": "application/json"})
        with urllib.request.urlopen(req) as r:
            assert r.headers["Content-Type"] == "audio/wav" and r.read() == b"RIFF....WAVE"
    finally:
        srv.shutdown()


def test_jarvis_opens_the_browser_without_lending_it_the_terminal(monkeypatch, capfd):
    # Firefox prints "[fluent.dom] An element named count wasn't found in the source" and
    # other console chatter to the terminal that started it (the owner's Jarvis terminal).
    import webbrowser

    from bau.cli_ext import _open_browser

    def chatty_open(url):
        os.write(2, b"[fluent.dom] noise\n")
        os.write(1, b"more noise\n")
        return True
    monkeypatch.setattr(webbrowser, "open", chatty_open)
    assert _open_browser("http://127.0.0.1:8766/?k=x") is True
    print("after", flush=True)
    out, err = capfd.readouterr()
    assert "noise" not in out + err and "after" in out
