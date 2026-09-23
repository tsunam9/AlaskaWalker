package com.alaskacampaign.walker;

import android.Manifest;
import android.app.Activity;
import android.content.pm.PackageManager;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.util.Log;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import com.alaskacampaign.walker.core.RuntimeConfig;
import com.alaskacampaign.walker.validnation.DeviceInfo;
import com.alaskacampaign.walker.validnation.GpsTracker;
import com.alaskacampaign.walker.validnation.ShiftRepository;
import com.alaskacampaign.walker.validnation.VnApiClient;
import com.alaskacampaign.walker.validnation.VnSessionStore;

import org.json.JSONObject;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class MainActivity extends Activity {

    private static final String TAG = "VnAuth";

    /** Proactive refresh lead time: 60 s before JWT exp (plugins/auth.ts:35-39,
     *  config/AuthRefreshHandler.ts:82-103). */
    private static final long PROACTIVE_REFRESH_LEAD_MS = 60_000;

    private static final int REQ_LOCATION = 41;

    private final ExecutorService bg = Executors.newSingleThreadExecutor();
    private final Handler main = new Handler(Looper.getMainLooper());

    private VnSessionStore store;
    private VnApiClient client;
    private RuntimeConfig config;
    private DeviceInfo deviceInfo;
    private ShiftRepository shiftRepo;
    private GpsTracker gpsTracker;

    private EditText serverField;
    private EditText emailField;
    private EditText passwordField;
    private TextView statusView;
    private TextView shiftView;
    private TextView logView;

    private final Runnable proactiveRefresh = () -> bg.execute(() -> {
        try {
            log("proactive refresh (exp-60s)");
            if (client.refresh()) {
                log("refresh OK");
                scheduleProactiveRefresh();
            } else {
                store.clear();
                log("refresh rejected; session cleared");
                setStatus("signed out");
            }
        } catch (Exception e) {
            log("proactive refresh failed: " + e.getMessage());
        }
    });

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        config = RuntimeConfig.load(this);
        store = new VnSessionStore(this);
        deviceInfo = new DeviceInfo(this);

        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        int pad = (int) (16 * getResources().getDisplayMetrics().density);
        root.setPadding(pad, pad, pad, pad);

        serverField = field(root, "server", config.apiBase);
        emailField = field(root, "email", config.email);
        passwordField = field(root, "password", config.password);

        LinearLayout authButtons = new LinearLayout(this);
        authButtons.setOrientation(LinearLayout.HORIZONTAL);
        root.addView(authButtons);
        addButton(authButtons, "Log in", v -> login());
        addButton(authButtons, "Profile", v -> fetchProfile());
        addButton(authButtons, "Log out", v -> logout());

        statusView = new TextView(this);
        statusView.setTextSize(16);
        root.addView(statusView);

        LinearLayout shiftButtons = new LinearLayout(this);
        shiftButtons.setOrientation(LinearLayout.HORIZONTAL);
        root.addView(shiftButtons);
        addButton(shiftButtons, "Start shift", v -> startShift());
        addButton(shiftButtons, "Break", v -> pauseShift());
        addButton(shiftButtons, "Resume", v -> resumeShift());
        addButton(shiftButtons, "End shift", v -> stopShift());

        shiftView = new TextView(this);
        shiftView.setTextSize(14);
        root.addView(shiftView);

        ScrollView scroll = new ScrollView(this);
        logView = new TextView(this);
        logView.setTextSize(12);
        scroll.addView(logView);
        root.addView(scroll, new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, 0, 1f));

        setContentView(root);
        setStatus("signed out");
        updateShiftView();
        restoreSession();
    }

    private void rebuildDomain() {
        client = new VnApiClient(serverField.getText().toString().trim(), store);
        shiftRepo = new ShiftRepository(this, client, deviceInfo, this::log);
        gpsTracker = new GpsTracker(this, client, deviceInfo, this::log);
    }

    // --- session ---------------------------------------------------------------

    private void restoreSession() {
        rebuildDomain();
        String access = store.getAccessToken();
        if (access != null) {
            log("session restored; fetching profile");
            fetchProfile();
        } else if (store.getRefreshToken() != null) {
            log("only refresh token survives; refreshing");
            bg.execute(() -> {
                try {
                    if (client.refresh()) {
                        log("refresh OK");
                        scheduleProactiveRefresh();
                        fetchProfile();
                    } else {
                        store.clear();
                        log("refresh rejected; session cleared");
                    }
                } catch (Exception e) {
                    log("refresh failed: " + e.getMessage());
                }
            });
        } else if (!config.email.isEmpty()) {
            log("config credentials present; logging in");
            login();
        }
    }

    private void login() {
        String email = emailField.getText().toString().trim();
        String password = passwordField.getText().toString();
        rebuildDomain();
        setStatus("signing in...");
        bg.execute(() -> {
            try {
                client.login(email, password);
                log("login OK");
                scheduleProactiveRefresh();
                // Stock links the device right after login
                // (pages/login.vue:108, ensureDeviceLinked).
                client.updateDeviceInfo(deviceInfo.updateInfoBody());
                log("device linked: " + deviceInfo.deviceId());
                fetchProfile();
            } catch (VnApiClient.ApiException e) {
                log("login failed (" + e.status + "): " + e.getMessage());
                setStatus("sign-in failed");
            } catch (Exception e) {
                log("login error: " + e.getMessage());
                setStatus("sign-in failed");
            }
        });
    }

    private void fetchProfile() {
        rebuildDomain();
        bg.execute(() -> {
            try {
                JSONObject p = client.getProfile();
                JSONObject user = p.getJSONObject("token").getJSONObject("user");
                String name = user.optString("first_name") + " "
                        + user.optString("last_name");
                String role = user.optString("role");
                String banner = p.optJSONObject("alerts") != null
                        ? p.getJSONObject("alerts").optString("banner_alert")
                        : "";
                log("profile OK: " + name + " <" + user.optString("email")
                        + "> role=" + role);
                if (banner != null && !banner.isEmpty() && !"null".equals(banner)) {
                    log("banner_alert: " + banner);
                }
                setStatus("signed in as " + name + " (" + role + ")");
                scheduleProactiveRefresh();
                maybeAutoStartShift();
            } catch (VnApiClient.SessionExpired e) {
                log("session expired; signed out");
                setStatus("signed out");
            } catch (VnApiClient.ApiException e) {
                log("profile failed (" + e.status + "): " + e.getMessage());
            } catch (Exception e) {
                log("profile error: " + e.getMessage());
            }
        });
    }

    private void logout() {
        rebuildDomain();
        bg.execute(() -> {
            try {
                if (shiftRepo.currentShiftId() != null) {
                    stopShiftBlocking();
                }
                client.logout();
                log("logout OK");
            } catch (Exception e) {
                log("logout API error (local logout stands): " + e.getMessage());
            }
            main.post(() -> setStatus("signed out"));
        });
    }

    // --- shift -----------------------------------------------------------------

    private void startShift() {
        if (checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION)
                != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{Manifest.permission.ACCESS_FINE_LOCATION},
                    REQ_LOCATION);
            return;
        }
        rebuildDomain();
        bg.execute(() -> {
            try {
                String sid = shiftRepo.start(config.projectId);
                gpsTracker.start(sid);
                main.post(this::updateShiftView);
                maybeAutoStopShift();
            } catch (Exception e) {
                log("shift start failed: " + e.getMessage());
            }
        });
    }

    private void pauseShift() {
        bg.execute(() -> {
            try {
                gpsTracker.stop();
                shiftRepo.pause();
                main.post(this::updateShiftView);
            } catch (Exception e) {
                log("pause failed: " + e.getMessage());
            }
        });
    }

    private void resumeShift() {
        bg.execute(() -> {
            try {
                shiftRepo.resume();
                gpsTracker.start(shiftRepo.currentShiftId());
                main.post(this::updateShiftView);
            } catch (Exception e) {
                log("resume failed: " + e.getMessage());
            }
        });
    }

    private void stopShift() {
        bg.execute(() -> {
            try {
                stopShiftBlocking();
                main.post(this::updateShiftView);
            } catch (Exception e) {
                log("stop failed: " + e.getMessage());
            }
        });
    }

    /** Drain GPS buffer first, then finalize with data_complete:true
     *  (useUploader.ts:43-74 — shift_end only after other payloads drain). */
    private void stopShiftBlocking() throws Exception {
        gpsTracker.stop();
        shiftRepo.stop();
    }

    private void maybeAutoStartShift() {
        if (config.autoStartShift && shiftRepo.currentShiftId() == null) {
            main.post(this::startShift);
        }
    }

    private void maybeAutoStopShift() {
        if (config.autoStopAfterS > 0) {
            main.postDelayed(this::stopShift, config.autoStopAfterS * 1000L);
        }
    }

    private void updateShiftView() {
        String sid = shiftRepo != null ? shiftRepo.currentShiftId() : null;
        shiftView.setText(sid == null ? "no active shift"
                : "shift: " + sid + (shiftRepo.isPaused() ? " (break)" : ""));
    }

    @Override
    public void onRequestPermissionsResult(int requestCode, String[] permissions,
            int[] grantResults) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults);
        if (requestCode == REQ_LOCATION && grantResults.length > 0
                && grantResults[0] == PackageManager.PERMISSION_GRANTED) {
            startShift();
        }
    }

    // --- misc -------------------------------------------------------------------

    /** Arm the proactive refresh at JWT exp-60 s, re-armed on every token
     *  change (AuthRefreshHandler.ts:51-58, authRefreshSchedule.ts:24-35). */
    private void scheduleProactiveRefresh() {
        main.post(() -> {
            main.removeCallbacks(proactiveRefresh);
            String access = store.getAccessToken();
            Long exp = access != null ? VnSessionStore.getExpiryMs(access) : null;
            if (exp == null || store.getRefreshToken() == null) {
                return;
            }
            long delay = Math.max(0,
                    exp - System.currentTimeMillis() - PROACTIVE_REFRESH_LEAD_MS);
            log("proactive refresh armed in " + (delay / 1000) + " s");
            main.postDelayed(proactiveRefresh, delay);
        });
    }

    private EditText field(LinearLayout root, String hint, String text) {
        EditText e = new EditText(this);
        e.setHint(hint);
        e.setText(text);
        e.setSingleLine();
        root.addView(e);
        return e;
    }

    private void addButton(LinearLayout root, String label, View.OnClickListener l) {
        Button b = new Button(this);
        b.setText(label);
        b.setOnClickListener(l);
        root.addView(b, new LinearLayout.LayoutParams(0,
                LinearLayout.LayoutParams.WRAP_CONTENT, 1f));
    }

    private void setStatus(String s) {
        main.post(() -> statusView.setText(s));
    }

    private void log(String msg) {
        Log.i(TAG, msg);
        main.post(() -> logView.append(msg + "\n"));
    }
}
