"""Exercise cancellation over the real native messaging connection."""
import json
import os
from pathlib import Path
import select
import struct
import subprocess
import sys
import tempfile
import unittest

HOST = Path(__file__).resolve().parents[1] / "native-host/ytdl_host.py"


class Cancellation(unittest.TestCase):
    def test_cancel_stops_children_and_cleans_temporary_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            script = root / "ytdl"
            script.write_text('''#!/bin/bash
set -u
mkdir "$YTDL_ROOT/partial"
trap 'rmdir "$YTDL_ROOT/partial"; exit 143' TERM
sleep 30 &
echo "child=$!"
wait
''')
            script.chmod(0o755)
            proc = subprocess.Popen(
                [sys.executable, str(HOST)], stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                env=dict(os.environ, PATH=f"{root}{os.pathsep}{os.environ['PATH']}"),
            )

            def send(message):
                data = json.dumps(message).encode()
                proc.stdin.write(struct.pack("<I", len(data)) + data)
                proc.stdin.flush()

            def receive():
                self.assertTrue(select.select([proc.stdout], [], [], 10)[0],
                                "Native host did not respond within 10 seconds")
                size = struct.unpack("<I", proc.stdout.read(4))[0]
                return json.loads(proc.stdout.read(size))

            try:
                send({"cmd": "download", "url": "https://youtu.be/123", "folder": ".", "root": tmp})
                progress = receive()
                self.assertEqual(progress["type"], "progress")
                child = int(progress["line"].split("=")[1])
                self.assertTrue((root / "partial").is_dir())
                send({"cmd": "cancel"})
                result = receive()
                self.assertTrue(result["canceled"])
                self.assertFalse(result["ok"])
                self.assertFalse((root / "partial").exists())
                with self.assertRaises(ProcessLookupError):
                    os.kill(child, 0)
                # A fresh request still works after cancellation.
                send({"cmd": "list_folders", "root": tmp})
                self.assertTrue(receive()["ok"])
                proc.stdin.close()
                self.assertEqual(proc.wait(timeout=10), 0)
            finally:
                if proc.poll() is None:
                    proc.kill()
                    proc.wait()
                for stream in (proc.stdin, proc.stdout, proc.stderr):
                    stream.close()
