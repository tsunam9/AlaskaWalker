package com.alaskacampaign.walker.validnation;

import android.content.Context;
import android.content.SharedPreferences;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

/**
 * Shift state machine, mirroring the stock flow (audit/shift-lifecycle.md):
 *
 *  start:   status_v2 pre-check -> adopt / interrupt (finalize with
 *           data_complete:null, no state_payload — useMobileShift.ts:122-124)
 *           -> generate -> persist current_work_shift_id
 *  pause/resume: button_pressed_time events (stock routes them through the
 *           outbox; the mock is local so direct send is equivalent here)
 *  stop:    finalize_v2 [{work_shift_id, end_time, state_payload,
 *           data_complete: true}] — data_complete:true only after every other
 *           upload for the shift has drained (useUploader.ts:43-74); the GPS
 *           uploader flushes before this is called.
 */
public final class ShiftRepository {

    public interface Listener {
        void onLog(String msg);
    }

    private static final String PREFS = "vn_shift";
    private static final String KEY_SHIFT_ID = "current_work_shift_id";

    private final VnApiClient client;
    private final DeviceInfo deviceInfo;
    private final SharedPreferences prefs;
    private final Listener listener;
    private boolean paused;

    public ShiftRepository(Context ctx, VnApiClient client, DeviceInfo deviceInfo,
            Listener listener) {
        this.client = client;
        this.deviceInfo = deviceInfo;
        this.prefs = ctx.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
        this.listener = listener;
    }

    public String currentShiftId() {
        return prefs.getString(KEY_SHIFT_ID, null);
    }

    public boolean isPaused() {
        return paused;
    }

    private void log(String msg) {
        listener.onLog(msg);
    }

    /** status_v2 -> generate. Returns the shift id. */
    public String start(String projectId) throws Exception {
        JSONObject status = client.getShiftStatus();
        String serverShift = status.optString("work_shift_id", null);
        String serverDevice = status.optString("device_id", null);
        if (serverShift != null && !serverShift.isEmpty()
                && !deviceInfo.deviceId().equals(serverDevice)) {
            // Cross-device interrupt: finalize the other device's shift with
            // data_complete:null and NO state_payload, then proceed.
            log("server shift on another device; interrupting");
            JSONArray interrupt = new JSONArray();
            JSONObject item = new JSONObject();
            item.put("work_shift_id", serverShift);
            item.put("end_time", isoNow());
            item.put("data_complete", JSONObject.NULL);
            interrupt.put(item);
            client.finalizeShifts(interrupt);
        } else if (serverShift != null && !serverShift.isEmpty()) {
            log("adopting server shift " + serverShift);
            prefs.edit().putString(KEY_SHIFT_ID, serverShift).apply();
            return serverShift;
        }
        JSONObject gen = client.generateShift(deviceInfo.deviceId(), projectId,
                deviceInfo.statePayload(), deviceInfo.timezone());
        String sid = gen.getString("work_shift_id");
        prefs.edit().putString(KEY_SHIFT_ID, sid).apply();
        paused = false;
        // Stock posts update_info right after generate
        // (useTrackingController.ts:180-182).
        client.updateDeviceInfo(deviceInfo.updateInfoBody());
        log("shift started: " + sid);
        return sid;
    }

    public void pause() throws Exception {
        String sid = requireShift();
        client.shiftBreakEvent("/api/mobile/work_shift/pause", sid, isoNow());
        paused = true;
        log("shift paused");
    }

    public void resume() throws Exception {
        String sid = requireShift();
        client.shiftBreakEvent("/api/mobile/work_shift/resume", sid, isoNow());
        paused = false;
        log("shift resumed");
    }

    public void stop() throws Exception {
        String sid = requireShift();
        JSONArray arr = new JSONArray();
        JSONObject item = new JSONObject();
        item.put("work_shift_id", sid);
        item.put("end_time", isoNow());
        item.put("state_payload", deviceInfo.statePayload());
        item.put("data_complete", true);
        arr.put(item);
        client.finalizeShifts(arr);
        prefs.edit().remove(KEY_SHIFT_ID).apply();
        paused = false;
        log("shift finalized (data_complete)");
    }

    private String requireShift() {
        String sid = currentShiftId();
        if (sid == null) {
            throw new IllegalStateException("no active shift");
        }
        return sid;
    }

    private static String isoNow() {
        return new java.text.SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss'Z'",
                java.util.Locale.US).format(new java.util.Date());
    }
}
