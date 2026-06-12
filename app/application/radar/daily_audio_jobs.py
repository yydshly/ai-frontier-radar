"""Persistent background jobs for daily broadcast audio generation."""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import wave
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from app.application.radar.daily_broadcast import (
    DailyBroadcastScript,
    get_daily_broadcast_audio_dir,
    get_daily_broadcast_audio_path,
    is_valid_daily_broadcast_audio_file,
)
from app.application.radar.mimo_tts import (
    MiMoTTSClient,
    MiMoTTSError,
    MiMoTTSSettings,
)


VOICE_OPTIONS = ("冰糖", "茉莉", "苏打", "白桦")
JOB_ID_RE = re.compile(r"^[0-9a-f]{24}$")
JOB_STATUS_QUEUED = "queued"
JOB_STATUS_RUNNING = "running"
JOB_STATUS_GENERATED = "generated"
JOB_STATUS_FAILED = "failed"


@dataclass(frozen=True)
class DailyAudioJob:
    job_id: str
    status: str
    date_label: str
    title: str
    script_basis: str
    script_text: str
    voice: str
    style: str
    model: str
    created_at: str
    updated_at: str
    report_version: str | None = None
    chunk_count: int = 0
    completed_chunks: int = 0
    audio_filename: str | None = None
    error: str | None = None

    @property
    def audio_url(self) -> str | None:
        if self.status != JOB_STATUS_GENERATED or not self.audio_filename:
            return None
        return (
            "/radar/daily-report/broadcast/audio/files/"
            f"{self.audio_filename}"
        )


@dataclass(frozen=True)
class DailyAudioEnqueueResult:
    job: DailyAudioJob
    should_start: bool


def enqueue_daily_audio_job(
    script: DailyBroadcastScript,
    *,
    script_basis: str,
    voice: str,
    style: str,
    report_version: str | None = None,
    force: bool = False,
    root_dir: str | Path | None = None,
) -> DailyAudioEnqueueResult:
    if os.getenv("DAILY_BROADCAST_TTS_ENABLED", "").strip().lower() != "true":
        raise MiMoTTSError(
            "MiMo 语音合成未启用，请设置 DAILY_BROADCAST_TTS_ENABLED=true。"
        )
    settings = MiMoTTSSettings.from_env()
    clean_voice = voice.strip() or settings.voice
    if clean_voice not in VOICE_OPTIONS:
        raise MiMoTTSError("不支持所选音色。")
    clean_style = style.strip()[:500] or settings.style
    job_id = _build_job_id(
        script.full_text,
        settings.model,
        clean_voice,
        clean_style,
    )
    existing = load_daily_audio_job(job_id, root_dir=root_dir)
    if existing and not force:
        if existing.status in {JOB_STATUS_QUEUED, JOB_STATUS_RUNNING}:
            return DailyAudioEnqueueResult(existing, should_start=False)
        if (
            existing.status == JOB_STATUS_GENERATED
            and is_daily_audio_job_playable(existing, root_dir=root_dir)
        ):
            return DailyAudioEnqueueResult(existing, should_start=False)

    now = datetime.utcnow().isoformat(timespec="seconds")
    job = DailyAudioJob(
        job_id=job_id,
        status=JOB_STATUS_QUEUED,
        date_label=script.date_label,
        title=script.title,
        script_basis=script_basis,
        script_text=script.full_text,
        voice=clean_voice,
        style=clean_style,
        model=settings.model,
        created_at=existing.created_at if existing else now,
        updated_at=now,
        report_version=report_version,
    )
    if not _write_job(job, root_dir=root_dir):
        raise MiMoTTSError("无法保存语音生成任务，请检查运行目录权限。")
    cleanup_daily_audio_jobs(root_dir=root_dir)
    return DailyAudioEnqueueResult(job, should_start=True)


