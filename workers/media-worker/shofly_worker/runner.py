import hashlib
import json
import logging
import time
import shutil
import threading
from pathlib import Path
import httpx
from shofly_worker.client import ApiError, BackendClient
from shofly_worker.downloader import download, download_parallel
from shofly_worker.aria2_downloader import download_aria2
from shofly_worker.errors import LeaseLost, SourceExpired, WorkerError
from shofly_worker.probe import probe, verify_media, media_extension
from shofly_worker.segmentation import split_playable
from shofly_worker.retention import job_dir, mark_final, cleanup, touch_active, clear_active

log = logging.getLogger("shofly_worker")


class Heartbeat(threading.Thread):
    def __init__(self, client: BackendClient, jid: str, every: float):
        super().__init__(daemon=True)
        self.client, self.jid, self.every = client, jid, every
        self.stop_evt, self.lost = threading.Event(), threading.Event()

    def run(self):
        while not self.stop_evt.wait(self.every):
            try:
                self.client.heartbeat(self.jid)
            except LeaseLost:
                self.lost.set(); return
            except Exception:  # transient network blip: lease may still be valid, keep trying
                log.warning("heartbeat failed for job %s", self.jid)


def process_one(client: BackendClient, provider, settings, dl_http: httpx.Client, resolver=None, probe_fn=probe) -> str | None:
    """Claim and process one job. Returns the outcome label, or None if the queue is empty.
    Only a successful /complete marks a job done; any crash/disconnect leaves it to lease expiry."""
    job = client.claim()
    if job is None:
        return None
    jid = job["id"]
    persistent = bool(settings.persistent_download_dir) and settings.downloader == "aria2c"
    tmp = job_dir(settings.persistent_download_dir, jid) if persistent else Path(settings.tmp_dir) / jid
    retain_partial = persistent
    completed = False
    if persistent:
        # A partial transfer may be resumed only for the exact same source.
        marker = tmp / "source.json"
        fingerprint = hashlib.sha256(job["source_ref"].encode()).hexdigest()
        try:
            old = json.loads(marker.read_text()) if marker.exists() else {}
        except (ValueError, OSError):
            old = {}
        if old.get("fingerprint") != fingerprint:
            shutil.rmtree(tmp, ignore_errors=True)
        tmp.mkdir(parents=True, exist_ok=True)
        marker.write_text(json.dumps({"fingerprint": fingerprint}))
        (tmp / "retention.json").unlink(missing_ok=True)
        touch_active(tmp)

    hb = Heartbeat(client, jid, settings.heartbeat_seconds); hb.start()
    uploaded_refs = []
    started = time.monotonic()
    log.info("job_started job_id=%s", jid)

    last_touch = [0.0]

    def check():
        if hb.lost.is_set():
            raise LeaseLost()
        if persistent and time.monotonic() - last_touch[0] >= 30:
            touch_active(tmp)
            last_touch[0] = time.monotonic()

    try:
        check(); client.progress(jid, "DOWNLOADING", 5)
        hosts = {h.strip().lower() for h in settings.allowed_hosts.split(",") if h.strip()} or None
        mode = getattr(settings, "downloader", "httpx").lower()
        if mode == "aria2c" and hosts:
            size, sha = download_aria2(job["source_ref"], tmp / "source.bin", getattr(settings, "download_max_bytes", settings.max_bytes),
                                      settings.download_timeout, hosts, check,
                                      settings.aria2_connections, settings.aria2_retries)
        elif mode in ("httpx", "aria2c"):
            if mode == "aria2c":
                log.info("aria2c_no_allowlist_fallback_httpx job_id=%s", jid)
            size, sha = download_parallel(job["source_ref"], tmp / "source.bin", dl_http, getattr(settings, 'download_max_bytes', settings.max_bytes),
                                 settings.download_timeout, hosts, resolver, check,
                                 getattr(settings, "httpx_parallel_connections", 8),
                                 getattr(settings, "httpx_chunk_size_mb", 8) * 1024 * 1024)
        else:
            raise WorkerError("INVALID_DOWNLOADER", "Unknown downloader setting.", False)
        log.info("download_complete job_id=%s bytes=%s elapsed_s=%.1f", jid, size, time.monotonic()-started)
        check(); client.progress(jid, "PROBING", 40)
        info = probe_fn(tmp / "source.bin")
        log.info("probe_complete job_id=%s elapsed_s=%.1f", jid, time.monotonic()-started)
        if getattr(settings, "ffmpeg_verify", False):
            check()
            verify_media(tmp / "source.bin", settings.ffmpeg_verify_timeout)
            log.info("media_integrity_verified job_id=%s elapsed_s=%.1f", jid, time.monotonic()-started)
        check(); client.progress(jid, "UPLOADING", 60)
        source = tmp / "source.bin"
        extension = media_extension(source)
        if extension != ".bin":
            named_source = tmp / ("video" + extension)
            source.rename(named_source)
            source = named_source
        log.info("media_filename_prepared job_id=%s extension=%s", jid, extension)
        provider_limit = getattr(provider, "max", None)
        part_limit = getattr(settings, "segment_max_bytes", 0) or provider_limit
        if part_limit and provider_limit:
            part_limit = min(part_limit, provider_limit)
        if getattr(settings, "split_large_media", False) and part_limit and size > part_limit:
            parts = split_playable(source, tmp / "segments", part_limit,
                                   info["duration_sec"])
        else:
            parts = [source]
        for index, part in enumerate(parts):
            check()
            part_ref = provider.upload(part, info)
            uploaded_refs.append(part_ref)
            check()
            if not provider.verify(part_ref, part.stat().st_size):
                raise WorkerError("VERIFY_FAILED", "Uploaded part could not be verified.", True)
            log.info("segment_verified job_id=%s part=%s total=%s",
                     jid, index + 1, len(parts))
        ref = uploaded_refs[0]
        check(); client.progress(jid, "VERIFYING", 85)
        try:
            receipt = client.complete(jid, verified=True, provider=provider.name,
                            provider_ref=ref,
                            segment_refs=uploaded_refs if len(uploaded_refs) > 1 else [],
                            size_bytes=size, checksum_sha256=sha, **info)
        except ApiError as e:
            if e.code == "BLOCKED_RIGHTS":
                retain_partial = False
                return "BLOCKED_RIGHTS"
            raise
        completed = True
        if receipt.get("duplicate"):
            for uploaded_ref in uploaded_refs:
                try:
                    provider.delete(uploaded_ref)
                except Exception:
                    log.warning("duplicate_cleanup_failed job_id=%s", jid)
        log.info("job_completed job_id=%s elapsed_s=%.1f", jid, time.monotonic()-started)
        if getattr(settings, "generate_qualities", False) and not receipt.get("duplicate"):
            # The original is committed first. Variant failures never roll it back.
            try:
                from shofly_worker.transcode import generate_variants
                from shofly_worker.probe import probe as real_probe
                height = int(str(info.get("quality") or "0p").removesuffix("p"))
                for quality, variant_path in generate_variants(
                    source, tmp / "qualities", height, getattr(settings, "transcode_timeout", 7200)
                ):
                    variant_refs = []
                    registered = False
                    try:
                        variant_info = real_probe(variant_path)
                        provider_limit = getattr(provider, "max", None)
                        part_limit = getattr(settings, "segment_max_bytes", 0) or provider_limit
                        if part_limit and provider_limit:
                            part_limit = min(part_limit, provider_limit)
                        if part_limit and variant_path.stat().st_size > part_limit:
                            if not getattr(settings, "split_large_media", False):
                                raise WorkerError("FILE_TOO_LARGE", "Generated quality exceeds Telegram upload limit.", False)
                            variant_parts = split_playable(variant_path, tmp / ("quality_segments_" + quality),
                                                           part_limit, variant_info["duration_sec"])
                        else:
                            variant_parts = [variant_path]
                        for variant_part in variant_parts:
                            variant_ref = provider.upload(variant_part, variant_info)
                            variant_refs.append(variant_ref)
                            if not provider.verify(variant_ref, variant_part.stat().st_size):
                                raise WorkerError("VERIFY_FAILED", "Quality upload could not be verified.", True)
                        variant_hash = hashlib.sha256()
                        with variant_path.open("rb") as variant_file:
                            for block in iter(lambda: variant_file.read(1024 * 1024), b""):
                                variant_hash.update(block)
                        result = client.register_variant(
                            str(receipt["asset_id"]), provider_ref=variant_refs[0],
                            segment_refs=variant_refs if len(variant_refs) > 1 else [],
                            size_bytes=variant_path.stat().st_size,
                            checksum_sha256=variant_hash.hexdigest(), quality=quality,
                            duration_sec=variant_info["duration_sec"], codec=variant_info.get("codec"),
                            audio_language=variant_info.get("audio_language"))
                        registered = not result.get("duplicate")
                        log.info("quality_ready job_id=%s quality=%s bytes=%d", jid, quality, variant_path.stat().st_size)
                    except Exception as exc:
                        # One quality's upload failure must not prevent later qualities.
                        # Unregistered Telegram uploads are removed in the finally block.
                        log.warning("quality_upload_failed job_id=%s quality=%s reason=%s",
                                    jid, quality, type(exc).__name__)
                    finally:
                        if not registered:
                            for orphan_ref in variant_refs:
                                try:
                                    provider.delete(orphan_ref)
                                except Exception:
                                    log.warning("quality_orphan_cleanup_failed job_id=%s quality=%s", jid, quality)
                        variant_path.unlink(missing_ok=True)
            except Exception as exc:
                log.warning("quality_generation_incomplete job_id=%s reason=%s", jid, type(exc).__name__)
        return "COMPLETED"
    except LeaseLost:
        retain_partial = persistent
        return "LEASE_LOST"
    except WorkerError as e:
        retain_partial = persistent
        if persistent and not e.retryable:
            mark_final(tmp)
        log.warning("job_failed job_id=%s code=%s stage_elapsed_s=%.1f retryable=%s", jid, e.code, time.monotonic()-started, e.retryable)
        _report(client, jid, e.code, e.message, e.retryable)
        return e.code
    except Exception:  # unexpected: generic safe message only, details stay in local logs
        log.exception("job %s crashed", jid)
        _report(client, jid, "UNEXPECTED", "Unexpected worker error.", True)
        return "UNEXPECTED"
    finally:
        if not completed:
            for uploaded_ref in uploaded_refs:
                try:
                    provider.delete(uploaded_ref)
                except Exception:
                    log.warning("orphan_upload_cleanup_failed job_id=%s", jid)
        hb.stop_evt.set()
        if persistent and tmp.exists():
            clear_active(tmp)
        if completed or not retain_partial:
            shutil.rmtree(tmp, ignore_errors=True)


