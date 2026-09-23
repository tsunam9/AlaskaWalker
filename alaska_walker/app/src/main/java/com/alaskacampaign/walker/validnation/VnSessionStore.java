package com.alaskacampaign.walker.validnation;

import android.content.Context;
import android.content.SharedPreferences;
import android.util.Base64;

import org.json.JSONObject;

/**
 * Access/refresh token store. Keys match the stock app's storage keys
 * ('auth.token' / 'auth.refresh-token', useAuthState.ts:56-104).
 *
 * SECURITY (scaffold note): stock keeps these in Keystore-backed AES/GCM
 * storage (@aparajita/capacitor-secure-storage, audit/auth-session.md §6).
 * This scaffold uses plain MODE_PRIVATE prefs; switching to Keystore-backed
 * encryption is a step-5 hardening item before any real credential touches
 * the app.
 */
public final class VnSessionStore {

    private static final String PREFS = "vn_session";
    private static final String KEY_ACCESS = "auth.token";
    private static final String KEY_REFRESH = "auth.refresh-token";

    private final SharedPreferences prefs;

    public VnSessionStore(Context ctx) {
        prefs = ctx.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
    }

    public String getAccessToken() {
        return prefs.getString(KEY_ACCESS, null);
    }

    public String getRefreshToken() {
        return prefs.getString(KEY_REFRESH, null);
    }

    public void setTokens(String access, String refresh) {
        prefs.edit().putString(KEY_ACCESS, access).putString(KEY_REFRESH, refresh).apply();
    }

    public void setAccessToken(String access) {
        prefs.edit().putString(KEY_ACCESS, access).apply();
    }

    public void clear() {
        prefs.edit().remove(KEY_ACCESS).remove(KEY_REFRESH).apply();
    }

    /** Expiry (Unix ms) from the JWT's exp claim, or null if unparseable.
     *  Mirrors utils/authTokenExpiry.ts:25-34. */
    public static Long getExpiryMs(String jwt) {
        try {
            String payload = jwt.split("\\.")[1];
            String json = new String(Base64.decode(payload, Base64.URL_SAFE | Base64.NO_WRAP),
                    "UTF-8");
            JSONObject p = new JSONObject(json);
            if (!p.has("exp")) {
                return null;
            }
            return p.getLong("exp") * 1000L;
        } catch (Exception e) {
            return null;
        }
    }

    /** True if the token is expired or will be within bufferMs
     *  (stock pre-request buffer: 30 s, httpInterceptors.ts:34,58-67). */
    public static boolean isExpired(String jwt, long nowMs, long bufferMs) {
        Long exp = getExpiryMs(jwt);
        return exp == null || exp < nowMs + bufferMs;
    }
}
