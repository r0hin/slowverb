import array
import io
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import chdir, redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from slowverb import __version__, cli

URL = "https://youtu.be/jNQXAC9IVRw"


class CliTests(unittest.TestCase):
    def test_help_and_version_without_external_tools(self):
        for args in (["--help"], ["--version"]):
            with self.subTest(args=args), patch.dict(os.environ, {"PATH": ""}):
                result = subprocess.run(
                    [sys.executable, "-m", "slowverb", *args],
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("slowverb", result.stdout)
        self.assertIn(__version__, result.stdout)

    def test_invalid_input_never_downloads(self):
        cases = [
            [],
            ["https://example.com/video"],
            ["https://youtube.com.evil.example/video"],
            ["https://[invalid"],
            [URL, "--speed", "nan"],
            [URL, "--speed", "inf"],
            [URL, "--speed", "0.49"],
            [URL, "--reverb", "-0.1"],
            [URL, "--reverb", "1.1"],
            [URL, "-o", "audio.wav"],
        ]
        for args in cases:
            with self.subTest(args=args), redirect_stderr(io.StringIO()):
                with patch.object(cli.shutil, "which", return_value="available"):
                    with patch.object(cli, "download") as download:
                        with self.assertRaises(SystemExit) as error:
                            cli.main(args)
                        self.assertEqual(error.exception.code, 2)
                        download.assert_not_called()

    def test_missing_ffmpeg_has_actionable_error(self):
        error = io.StringIO()
        with redirect_stderr(error), patch.object(cli.shutil, "which", return_value=None):
            with self.assertRaises(SystemExit) as result:
                cli.main([URL])
        self.assertEqual(result.exception.code, 2)
        self.assertIn("FFmpeg is missing", error.getvalue())

    def test_titles_are_safe_and_fit_a_filename(self):
        for title in ('A / B: "night"', "音楽" * 100, " . ", "a\x00b"):
            with self.subTest(title=title):
                safe = cli.safe_title(title)
                self.assertTrue(safe)
                self.assertNotRegex(safe, r'[\x00-\x1f/\\:*?"<>|]')
                self.assertLess(len(f"{safe} (slowed + reverb).mp3".encode()), 255)


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg required")
class AudioTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.temp = Path(self.directory.name).resolve()
        self.source = self.temp / "source tone.wav"
        self.ffmpeg = shutil.which("ffmpeg")
        subprocess.run(
            [
                self.ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=440:duration=2:sample_rate=44100",
                "-ac",
                "2",
                str(self.source),
            ],
            check=True,
        )

    def decode(self, path):
        raw = subprocess.check_output(
            [self.ffmpeg, "-v", "error", "-i", str(path), "-f", "f32le", "-ac", "1", "-"]
        )
        samples = array.array("f", raw)
        if sys.byteorder != "little":
            samples.byteswap()
        return samples

    def invoke(self, args):
        stdout = io.StringIO()
        which = shutil.which
        with (self.temp / "stderr.txt").open("w", encoding="utf-8") as stderr:
            with redirect_stdout(stdout), redirect_stderr(stderr):
                with patch.object(cli, "download", return_value=(self.source, "Night / echo")):
                    with patch.object(
                        cli.shutil,
                        "which",
                        side_effect=lambda name: "deno" if name == "deno" else which(name),
                    ):
                        result = cli.main(args)
        return result, stdout.getvalue()

    def test_full_pipeline_pitch_tail_encoding_and_stdout(self):
        output = self.temp / "slow night.mp3"
        result, stdout = self.invoke([URL, "-o", str(output)])
        self.assertEqual(result, 0)
        self.assertEqual(stdout, f"{output}\n")
        samples = self.decode(output)
        body = samples[44100:88200]
        crossings = sum(a < 0 <= b for a, b in zip(body, body[1:]))
        self.assertAlmostEqual(crossings, 374, delta=2)
        self.assertAlmostEqual(len(samples) / 44100, 5.35, delta=0.1)
        tail = samples[132300:176400]
        self.assertGreater(math.sqrt(sum(x * x for x in tail) / len(tail)), 0.00001)
        self.assertLess(max(abs(x) for x in samples), 1.0)
        info = json.loads(
            subprocess.check_output(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_streams",
                    "-show_format",
                    "-of",
                    "json",
                    str(output),
                ]
            )
        )
        stream = info["streams"][0]
        self.assertEqual(stream["codec_name"], "mp3")
        self.assertEqual(stream["channels"], 2)
        self.assertEqual(stream["sample_rate"], "44100")
        self.assertEqual(stream["bit_rate"], "320000")
        self.assertIn("Night / echo", info["format"]["tags"]["title"])
        self.assertFalse(list(self.temp.glob(".slowverb-*")))

    def test_zero_reverb_has_no_extra_tail(self):
        output = self.temp / "dry.mp3"
        cli.render(self.source, output, 1.0, 0.0, self.temp, self.ffmpeg)
        samples = self.decode(output)
        self.assertAlmostEqual(len(samples) / 44100, 2.0, delta=0.1)

    def test_default_name_and_existing_file_protection(self):
        with chdir(self.temp):
            result, stdout = self.invoke([URL])
        output = self.temp / "Night _ echo (slowed + reverb).mp3"
        self.assertEqual(result, 0)
        self.assertEqual(stdout, f"{output}\n")
        original = output.read_bytes()
        with self.assertRaises(SystemExit) as error:
            self.invoke([URL, "-o", str(output)])
        self.assertEqual(error.exception.code, 2)
        self.assertEqual(output.read_bytes(), original)

    def test_encoder_failure_leaves_no_partial_output(self):
        output = self.temp / "failed.mp3"

        def fail(source, encoded, *args):
            encoded.write_bytes(b"partial")
            raise subprocess.CalledProcessError(1, ["ffmpeg"])

        with patch.object(cli, "render", side_effect=fail):
            result, stdout = self.invoke([URL, "-o", str(output)])
        self.assertEqual(result, 1)
        self.assertEqual(stdout, "")
        self.assertFalse(output.exists())
        self.assertFalse(list(self.temp.glob(".slowverb-*")))


if __name__ == "__main__":
    unittest.main()
