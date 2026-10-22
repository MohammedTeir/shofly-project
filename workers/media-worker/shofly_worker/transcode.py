"""Optional CPU transcoding of lower-quality MP4 variants for authorized imports."""
import subprocess
from pathlib import Path
from shofly_worker.errors import WorkerError

LADDER = ((1080, "4500k", "128k"), (720, "2500k", "128k"),
          (480, "1100k", "96k"), (360, "650k", "64k"))


def generate_variants(source: Path, output_dir: Path, original_height: int,
                      timeout: int = 7200, check=lambda: None, on_error=None):
    """Yield (quality, path) one at a time to bound local disk usage.

    Never upscale; the original file is retained independently. FFmpeg failures
    are reported without exposing potentially sensitive source paths.
    """
    if original_height <= 0:
        return
    output_dir.mkdir(parents=True, exist_ok=True)
    for height, video_rate, audio_rate in LADDER:
        if height >= original_height:
            continue
        check()
        output = output_dir / f"{height}p.mp4"
        cmd = ["ffmpeg", "-hide_banner", "-nostdin", "-y", "-v", "error",
               "-i", str(source), "-map", "0:v:0", "-map", "0:a:0?",
               "-vf", f"scale=-2:{height}", "-c:v", "libx264", "-preset", "veryfast",
               "-b:v", video_rate, "-maxrate", video_rate, "-bufsize", video_rate,
               "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", audio_rate,
               "-movflags", "+faststart", str(output)]
        try:
            result = subprocess.run(cmd, capture_output=True, timeout=timeout)
        except FileNotFoundError as exc:
            raise WorkerError("FFMPEG_UNAVAILABLE", "FFmpeg is not installed.", True) from exc
        except subprocess.TimeoutExpired as exc:
            output.unlink(missing_ok=True)
            if on_error is not None:
                on_error(f"{height}p", "TRANSCODE_TIMEOUT")
                continue
            raise WorkerError("TRANSCODE_TIMEOUT", "Quality conversion timed out.", True) from exc
        if result.returncode or not output.is_file() or not output.stat().st_size:
            output.unlink(missing_ok=True)
            if on_error is not None:
                on_error(f"{height}p", "TRANSCODE_FAILED")
                continue
            raise WorkerError("TRANSCODE_FAILED", "Unable to generate video quality.", True)
        yield f"{height}p", output