def run_daily_audio_job(
    job_id: str,
    *,
    root_dir: str | Path | None = None,
    client: MiMoTTSClient | None = None,
) -> None:
    job = load_daily_audio_job(job_id, root_dir=root_dir)
    if job is None:
        return

    lock_path = _job_lock_path(job_id, root_dir=root_dir)
    lock_fd: int | None = None
    _remove_stale_lock(lock_path)
    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_fd = os.open(
            lock_path,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY,
        )
    except FileExistsError:
        return
    except OSError:
        _update_job(job, status=JOB_STATUS_FAILED, error="无法获取任务锁。", root_dir=root_dir)
        return

    try:
        settings = MiMoTTSSettings.from_env()
        settings = MiMoTTSSettings(
            api_key=settings.api_key,
            base_url=settings.base_url,
            model=job.model,
            voice=job.voice,
            audio_format=settings.audio_format,
            style=job.style,
            timeout_seconds=settings.timeout_seconds,
            max_text_chars=settings.max_text_chars,
        )
        chunks = split_broadcast_text(
            job.script_text,
            max_chars=_env_int("MIMO_TTS_CHUNK_CHARS", 3000, minimum=200, maximum=10000),
        )
        job = _update_job(
            job,
            status=JOB_STATUS_RUNNING,
            chunk_count=len(chunks),
            completed_chunks=0,
            error=None,
            root_dir=root_dir,
        )
        tts_client = client or MiMoTTSClient(settings)
        wav_parts: list[bytes] = []
        for index, chunk in enumerate(chunks, start=1):
            _touch_lock(lock_path)
            wav_parts.append(tts_client.synthesize(chunk))
            _touch_lock(lock_path)
            job = _update_job(
                job,
                completed_chunks=index,
                root_dir=root_dir,
            )

        audio_bytes = merge_wav_parts(wav_parts)
        audio_filename = f"daily_broadcast_{job.date_label}_{job.job_id}.wav"
        audio_path = get_daily_broadcast_audio_dir(root_dir) / audio_filename
        _write_audio(audio_path, audio_bytes)
        _update_job(
            job,
            status=JOB_STATUS_GENERATED,
            completed_chunks=len(chunks),
            audio_filename=audio_filename,
            error=None,
            root_dir=root_dir,
        )
        cleanup_daily_audio_jobs(root_dir=root_dir)
    except (MiMoTTSError, OSError, ValueError, wave.Error) as exc:
        latest = load_daily_audio_job(job_id, root_dir=root_dir) or job
        try:
            _update_job(
                latest,
                status=JOB_STATUS_FAILED,
                error=str(exc)[:500],
                root_dir=root_dir,
            )
        except OSError:
            pass
    finally:
        if lock_fd is not None:
            os.close(lock_fd)
        try:
            lock_path.unlink(missing_ok=True)
        except OSError:
            pass


def load_daily_audio_job(
    job_id: str,
    *,
    root_dir: str | Path | None = None,
) -> DailyAudioJob | None:
    if not JOB_ID_RE.fullmatch(job_id):
        return None
    try:
        payload = json.loads(
            _job_path(job_id, root_dir=root_dir).read_text(encoding="utf-8")
        )
        return DailyAudioJob(**payload)
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return None


def list_daily_audio_jobs(
    *,
    root_dir: str | Path | None = None,
    limit: int = 20,
) -> list[DailyAudioJob]:
    jobs: list[DailyAudioJob] = []
    jobs_dir = _jobs_dir(root_dir)
    if not jobs_dir.is_dir():
        return []
    for path in jobs_dir.glob("*.json"):
        job = load_daily_audio_job(path.stem, root_dir=root_dir)
        if job is not None:
            jobs.append(job)
    jobs.sort(key=lambda value: value.updated_at, reverse=True)
    return jobs[: max(1, limit)]


def is_daily_audio_job_playable(
    job: DailyAudioJob,
    *,
    root_dir: str | Path | None = None,
) -> bool:
    """Return whether a generated job points to an existing valid WAV file."""
    if job.status != JOB_STATUS_GENERATED or not job.audio_filename:
        return False
    audio_path = get_daily_broadcast_audio_path(
        job.audio_filename,
        root_dir=root_dir,
    )
    return bool(
        audio_path
        and audio_path.is_file()
        and is_valid_daily_broadcast_audio_file(audio_path)
    )


def select_daily_audio_job(
    audio_jobs: list[DailyAudioJob],
    *,
    date_label: str,
    report_version: str | None,
    root_dir: str | Path | None = None,
    require_file: bool = True,
) -> DailyAudioJob | None:
    """Select today's newest playable audio, preferring the report version."""
    candidates = [
        job
        for job in audio_jobs
        if job.status == JOB_STATUS_GENERATED
        and job.audio_url
        and job.date_label == date_label
        and (
            not require_file
            or is_daily_audio_job_playable(job, root_dir=root_dir)
        )
    ]
    if report_version:
        for job in candidates:
            if job.report_version == report_version:
                return job
    return candidates[0] if candidates else None


