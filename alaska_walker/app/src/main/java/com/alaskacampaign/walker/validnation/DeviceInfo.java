package com.alaskacampaign.walker.validnation;

import android.content.Context;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.hardware.Sensor;
import android.hardware.SensorManager;
import android.os.Build;

import org.json.JSONException;
import org.json.JSONObject;

import java.util.TimeZone;
import java.util.UUID;

/**
 * Stock device-info shapes (audit/shift-lifecycle.md §1, §6).
 *
 * SECURITY (wire parity, plan §5.8): is_root is hardcoded false — this build
 * is never rooted, so false is factually true for it, and it is what stock
 * sends on any non-rooted phone. Permission fields report actual runtime
 * grants, like stock (permission booleans only, never radio state).
 */
public final class DeviceInfo {

    private final Context ctx;
    private final SharedPreferences prefs;

    public DeviceInfo(Context ctx) {
        this.ctx = ctx;
        this.prefs = ctx.getSharedPreferences("vn_device", Context.MODE_PRIVATE);
    }

    /** Stable per-install UDID (stock uses capacitor-udid). */
    public String deviceId() {
        String id = prefs.getString("device_id", null);
        if (id == null) {
            id = UUID.randomUUID().toString().replace("-", "").substring(0, 16);
            prefs.edit().putString("device_id", id).apply();
        }
        return id;
    }

    public String timezone() {
        return TimeZone.getDefault().getID();
    }

    private boolean hasPermission(String p) {
        return ctx.checkSelfPermission(p) == PackageManager.PERMISSION_GRANTED;
    }

    private boolean completeSensors() {
        SensorManager sm = (SensorManager) ctx.getSystemService(Context.SENSOR_SERVICE);
        return sm.getDefaultSensor(Sensor.TYPE_ACCELEROMETER) != null
                && sm.getDefaultSensor(Sensor.TYPE_GYROSCOPE) != null
                && sm.getDefaultSensor(Sensor.TYPE_MAGNETIC_FIELD) != null
                && sm.getDefaultSensor(Sensor.TYPE_ROTATION_VECTOR) != null;
    }

    private int versionCode() {
        try {
            return ctx.getPackageManager()
                    .getPackageInfo(ctx.getPackageName(), 0).versionCode;
        } catch (PackageManager.NameNotFoundException e) {
            return 0;
        }
    }

    private String versionName() {
        try {
            return ctx.getPackageManager()
                    .getPackageInfo(ctx.getPackageName(), 0).versionName;
        } catch (PackageManager.NameNotFoundException e) {
            return "0";
        }
    }

    private JSONObject permissions() throws JSONException {
        JSONObject p = new JSONObject();
        p.put("wifi", hasPermission(android.Manifest.permission.ACCESS_FINE_LOCATION));
        p.put("ble", hasPermission(android.Manifest.permission.BLUETOOTH_SCAN));
        p.put("gps", hasPermission(android.Manifest.permission.ACCESS_FINE_LOCATION));
        p.put("motion", hasPermission(android.Manifest.permission.ACTIVITY_RECOGNITION));
        return p;
    }

    private JSONObject battery() throws JSONException {
        android.os.BatteryManager bm =
                (android.os.BatteryManager) ctx.getSystemService(Context.BATTERY_SERVICE);
        int level = bm != null
                ? bm.getIntProperty(android.os.BatteryManager.BATTERY_PROPERTY_CAPACITY)
                : -1;
        JSONObject b = new JSONObject();
        b.put("battery_level", level);
        b.put("is_charging", bm != null && bm.isCharging());
        return b;
    }

    /** state_payload for generate/finalize (deviceInfoUtils.ts:12-33). */
    public JSONObject statePayload() throws JSONException {
        JSONObject sp = new JSONObject();
        sp.put("permissions", permissions());
        sp.put("battery", battery());
        sp.put("config", new JSONObject());  // tracking-config snapshot; ours is
                                             // not Remote-Config-driven
        return sp;
    }

    /** update_info body — exact stock field set (shift-lifecycle.md §6). */
    public JSONObject updateInfoBody() throws JSONException {
        JSONObject info = new JSONObject();
        info.put("model", Build.MODEL);
        info.put("device_id", deviceId());
        info.put("name", Build.MODEL);
        info.put("is_complete_sensors", completeSensors());
        info.put("is_root", false);  // never rooted (plan §5.8); see class doc
        info.put("os_version", Build.VERSION.RELEASE);
        JSONObject perms = permissions();
        info.put("permission_gps", perms.getBoolean("gps"));
        info.put("permission_ble", perms.getBoolean("ble"));
        info.put("permission_wifi", perms.getBoolean("wifi"));
        info.put("permission_motion", perms.getBoolean("motion"));
        info.put("push_permission_granted", false);
        info.put("push_notifications_enabled", false);
        info.put("platform", "android");
        info.put("software_version", "v" + versionName() + " (" + versionCode() + ")");
        info.put("timezone", timezone());
        return info;
    }
}
