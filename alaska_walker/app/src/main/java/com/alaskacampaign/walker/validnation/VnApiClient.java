package com.alaskacampaign.walker.validnation;

import com.alaskacampaign.walker.core.Http;

import org.json.JSONException;
import org.json.JSONObject;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.Map;

/**
 * ValidNation auth API client. Wire shapes reproduce the stock app exactly
 * (patriot_grassroots/audit/auth-session.md, verified against the recovered
 * frontend source 2026-09-20):
 *
 *  - login:    POST /api/auth/token, multipart/form-data fields
 *              {username, password}, no Authorization header
 *              (pages/login.vue:98-100, useAuth.ts:67-114)
 *  - refresh:  POST /api/auth/refresh, JSON {refresh_token},
 *              Content-Type: application/json, NO Authorization header
 *              (useAuth.ts:228-240)
 *  - profile:  GET /api/auth/profile, Authorization: Bearer <jwt>
 *              (useAuth.ts:178-226)
 *  - logout:   POST /api/auth/logout, Bearer + JSON {refresh_token};
 *              tokens cleared locally BEFORE the call (useAuth.ts:137-162)
 *
 * 401 policy mirrors stock: refresh once, replay once, then clear the
 * session (httpInterceptors.ts:110-132). Success is strictly HTTP 200
 * (utils/authRequestHandlers.ts:22-27). Error messages come from the
 * body's "detail" field, then "message" (same file, line 25).
 */
public final class VnApiClient {

    /** Thrown when the session is unrecoverable (401 after refresh+replay). */
    public static final class SessionExpired extends Exception {
        SessionExpired(String msg) {
            super(msg);
        }
    }

    public static final class ApiException extends Exception {
        public final int status;

        ApiException(int status, String detail) {
            super(detail);
            this.status = status;
        }
    }

    /** 30 s pre-request expiry buffer (httpInterceptors.ts:34). */
    private static final long PRE_REQUEST_EXPIRY_BUFFER_MS = 30_000;

    private final String apiBase;
    private final VnSessionStore store;

    public VnApiClient(String apiBase, VnSessionStore store) {
        this.apiBase = apiBase.replaceAll("/+$", "");
        this.store = store;
    }

    public JSONObject login(String email, String password) throws IOException, ApiException {
        String boundary = "----VnFormBoundary" + Long.toHexString(System.nanoTime());
        String body = "--" + boundary + "\r\n"
                + "Content-Disposition: form-data; name=\"username\"\r\n\r\n" + email + "\r\n"
                + "--" + boundary + "\r\n"
                + "Content-Disposition: form-data; name=\"password\"\r\n\r\n" + password + "\r\n"
                + "--" + boundary + "--\r\n";
        Map<String, String> headers = new HashMap<>();
        headers.put("Content-Type", "multipart/form-data; boundary=" + boundary);
        Http.Response r = Http.request("POST", apiBase + "/api/auth/token", headers,
                body.getBytes(StandardCharsets.UTF_8));
        JSONObject json = parse(r);
        store.setTokens(json.optString("access_token"), json.optString("refresh_token"));
        return json;
    }

    /** Single-flight refresh (synchronized; stock uses refreshSingleFlight.ts).
     *  Returns false when the refresh token is rejected (401). */
    public synchronized boolean refresh() throws IOException, ApiException {
        String rt = store.getRefreshToken();
        if (rt == null) {
            return false;
        }
        Map<String, String> headers = new HashMap<>();
        headers.put("Content-Type", "application/json");
        // No Authorization header on this endpoint (sdk.gen.ts:420-433).
        String body = "{\"refresh_token\": " + JSONObject.quote(rt) + "}";
        Http.Response r = Http.request("POST", apiBase + "/api/auth/refresh", headers,
                body.getBytes(StandardCharsets.UTF_8));
        if (r.status == 401) {
            return false;
        }
        JSONObject json = parse(r);
        // Only access_token is consumed; the refresh token is NOT rotated
        // client-side (useAuth.ts:241-246).
        store.setAccessToken(json.optString("access_token"));
        return true;
    }

    public JSONObject getProfile() throws IOException, ApiException, SessionExpired {
        return authedGet("/api/auth/profile");
    }

