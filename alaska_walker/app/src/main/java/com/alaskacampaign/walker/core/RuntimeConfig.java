package com.alaskacampaign.walker.core;

import android.content.Context;

import org.json.JSONObject;

import java.io.File;
import java.io.FileInputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;

/**
 * Harness config, loaded from an external file (external over asset, plan
 * §5.7): &lt;external-files&gt;/alaska_walker.json
 *
 * {
 *   "validnation": {
 *     "api_base": "http://50.39.218.242:19001",
 *     "email": "canvasser@alaska.test",
 *     "password": "alaska-test-1"
 *   }
 * }
 *
 * Port convention (router port-forwards to the mock host): 19001 = patriot
 * mock, 19002 = numinar mock (not yet implemented). The default api_base is
 * the public-facing forwarded address; override per-device via this file.
 */
public final class RuntimeConfig {

    public String apiBase = "http://50.39.218.242:19001";
    public String email = "";
    public String password = "";
    public String projectId = "3f8a2c1e-7b4d-4e2a-9c5f-1a2b3c4d5e6f";
    public boolean autoStartShift = false;
    public int autoStopAfterS = 0;

    public static RuntimeConfig load(Context ctx) {
        RuntimeConfig c = new RuntimeConfig();
        File dir = ctx.getExternalFilesDir(null);
        File f = dir != null ? new File(dir, "alaska_walker.json") : null;
        if (f == null || !f.isFile()) {
            return c;
        }
        try {
            byte[] raw = new byte[(int) f.length()];
            try (FileInputStream in = new FileInputStream(f)) {
                int off = 0;
                while (off < raw.length) {
                    int n = in.read(raw, off, raw.length - off);
                    if (n < 0) {
                        break;
                    }
                    off += n;
                }
            }
            JSONObject vn = new JSONObject(new String(raw, StandardCharsets.UTF_8))
                    .optJSONObject("validnation");
            if (vn != null) {
                c.apiBase = vn.optString("api_base", c.apiBase);
                c.email = vn.optString("email", c.email);
                c.password = vn.optString("password", c.password);
                c.projectId = vn.optString("project_id", c.projectId);
                c.autoStartShift = vn.optBoolean("auto_start_shift", false);
                c.autoStopAfterS = vn.optInt("auto_stop_after_s", 0);
            }
        } catch (IOException | org.json.JSONException ignored) {
            // Fall back to defaults; the UI fields stay editable.
        }
        return c;
    }
}