def delete_daily_audio_job(
    job_id: str,
    *,
    root_dir: str | Path | None = None,
) -> bool:
    job = load_daily_audio_job(job_id, root_dir=root_dir)
    if job is None or job.status in {JOB_STATUS_QUEUED, JOB_STATUS_RUNNING}:
        return False
    paths = [_job_path(job_id, root_dir=root_dir), _job_lock_path(job_id, root_dir=root_dir)]
    if job.audio_filename:
        paths.append(get_daily_broadcast_audio_dir(root_dir) / job.audio_filename)
    removed = False
    for path in paths:
        try:
            if path.exists():
                path.unlink()
                removed = True
        except OSError:
            pass
    return removed


def retry_daily_audio_job(
    job_id: str,
    *,
    root_dir: str | Path | None = None,
) -> DailyAudioEnqueueResult | None:
    job = load_daily_audio_job(job_id, root_dir=root_dir)
    if job is None:
        return None
    if job.status in {JOB_STATUS_QUEUED, JOB_STATUS_RUNNING}:
        return DailyAudioEnqueueResult(job, should_start=False)
    if job.status == JOB_STATUS_GENERATED:
        return DailyAudioEnqueueResult(job, should_start=False)
    queued = _update_job(
        job,
        status=JOB_STATUS_QUEUED,
        completed_chunks=0,
        audio_filename=None,
        error=None,
        root_dir=root_dir,
    )
    return DailyAudioEnqueueResult(queued, should_start=True)


def resume_daily_audio_job(
    job_id: str,
    *,
    root_dir: str | Path | None = None,
) -> DailyAudioEnqueueResult | None:
    """Resume a queued job or a running job whose process lock disappeared."""
    job = load_daily_audio_job(job_id, root_dir=root_dir)
    if job is None:
        return None
    if job.status == JOB_STATUS_QUEUED:
        return DailyAudioEnqueueResult(job, should_start=True)
    if job.status != JOB_STATUS_RUNNING:
        return DailyAudioEnqueueResult(job, should_start=False)
    lock_path = _job_lock_path(job_id, root_dir=root_dir)
    _remove_stale_lock(lock_path)
    if lock_path.exists():
        return DailyAudioEnqueueResult(job, should_start=False)
    queued = _update_job(
        job,
        status=JOB_STATUS_QUEUED,
        error=None,
        root_dir=root_dir,
    )
    return DailyAudioEnqueueResult(queued, should_start=True)


def cleanup_daily_audio_jobs(
    *,
    root_dir: str | Path | None = None,
) -> int:
    retention_days = _env_int(
        "DAILY_BROADCAST_AUDIO_RETENTION_DAYS",
        30,
        minimum=1,
        maximum=3650,
    )
    max_files = _env_int(
        "DAILY_BROADCAST_AUDIO_MAX_FILES",
        100,
        minimum=1,
        maximum=10000,
    )
    jobs = list_daily_audio_jobs(root_dir=root_dir, limit=10000)
    cutoff = datetime.utcnow() - timedelta(days=retention_days)
    remove_ids: set[str] = set()
    for job in jobs:
        try:
            updated_at = datetime.fromisoformat(job.updated_at)
        except ValueError:
            updated_at = datetime.min
        if job.status != JOB_STATUS_RUNNING and updated_at < cutoff:
            remove_ids.add(job.job_id)
    for job in jobs[max_files:]:
        if job.status != JOB_STATUS_RUNNING:
            remove_ids.add(job.job_id)
    removed = sum(
        1
        for job_id in remove_ids
        if delete_daily_audio_job(job_id, root_dir=root_dir)
    )
    remaining_jobs = list_daily_audio_jobs(root_dir=root_dir, limit=10000)
    referenced_audio = {
        job.audio_filename
        for job in remaining_jobs
        if job.audio_filename
    }
    audio_dir = get_daily_broadcast_audio_dir(root_dir)
    if audio_dir.is_dir():
        for path in audio_dir.glob("daily_broadcast_*.wav"):
            if path.name in referenced_audio:
                continue
            try:
                modified_at = datetime.utcfromtimestamp(path.stat().st_mtime)
                if modified_at < cutoff:
                    path.unlink()
                    removed += 1
            except OSError:
                pass
    jobs_dir = _jobs_dir(root_dir)
    if jobs_dir.is_dir():
        for lock_path in jobs_dir.glob("*.lock"):
            existed = lock_path.exists()
            _remove_stale_lock(lock_path)
            if existed and not lock_path.exists():
                removed += 1
    return removed


