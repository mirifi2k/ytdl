"""Download root selection and destination containment checks."""
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock

spec = importlib.util.spec_from_file_location(
    "host", Path(__file__).resolve().parents[1] / "native-host/ytdl_host.py"
)
host = importlib.util.module_from_spec(spec)
spec.loader.exec_module(host)


class DownloadRoot(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve() / "My Music"
        (self.root / "House" / "Deep").mkdir(parents=True)
        (self.root / ".hidden" / "Secret").mkdir(parents=True)

    def test_recursive_listing_and_empty_root(self):
        result = host.handle_list_folders(self.root)
        self.assertEqual(result["folders"], [".", "House", "House/Deep"])
        self.assertEqual(result["root"], str(self.root))
        self.assertEqual(host.handle_list_folders(self.root / "House/Deep")["folders"], ["."])
        self.assertFalse(host.handle_list_folders(self.root / "missing")["ok"])

    def test_root_validation(self):
        self.assertEqual(host.download_root(str(self.root)), self.root)
        self.assertEqual(host.download_root("~/Music"), (Path.home() / "Music").resolve())
        with self.assertRaises(ValueError):
            host.download_root("relative/folder")

    @patch.object(host, "find_ytdl", return_value="/bin/ytdl")
    @patch.object(host.subprocess, "Popen")
    def test_download_uses_selected_root(self, popen, _find):
        popen.return_value = Mock(stdout=io.StringIO(""), wait=lambda: 0)
        for folder in (".", "House/Deep"):
            self.assertTrue(host.handle_download("https://youtu.be/123", folder, self.root)["ok"])
            args, kwargs = popen.call_args
            self.assertEqual(args[0], ["/bin/ytdl", "https://youtu.be/123", folder])
            self.assertEqual(kwargs["env"]["YTDL_ROOT"], str(self.root))

    @patch.object(host, "find_ytdl", return_value="/bin/ytdl")
    @patch.object(host.subprocess, "Popen")
    def test_escape_paths_are_rejected(self, popen, _find):
        outside = self.root.parent / "outside"
        outside.mkdir()
        (self.root / "escape").symlink_to(outside, target_is_directory=True)
        for folder in ("../outside", str(outside), "escape"):
            self.assertFalse(host.handle_download("url", folder, self.root)["ok"])
        popen.assert_not_called()
