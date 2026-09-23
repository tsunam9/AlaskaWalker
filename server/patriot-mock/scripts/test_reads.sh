#!/usr/bin/env bash
# Exercises mock/reads.py against a mock running on PM_PORT (default 8899).
# Start the server first:  PM_PORT=8899 python3 patriot_mock.py
set -u
PORT="${PM_PORT:-8899}"
BASE="http://127.0.0.1:$PORT"
PASS=0; FAIL=0

check() { # check <label> <expected> <actual>
  if [ "$2" = "$3" ]; then PASS=$((PASS+1)); echo "ok   $1 ($3)";
  else FAIL=$((FAIL+1)); echo "FAIL $1 — expected $2, got $3"; fi
}

get()  { curl -s -o /dev/null -w "%{http_code}" -H "$AUTH" "$BASE$1"; }
getj() { curl -s -H "$AUTH" "$BASE$1"; }
post() { curl -s -o /dev/null -w "%{http_code}" -X POST -H "$AUTH" -H 'Content-Type: application/json' ${3:+-d "$3"} "$BASE$1"; }
put()  { curl -s -o /dev/null -w "%{http_code}" -X PUT  -H "$AUTH" -H 'Content-Type: application/json' ${2:+-d "$2"} "$BASE$1"; }
patch(){ curl -s -o /dev/null -w "%{http_code}" -X PATCH -H "$AUTH" -H 'Content-Type: application/json' ${2:+-d "$2"} "$BASE$1"; }

