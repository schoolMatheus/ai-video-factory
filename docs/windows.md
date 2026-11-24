# Running on native Windows

Use PowerShell in the repository directory. WSL is not required for the CLI
or the `video-pipeline` render path. There is no web application to start.

## First installation

Install Python 3.12, Node.js/npm, FFmpeg/ffprobe, and Chrome or Edge. Ensure
Python, Node and FFmpeg are on PATH. Then run:

```powershell
python -m pip install --user uv
python -m uv sync
npm.cmd --prefix remotion ci --no-audit --no-fund
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

The Python environment belongs to this checkout. The launcher uses it directly,
so activating a virtual environment or changing PowerShell execution policy is
unnecessary. It also works when called from a different working directory.

## Start and verify

```powershell
.\aivideofactory.cmd
.\aivideofactory.cmd doctor
.\aivideofactory.cmd test-pipeline --json
```

The first command shows the CLI. The last produces the checked-in three-second
synthetic fixture, adds a silent audio track, and performs technical QC. Its
JSON response contains the output MP4 and QC report paths. This is an installation
test, not a narrated documentary. Completed stages are reused on subsequent runs.

ROCm checks can report `not_ready` on Windows and make `doctor` report `degraded`;
they are not required for the synthetic renderer. Check FFmpeg, ffprobe, Node
and npm separately in the report.

Chrome and Edge are discovered under Program Files and LocalAppData. To select
another installation explicitly, set its executable in the current shell:

```powershell
$env:REMOTION_CHROME_EXECUTABLE = 'C:\Program Files\Google\Chrome\Application\chrome.exe'
```

## Producing narrated videos

Configure Pexels/Pixabay credentials in `.env`, an OpenAI-compatible chat
completions endpoint, and a usable TTS engine/model. These services and models
are not installed by `uv sync`. The current default narrator is English.

With those requirements ready, a short draft can be launched with:

```powershell
.\aivideofactory.cmd video-pipeline "The Fermi Paradox" --duration 90 --draft --llm-url http://localhost:1234/v1/chat/completions --output data/projects/first-draft
```

For the long-form path, use `--longform --duration-minutes 25` instead of
`--duration 90`. Review the short draft before attempting a full documentary.

The advanced `daily` research workflow still uses POSIX `SIGALRM` to enforce
hard deadlines and refuses to run that stage on Windows. Startup/render
compatibility does not imply support for that separate workflow or for optional
GPU model backends. Local LTX model installation and GPU compatibility require
their own validation.

## Developer validation

```powershell
python -m uv run pytest tests/test_windows_support.py tests/test_cli.py tests/test_doctor.py tests/test_scheduler.py tests/test_pipeline.py tests/test_pipeline_reliability.py tests/test_preflight.py tests/test_hero_video.py tests/test_thumbnail_karaoke.py tests/test_run_store.py -q
npm.cmd --prefix remotion run build
npm.cmd --prefix remotion test -- --run tests/render.test.ts
```

At the time of Windows validation, the existing Remotion schema suite has three
unrelated failures around rejection of unknown fields. `src/schema.ts` is
unchanged by the Windows work; the full frontend test suite is not green.
