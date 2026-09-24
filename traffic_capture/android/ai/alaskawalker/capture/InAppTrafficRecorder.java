package ai.alaskawalker.capture;

import android.app.Activity;
import android.content.Context;
import android.content.SharedPreferences;
import android.webkit.JavascriptInterface;
import android.webkit.WebView;

import org.json.JSONObject;

import java.io.BufferedInputStream;
import java.io.BufferedOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.Comparator;
import java.util.UUID;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicLong;

/** Private, app-internal traffic queue with delayed upload to the dedicated logger. */
public final class InAppTrafficRecorder {
    private static final Object FILE_LOCK = new Object();
    private static final ScheduledExecutorService IO = Executors.newSingleThreadScheduledExecutor();
    private static final AtomicBoolean UPLOAD_SCHEDULED = new AtomicBoolean(false);
    private static final AtomicLong SEQUENCE = new AtomicLong(0L);
    private static volatile Context context;
    private static volatile String appName = "unknown";
    private static volatile String endpoint = "";
    private static volatile String bearerToken = "";
    private static volatile String installId = "";

    private InAppTrafficRecorder() {}

    public static void configure(Context source, String app, String loggerUrl, String token) {
        if (source == null) return;
        context = source.getApplicationContext();
        appName = app == null ? "unknown" : app;
        endpoint = loggerUrl == null ? "" : loggerUrl.trim();
        bearerToken = token == null ? "" : token;
        SharedPreferences preferences = context.getSharedPreferences("alaska_capture", Context.MODE_PRIVATE);
        installId = preferences.getString("install_id", "");
        if (installId.isEmpty()) {
            installId = UUID.randomUUID().toString();
            preferences.edit().putString("install_id", installId).apply();
        }
        ensureDirectory();
        scheduleUpload(1L);
    }

    public static void installWebView(Activity activity, String app, String loggerUrl, String token) {
        configure(activity, app, loggerUrl, token);
        try {
            Object bridge = activity.getClass().getMethod("getBridge").invoke(activity);
            Object candidate = bridge.getClass().getMethod("getWebView").invoke(bridge);
            if (candidate instanceof WebView) {
                attachWebView((WebView) candidate);
            }
        } catch (Throwable error) {
            recordError("webview_bridge_install", error);
        }
    }

    public static void attachWebView(WebView webView) {
        if (webView == null) return;
        webView.addJavascriptInterface(new JavascriptBridge(), "AlaskaCapture");
    }

    public static void record(JSONObject event) {
        if (event == null || context == null) return;
        try {
            if (!event.has("captured_at_ms")) event.put("captured_at_ms", System.currentTimeMillis());
            event.put("sequence", SEQUENCE.incrementAndGet());
            event.put("capture_app", appName);
            event.put("capture_install_id", installId);
            final String line = event.toString() + "\n";
            IO.execute(() -> append(line));
        } catch (Throwable ignored) {
            // Capture must never affect the app's normal control flow.
        }
    }

    public static void recordJson(String raw) {
        try {
            record(new JSONObject(raw));
        } catch (Throwable error) {
            recordError("invalid_js_event", error);
        }
    }

    public static void flush() {
        scheduleUpload(0L);
    }

    private static void recordError(String stage, Throwable error) {
        try {
            JSONObject event = new JSONObject();
            event.put("kind", "capture_error");
            event.put("stage", stage);
            event.put("error", String.valueOf(error));
            record(event);
        } catch (Throwable ignored) {
        }
    }

    private static File ensureDirectory() {
        Context current = context;
        if (current == null) return null;
        File directory = new File(current.getFilesDir(), "network-capture");
        if (!directory.exists()) directory.mkdirs();
        return directory;
    }

    private static void append(String line) {
        File directory = ensureDirectory();
        if (directory == null) return;
        synchronized (FILE_LOCK) {
            try (FileOutputStream stream = new FileOutputStream(new File(directory, "current.ndjson"), true)) {
                stream.write(line.getBytes(StandardCharsets.UTF_8));
                stream.getFD().sync();
            } catch (Throwable ignored) {
                return;
            }
        }
        scheduleUpload(10L);
    }

    private static void scheduleUpload(long delaySeconds) {
        if (context == null || endpoint.isEmpty()) return;
        if (!UPLOAD_SCHEDULED.compareAndSet(false, true)) return;
        IO.schedule(() -> {
            try {
                uploadPending();
            } finally {
                UPLOAD_SCHEDULED.set(false);
            }
        }, delaySeconds, TimeUnit.SECONDS);
    }

    private static void uploadPending() {
        File directory = ensureDirectory();
        if (directory == null || endpoint.isEmpty()) return;
        synchronized (FILE_LOCK) {
            File current = new File(directory, "current.ndjson");
            if (current.isFile() && current.length() > 0L) {
                current.renameTo(new File(directory, "pending-" + System.currentTimeMillis() + ".ndjson"));
            }
        }
        File[] pending = directory.listFiles((dir, name) -> name.startsWith("pending-") && name.endsWith(".ndjson"));
        if (pending == null) return;
        Arrays.sort(pending, Comparator.comparing(File::getName));
        for (File file : pending) {
            if (!upload(file)) break;
        }
    }

    private static boolean upload(File file) {
        HttpURLConnection connection = null;
        try {
            URL url = new URL(endpoint);
            connection = (HttpURLConnection) url.openConnection();
            connection.setConnectTimeout(15_000);
            connection.setReadTimeout(30_000);
            connection.setRequestMethod("POST");
            connection.setDoOutput(true);
            connection.setFixedLengthStreamingMode(file.length());
            connection.setRequestProperty("Content-Type", "application/x-ndjson");
            connection.setRequestProperty("X-Capture-App", appName);
            connection.setRequestProperty("X-Capture-Install", installId);
            connection.setRequestProperty("X-Capture-Batch", file.getName());
            if (!bearerToken.isEmpty()) connection.setRequestProperty("Authorization", "Bearer " + bearerToken);
            try (BufferedInputStream input = new BufferedInputStream(new FileInputStream(file));
                 BufferedOutputStream output = new BufferedOutputStream(connection.getOutputStream())) {
                byte[] buffer = new byte[32 * 1024];
                int count;
                while ((count = input.read(buffer)) != -1) output.write(buffer, 0, count);
            }
            int status = connection.getResponseCode();
            if (status >= 200 && status < 300) return file.delete();
        } catch (Throwable ignored) {
        } finally {
            if (connection != null) connection.disconnect();
        }
        return false;
    }

    public static final class JavascriptBridge {
        @JavascriptInterface
        public void record(String event) {
            recordJson(event);
        }

        @JavascriptInterface
        public void flush() {
            InAppTrafficRecorder.flush();
        }
    }
}
