"""Container-based safe naming tests for uploaded video files."""
from types import SimpleNamespace

import pytest

from shofly_worker.probe import media_extension


@pytest.mark.parametrize(("format_name", "expected"), [
    ("mov,mp4,m4a,3gp,3g2,mj2", ".mp4"),
    ("matroska,webm", ".mkv"),
    ("webm", ".webm"),
    ("avi", ".avi"),
    ("mpegts", ".ts"),
    ("unknown", ".bin"),
])
def test_media_extension(tmp_path, format_name, expected):
    def fake_run(command, **kwargs):
        assert command[0] == "ffprobe"
        return SimpleNamespace(returncode=0, stdout=format_name + "\n")
    assert media_extension(tmp_path / "source.bin", run=fake_run) == expected