    /** GET with the stock 401 policy: refresh once, replay once, then clear. */
    public JSONObject authedGet(String path) throws IOException, ApiException, SessionExpired {
        ensureFreshAccessToken();
        Http.Response r = doGet(path);
        if (r.status == 401) {
            if (!refresh()) {
                store.clear();
                throw new SessionExpired("refresh token rejected");
            }
            r = doGet(path);
            if (r.status == 401) {
                store.clear();
                throw new SessionExpired("session expired");
            }
        }
        return parse(r);
    }

    /** Authed JSON request with the stock 401 policy: pre-request expiry
     *  check, then refresh once + replay once, then clear the session
     *  (httpInterceptors.ts:110-132). Returns the parsed body ({} when the
     *  endpoint returns nothing the client consumes). */
    public JSONObject authedRequest(String method, String path, JSONObject body)
            throws IOException, ApiException, SessionExpired {
        ensureFreshAccessToken();
        Http.Response r = doJson(method, path, body);
        if (r.status == 401) {
            if (!refresh()) {
                store.clear();
                throw new SessionExpired("refresh token rejected");
            }
            r = doJson(method, path, body);
            if (r.status == 401) {
                store.clear();
                throw new SessionExpired("session expired");
            }
        }
        return parse(r);
    }

    /** Same 401 policy for array bodies (finalize_v2 takes a JSON array). */
    public JSONObject authedRequest(String method, String path, org.json.JSONArray body)
            throws IOException, ApiException, SessionExpired {
        ensureFreshAccessToken();
        Http.Response r = doJson(method, path, body == null ? null : body.toString());
        if (r.status == 401) {
            if (!refresh()) {
                store.clear();
                throw new SessionExpired("refresh token rejected");
            }
            r = doJson(method, path, body == null ? null : body.toString());
            if (r.status == 401) {
                store.clear();
                throw new SessionExpired("session expired");
            }
        }
        return parse(r);
    }

    private Http.Response doJson(String method, String path, Object body)
            throws IOException {
        Map<String, String> headers = new HashMap<>();
        String access = store.getAccessToken();
        if (access != null) {
            headers.put("Authorization", "Bearer " + access);
        }
        byte[] data = null;
        if (body != null) {
            headers.put("Content-Type", "application/json");
            data = body.toString().getBytes(StandardCharsets.UTF_8);
        }
        return Http.request(method, apiBase + path, headers, data);
    }

    public void logout() throws IOException {
        String access = store.getAccessToken();
        String rt = store.getRefreshToken();
        // Clear tokens before the API call so no refresh can race the logout
        // (useAuth.ts:144-148). The Authorization header is snapshotted first.
        store.clear();
        if (access == null) {
            return;
        }
        Map<String, String> headers = new HashMap<>();
        headers.put("Authorization", "Bearer " + access);
        headers.put("Content-Type", "application/json");
        String body = "{\"refresh_token\": " + JSONObject.quote(rt) + "}";
        try {
            Http.request("POST", apiBase + "/api/auth/logout", headers,
                    body.getBytes(StandardCharsets.UTF_8));
        } catch (IOException e) {
            // Local logout is unconditional; the API error is swallowed
            // (useAuth.ts:165-167).
            throw e;
        }
    }

    /** Pre-request expiry check: if the access token expires within the 30 s
     *  buffer and a refresh token exists, refresh before sending
     *  (httpInterceptors.ts:50-69). */
    private void ensureFreshAccessToken() throws IOException, ApiException, SessionExpired {
        String access = store.getAccessToken();
        if (access != null && store.getRefreshToken() != null
                && VnSessionStore.isExpired(access, System.currentTimeMillis(),
                        PRE_REQUEST_EXPIRY_BUFFER_MS)) {
            if (!refresh()) {
                store.clear();
                throw new SessionExpired("refresh token rejected");
            }
        }
    }

    private Http.Response doGet(String path) throws IOException {
        Map<String, String> headers = new HashMap<>();
        String access = store.getAccessToken();
        if (access != null) {
            headers.put("Authorization", "Bearer " + access);
        }
        return Http.request("GET", apiBase + path, headers, null);
    }

