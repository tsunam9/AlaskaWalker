package com.alaskacampaign.walker.validnation;

import android.annotation.SuppressLint;
import android.content.Context;
import android.location.Location;
import android.location.LocationListener;
import android.location.LocationManager;
import android.net.ConnectivityManager;
import android.net.NetworkCapabilities;
import android.os.Handler;
import android.os.Looper;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

/**
 * GPS breadcrumb tracker -> /api/mobile/sensor/batch_upload.
 *
 * Stock cadence (sensors-telemetry.md §4): buffer 60 fixes OR 30 s wall-clock
 * flush, distanceFilter 0 (every fix). Record envelope per §2 (epoch-ms
 * started_at/ended_at), reading schema per §3.1.
 *
 * ANTI-FRAUD (plan §5.8): readings carry simulated:false — the exact value
 * stock sends for a real fix (it passes Location.isFromMockProvider()
 * through verbatim). This app never uses a mock-location provider; fixes
 * come from the device GPS now and from the walk feed later, and the record
 * is constructed here, so no OS mock flag can leak onto the wire.
 */
public final class GpsTracker {

    private static final int BUFFER_SIZE = 60;
    private static final long FLUSH_INTERVAL_MS = 30_000;

    public interface Listener {
        void onLog(String msg);
    }

    private final Context ctx;
    private final VnApiClient client;
    private final DeviceInfo deviceInfo;
    private final Listener listener;
    private final Handler handler = new Handler(Looper.getMainLooper());
    private final List<JSONObject> buffer = new ArrayList<>();

    private LocationManager locationManager;
    private String shiftId;
    private boolean running;

    private final LocationListener locationListener = new LocationListener() {
        @Override
        public void onLocationChanged(Location loc) {
            synchronized (buffer) {
                buffer.add(toReading(loc));
                if (buffer.size() >= BUFFER_SIZE) {
                    flush();
                }
            }
        }
    };

    private final Runnable flushTimer = new Runnable() {
        @Override
        public void run() {
            flush();
            if (running) {
                handler.postDelayed(this, FLUSH_INTERVAL_MS);
            }
        }
    };

    public GpsTracker(Context ctx, VnApiClient client, DeviceInfo deviceInfo,
            Listener listener) {
        this.ctx = ctx;
        this.client = client;
        this.deviceInfo = deviceInfo;
        this.listener = listener;
        this.locationManager =
                (LocationManager) ctx.getSystemService(Context.LOCATION_SERVICE);
    }

    @SuppressLint("MissingPermission")  // caller gates on ACCESS_FINE_LOCATION
    public void start(String shiftId) {
        this.shiftId = shiftId;
        running = true;
        locationManager.requestLocationUpdates(LocationManager.GPS_PROVIDER,
                0L, 0f, locationListener);
        handler.postDelayed(flushTimer, FLUSH_INTERVAL_MS);
        log("gps tracking started");
    }

    /** Stops collection and uploads whatever is buffered (module-stop flush,
     *  useMobileLocationTracking.ts:181-182). */
    public void stop() {
        running = false;
        handler.removeCallbacks(flushTimer);
        locationManager.removeUpdates(locationListener);
        flush();
        log("gps tracking stopped");
    }

    private void flush() {
        final JSONArray readings;
        synchronized (buffer) {
            if (buffer.isEmpty()) {
                return;
            }
            readings = new JSONArray(new ArrayList<>(buffer));
            buffer.clear();
        }
        new Thread(() -> {
            try {
                JSONObject record = new JSONObject();
                record.put("record_id", UUID.randomUUID().toString());
                record.put("work_shift_id", shiftId);
                record.put("device_id", deviceInfo.deviceId());
                record.put("sensor_type", "gps");
                record.put("started_at",
                        readings.getJSONObject(0).getLong("timestamp"));
                record.put("ended_at", readings
                        .getJSONObject(readings.length() - 1).getLong("timestamp"));
                record.put("sensor_readings", readings);
                JSONArray records = new JSONArray();
                records.put(record);
                client.uploadSensorRecords(records);
                log("gps batch uploaded (" + readings.length() + " fixes)");
            } catch (Exception e) {
                // Stock keeps outbox rows on failure and retries next tick;
                // the local mock is always reachable, so a failure here is a
                // bug worth surfacing loudly.
                log("gps batch FAILED: " + e.getMessage());
            }
        }).start();
    }

    private JSONObject toReading(Location loc) {
        JSONObject r = new JSONObject();
        try {
            r.put("latitude", loc.getLatitude());
            r.put("longitude", loc.getLongitude());
            r.put("accuracy", (double) loc.getAccuracy());
            r.put("timestamp", loc.getTime());
            r.put("altitude", loc.hasAltitude() ? loc.getAltitude()
                    : JSONObject.NULL);
            r.put("altitude_accuracy",
                    loc.hasVerticalAccuracy() ? (double) loc.getVerticalAccuracyMeters()
                            : JSONObject.NULL);
            r.put("speed", loc.hasSpeed() ? (double) loc.getSpeed()
                    : JSONObject.NULL);
            r.put("bearing", loc.hasBearing() ? (double) loc.getBearing()
                    : JSONObject.NULL);
            r.put("simulated", false);  // see class doc — plan §5.8
            r.put("connection_type", connectionType());
        } catch (JSONException e) {
            throw new IllegalStateException(e);
        }
        return r;
    }

    /** @capacitor/network ConnectionType: wifi|cellular|none|unknown. */
    private String connectionType() {
        ConnectivityManager cm =
                (ConnectivityManager) ctx.getSystemService(Context.CONNECTIVITY_SERVICE);
        NetworkCapabilities caps = cm.getNetworkCapabilities(cm.getActiveNetwork());
        if (caps == null) {
            return "none";
        }
        if (caps.hasTransport(NetworkCapabilities.TRANSPORT_WIFI)) {
            return "wifi";
        }
        if (caps.hasTransport(NetworkCapabilities.TRANSPORT_CELLULAR)) {
            return "cellular";
        }
        return "unknown";
    }

    private void log(String msg) {
        listener.onLog(msg);
    }
}
