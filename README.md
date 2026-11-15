# Character Reel render service

FastAPI + Kokoro-82M on CPU. A synchronous request returns two H.264/AAC 1080×1920 videos: word-synced captions with voice and ducked music, and a music-free sibling. Character voice, speed, style and highlight are request-specific. The social caption is returned as metadata, never burned. No publishing integration is configured.

## Local use

From `/workspace/aria-reels/render-service`:

```bash
# Existing Python 3.12 Kokoro environment stays unchanged.
uv pip install --python /workspace/aria-reels/auto-test/.venv/bin/python --target .deps fastapi uvicorn python-multipart
export PYTHONPATH="$PWD/.deps${PYTHONPATH:+:$PYTHONPATH}"
/workspace/aria-reels/auto-test/.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
```

Stop with Ctrl-C. No server was left running for this delivery. First speech use lazily downloads the Hugging Face model and requested voices into the normal Hugging Face cache; later calls reuse CPU pipelines and voice tensors. `GET /health` reports loaded voice expressions, without forcing model loading. `TTS_THREADS=4` is the default. For a new environment, install `requirements.txt` with CPU torch and ensure ffmpeg/ffprobe are available.

```bash
PYTHONPATH=.deps /workspace/aria-reels/auto-test/.venv/bin/python -m app.cli \
  --video /workspace/aria-reels/delivery/S04-1080x1920-24fps-silent.mp4 \
  --voiceover "Studio's empty so obviously I made it everyone's problem. Form check, or are we pretending we're looking at my back?" \
  --style champagne --voice bf_isabella --speed 0.90 --out-dir style-variants/champagne
```

Repeat with `--style soft_pink --out-dir style-variants/soft_pink`. `python -m app.qa` then exports named samples and all mid-word/boundary QA frames. Tests: `PYTHONPATH=.deps /workspace/aria-reels/auto-test/.venv/bin/python -m unittest discover -s tests -v`.

## API and n8n call

Service URL: `https://<CPU_RENDER_HOST>` (placeholder). This box cannot be reached from Jamie's n8n cloud. Choose a reachable CPU host before replacing the placeholder.

n8n HTTP Request node: POST `https://<CPU_RENDER_HOST>/render`, JSON body below, response JSON, allow a long timeout (e.g. 10 minutes for cold model loading). Retry HTTP 429 with a delay; one render runs at a time per process. Use one uvicorn worker. Send an HTTP-accessible video URL when n8n and renderer do not share storage.

```json
{
  "video_url": "https://<MEDIA_HOST>/silent.mp4",
  "voiceover": "Your spoken line here.",
  "caption": "Social post copy, kept as metadata",
  "music_mood": "upbeat funky confident",
  "music_url": null,
  "character": {
    "id": "aria",
    "name": "Aria Cole",
    "tts_voice_id": "bf_isabella*0.7+bf_alice*0.3",
    "tts_speed": 0.88,
    "caption_style": "champagne",
    "caption_highlight_color": null
  }
}
```

Voices accept a Kokoro name, `bf_isabella,bf_alice` (equal average), or positive weighted expressions. Weights are normalized; mixed-language blends are rejected. Language is the first letter of the first voice. Speed defaults to 1.0 (supported request range 0.5–1.18). Styles: `champagne` and `soft_pink`; optional `#RRGGBB` highlight override.

Response fields: `job_id`, `duration_s`, `voice` (id/language/actual speed), `character`, `caption`, `music` (id/title/artist/license/attribution), and `outputs["full.mp4"]` / `outputs["voice_captions.mp4"]`, each containing `path` and `url`. Download the returned URLs using n8n HTTP Request nodes as binary files. Output routes expose only those two completed MP4s, not temporary inputs or arbitrary paths. `GET /library` returns manifest rows.

Local paths must resolve under `/workspace` or `/data`; traversal and symlink escapes are refused. HTTP(S) inputs stream to a per-render temporary directory (1 GiB limit, removed afterward). Custom music has unknown rights; its response metadata explicitly says user-supplied. Library selection weights mood/tag matches and prefers instrumental tracks; tracks too short are excluded unless `loop_ok`. Funkorama requires the returned attribution in publishing descriptions. BPM/energy are approximate editorial tags.

Speech is peak-normalized to 0.95, with a 180ms tail. If it exceeds picture duration by at most 2.25 seconds, freeze the final frame. Longer speech is resynthesized progressively up to 1.18; if still too long, return 422 asking for shorter text. Final duration rounds upward to the source frame grid. Short audio is silence-padded. Audio mux trims/pads to the encoded picture duration and copies video without `-t` or `-shortest`.

Static Poppins ExtraBold is bundled and registered through `fontsdir`. Captions use 1080×1920 coordinates, bottom-center, margins 90/90/450, white fill and gold or pink highlights. Phrases contain at most five words; a final orphan borrows words. ASS event end times clamp to the next phrase start before centisecond quantization. Longer phrases may wrap within safe margins.

## Baked CPU image (review only)

The Dockerfile installs CPU torch, Kokoro, ffmpeg/ffprobe, Poppins (with its
bundled OFL), the English spaCy model, and Kokoro weights/config/all voice
assets. HF_HOME is `/opt/kokoro-cache` so a `/data` volume cannot hide it.
English British/American speech and blends are checked offline; additional
language frontends are outside this packaging change. Missing model assets
fail with offline mode enabled. Media URLs still require network access.

`.github/workflows/render-image.yml` builds on PRs without publishing. Manual
`workflow_dispatch` with `publish=true` publishes only after offline CPU speech
and service checks pass, using the repository GITHUB_TOKEN with packages:write.
No personal package token is needed. It publishes
`ghcr.io/jamiechwcampbell/aria-render-service:sha-<full-commit>` for linux/amd64;
it never deploys. Dependencies/model main are resolved at build time, so retain
the published digest for an exact rollout/rollback (rebuilds can differ).

Jamie must approve switching the endpoint image. Before any approved switch,
record the existing image/start command/environment for rollback, verify GHCR
package pull access (new packages can be private), record the published digest,
and select that digest with the image's default `python -u handler.py` command.
Remove the bootstrap start-command override and any HF_HOME override pointing
at an empty cache. Do not run start.sh with this image. Keep workers.max=0;
a billed benchmark requires separate approval. Pull/extract and CPU model load
still take time: cold-start improvement has not been measured.

Local/CI verification (CPU only, no endpoint calls):

```bash
docker build -t renderer-check:local .
docker run --rm --network none --entrypoint python renderer-check:local scripts/check_image.py
```

The workflow follows [GitHub's GHCR guidance](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry).

## RunPod CPU worker

This repo is the fetchable source for a scale-to-zero RunPod **CPU** serverless worker (`handler.py` + `start.sh`). Do not launch GPU workers. The official S04 silent source lives at `samples/S04-1080x1920-24fps-silent.mp4` so n8n can pass a raw GitHub URL as `video_url`. Funkorama is Kevin MacLeod, CC BY 4.0 (see `library/LICENSE.md`).
