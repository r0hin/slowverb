<div align="center">

# slowverb

**YouTube to slowed + reverb MP3. One command.**

[![checks](https://github.com/r0hin/slowverb/actions/workflows/ci.yml/badge.svg)](https://github.com/r0hin/slowverb/actions/workflows/ci.yml)
[![python](https://img.shields.io/badge/python-3.11%2B-3776AB?style=flat-square)](https://www.python.org/)
[![license](https://img.shields.io/badge/license-MIT-black?style=flat-square)](LICENSE)

```sh
slowverb "https://youtu.be/VIDEO_ID"
```

0.85× speed · stereo convolution reverb · 320 kbps MP3

</div>

## Install

On macOS with [Homebrew](https://brew.sh/):

```sh
brew install uv ffmpeg deno
uv tool install git+https://github.com/r0hin/slowverb
```

On Linux or Windows, install [uv](https://docs.astral.sh/uv/getting-started/installation/),
[FFmpeg](https://ffmpeg.org/download.html) (with `libmp3lame`), and
[Deno](https://docs.deno.com/runtime/getting_started/installation/), then run the same
`uv tool install` command. Python 3.11+ is required; uv can install it for you.

Prefer pipx? `pipx install git+https://github.com/r0hin/slowverb` works too.

## Use

```sh
slowverb "https://youtu.be/VIDEO_ID"
slowverb "https://youtu.be/VIDEO_ID" --open
slowverb "https://youtu.be/VIDEO_ID" --speed 0.85 --reverb 0.4 -o night.mp3
```

| Option | Default | |
| :--- | :--- | :--- |
| `--speed` | `0.85` | Speed and pitch, `0.5`–`1.0` |
| `--reverb` | `0.3` | Reverb mix, `0`–`1` |
| `-o, --output` | Video title | Output `.mp3` path |
| `--open` | Off | Open the finished MP3 in your default audio app |

Saves to your current folder. One video per run, even with a playlist link.
Existing files are never overwritten. Progress goes to stderr; the saved path goes to stdout.

Update: `uv tool upgrade slowverb`. If the command isn't found, run `uv tool update-shell`
and reopen your terminal. Private, restricted, and live videos aren't supported.

<details>
<summary>Development</summary>

```sh
git clone https://github.com/r0hin/slowverb
cd slowverb
uv sync
uv run slowverb --help
uv run python -m unittest discover -s tests -v
uv run ruff check .
uv run ruff format --check .
uv build
```

Audio tests use generated tones, so CI doesn't depend on YouTube access.

</details>

---

Built with [yt-dlp](https://github.com/yt-dlp/yt-dlp) and [FFmpeg](https://ffmpeg.org/).
Use audio you own or have permission to download. [MIT](LICENSE).