    // --- mobile work shift (audit/shift-lifecycle.md) -------------------------

    /** GET status_v2. Response fields the stock client consumes: device_id,
     *  work_shift_id, project_id, start_time (useMobileShift.ts:102-106). */
    public JSONObject getShiftStatus() throws IOException, ApiException, SessionExpired {
        return authedRequest("GET", "/api/mobile/work_shift/status_v2", (JSONObject) null);
    }

    /** Body per useMobileShift.ts:138-144. Response consumes work_shift_id +
     *  the server-canonical start_time. */
    public JSONObject generateShift(String deviceId, String projectId,
            JSONObject statePayload, String timeZone)
            throws IOException, ApiException, SessionExpired {
        JSONObject body = new JSONObject();
        try {
            body.put("device_id", deviceId);
            body.put("project_id", projectId);
            body.put("start_time", isoNow());
            body.put("state_payload", statePayload);
            body.put("time_zone", timeZone);
        } catch (JSONException e) {
            throw new IllegalStateException(e);
        }
        return authedRequest("POST", "/api/mobile/work_shift/generate", body);
    }

    /** Breaks: {work_shift_id, button_pressed_time}; the stock uploader drops
     *  the outbox row on 400/404 (uploadShiftBreakEventBatch.ts:26-34). */
    public void shiftBreakEvent(String path, String workShiftId, String buttonPressedIso)
            throws IOException, ApiException, SessionExpired {
        JSONObject body = new JSONObject();
        try {
            body.put("work_shift_id", workShiftId);
            body.put("button_pressed_time", buttonPressedIso);
        } catch (JSONException e) {
            throw new IllegalStateException(e);
        }
        authedRequest("POST", path, body);
    }

    /** finalize_v2 takes a JSON ARRAY of {work_shift_id, end_time,
     *  state_payload?, data_complete} (shift-lifecycle §4). */
    public void finalizeShifts(org.json.JSONArray items)
            throws IOException, ApiException, SessionExpired {
        authedRequest("POST", "/api/mobile/work_shift/finalize_v2", items);
    }

    // --- device (shift-lifecycle §6-§9) ----------------------------------------

    public void updateDeviceInfo(JSONObject info)
            throws IOException, ApiException, SessionExpired {
        authedRequest("POST", "/api/mobile/device/update_info", info);
    }

    /** Envelope per mobileEvents.ts:9-28: {device_id, created_at, event_type,
     *  payload}. */
    public void sendDeviceEvent(String deviceId, String eventType, JSONObject payload)
            throws IOException, ApiException, SessionExpired {
        JSONObject env = new JSONObject();
        try {
            env.put("device_id", deviceId);
            env.put("created_at", isoNow());
            env.put("event_type", eventType);
            env.put("payload", payload);
        } catch (JSONException e) {
            throw new IllegalStateException(e);
        }
        authedRequest("POST", "/api/mobile/device/event/send", env);
    }

    // --- sensors (audit/sensors-telemetry.md §1-2) ------------------------------

    /** {"records": [<envelope>]} — one sensor_type per request. */
    public void uploadSensorRecords(org.json.JSONArray records)
            throws IOException, ApiException, SessionExpired {
        JSONObject body = new JSONObject();
        try {
            body.put("records", records);
        } catch (JSONException e) {
            throw new IllegalStateException(e);
        }
        authedRequest("POST", "/api/mobile/sensor/batch_upload", body);
    }

    private static String isoNow() {
        return new java.text.SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss'Z'",
                java.util.Locale.US).format(new java.util.Date());
    }

    private static JSONObject parse(Http.Response r) throws ApiException {
        JSONObject json;
        try {
            json = new JSONObject(r.body == null || r.body.isEmpty() ? "{}" : r.body);
        } catch (JSONException e) {
            throw new ApiException(r.status, "unparseable response");
        }
        if (r.status != 200) {
            String detail = json.optString("detail");
            if (detail.isEmpty()) {
                detail = json.optString("message");
            }
            if (detail.isEmpty()) {
                detail = "Unknown error";
            }
            throw new ApiException(r.status, detail);
        }
        return json;
    }
}