def split_broadcast_text(text: str, *, max_chars: int) -> list[str]:
    clean_text = text.strip()
    if not clean_text:
        raise MiMoTTSError("播报文稿为空，无法生成音频。")
    paragraphs = [part.strip() for part in re.split(r"\n+", clean_text) if part.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        for piece in _split_long_piece(paragraph, max_chars):
            candidate = f"{current}\n{piece}".strip() if current else piece
            if len(candidate) <= max_chars:
                current = candidate
            else:
                if current:
                    chunks.append(current)
                current = piece
    if current:
        chunks.append(current)
    return chunks


def merge_wav_parts(parts: list[bytes]) -> bytes:
    if not parts:
        raise MiMoTTSError("没有可合并的音频片段。")
    output = io.BytesIO()
    reference: tuple[int, int, int, str, str] | None = None
    frames: list[bytes] = []
    for part in parts:
        with wave.open(io.BytesIO(part), "rb") as reader:
            params = (
                reader.getnchannels(),
                reader.getsampwidth(),
                reader.getframerate(),
                reader.getcomptype(),
                reader.getcompname(),
            )
            if reference is None:
                reference = params
            elif params != reference:
                raise MiMoTTSError("MiMo 返回的分段音频参数不一致，无法合并。")
            frames.append(reader.readframes(reader.getnframes()))
    assert reference is not None
    with wave.open(output, "wb") as writer:
        writer.setnchannels(reference[0])
        writer.setsampwidth(reference[1])
        writer.setframerate(reference[2])
        writer.setcomptype(reference[3], reference[4])
        for frame in frames:
            writer.writeframes(frame)
    return output.getvalue()


def _split_long_piece(text: str, max_chars: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    sentences = [
        value.strip()
        for value in re.split(r"(?<=[。！？；.!?;])", text)
        if value.strip()
    ]
    if len(sentences) <= 1:
        return [text[index:index + max_chars] for index in range(0, len(text), max_chars)]
    pieces: list[str] = []
    current = ""
    for sentence in sentences:
        if len(sentence) > max_chars:
            if current:
                pieces.append(current)
                current = ""
            pieces.extend(_split_long_piece(sentence, max_chars))
            continue
        candidate = current + sentence
        if len(candidate) <= max_chars:
            current = candidate
        else:
            pieces.append(current)
            current = sentence
    if current:
        pieces.append(current)
    return pieces


def _build_job_id(text: str, model: str, voice: str, style: str) -> str:
    return hashlib.sha256(
        "\n".join((text, model, voice, style)).encode("utf-8")
    ).hexdigest()[:24]


def _jobs_dir(root_dir: str | Path | None) -> Path:
    return get_daily_broadcast_audio_dir(root_dir) / "jobs"


def _job_path(job_id: str, *, root_dir: str | Path | None) -> Path:
    return _jobs_dir(root_dir) / f"{job_id}.json"


def _job_lock_path(job_id: str, *, root_dir: str | Path | None) -> Path:
    return _jobs_dir(root_dir) / f"{job_id}.lock"


def _write_job(job: DailyAudioJob, *, root_dir: str | Path | None) -> bool:
    path = _job_path(job.job_id, root_dir=root_dir)
    temp_path = path.with_suffix(".json.tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path.write_text(
            json.dumps(asdict(job), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(temp_path, path)
        return True
    except (OSError, TypeError, ValueError):
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass
        return False


def _update_job(
    job: DailyAudioJob,
    *,
    root_dir: str | Path | None,
    **changes: Any,
) -> DailyAudioJob:
    payload = asdict(job)
    payload.update(changes)
    payload["updated_at"] = datetime.utcnow().isoformat(timespec="seconds")
    updated = DailyAudioJob(**payload)
    if not _write_job(updated, root_dir=root_dir):
        raise OSError("无法保存语音任务状态。")
    return updated


def _write_audio(path: Path, audio_bytes: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(".wav.tmp")
    temp_path.write_bytes(audio_bytes)
    os.replace(temp_path, path)


def _remove_stale_lock(path: Path) -> None:
    stale_minutes = _env_int(
        "DAILY_BROADCAST_AUDIO_LOCK_MINUTES",
        30,
        minimum=1,
        maximum=1440,
    )
    try:
        modified_at = datetime.utcfromtimestamp(path.stat().st_mtime)
        if modified_at < datetime.utcnow() - timedelta(minutes=stale_minutes):
            path.unlink(missing_ok=True)
    except OSError:
        pass


def _touch_lock(path: Path) -> None:
    """Refresh the task lease while a long-running synthesis is active."""
    try:
        path.touch(exist_ok=True)
    except OSError:
        pass


def _env_int(
    name: str,
    default: int,
    *,
    minimum: int,
    maximum: int,
) -> int:
    try:
        return max(minimum, min(maximum, int(os.getenv(name, str(default)))))
    except ValueError:
        return default
