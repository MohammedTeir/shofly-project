"""Create independently playable video segments for authorized media.

Segmenting uses stream copy (no quality loss) and conservative size targets.
Exact size is checked after each segment; oversized segments fail closed.
"""
import json
import subprocess
from pathlib import Path
from shofly_worker.errors import WorkerError


def split_playable(source: Path, output_dir: Path, max_part_bytes: int,
                   duration_seconds: int, timeout: int = 3600) -> list[Path]:
    if max_part_bytes < 1024 * 1024 or duration_seconds <= 0:
        raise WorkerError("SEGMENT_CONFIG_INVALID", "Invalid segmentation limits.", False)
    if not source.is_file() or source.stat().st_size == 0:
        raise WorkerError("SEGMENT_SOURCE_INVALID", "Source file is missing.", False)
    if source.stat().st_size <= max_part_bytes:
        return [source]
    output_dir.mkdir(parents=True, exist_ok=True)
    # Reserve 25% margin for uneven bitrate and keyframe alignment.
    target_seconds = max(1, int(duration_seconds * max_part_bytes * 0.75 / source.stat().st_size))
    pattern = str(output_dir / "part_%04d.mkv")
    cmd = ["ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error",
           "-i", str(source), "-map", "0:v:0", "-map", "0:a?",
           "-c", "copy", "-f", "segment", "-segment_time", str(target_seconds),
           "-reset_timestamps", "1", pattern]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=timeout)
    except FileNotFoundError:
        raise WorkerError("FFMPEG_UNAVAILABLE", "FFmpeg is not installed.", True)
    except subprocess.TimeoutExpired:
        raise WorkerError("SEGMENT_TIMEOUT", "Video segmentation timed out.", True)
    if proc.returncode != 0:
        raise WorkerError("SEGMENT_FAILED", "Unable to split media into playable parts.", False)
    parts = sorted(output_dir.glob("part_*.mkv"))
    if not parts or any(p.stat().st_size == 0 or p.stat().st_size > max_part_bytes for p in parts):
        raise WorkerError("SEGMENT_SIZE_EXCEEDED", "Segment exceeds provider limit; re-encoding or smaller segments required.", False)
    return parts
