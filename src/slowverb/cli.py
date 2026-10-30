import argparse
import json
import math
import os
import random
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import wave
from pathlib import Path
from urllib.parse import urlparse

from slowverb import __version__


def number_between(low, high):
    def parse(value):
        try:
            number = float(value)
        except ValueError:
            raise argparse.ArgumentTypeError("must be a number")
        if not low <= number <= high:
            raise argparse.ArgumentTypeError(f"must be between {low} and {high}")
        return number

    return parse


def impulse_response(path):
    rate = 44100
    rng = random.Random(7)
    frames = bytearray()
    previous = [0.0, 0.0]
    for i in range(rate * 3):
        time = i / rate
        for channel in range(2):
            previous[channel] = 0.65 * previous[channel] + 0.35 * rng.uniform(-1, 1)
            envelope = math.exp(-3.0 * time) * min(1.0, max(0.0, (time - 0.02) / 0.04))
            sample = previous[channel] * envelope * 0.08
            frames.extend(struct.pack("<h", round(sample * 32767)))
    with wave.open(str(path), "wb") as audio:
        audio.setparams((2, 2, rate, 0, "NONE", "not compressed"))
        audio.writeframes(frames)


def run(args):
    subprocess.run(args, check=True, stdout=sys.stderr)


def safe_title(title):
    title = re.sub(r'[\x00-\x1f/\\:*?"<>|]', "_", title).strip(" .")
    return title.encode("utf-8")[:160].decode("utf-8", errors="ignore").rstrip(" .") or "audio"


def render(source, output, speed, reverb, temp, ffmpeg, title="audio"):
    inputs = ["-i", str(source)]
    slow = (
        f"aresample=44100,asetrate={round(44100 * speed)},"
        "aresample=44100,aformat=channel_layouts=stereo"
    )
    if reverb:
        impulse = temp / "room.wav"
        impulse_response(impulse)
        inputs += ["-i", str(impulse)]
        options = subprocess.run(
            [ffmpeg, "-hide_banner", "-h", "filter=afir"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        normalization = "irnorm=2" if "irnorm" in options else "gtype=gn"
        filters = (
            f"[0:a]{slow},apad=pad_dur=3,asplit=2[dry][send];"
            f"[send][1:a]afir=dry=1:wet=1:{normalization}[room];"
            f"[dry][room]amix=inputs=2:weights='{1 - reverb} {reverb}':normalize=0,"
            "alimiter=limit=0.95:level=0:latency=1[out]"
        )
    else:
        filters = f"[0:a]{slow},alimiter=limit=0.95:level=0:latency=1[out]"
    run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostdin",
            "-n",
            *inputs,
            "-filter_complex",
            filters,
            "-map",
            "[out]",
            "-vn",
            "-c:a",
            "libmp3lame",
            "-b:a",
            "320k",
            "-ar",
            "44100",
            "-ac",
            "2",
            "-metadata",
            f"title={title} (slowed + reverb)",
            str(output),
        ]
    )


def download(url, temp, runtime):
    manifest = temp / "download.json"
    print("Downloading audio...", file=sys.stderr, flush=True)
    run(
        [
            sys.executable,
            "-m",
            "yt_dlp",
            "--ignore-config",
            "--no-playlist",
            "--no-progress",
            "--js-runtimes",
            runtime,
            "--match-filters",
            "!is_live",
            "--socket-timeout",
            "20",
            "--retries",
            "3",
            "--fragment-retries",
            "3",
            "-f",
            "bestaudio/best",
            "--write-info-json",
            "--no-simulate",
            "--print-to-file",
            "after_move:%(filepath)j",
            str(manifest),
            "-o",
            str(temp / "source.%(ext)s"),
            "--",
            url,
        ]
    )
    if not manifest.is_file():
        raise ValueError("no audio downloaded; live videos are not supported")
    source = Path(json.loads(manifest.read_text(encoding="utf-8").strip()))
    info = json.loads((temp / "source.info.json").read_text(encoding="utf-8"))
    return source, str(info.get("title") or info.get("id") or "audio")


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Turn a YouTube video into a slowed + reverb MP3.",
        epilog='Example: slowverb "https://www.youtube.com/watch?v=VIDEO_ID"',
    )
    parser.add_argument("--version", action="version", version=f"slowverb {__version__}")
    parser.add_argument("url", help="YouTube video URL (quote it)")
    parser.add_argument(
        "-o", "--output", type=Path, help="output MP3 path; defaults to the video title"
    )
    parser.add_argument(
        "--speed",
        type=number_between(0.5, 1.0),
        default=0.85,
        help="speed and pitch multiplier (default: 0.85)",
    )
    parser.add_argument(
        "--reverb",
        type=number_between(0.0, 1.0),
        default=0.3,
        help="reverb mix, 0 to 1 (default: 0.3)",
    )
    args = parser.parse_args(argv)

    try:
        url = urlparse(args.url)
        hostname = url.hostname
    except ValueError:
        parser.error("provide a valid YouTube video URL")
    if url.scheme not in ("http", "https") or hostname not in (
        "youtube.com",
        "www.youtube.com",
        "m.youtube.com",
        "music.youtube.com",
        "youtu.be",
        "www.youtu.be",
    ):
        parser.error("provide a full YouTube video URL, starting with https://")
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        parser.error(
            "FFmpeg is missing; install it and add it to PATH (macOS: brew install ffmpeg)"
        )
    runtime = next((tool for tool in ("deno", "node") if shutil.which(tool)), None)
    if not runtime:
        parser.error("Deno is missing; install it and add it to PATH (macOS: brew install deno)")
    if args.output and args.output.suffix.lower() != ".mp3":
        parser.error("--output must end in .mp3")
    output = args.output.expanduser().absolute() if args.output else None
    if output:
        if output.exists() or output.is_symlink():
            parser.error(f"output already exists: {output}")
        if not output.parent.is_dir():
            parser.error(f"output folder does not exist: {output.parent}")

    try:
        with tempfile.TemporaryDirectory(prefix="slowverb-") as directory:
            temp = Path(directory)
            source, title = download(args.url, temp, runtime)
            output = output or Path(f"{safe_title(title)} (slowed + reverb).mp3").absolute()
            if output.exists() or output.is_symlink():
                raise FileExistsError(f"output already exists: {output}")
            if not output.parent.is_dir():
                raise FileNotFoundError(f"output folder does not exist: {output.parent}")

            print(
                f"Processing at {args.speed:g}x speed with {args.reverb:g} reverb...",
                file=sys.stderr,
                flush=True,
            )
            with tempfile.TemporaryDirectory(prefix=".slowverb-", dir=output.parent) as staging:
                encoded = Path(staging) / "audio.mp3"
                render(source, encoded, args.speed, args.reverb, temp, ffmpeg, title)
                os.link(encoded, output)
            print(str(output), flush=True)
        return 0
    except subprocess.CalledProcessError as error:
        tool = "yt-dlp" if "yt_dlp" in error.cmd else "FFmpeg"
        print(f"slowverb: {tool} failed; see the error above.", file=sys.stderr)
        return 1
    except (OSError, ValueError) as error:
        print(f"slowverb: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nslowverb: cancelled.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
