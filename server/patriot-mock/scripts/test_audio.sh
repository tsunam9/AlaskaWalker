#!/usr/bin/env bash
# Exercises mock/audio.py against a mock running on PM_PORT (default 8899).
# Start the server first:  PM_PORT=8899 python3 patriot_mock.py
set -u
PORT="${PM_PORT:-8899}"
BASE="http://127.0.0.1:$PORT"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
PASS=0; FAIL=0

check() { # check <label> <expected> <actual>
  if [ "$2" = "$3" ]; then PASS=$((PASS+1)); echo "ok   $1 ($3)";
  else FAIL=$((FAIL+1)); echo "FAIL $1 — expected $2, got $3"; fi
}

# --- fixtures -------------------------------------------------------------------
python3 - <<PYEOF
import base64, json, struct, wave, math, os
tmp = "$TMP"
# 1 s of 48 kHz Int16-LE PCM for the voice sample
pcm = b"".join(struct.pack("<h", int(8000 * math.sin(2 * math.pi * 440 * i / 48000)))
               for i in range(48000))
open(os.path.join(tmp, "pcm.b64"), "w").write(base64.b64encode(pcm).decode())
# tiny valid WAVs (16 kHz mono 16-bit) for multipart tests
for name in ("chunk.wav", "clip0.wav", "clip1.wav"):
    with wave.open(os.path.join(tmp, name), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
        w.writeframes(b"".join(struct.pack("<h", int(5000 * math.sin(2 * math.pi * 440 * i / 16000)))
                               for i in range(4000)))
PYEOF

# --- auth ------------------------------------------------------------------------
curl -s -o "$TMP/token.json" -w "%{http_code}" -X POST "$BASE/api/auth/token" \
  -F username=canvasser@alaska.test -F password=alaska-test-1 > "$TMP/code"
check "POST /api/auth/token" 200 "$(cat "$TMP/code")"
TOKEN=$(python3 -c "import json;print(json.load(open('$TMP/token.json'))['access_token'])")
AUTH="Authorization: Bearer $TOKEN"

CODE=$(curl -s -o "$TMP/p1.json" -w "%{http_code}" "$BASE/api/auth/profile" -H "$AUTH")
check "GET profile (banner armed)" 200 "$CODE"
BANNER=$(python3 -c "import json;print(json.load(open('$TMP/p1.json'))['alerts']['banner_alert'])")
check "banner before sample" "record_voice_sample" "$BANNER"

# --- voice sample -----------------------------------------------------------------
B64=$(cat "$TMP/pcm.b64")
CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE/api/account/voice_sample/" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d "{\"audio_data\":\"$B64\",\"audio_config\":{\"sample_rate\":48000,\"channels\":1,\"bits_per_sample\":16,\"encoding\":\"linear16\"}}")
check "POST voice_sample" 200 "$CODE"

CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE/api/account/voice_sample/" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"audio_data":"!!!not-base64!!!","audio_config":{}}')
check "POST voice_sample bad base64" 400 "$CODE"

CODE=$(curl -s -o "$TMP/p2.json" -w "%{http_code}" "$BASE/api/auth/profile" -H "$AUTH")
check "GET profile (banner cleared)" 200 "$CODE"
BANNER=$(python3 -c "import json;print(json.load(open('$TMP/p2.json'))['alerts']['banner_alert'])")
check "banner after sample" "None" "$BANNER"

# --- canvasser_voice/receive -------------------------------------------------------
SEGMENTS='[{"start_ms":1000,"end_ms":4000,"gps_point":{"timestamp":1000,"latitude":61.2,"longitude":-149.9,"accuracy":5.0,"altitude":30.0,"altitude_accuracy":3.0}}]'
CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE/api/canvasser_voice/receive" \
  -H "$AUTH" \
  -F "audio=@$TMP/chunk.wav;type=audio/wav;filename=voice_chunk.wav" \
  -F "work_shift_id=shift-uuid-1" -F "vad_model_name=silero" -F "device_id=device-uuid-1" \
  -F "sample_rate=16000" -F "wallclock_start=2026-09-20T10:00:00.000Z" \
  -F "wallclock_end=2026-09-20T10:02:00.000Z" -F "segments=$SEGMENTS" \
  -F "span_upload_id=span-uuid-1")
check "POST receive" 200 "$CODE"

CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE/api/canvasser_voice/receive" \
  -H "$AUTH" -F "work_shift_id=shift-uuid-1")
check "POST receive missing audio" 400 "$CODE"

# --- canvasser_voice/cached_receive -------------------------------------------------
# segments: JSON array whose elements are themselves JSON strings (AudioManager.java:636)
CSEGMENTS='["[{\"start_ms\":1000,\"end_ms\":4000,\"gps_point\":null}]","[{\"start_ms\":5000,\"end_ms\":8000,\"gps_point\":null}]"]'
CODE=$(curl -s -o "$TMP/cr.json" -w "%{http_code}" -X POST "$BASE/api/canvasser_voice/cached_receive" \
  -H "$AUTH" \
  -F "audio=@$TMP/chunk.wav;type=audio/wav;filename=voice_chunk_0.wav" \
  -F "work_shift_id=shift-uuid-1" -F "wallclock_start=2026-09-20T09:00:00.000Z" \
  -F "wallclock_end=2026-09-20T09:02:00.000Z" -F "vad_model_name=silero" \
  -F "span_upload_id=span-uuid-0" \
  -F "audio=@$TMP/chunk.wav;type=audio/wav;filename=voice_chunk_1.wav" \
  -F "work_shift_id=shift-uuid-1" -F "wallclock_start=2026-09-20T09:02:00.000Z" \
  -F "wallclock_end=2026-09-20T09:04:00.000Z" -F "vad_model_name=silero" \
  -F "span_upload_id=span-uuid-1" \
  -F "device_id=device-uuid-1" -F "segments=$CSEGMENTS")
check "POST cached_receive" 200 "$CODE"
SUCCEEDED=$(python3 -c "import json;print(sorted(json.load(open('$TMP/cr.json'))['succeeded_filenames']))")
check "cached_receive succeeded_filenames" "['voice_chunk_0.wav', 'voice_chunk_1.wav']" "$SUCCEEDED"

# --- wake-word event + clips ---------------------------------------------------------
CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE/api/canvasser_voice/wake_word_event" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"id":"event-uuid-1","work_shift_id":"shift-uuid-1","device_id":"device-uuid-1","timestamp_ms":1758340000000,"gps_point":{"latitude":61.2,"longitude":-149.9,"accuracy":5.0,"altitude":30.0,"altitude_accuracy":3.0,"timestamp":"2026-09-20T10:06:40Z"}}')
check "POST wake_word_event" 200 "$CODE"

CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE/api/canvasser_voice/wake_word_event" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"work_shift_id":"shift-uuid-1"}')
check "POST wake_word_event malformed" 400 "$CODE"

CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE/api/canvasser_voice/wake_word_audio" \
  -H "$AUTH" \
  -F "audio=@$TMP/clip0.wav;type=audio/wav;filename=wake_word_clip.wav" \
  -F "event_id=event-uuid-1" -F "work_shift_id=shift-uuid-1" -F "device_id=device-uuid-1" \
  -F "clip_start_ms=1758339997000" -F "clip_end_ms=1758340001000")
check "POST wake_word_audio (known event)" 200 "$CODE"

CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE/api/canvasser_voice/wake_word_audio" \
  -H "$AUTH" \
  -F "audio=@$TMP/clip0.wav;type=audio/wav;filename=wake_word_clip.wav" \
  -F "event_id=event-uuid-unknown" -F "work_shift_id=shift-uuid-1" -F "device_id=device-uuid-1" \
  -F "clip_start_ms=1" -F "clip_end_ms=2")
check "POST wake_word_audio (unknown event)" 404 "$CODE"

CLIPS='[{"event_id":"event-uuid-1","work_shift_id":"shift-uuid-1","clip_start_ms":100,"clip_end_ms":4100},{"event_id":"event-uuid-unknown","work_shift_id":"shift-uuid-1","clip_start_ms":200,"clip_end_ms":4200}]'
CODE=$(curl -s -o "$TMP/wwc.json" -w "%{http_code}" -X POST "$BASE/api/canvasser_voice/wake_word_audio_cached" \
  -H "$AUTH" \
  -F "audio=@$TMP/clip0.wav;type=audio/wav;filename=wake_word_clip_0.wav" \
  -F "audio=@$TMP/clip1.wav;type=audio/wav;filename=wake_word_clip_1.wav" \
  -F "device_id=device-uuid-1" -F "clips=$CLIPS")
check "POST wake_word_audio_cached" 200 "$CODE"
IDX=$(python3 -c "import json;print(json.load(open('$TMP/wwc.json'))['succeeded_indices'])")
check "wake_word_audio_cached succeeded_indices (only known event)" "[0]" "$IDX"

# --- signatory voice verification ----------------------------------------------------
PROJECT_ID=$(python3 -c "import json;print(json.load(open('$(dirname "$0")/../projects.json'))['projects'][1]['id'])")
CODE=$(curl -s -o "$TMP/vv.json" -w "%{http_code}" -X PUT "$BASE/api/verifications/voice/" \
  -H "$AUTH" -H "Content-Type: application/json" -d "{\"project_id\":\"$PROJECT_ID\"}")
check "PUT verifications/voice" 200 "$CODE"
CONV_ID=$(python3 -c "import json;print(json.load(open('$TMP/vv.json'))['id'])")

CODE=$(curl -s -o /dev/null -w "%{http_code}" -X PUT "$BASE/api/verifications/voice/" \
  -H "$AUTH" -H "Content-Type: application/json" -d '{"project_id":"no-such-project"}')
check "PUT verifications/voice unknown project" 404 "$CODE"

CODE=$(curl -s -o "$TMP/vvd.json" -w "%{http_code}" "$BASE/api/verifications/voice/$CONV_ID" -H "$AUTH")
check "GET verifications/voice/{id}" 200 "$CODE"
STATUS=$(python3 -c "import json;print(json.load(open('$TMP/vvd.json'))['status'])")
check "verification status after create" "new" "$STATUS"

CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE/api/verifications/voice/$CONV_ID/submit" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"signatories":[{"first_name":"Jane","last_name":"Doe","middle_name":null,"state":"AK","city":"Anchorage","county":null,"address_1":"1 Main St","address_2":null,"zip_code":"99501","signed_date":"2026-09-20"}]}')
check "POST submit" 200 "$CODE"

CODE=$(curl -s -o "$TMP/vvd2.json" -w "%{http_code}" "$BASE/api/verifications/voice/$CONV_ID" -H "$AUTH")
STATUS=$(python3 -c "import json;print(json.load(open('$TMP/vvd2.json'))['status'])")
check "verification status after submit" "ready_for_processing" "$STATUS"

CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE/api/verifications/voice/$CONV_ID/submit" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"signatories":[{"first_name":"A","last_name":"B"}]}')
check "POST submit twice" 400 "$CODE"

CODE=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/api/verifications/voice/no-such-conv" -H "$AUTH")
check "GET unknown conversation" 404 "$CODE"

# --- auth guard ----------------------------------------------------------------------
CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE/api/canvasser_voice/receive")
check "receive without bearer" 401 "$CODE"

# --- mock state sanity -----------------------------------------------------------------
COUNTS=$(curl -s "$BASE/__mock/state" | python3 -c "import json,sys;d=json.load(sys.stdin);print(d['audio_upload_count'])")
echo "audio_upload_count=$COUNTS"

echo
echo "PASS=$PASS FAIL=$FAIL"
[ "$FAIL" -eq 0 ]
