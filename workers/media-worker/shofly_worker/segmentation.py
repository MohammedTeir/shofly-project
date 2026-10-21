"""Create independently playable video segments for authorized media.

Segmenting uses stream copy (no quality loss) and conservative size targets.
Exact size is checked after each segment; oversized segments fail closed.
"""
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
    # Keyframe alignment and variable bitrate can produce oversized pieces.
    # Retry with shorter durations; never upload a piece above the limit.
    initial = max(1, int(duration_seconds * max_part_bytes * 0.65 / source.stat().st_size))
    for attempt in range(6):
        for stale in output_dir.glob("part_*.mkv"):
            stale.unlink()
        seconds = max(1, initial // (2 ** attempt))
        pattern = str(output_dir / "part_%04d.mkv")
        cmd = ["ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error",
               "-i", str(source), "-map", "0:v:0", "-map", "0:a?",
               "-c", "copy", "-f", "segment", "-segment_time", str(seconds),
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
        if parts and all(0 < p.stat().st_size <= max_part_bytes for p in parts):
            return parts
        if seconds == 1:
            break
    raise WorkerError("SEGMENT_SIZE_EXCEEDED",
                      "Unable to segment within provider limit without re-encoding.", False)
