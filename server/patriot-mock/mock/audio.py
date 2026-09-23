"""Audio & voice blueprint — /api/account/voice_sample/, /api/canvasser_voice/*,
/api/verifications/voice/*.

Wire contracts per audit/audio-voice.md (verified against /tmp/vn_src and the
decompiled native plugin on 2026-09-20):

  voice_sample/          JSON {audio_data: base64 Int16-LE PCM, audio_config:
                         {sample_rate, channels, bits_per_sample, encoding}}
                         — NOT multipart (mutations/createSample.ts:7-11).
                         Response body unused (createSample.ts:12-15).
  receive                native OkHttp multipart, parts: audio (voice_chunk.wav),
                         work_shift_id, vad_model_name, device_id, sample_rate,
                         wallclock_start, wallclock_end, segments (JSON string),
                         span_upload_id (AudioManager.java:960). Response body
                         NOT parsed (AudioManager.java:987-1002).
  cached_receive         multipart batch: repeated parts audio (voice_chunk_{i}.wav),
                         work_shift_id, wallclock_start, wallclock_end,
                         vad_model_name, span_upload_id (only when rows have one);
                         once: device_id, segments = JSON array whose elements are
                         themselves JSON strings (AudioManager.java:635-667).
                         Response consumed: succeeded_filenames
                         (AudioManager.java:695-719).
  wake_word_event        JSON {id, work_shift_id, device_id, timestamp_ms,
                         gps_point|null} (useWakeWordHandler.ts:12-21). Client
                         outbox DROPS rows on 400/404, retries anything else
                         (useUploader.ts:87-100) — so 400 only for malformed
                         bodies, never 404.
  wake_word_audio        multipart: audio (wake_word_clip.wav), event_id,
                         work_shift_id, device_id, clip_start_ms, clip_end_ms
                         (AudioManager.java:1029). 404 when the event row has not
                         landed yet (client comment, useWakeWordHandler.ts:33-34);
                         success body ignored (AudioManager.java:1064-1069).
  wake_word_audio_cached multipart: audio (wake_word_clip_{i}.wav) x N, device_id,
                         clips = JSON string [{event_id, work_shift_id,
                         clip_start_ms, clip_end_ms}] (AudioManager.java:764-789).
                         Response consumed: succeeded_indices
                         (AudioManager.java:813-839).
  verifications/voice    PUT {project_id} -> consumes response.id
                         (stores/verification/voice.ts:19-28); GET consumes
                         status + id + extracted_signatories
                         (useVoiceVerification.ts:95-101); POST submit consumes
                         nothing (mutations/verification/voice.ts:16-19).

The WebSocket /api/ws/voice_verification/{id} (useVoiceVerification.ts:135-149)
is OUT OF SCOPE for this mock: Flask's dev server cannot serve WebSockets.
Without it the stock client streams nothing and never receives
ready_for_submission, so the HTTP submit path here accepts submissions from any
non-terminal conversation state (see [H] note in submit_voice()).
"""

import base64
import binascii
import json
import uuid

from flask import Blueprint, jsonify, request

from . import state
from .auth import detail, require_auth

bp = Blueprint("audio", __name__)


def _record_upload(kind, user_id, **fields):
    entry = {
        "kind": kind,
        "user_id": str(user_id),
        "received_at": state.iso_now(),
    }
    entry.update(fields)
    state.audio_uploads.append(entry)
    state.capture("audio", entry)
    return entry


def _parse_json_string(raw):
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return None


# --- voice-sample enrollment ---------------------------------------------------