def _report(client, jid, code, msg, retryable):
    try:
        client.fail(jid, code, msg, retryable)
    except LeaseLost:
        log.warning("job_failure_report_rejected job_id=%s reason=lease_lost", jid)
    except ApiError as exc:
        log.warning("job_failure_report_rejected job_id=%s reason=backend_error code=%s", jid, exc.code)
    except httpx.HTTPError as exc:
        log.warning("job_failure_report_failed job_id=%s reason=%s", jid, type(exc).__name__)
    else:
        log.info("job_failure_report_accepted job_id=%s error_code=%s", jid, code)


def process_cleanup(client, provider) -> str | None:
    """Process one explicitly requested cleanup, including from the Colab notebook."""
    if not hasattr(provider, "delete_confirmed"):
        return None
    task = client.claim_cleanup()
    if not task:
        return None
    success = True
    try:
        for ref in task["refs"]:
            if not provider.delete_confirmed(ref):
                success = False
                break
    except Exception as exc:
        log.warning("cleanup_delete_failed asset_id=%s reason=%s", task["id"], type(exc).__name__)
        success = False
    client.finish_cleanup(task["id"], success, None if success else "TELEGRAM_DELETE_FAILED")
    log.info("cleanup_result asset_id=%s confirmed=%s", task["id"], success)
    return "CLEANUP_DELETED" if success else "CLEANUP_FAILED"


def run_until_empty(client, provider, settings, dl_http, max_jobs: int = 100, **kw) -> list[str]:
    results = []
    # Cleanup is also polled when no import jobs are available.
    for _ in range(min(max_jobs, 100)):
        try:
            cleanup_result = process_cleanup(client, provider)
        except Exception as exc:
            log.warning("cleanup_processing_interrupted reason=%s", type(exc).__name__)
            break
        if cleanup_result is None:
            break
        results.append(cleanup_result)
    if getattr(settings, "persistent_download_dir", "") and getattr(settings, "downloader", "httpx") == "aria2c":
        try:
            cleanup(settings.persistent_download_dir)
        except (OSError, ValueError) as exc:
            log.warning("retention_cleanup_failed reason=%s", type(exc).__name__)
    for _ in range(max_jobs):
        out = process_one(client, provider, settings, dl_http, **kw)
        if out is None:
            break
        results.append(out)
    return results
