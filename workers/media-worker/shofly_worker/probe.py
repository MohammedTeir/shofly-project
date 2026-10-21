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



def verify_media(path: Path, timeout: int = 600, run=subprocess.run) -> None:
    """Decode the media to a null output to detect corrupt/truncated streams.

    This does not transcode, modify or save the input file. FFmpeg stderr is
    intentionally not logged: source paths may contain sensitive information.
    """
    if not 1 <= timeout <= 3600:
        raise WorkerError("INVALID_FFMPEG_CONFIG", "Invalid media verification timeout.", False)
    cmd = ["ffmpeg", "-hide_banner", "-nostdin", "-v", "error", "-xerror",
           "-i", str(path), "-map", "0:v:0", "-map", "0:a?", "-f", "null", "-"]
    try:
        result = run(cmd, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        raise WorkerError("FFMPEG_UNAVAILABLE", "FFmpeg is not installed.", True)
    except subprocess.TimeoutExpired:
        raise WorkerError("FFMPEG_TIMEOUT", "Media integrity check timed out.", True)
    if result.returncode != 0:
        raise WorkerError("MEDIA_CORRUPT", "Media integrity verification failed.", False)


def media_extension(path: Path, run=subprocess.run) -> str:
    """Choose an extension from the probed container, never the source URL."""
    try:
        result = run(["ffprobe", "-v", "error", "-show_entries", "format=format_name",
                      "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
                     capture_output=True, text=True, timeout=120)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        raise WorkerError("PROBE_UNAVAILABLE", "Unable to identify media container.", True)
    if result.returncode:
        raise WorkerError("PROBE_FAILED", "Unable to identify media container.", False)
    formats = set(result.stdout.strip().lower().split(","))
    if "matroska" in formats or "webm" in formats:
        return ".webm" if "webm" in formats and "matroska" not in formats else ".mkv"
    if "mov" in formats or "mp4" in formats or "m4a" in formats or "3gp" in formats or "3g2" in formats or "mj2" in formats:
        return ".mp4"
    if "avi" in formats:
        return ".avi"
    if "mpegts" in formats:
        return ".ts"
    return ".bin"
