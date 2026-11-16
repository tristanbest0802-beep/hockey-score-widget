import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from hockey_widget import update_check as uc

BASE = uc.DOWNLOAD_PREFIX + "v1.2.0/"


def release(tag="v1.2.0", assets=(uc.INSTALLER, uc.SUMS)) -> dict:
    return {"tag_name": tag, "assets": [{"name": n, "browser_download_url": BASE + n} for n in assets]}


class UpdateCheckTest(unittest.TestCase):
    def test_newer_release_found(self):
        info = uc.check("1.1.5", lambda url: json.dumps(release()).encode())
        self.assertEqual(info, uc.UpdateInfo("1.2.0", BASE + uc.INSTALLER, BASE + uc.SUMS))

    def test_same_or_older_or_incomplete_is_none(self):
        self.assertIsNone(uc.find_update("1.2.0", release()))
        self.assertIsNone(uc.find_update("1.10.0", release()))
        self.assertIsNone(uc.find_update("1.1.5", release(assets=(uc.INSTALLER,))))
        bad = release()
        bad["assets"][0]["browser_download_url"] = "https://evil.example/" + uc.INSTALLER
        self.assertIsNone(uc.find_update("1.1.5", bad))

    def test_install_checks_sha(self):
        data = b"installer bytes"
        good = f"{hashlib.sha256(data).hexdigest()}  {uc.INSTALLER}\n{'0' * 64}  HockeyScoreWidget.exe\n"
        info = uc.find_update("1.0.0", release())
        with tempfile.TemporaryDirectory() as tmp:
            launched = []
            files = {info.sums_url: good.encode(), info.installer_url: data}
            uc.install_update(info, Path(tmp), files.__getitem__, launched.append)
            self.assertEqual(launched, [[str(Path(tmp) / uc.INSTALLER)]])
            files[info.installer_url] = b"tampered"
            with self.assertRaises(uc.UpdateError):
                uc.install_update(info, Path(tmp) / "b", files.__getitem__, launched.append)
            self.assertEqual(len(launched), 1)


if __name__ == "__main__":
    unittest.main()
