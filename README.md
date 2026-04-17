# omnivoice-api

HTTP API wrapping [k2-fsa/OmniVoice](https://github.com/k2-fsa/OmniVoice) zero-shot TTS (voice clone + voice design).

Audio I/O is routed through S3-compatible object storage:

- **Local dev** — MinIO via `docker-compose.yml`.
- **Prod** — Cloudflare R2 (S3 API).

The server never streams audio in the HTTP body: clients upload reference clips directly to storage via a presigned `PUT`, then hit the TTS endpoint which returns a presigned `GET` for the generated WAV.

## Environments

| pixi env  | Platform   | Python | Torch                 | Device    |
|-----------|------------|--------|-----------------------|-----------|
| `default` | osx-arm64  | 3.13   | `torch==2.11.0`       | MPS / CPU |
| `prod`    | linux-64   | 3.13   | `torch==2.11.0+cu128` | CUDA 12.8 |

Both resolve `omnivoice==0.1.4` and the FastAPI stack.

## Local dev (macOS)

```bash
pixi install                  # resolves default (dev) env
pixi run minio-up             # start MinIO on :9000 (console :9001), create bucket
cp .env.example .env          # defaults already point at local MinIO
pixi run serve                # uvicorn on :8000, --reload
```

MinIO console: http://localhost:9001 (minioadmin / minioadmin).

First request triggers model download from HuggingFace (~cached in `~/.cache/huggingface`).

Pre-cache:

```bash
pixi run download-model
```

Stop MinIO:

```bash
pixi run minio-down
```

## Prod (WSL2 + CUDA 12.8 + R2)

```bash
pixi install -e prod
pixi run -e prod info         # should report cuda available=True
# set OMNIVOICE_S3_* env vars to point at your R2 account (see .env.example)
pixi run -e prod serve-prod
```

Requires host with NVIDIA driver supporting CUDA 12.8 (driver >= 550). WSL2: install `nvidia-cuda-toolkit` inside the distro is **not** required — the driver bridge from Windows is enough.

## Flow

```
client --PUT presigned--> S3            (1) upload ref audio
client --POST /v1/tts/clone--> api      (2) generate
                 api --GET--> S3        (2a) fetch ref internally
                 api --PUT--> S3        (2b) store wav result
       <--download_url-- api            (3) presigned GET for result
client --GET presigned--> S3            (4) download wav
```

## Endpoints

### `GET /health`

```json
{ "status": "ok", "device": "cuda:0", "dtype": "torch.float16", "model_loaded": true }
```

### `POST /v1/uploads/presign`

Request presigned `PUT` URL for a reference audio clip.

Request:
```json
{ "filename": "ref.wav", "content_type": "audio/wav" }
```

Response:
```json
{ "key": "ref/ab12...c3.wav", "upload_url": "https://...", "expires_in": 3600, "content_type": "audio/wav" }
```

Client then uploads directly:
```bash
curl -X PUT --upload-file ref.wav -H "content-type: audio/wav" "$upload_url"
```

### `POST /v1/tts/clone` — voice clone (application/json)

| field           | type   | required | note                                          |
|-----------------|--------|----------|-----------------------------------------------|
| `text`          | string | yes      | text to synthesize                            |
| `ref_audio_key` | string | yes      | key returned by `/v1/uploads/presign`         |
| `ref_text`      | string | no       | transcript of ref; auto via Whisper if empty  |
| `num_step`      | int    | no       | diffusion steps (default 32, 16 = fast)       |
| `speed`         | float  | no       | default 1.0                                   |
| `duration`      | float  | no       | fixed seconds; overrides speed                |

Response:
```json
{ "output_key": "out/4f9...e2.wav", "download_url": "https://...", "expires_in": 3600 }
```

End-to-end example:
```bash
# 1) presign
read UPLOAD_URL KEY < <(curl -s -X POST http://localhost:8000/v1/uploads/presign \
  -H 'content-type: application/json' \
  -d '{"filename":"ref.wav"}' \
  | jq -r '.upload_url + " " + .key')

# 2) upload ref
curl -X PUT --upload-file ref.wav -H 'content-type: audio/wav' "$UPLOAD_URL"

# 3) generate
DL=$(curl -s -X POST http://localhost:8000/v1/tts/clone \
  -H 'content-type: application/json' \
  -d "{\"text\":\"Hello from OmniVoice.\",\"ref_audio_key\":\"$KEY\",\"ref_text\":\"This is the reference transcript.\"}" \
  | jq -r '.download_url')

# 4) download result
curl -o out.wav "$DL"
```

### `POST /v1/tts/design` — voice design (application/json)

```bash
curl -X POST http://localhost:8000/v1/tts/design \
  -H 'content-type: application/json' \
  -d '{"text":"Hello world.","instruct":"female, british accent, calm","num_step":32}'
```

Response is the same `TTSResponse` shape — caller downloads `download_url` to get the WAV.

## Docker image (production)

CUDA 12.8 runtime image is built via `Dockerfile`. Requires a host with NVIDIA driver advertising CUDA >= 12.8 and `nvidia-container-toolkit` installed.

Build + run locally:
```bash
docker build -t omnivoice-api:local .
docker run --rm --gpus all -p 8000:8000 --env-file .env omnivoice-api:local
```

GitHub Actions workflow `.github/workflows/build-image.yml` builds and pushes to GHCR as `ghcr.io/<org>/<repo>:latest`. Trigger manually via the Actions tab (**Run workflow**) or `gh workflow run "Build production image"`.

Buildx layer cache is kept in GitHub Actions cache (`type=gha, mode=max`) so rebuilds only re-run the `pixi install` layer when `pixi.lock` or source changes.

Pull + run from GHCR:
```bash
docker pull ghcr.io/<org>/<repo>:latest
docker run --rm --gpus all -p 8000:8000 --env-file .env ghcr.io/<org>/<repo>:latest
```

## Tests

End-to-end test (requires the server + MinIO already running):

```bash
pixi run minio-up
pixi run serve              # terminal 1
pixi run test-e2e           # terminal 2
```

`tests/test_e2e_clone.py` drives the full pipeline: presign → PUT ref mp3 → clone → GET → WAV structural + soundfile decode check. Reference clip lives in-repo at `tests/fixtures/domixi.mp3`. Override the server URL with `OMNIVOICE_API_URL=http://host:port`.

Generated WAV is written to pytest's `tmp_path` and printed on success — useful for manual listening.

## Config (env vars, `.env` supported)

Prefix: `OMNIVOICE_`. See `.env.example` for full list.

Core:
- `DEVICE`, `DTYPE`, `MODEL_ID`, `MAX_TEXT_CHARS`, `DEFAULT_NUM_STEP`, `WARMUP_ON_STARTUP`, `HF_ENDPOINT`

S3 / R2:
- `S3_ENDPOINT_URL` — internal endpoint the API reaches (e.g. `http://localhost:9000` local, `https://<acct>.r2.cloudflarestorage.com` prod)
- `S3_PUBLIC_ENDPOINT_URL` — optional; endpoint hostname baked into presigned URLs (use when clients see a different host than the server)
- `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`, `S3_REGION`, `S3_BUCKET`
- `S3_FORCE_PATH_STYLE` — `true` for MinIO, `false` for R2
- `S3_PRESIGN_EXPIRES` — seconds (default 3600)
- `S3_REF_PREFIX`, `S3_OUT_PREFIX` — key prefixes (default `ref/`, `out/`)
- `S3_ENSURE_BUCKET` — create bucket on startup if missing (default true)

## Layout

```
src/omnivoice_api/
  main.py          FastAPI app + endpoints
  service.py       OmniVoiceService (lazy-load, lock, WAV encode)
  storage.py       S3/R2 client (presign, upload, download)
  device.py        auto-pick cuda > mps > cpu, fp16 on cuda
  config.py        pydantic-settings
  schemas.py       pydantic request/response models
  scripts/download_model.py
docker-compose.yml MinIO for local dev
```

## Notes / caveats

- **MPS on macOS**: OmniVoice core supports `device_map="mps"` but community reports instability under sustained server load. For dev: set `OMNIVOICE_DEVICE=cpu` if crashes.
- **Concurrency**: a global `threading.Lock` serializes GPU calls. Scale by adding workers behind a queue, not `--workers N` (each worker loads the full model).
- **transformers >=5.3.0**: high pin per upstream `pyproject.toml`; may require pre-release channel when resolving.
- **pydub on Python 3.13**: upstream `pydub` 0.25.1 imports the removed stdlib `audioop`. We use `pydub-ng` (drop-in, same `from pydub import AudioSegment` API, pulls in `audioop-lts`).
- **GPU / driver**: any NVIDIA driver that advertises CUDA >= 12.8 works with the `cu128` wheels (backward compatible on newer drivers, e.g. driver 595 / CUDA 13.2 tested).
- **Presigned URLs from inside Docker**: if you run the API in a container too, set `S3_ENDPOINT_URL=http://minio:9000` (internal) and `S3_PUBLIC_ENDPOINT_URL=http://localhost:9000` (what browser/curl on host uses).
- **R2 presigned URLs**: R2 requires `region=auto` and does not support path-style — set `S3_FORCE_PATH_STYLE=false`.