PROJ="3f8a2c1e-7b4d-4e2a-9c5f-1a2b3c4d5e6f"
NOW="$(python3 -c "import datetime;print(datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'))")"

# --- auth ---------------------------------------------------------------------
curl -s -o /tmp/rt_token.json -X POST "$BASE/api/auth/token" \
  -F username=canvasser@alaska.test -F password=alaska-test-1
AT=$(python3 -c "import json;print(json.load(open('/tmp/rt_token.json'))['access_token'])")
AUTH="Authorization: Bearer $AT"
check "login" 200 "$(curl -s -o /dev/null -w '%{http_code}' -X POST "$BASE/api/auth/token" -F username=canvasser@alaska.test -F password=alaska-test-1)"

# --- account & profile ----------------------------------------------------------
check "GET account/" 200 "$(get /api/account/)"
check "voice_sample_recorded present" "True" "$(getj /api/account/ | python3 -c 'import json,sys;print(isinstance(json.load(sys.stdin)["voice_sample_recorded"], bool))')"
check "PATCH account/settings/edit" 200 "$(patch /api/account/settings/edit '{"time_zone":"America/Anchorage"}')"
check "PUT password/edit (wrong old)" 400 "$(put /api/account/password/edit '{"old_password":"nope","new_password":"x"}')"
check "PUT password/edit" 200 "$(put /api/account/password/edit '{"old_password":"alaska-test-1","new_password":"alaska-test-1"}')"
check "POST password/reset (unauth)" 200 "$(curl -s -o /dev/null -w '%{http_code}' -X POST -H 'Content-Type: application/json' -d '{"email":"canvasser@alaska.test"}' "$BASE/api/account/password/reset")"
check "POST password/set (bad token)" 400 "$(curl -s -o /dev/null -w '%{http_code}' -X POST -H 'Content-Type: application/json' -d '{"token":"x","password":"y"}' "$BASE/api/account/password/set")"
check "PATCH account/1001/delete" 200 "$(patch /api/account/1001/delete '{}')"
check "POST profile/" 200 "$(post /api/profile/ '' '{"first_name":"Test"}')"
check "POST profile/generate-bio" 200 "$(post /api/profile/generate-bio '' '{}')"
check "GET profile/1001" 200 "$(get /api/profile/1001)"
check "PUT profile/1001" 200 "$(put /api/profile/1001 '{"last_name":"Canvasser"}')"
check "GET shared_link (none)" 200 "$(get /api/profile/1001/shared_link)"
CODE=$(curl -s -X POST -H "$AUTH" "$BASE/api/profile/shared/1001/generate" | python3 -c 'import json,sys;print(json.load(sys.stdin)["shareable_code"])')
check "POST shared generate" "True" "$([ -n "$CODE" ] && echo True)"
check "GET public shared profile" 200 "$(curl -s -o /dev/null -w '%{http_code}' "$BASE/api/profile/shared/$CODE")"
check "PUT shared disable" 200 "$(put /api/profile/shared/1001/disable)"
check "GET public shared after disable" 404 "$(curl -s -o /dev/null -w '%{http_code}' "$BASE/api/profile/shared/$CODE")"

# --- selector & projects ---------------------------------------------------------
check "selector/project" 200 "$(get '/api/selector/project?assigned_user_ids[]=1001&statuses[]=active')"
check "selector/project other user empty" "0" "$(getj '/api/selector/project?assigned_user_ids[]=9999' | python3 -c 'import json,sys;print(len(json.load(sys.stdin)["items"]))')"
check "GET projects/" 200 "$(get /api/projects/)"
check "GET projects/{id}" 200 "$(get /api/projects/$PROJ)"
check "project carries audio config" "no_recording" "$(getj /api/projects/$PROJ | python3 -c 'import json,sys;print(json.load(sys.stdin)["audio_recording_config"]["permission"])')"
check "GET projects/{id}/short_info" 200 "$(get /api/projects/$PROJ/short_info)"
check "GET projects/{id}/voter_database" 200 "$(get /api/projects/$PROJ/voter_database)"
check "GET projects/unknown 404" 404 "$(get /api/projects/nope)"

# --- shift lifecycle (feeds work_shift + earnings reads) --------------------------
post /api/mobile/device/update_info '' '{"device_id":"dev-reads-1","is_root":false,"platform":"android"}' >/dev/null
SID=$(curl -s -X POST -H "$AUTH" -H 'Content-Type: application/json' "$BASE/api/mobile/work_shift/generate" \
  -d "{\"device_id\":\"dev-reads-1\",\"project_id\":\"$PROJ\",\"start_time\":\"$NOW\",\"state_payload\":{},\"time_zone\":\"America/Anchorage\"}" \
  | python3 -c 'import json,sys;print(json.load(sys.stdin)["work_shift_id"])')
check "generate" "True" "$([ -n "$SID" ] && echo True)"
check "earning_progress (active)" 200 "$(get /api/work_shift/$SID/earning_progress)"
check "work_shift list" 200 "$(get '/api/work_shift/?page=1&size=5&sort_by=start_time&sort_type=desc&timezone=America/Anchorage')"
post /api/mobile/work_shift/pause '' "{\"work_shift_id\":\"$SID\",\"button_pressed_time\":\"$NOW\"}" >/dev/null
post /api/mobile/work_shift/resume '' "{\"work_shift_id\":\"$SID\",\"button_pressed_time\":\"$NOW\"}" >/dev/null
check "conversations (empty)" 200 "$(get /api/work_shift/$SID/conversations)"
check "work_shift short_info" 200 "$(get /api/work_shift/$SID/short_info)"
check "work_shift details" 200 "$(get /api/work_shift/$SID)"
END="$(python3 -c "import datetime;print((datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(hours=2)).strftime('%Y-%m-%dT%H:%M:%SZ'))")"
check "finalize_v2" 200 "$(curl -s -o /dev/null -w '%{http_code}' -X POST -H "$AUTH" -H 'Content-Type: application/json' -d "[{\"work_shift_id\":\"$SID\",\"end_time\":\"$END\",\"data_complete\":true}]" "$BASE/api/mobile/work_shift/finalize_v2")"
check "earning_progress (finalized -> 404)" 404 "$(get /api/work_shift/$SID/earning_progress)"

# --- earnings ----------------------------------------------------------------------
check "earnings list" 200 "$(get /api/earnings/)"
EID=$(getj /api/earnings/ | python3 -c 'import json,sys;print(json.load(sys.stdin)["items"][0]["id"])')
check "earning details" 200 "$(get /api/earnings/$EID)"
check "earning short_info" 200 "$(get /api/earnings/$EID/short_info)"
check "earning unknown 404" 404 "$(get /api/earnings/999999)"
check "balance pending>0" "True" "$(getj /api/earnings/balance/ | python3 -c 'import json,sys;print(json.load(sys.stdin)["pending"]>0)')"
check "totals-by-rate-type" 200 "$(get /api/earnings/totals-by-rate-type/)"
check "withdraw before approval" 400 "$(post /api/earnings/withdraw)"
curl -s -o /dev/null -X POST "$BASE/__mock/earnings/$EID/approve"
check "balance ready>0 after approve" "True" "$(getj /api/earnings/balance/ | python3 -c 'import json,sys;print(json.load(sys.stdin)["ready_for_payment"]>0)')"
check "withdraw" 200 "$(post /api/earnings/withdraw)"
check "balance zeroed after withdraw" "True" "$(getj /api/earnings/balance/ | python3 -c 'import json,sys;d=json.load(sys.stdin);print(d["ready_for_payment"]==0)')"
check "transactions list" 200 "$(get /api/earnings/transactions/)"
TID=$(getj /api/earnings/transactions/ | python3 -c 'import json,sys;print(json.load(sys.stdin)["items"][0]["id"])')
check "transaction details" 200 "$(get /api/earnings/transactions/$TID)"
check "transaction earnings" 200 "$(get /api/earnings/transactions/$TID/earnings)"
check "PATCH earnings/account/1001" 200 "$(patch /api/earnings/account/1001 '{}')"
check "GET earnings/account/" 200 "$(get /api/earnings/account/)"

# --- notifications ------------------------------------------------------------------
check "unread-count" 200 "$(get /api/notifications/unread-count)"
NID=$(getj '/api/notifications/list?page=1&size=10&sort_type=desc' | python3 -c 'import json,sys;print(json.load(sys.stdin)["notifications"][0]["id"])')
check "notifications list" 200 "$(get '/api/notifications/list?page=1&size=10&sort_type=desc')"
check "mark_as_read" 200 "$(post /api/notifications/mark_as_read/$NID)"
check "mark_all_as_read" 200 "$(post /api/notifications/mark_all_as_read)"
check "unread-count zeroed" "0" "$(getj /api/notifications/unread-count | python3 -c 'import json,sys;print(json.load(sys.stdin)["count"])')"

# --- applications ---------------------------------------------------------------------
check "applications upcoming" 200 "$(get '/api/applications/?page=1&size=10&sort_by=start_date&sort_type=desc')"
check "applications create" 200 "$(put /api/applications/create "{\"project_id\":\"$PROJ\"}")"
check "applications create twice" 400 "$(put /api/applications/create "{\"project_id\":\"$PROJ\"}")"
check "applications applied" 200 "$(get /api/applications/applied)"
check "application details" 200 "$(get /api/applications/$PROJ)"
check "canvasser_application general_info" 200 "$(post /api/canvasser_application/general_info '' '{"phone":"+19075550100"}')"
check "canvasser_application documents (empty)" 400 "$(post /api/canvasser_application/documents '' '{"id_photo_urls":[]}')"

# --- misc ------------------------------------------------------------------------------
check "contracts v2 list" 200 "$(get /api/contracts/v2/)"
check "contract v2 unknown 404" 404 "$(get /api/contracts/v2/123)"
check "contract short_info 404" 404 "$(get /api/contracts/123/short_info)"
check "users short_info" 200 "$(get /api/users/1001/short_info)"
check "subcontractor short_info 404" 404 "$(get /api/subcontractor_company/1/short_info)"
check "coaching short_info 404" 404 "$(get /api/coaching_feedback/1/short_info)"
check "docs list" 200 "$(get /api/docs/)"
check "docs page 404" 404 "$(get /api/docs/shifts)"
check "wake_word_events list" 200 "$(get /api/wake_word_events/)"
check "wake_word_event 404" 404 "$(get /api/wake_word_events/nope)"
check "verifications voter" 200 "$(put /api/verifications/voter/ "{\"project_id\":\"$PROJ\",\"infos\":[{\"first_name\":\"A\",\"last_name\":\"B\"}]}")"
check "export job" 200 "$(get /api/export/job-1)"
check "upload" 200 "$(curl -s -o /dev/null -w '%{http_code}' -X POST -H "$AUTH" -F file=@/etc/hostname "$BASE/api/upload/")"
check "upload no file" 400 "$(curl -s -o /dev/null -w '%{http_code}' -X POST -H "$AUTH" "$BASE/api/upload/")"
check "supabase unread chat count" "0" "$(curl -s -X POST -H "$AUTH" -H 'Content-Type: application/json' -H 'apikey: sb_publishable_xeO1bd3QP8IbXsKvFBW27g_OLjQU62U' "$BASE/rest/v1/rpc/get_unread_chat_count")"
check "supabase chats cursor" "[]" "$(curl -s -X POST -H "$AUTH" -H 'Content-Type: application/json' "$BASE/rest/v1/rpc/get_user_chats_cursor")"

echo
echo "PASS=$PASS FAIL=$FAIL"
[ "$FAIL" = 0 ]