@bp.post("/api/account/voice_sample/")
@require_auth
def create_voice_sample():
    body = request.get_json(silent=True) or {}
    audio_data = body.get("audio_data")
    audio_config = body.get("audio_config")
    if not isinstance(audio_data, str) or not isinstance(audio_config, dict):
        return detail(400, "audio_data and audio_config are required")
    try:
        pcm = base64.b64decode(audio_data, validate=True)
    except (binascii.Error, ValueError):
        return detail(400, "audio_data must be valid base64")
    # Duration from raw Int16-LE byte count ([R] capture path,
    # useSampleRecorder.ts:110-115); config values from
    # utils/createAudioConfig.ts:6-11. Stored only server-side — the client
    # never reads it back (voice_sample_recorded flips on the account).
    sample_rate = int(audio_config.get("sample_rate") or 48000)
    channels = int(audio_config.get("channels") or 1)
    bits = int(audio_config.get("bits_per_sample") or 16)
    bytes_per_second = max(1, sample_rate * channels * (bits // 8))
    state.voice_samples[str(request.mock_user["id"])] = {
        "uploaded_at": state.iso_now(),
        "audio_config": {
            "sample_rate": sample_rate,
            "channels": channels,
            "bits_per_sample": bits,
            "encoding": audio_config.get("encoding", "linear16"),
        },
        "seconds": round(len(pcm) / bytes_per_second, 3),
    }
    return jsonify({})  # [H] body unused by the client; minimal plausible shape


# --- continuous shift audio (VAD pipeline) --------------------------------------

@bp.post("/api/canvasser_voice/receive")
@require_auth
def receive():
    # [R] exact part set from AudioManager.java:960 (single-line builder).
    audio = request.files.get("audio")
    work_shift_id = request.form.get("work_shift_id")
    if audio is None or not work_shift_id:
        # Non-2xx -> native keeps segments, JS re-queues (retryable). 400 here
        # only for a structurally broken request, which the stock client never
        # sends.
        return detail(400, "audio and work_shift_id are required")
    wav = audio.read()
    segments_raw = request.form.get("segments")
    _record_upload(
        "receive", request.mock_user["id"],
        work_shift_id=work_shift_id,
        device_id=request.form.get("device_id"),
        vad_model_name=request.form.get("vad_model_name"),
        sample_rate=request.form.get("sample_rate"),
        wallclock_start=request.form.get("wallclock_start"),
        wallclock_end=request.form.get("wallclock_end"),
        span_upload_id=request.form.get("span_upload_id"),
        segments=_parse_json_string(segments_raw),
        filename=audio.filename,
        audio_bytes=len(wav),
    )
    return jsonify({})  # [H] body not parsed (AudioManager.java:987-1002)


@bp.post("/api/canvasser_voice/cached_receive")
@require_auth
def cached_receive():
    # [R] AudioManager.java:635-667 — repeated per-chunk parts, device_id and
    # the doubly-nested segments string once per request.
    files = request.files.getlist("audio")
    work_shift_ids = request.form.getlist("work_shift_id")
    if not files or len(work_shift_ids) != len(files):
        return detail(400, "one audio part and one work_shift_id per cached chunk")
    starts = request.form.getlist("wallclock_start")
    ends = request.form.getlist("wallclock_end")
    vad_names = request.form.getlist("vad_model_name")
    span_ids = request.form.getlist("span_upload_id")  # absent when no row has one
    segments_outer = _parse_json_string(request.form.get("segments"))
    succeeded = []
    for i, f in enumerate(files):
        _record_upload(
            "cached_receive", request.mock_user["id"],
            work_shift_id=work_shift_ids[i],
            device_id=request.form.get("device_id"),
            vad_model_name=vad_names[i] if i < len(vad_names) else None,
            wallclock_start=starts[i] if i < len(starts) else None,
            wallclock_end=ends[i] if i < len(ends) else None,
            span_upload_id=span_ids[i] if i < len(span_ids) else None,
            segments=_parse_json_string(segments_outer[i])
                     if isinstance(segments_outer, list) and i < len(segments_outer)
                     else None,
            filename=f.filename,
            audio_bytes=len(f.read()),
        )
        succeeded.append(f.filename)
    # [R] consumed field (AudioManager.java:695-719). [H] the mock accepts
    # every well-formed chunk; a real server would omit rejected files.
    return jsonify({"succeeded_filenames": succeeded})


# --- wake-word pipeline ----------------------------------------------------------

@bp.post("/api/canvasser_voice/wake_word_event")
@require_auth
def wake_word_event():
    body = request.get_json(silent=True) or {}
    event_id = body.get("id")
    if not isinstance(body, dict) or not event_id \
            or not body.get("work_shift_id") \
            or body.get("timestamp_ms") is None:
        # Client drops the outbox row permanently on 400 — reserve it for
        # genuinely malformed payloads (useUploader.ts:87-100).
        return detail(400, "id, work_shift_id and timestamp_ms are required")
    state.wake_word_events.append({
        "id": event_id,
        "user_id": str(request.mock_user["id"]),
        "work_shift_id": body.get("work_shift_id"),
        "device_id": body.get("device_id"),
        "timestamp_ms": body.get("timestamp_ms"),
        "gps_point": body.get("gps_point"),  # null when no fresh fix ([R])
        "received_at": state.iso_now(),
    })
    return jsonify({})  # [R] nothing consumed (shift-lifecycle.md §8)


def _event_exists(event_id):
    return any(e["id"] == event_id for e in state.wake_word_events)


@bp.post("/api/canvasser_voice/wake_word_audio")
@require_auth
def wake_word_audio():
    # [R] part set from AudioManager.java:1029.
    audio = request.files.get("audio")
    event_id = request.form.get("event_id")
    if audio is None or not event_id:
        return detail(400, "audio and event_id are required")
    if not _event_exists(event_id):
        # [R] event row not yet landed -> 404; native caches the clip and the
        # uploader retries (useWakeWordHandler.ts:33-34).
        return detail(404, "Wake word event not found")
    _record_upload(
        "wake_word_audio", request.mock_user["id"],
        event_id=event_id,
        work_shift_id=request.form.get("work_shift_id"),
        device_id=request.form.get("device_id"),
        clip_start_ms=request.form.get("clip_start_ms"),
        clip_end_ms=request.form.get("clip_end_ms"),
        filename=audio.filename,
        audio_bytes=len(audio.read()),
    )
    return jsonify({})  # [R] success body ignored (AudioManager.java:1064-1069)


@bp.post("/api/canvasser_voice/wake_word_audio_cached")
@require_auth
def wake_word_audio_cached():
    # [R] AudioManager.java:764-789 — N audio parts, device_id, clips JSON.
    files = request.files.getlist("audio")
    clips = _parse_json_string(request.form.get("clips"))
    if not files or not isinstance(clips, list) or len(clips) != len(files):
        return detail(400, "one audio part per clips[] entry is required")
    succeeded = []
    for i, f in enumerate(files):
        clip = clips[i] if isinstance(clips[i], dict) else {}
        event_id = clip.get("event_id")
        if not event_id or not _event_exists(event_id):
            # [H] per-clip failure mirrors the single-clip 404: the index is
            # omitted so the client keeps the row cached (its 4-day TTL is the
            # final cleanup, uploadWakeWordClipNative.ts:15-25).
            continue
        _record_upload(
            "wake_word_audio_cached", request.mock_user["id"],
            event_id=event_id,
            work_shift_id=clip.get("work_shift_id"),
            device_id=request.form.get("device_id"),
            clip_start_ms=clip.get("clip_start_ms"),
            clip_end_ms=clip.get("clip_end_ms"),
            filename=f.filename,
            audio_bytes=len(f.read()),
        )
        succeeded.append(i)
    # [R] consumed field (AudioManager.java:813-839).
    return jsonify({"succeeded_indices": succeeded})


# --- signatory voice verification -------------------------------------------------

def _verification_view(v):
    # Consumed fields: id, status, extracted_signatories
    # (useVoiceVerification.ts:95-101). Rest mirrors VoiceVerificationState
    # naming (constants/conversations/voiceVerificationStateDescriptions.ts).
    return {
        "id": v["id"],
        "project_id": v["project_id"],
        "status": v["status"],
        "extracted_signatories": v["extracted_signatories"],
        "created_at": v["created_at"],
    }


@bp.put("/api/verifications/voice/")
@require_auth
def create_voice_verification():
    body = request.get_json(silent=True) or {}
    project_id = body.get("project_id")
    if not project_id:
        return detail(400, "project_id is required")
    if project_id not in state.PROJECTS:
        return detail(404, "Project not found")
    conv_id = str(uuid.uuid4())  # [H] server-generated conversation id format
    state.verifications[conv_id] = {
        "id": conv_id,
        "user_id": str(request.mock_user["id"]),
        "project_id": project_id,
        "status": "new",  # [R] initial state the client streams from
        "extracted_signatories": [],
        "submitted_signatories": None,
        "created_at": state.iso_now(),
    }
    # [R] only response.id is consumed (stores/verification/voice.ts:23).
    return jsonify(_verification_view(state.verifications[conv_id]))


@bp.get("/api/verifications/voice/<conversation_id>")
@require_auth
def get_voice_verification(conversation_id):
    v = state.verifications.get(conversation_id)
    if v is None or v["user_id"] != str(request.mock_user["id"]):
        return detail(404, "Voice verification not found")
    return jsonify(_verification_view(v))


@bp.post("/api/verifications/voice/<conversation_id>/submit")
@require_auth
def submit_voice_verification(conversation_id):
    v = state.verifications.get(conversation_id)
    if v is None or v["user_id"] != str(request.mock_user["id"]):
        return detail(404, "Voice verification not found")
    body = request.get_json(silent=True) or {}
    signatories = body.get("signatories")
    if not isinstance(signatories, list) or not signatories:
        return detail(400, "signatories must be a non-empty array")
    for s in signatories:
        if not isinstance(s, dict) or not s.get("first_name") \
                or not s.get("last_name"):
            return detail(400, "each signatory requires first_name and last_name")
    if v["status"] in ("ready_for_processing", "processing", "completed",
                       "canceled", "failed"):
        return detail(400, "Voice verification is not open for submission")
    # [H] without the WS bridge no extraction runs, so submissions are accepted
    # from any open state (new/in_progress/ready_for_submit) and the
    # conversation moves to the post-submit state named in
    # voiceVerificationStateDescriptions.ts:13.
    v["submitted_signatories"] = signatories
    v["status"] = "ready_for_processing"
    return jsonify(_verification_view(v))  # [R] body unused by the client
