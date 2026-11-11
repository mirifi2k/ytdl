"""Offline CLI integration checks using real audio and stub downloaders."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "requires ffmpeg")
class Downloads(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.music = self.root / "Music"
        (self.music / "House").mkdir(parents=True)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        script = (ROOT / "ytdl.sh").read_text()
        self.script = self.root / "ytdl.sh"
        self.script.write_text(script)
        shutil.copy(ROOT / "metadata_parser.py", self.root)
        self.fixture = self.root / "fixture.mp3"
        subprocess.run([
            "ffmpeg", "-v", "error", "-f", "lavfi", "-i", "anullsrc", "-t", "0.1",
            "-metadata", "artist=Uploader", "-metadata", "title=Artist - Track",
            str(self.fixture),
        ], check=True)
        self.env = dict(os.environ, PATH=f"{self.bin}{os.pathsep}{os.environ['PATH']}",
                        FIXTURE=str(self.fixture), YTDL_ROOT=str(self.music))

    def stub(self, name, body):
        path = self.bin / name
        path.write_text("#!/usr/bin/env python3\n" + body)
        path.chmod(0o755)

    def run_cli(self, url, *args):
        return subprocess.run(["bash", str(self.script), url, *args, "House"],
                              env=self.env, capture_output=True, text=True)

    def soundcloud_stub(self, count=1):
        self.stub("scdl", f'''import os, shutil, sys
from pathlib import Path
args = sys.argv[1:]
assert "--no-playlist" in args and "--no-original" in args
path = Path(args[args.index("--path") + 1])
for i in range({count}):
    shutil.copy(os.environ["FIXTURE"], path / f"track{{i}}.mp3")
''')
        self.stub("yt-dlp", 'raise RuntimeError("wrong downloader")\n')

    def test_soundcloud_metadata_and_manual_override(self):
        self.soundcloud_stub()
        for args, expected in [((), "Track.mp3"),
                               (("Manual Artist", "Manual Track"), "Manual Track.mp3")]:
            result = self.run_cli("https://soundcloud.com/u/t/s-secret?secret_token=s-secret", *args)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            audio = self.music / "House" / expected
            self.assertTrue(audio.is_file(), result.stdout)
            probe = subprocess.run(["ffprobe", "-v", "quiet", "-show_format", "-of", "json", str(audio)],
                                   capture_output=True, text=True, check=True)
            tags = json.loads(probe.stdout)["format"]["tags"]
            self.assertEqual(tags["artist"], args[0] if args else "Artist")
            self.assertEqual(tags["title"], args[1] if args else "Track")

    def test_no_audio_and_multiple_tracks_are_rejected(self):
        for count in (0, 2):
            self.soundcloud_stub(count)
            result = self.run_cli("https://soundcloud.com/u/t")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(f"found {count}", result.stderr)
        self.assertEqual(list((self.music / "House").iterdir()), [])

    def test_scdl_failure_is_propagated(self):
        self.stub("scdl", "raise SystemExit(7)\n")
        result = self.run_cli("https://on.soundcloud.com/example")
        self.assertEqual(result.returncode, 7)
        self.assertIn("scdl failed", result.stderr)

    def test_missing_mutagen_fails_before_downloading(self):
        self.stub("yt-dlp", 'raise RuntimeError("downloader must not run")\n')
        python = self.bin / "python-without-mutagen"
        python.write_text('#!/bin/sh\nexit 1\n')
        python.chmod(0o755)
        self.env["YTDL_PYTHON"] = str(python)
        result = self.run_cli("https://youtube.com/watch?v=123")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("mutagen is required", result.stderr)
        self.assertNotIn("Downloading...", result.stdout)

    def test_youtube_still_uses_ytdlp(self):
        self.env["YTDL_PYTHON"] = sys.executable
        self.stub("scdl", 'raise RuntimeError("wrong downloader")\n')
        self.stub("yt-dlp", '''import os, shutil, sys
from pathlib import Path
args = sys.argv[1:]
assert "--no-playlist" in args
info = Path(args[args.index("--print-to-file") + 2])
audio = info.parent / "video.mp3"
shutil.copy(os.environ["FIXTURE"], audio)
info.write_text(f"{audio}|||Artist|||Track|||Artist - Track\\n")
''')
        result = self.run_cli("https://youtube.com/watch?v=123")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue((self.music / "House" / "Track.mp3").is_file())


if __name__ == "__main__":
    unittest.main()
