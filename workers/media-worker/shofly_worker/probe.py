import json
import subprocess
from pathlib import Path
from shofly_worker.errors import WorkerError


def probe(path: Path, run=subprocess.run) -> dict:
    """ffprobe metadata. No transcoding: originals are kept as-is (optional FFmpeg step not implemented)."""
    try:
        p = run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
                capture_output=True, text=True, timeout=120)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        raise WorkerError("PROBE_UNAVAILABLE", "ffprobe is not available or timed out.", True)
    if p.returncode != 0:
        raise WorkerError("PROBE_FAILED", "File is not a readable media file.", False)
    try:
        data = json.loads(p.stdout)
        streams = data.get("streams", [])
        video = next((s for s in streams if s.get("codec_type") == "video"), None)
        audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
        dur = float(data.get("format", {}).get("duration") or 0)
    except (ValueError, TypeError):
        raise WorkerError("PROBE_FAILED", "Unreadable probe output.", False)
    if not video or dur <= 0:
        raise WorkerError("NOT_VIDEO", "File has no video stream or duration.", False)
    h = video.get("height")
    return {"duration_sec": int(round(dur)), "codec": video.get("codec_name"), "quality": f"{h}p" if h else None,
            "audio_language": (audio or {}).get("tags", {}).get("language")}
