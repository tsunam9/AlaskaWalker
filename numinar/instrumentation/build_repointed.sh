#!/usr/bin/env bash
# Build a repointed stock Numinar APK set: identical app, all Numinar origins
# retargeted to the local mock (server/numinar-mock), third-party telemetry
# neutered, expo-updates disabled. Stock APKs in ../stock/ are never touched.
#
# Hermes v96 string table entries are patched same-length (hermes-decomp
# patch-string); URL padding uses "/." segments that OkHttp normalizes away
# plus a trailing "/" that the mock's slash-collapse middleware absorbs.
# The six `"https://" + AUTH0_DOMAIN` call sites are patched to "http://" at
# the instruction level (hermes-decomp asm) because the shared "https://"
# string is also used by unrelated startsWith() validators.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/../.." && pwd)"
STOCK_DIR="$REPO_ROOT/numinar/stock"
BUILD_DIR="$SCRIPT_DIR/build-repointed"
WORK_TREE="$BUILD_DIR/apktool"
OUT_DIR="$BUILD_DIR/out"
TOOLS_DIR="$SCRIPT_DIR/.tools"
PATRIOT_TOOLS="$REPO_ROOT/patriot_grassroots/instrumentation/.tools"
APKTOOL_VERSION="3.0.3"
APKTOOL_JAR="$TOOLS_DIR/apktool_${APKTOOL_VERSION}.jar"
APKTOOL_SHA256="dbf930b076c6b9be08d57c449cacefc3bdd6b71ebd59b3066fc0e1f5b14f9423"
HERMES_DECOMP="${HERMES_DECOMP:-/tmp/hermes-decomp/target/release/hermes-decomp}"
SDK_ROOT="${ANDROID_SDK_ROOT:-${ANDROID_HOME:-$HOME/Android/Sdk}}"

# Mock target as seen from the device. Default is loopback (phone plugged
# into this machine + adb reverse). For a phone elsewhere on the internet,
# set TARGET_HOST to this network's public IP with port TARGET_PORT
# forwarded to this machine; adb reverse is then not needed. Note the public
# variant is plain HTTP over the internet — mock fixtures only.
TARGET_HOST="${TARGET_HOST:-127.0.0.1}"
TARGET_PORT="${TARGET_PORT:-19002}"

if [[ ! -f "$STOCK_DIR/base.apk" ]]; then
  printf 'Stock base APK is missing.\n' >&2
  exit 1
fi
if [[ ! -x "$HERMES_DECOMP" ]]; then
  printf 'hermes-decomp not found at %s\n' "$HERMES_DECOMP" >&2
  exit 1
fi

BUILD_TOOLS="$(find "$SDK_ROOT/build-tools" -mindepth 1 -maxdepth 1 -type d | sort -V | tail -1)"
APKSIGNER="$BUILD_TOOLS/apksigner"
ZIPALIGN="$BUILD_TOOLS/zipalign"
if [[ ! -x "$APKSIGNER" || ! -x "$ZIPALIGN" ]]; then
  printf 'Android build-tools not found under %s.\n' "$SDK_ROOT" >&2
  exit 1
fi

mkdir -p "$TOOLS_DIR" "$BUILD_DIR" "$OUT_DIR"
if [[ ! -f "$APKTOOL_JAR" ]]; then
  if [[ -f "$PATRIOT_TOOLS/apktool_${APKTOOL_VERSION}.jar" ]]; then
    cp "$PATRIOT_TOOLS/apktool_${APKTOOL_VERSION}.jar" "$APKTOOL_JAR"
  else
    curl -fL --retry 3 -o "$APKTOOL_JAR" \
      "https://github.com/iBotPeaches/Apktool/releases/download/v${APKTOOL_VERSION}/apktool_${APKTOOL_VERSION}.jar"
  fi
fi
printf '%s  %s\n' "$APKTOOL_SHA256" "$APKTOOL_JAR" | sha256sum --check --status

if [[ -d "$WORK_TREE" ]]; then
  mv "$WORK_TREE" "$BUILD_DIR/apktool.previous.$(date +%s)"
fi
java -jar "$APKTOOL_JAR" decode --frame-path "$PATRIOT_TOOLS/framework-device" \
  --force --output "$WORK_TREE" "$STOCK_DIR/base.apk"

BUNDLE_ORIG="$WORK_TREE/assets/index.android.bundle"
PATCH_DIR="$BUILD_DIR/patch"
rm -rf "$PATCH_DIR"
mkdir -p "$PATCH_DIR"

# ---------------------------------------------------------------------------
# 1. Same-length string table patches
# ---------------------------------------------------------------------------
# auth.numinar.com is a 16-char entry and the Auth0 SDK rejects domains with a
# scheme, so a host:port longer than 15 chars cannot fit it. In that case the
# 32-char MIXPANEL_TOKEN entry is repurposed as the domain carrier and the
# constants module (f18903) is instruction-patched to load it instead.
python3 - "$TARGET_HOST" "$TARGET_PORT" > "$PATCH_DIR/patch_plan.json" <<'PY'
import json, re, sys

host, port = sys.argv[1], sys.argv[2]
origin = f"http://{host}:{port}"
ws_origin = f"ws://{host}:{port}"
hostport = f"{host}:{port}"

def pad_path(base, total):
    """Pad a URL prefix with '/.' segments (OkHttp dot-resolution removes
    them) plus an optional trailing '/' (mock slash-collapse absorbs it)."""
    n = total - len(base)
    pad = "/." * (n // 2) + ("/" if n % 2 else "") if n >= 0 else None
    return base + pad if pad is not None and n >= 0 else None

def pad_domain(base, total):
    n = total - len(base)
    return base + "/" * n if n >= 0 else None

def neuter_sentry(old):
    """Move the Sentry host to the RFC 2606 .invalid TLD, compensating the
    length change inside the hex key so the entry stays same-length."""
    new = old.replace("ingest.sentry.io", "ingest.sentry.invalid", 1)
    assert new != old and len(new) > len(old)
    m = re.search(r"[0-9a-f]{27,32}", new)
    trim = len(new) - len(old)
    new = new[:m.start()] + new[m.start():m.end() - trim] + new[m.end():]
    assert len(new) == len(old), (len(new), len(old))
    return new

pairs = []
for old, base in [
    ("https://fast-api.numinar.com/api", f"{origin}/api"),
    ("https://rust-server.numinar.com", origin),
    ("wss://rust-server.numinar.com/websocket", f"{ws_origin}/websocket"),
]:
    new = pad_path(base, len(old))
    if new is None:
        raise SystemExit(f"target too long for {old!r}: {base!r}")
    pairs.append((old, new))

direct_auth = pad_domain(hostport, 16)
if direct_auth is not None:
    pairs.append(("auth.numinar.com", direct_auth))
    carrier = None
else:
    carrier = pad_domain(hostport, 32)  # carried by the MIXPANEL_TOKEN entry
    pairs.append(("a0a85ec57b490e5801b70f516709000d", carrier))

for old, mock_path, dead in [
    ("https://api.mixpanel.com", f"{origin}/m", "https://mixpanel.invalid"),
    ("https://browser.sentry-cdn.com", f"{origin}/s", "https://sentry-cdn.invalid"),
]:
    new = pad_path(mock_path, len(old))
    if new is None:
        new = pad_path(dead, len(old))
        if new is None:
            new = pad_domain(dead, len(old))
        if new is None:
            raise SystemExit(f"cannot neuter {old!r} at this target length")
    pairs.append((old, new))

pairs.append(("https://95e84220d4cb4014badfe47db424924d@o463956.ingest.sentry.io/5469707",
              neuter_sentry("https://95e84220d4cb4014badfe47db424924d@o463956.ingest.sentry.io/5469707")))
pairs.append(("https://o447951.ingest.sentry.io/api/4509632503087104/envelope/?sentry_version=7&sentry_key=c1dfb07d783ad5325c245c1fd3725390&sentry_client=sentry.javascript.browser%2F1.33.7",
              neuter_sentry("https://o447951.ingest.sentry.io/api/4509632503087104/envelope/?sentry_version=7&sentry_key=c1dfb07d783ad5325c245c1fd3725390&sentry_client=sentry.javascript.browser%2F1.33.7")))
pairs.append(("idif65k6cl4w", "000000000000"))  # ADJUST_APP_TOKEN (initSdk call is also removed)

# Vendor egress isolation (REQUIREMENTS §8.1): Expo push remains blocked.
# Mapbox is the explicit map-rendering exception added 2026-09-23 per user
# direction, so its stock account token is deliberately left untouched.
EXPO_PUSH = "https://exp.host/--/api/v2/"
expo_dead = "https://exp.invalid/api/v2/"
assert len(expo_dead) == len(EXPO_PUSH)
pairs.append((EXPO_PUSH, expo_dead))
EXPO_PUSH2 = "https://exp.host/--/api/v2/push/updateDeviceToken"
expo_dead2 = "https://exp.invalid/api/v2/push/updateDeviceToken"
assert len(expo_dead2) == len(EXPO_PUSH2)
pairs.append((EXPO_PUSH2, expo_dead2))

for old, new in pairs:
    assert len(old) == len(new), (old, new)
print(json.dumps({"pairs": pairs, "carrier": carrier, "hostport": hostport}))
PY
python3 - "$PATCH_DIR/patch_plan.json" > "$PATCH_DIR/strings.tsv" <<'PY'
import json, sys
plan = json.load(open(sys.argv[1]))
for old, new in plan["pairs"]:
    print(f"{old}\t{new}")
PY

cp "$BUNDLE_ORIG" "$PATCH_DIR/bundle.hbc"
while IFS=$'\t' read -r old new; do
  "$HERMES_DECOMP" patch-string --old "$old" --new "$new" \
    "$PATCH_DIR/bundle.hbc" -o "$PATCH_DIR/bundle.next.hbc" >/dev/null
  mv "$PATCH_DIR/bundle.next.hbc" "$PATCH_DIR/bundle.hbc"
  printf 'patched string: %s -> %s\n' "$old" "$new"
done < "$PATCH_DIR/strings.tsv"

# ---------------------------------------------------------------------------
# 2. Instruction-level patches (hermes-decomp asm)
# ---------------------------------------------------------------------------
# 2a. The only six `"https://" + AUTH0_DOMAIN` builders in the bundle
#     (auth-session.md §2): SDK baseUrl, passwordless/start, oauth/token x2,
#     userinfo, refresh oauth/token. Downgrade scheme to http:// so auth
#     reaches the plain-HTTP mock. The shared "https://" string entry is left
#     intact for the startsWith() validators that reference it.
AUTH_SCHEME_FUNCS=(19929 21886 21890 21897 22568 22574)
for fn in "${AUTH_SCHEME_FUNCS[@]}"; do
  hasm="$PATCH_DIR/f${fn}.hasm"
  "$HERMES_DECOMP" asm-check --function "$fn" "$PATCH_DIR/bundle.hbc" >/dev/null
  "$HERMES_DECOMP" emit-hasm --function "$fn" "$PATCH_DIR/bundle.hbc" -o "$hasm" >/dev/null
  count="$(grep -cE '^[0-9a-f]+  LoadConstString r[0-9]+, "https://"$' "$hasm")"
  if [[ "$count" != "1" ]]; then
    printf 'function %s: expected 1 auth scheme load, found %s\n' "$fn" "$count" >&2
    exit 1
  fi
  sed -i 's|^\([0-9a-f]*  LoadConstString r[0-9]*, \)"https://"$|\1"http://"|' "$hasm"
  "$HERMES_DECOMP" asm --function "$fn" "$PATCH_DIR/bundle.hbc" "$hasm" \
    -o "$PATCH_DIR/bundle.next.hbc" >/dev/null
  mv "$PATCH_DIR/bundle.next.hbc" "$PATCH_DIR/bundle.hbc"
  printf 'patched function %s: auth URL scheme -> http\n' "$fn"
done

# 2b. Neuter Adjust: drop the Adjust.initSdk(config) call so the SDK never
#     starts (security-antifraud.md: Adjust is the one real tracker here).
ADJUST_FUNC=33115
hasm="$PATCH_DIR/f${ADJUST_FUNC}.hasm"
"$HERMES_DECOMP" asm-check --function "$ADJUST_FUNC" "$PATCH_DIR/bundle.hbc" >/dev/null
"$HERMES_DECOMP" emit-hasm --function "$ADJUST_FUNC" "$PATCH_DIR/bundle.hbc" -o "$hasm" >/dev/null
python3 - "$hasm" <<'PY'
import re, sys
path = sys.argv[1]
lines = open(path).read().splitlines(keepends=True)
for i, line in enumerate(lines):
    if re.search(r'GetById r\d+, r\d+, \d+, "initSdk"$', line.strip()):
        call = lines[i + 1]
        m = re.match(r"^(\s*[0-9a-f]+\s+)Call2 (r\d+), r\d+, r\d+, r\d+\s*$", call)
        if not m:
            raise SystemExit(f"unexpected instruction after initSdk GetById: {call!r}")
        lines[i + 1] = f"{m.group(1)}LoadConstUndefined {m.group(2)}\n"
        open(path, "w").writelines(lines)
        print("neutered Adjust.initSdk call")
        break
else:
    raise SystemExit("initSdk GetById not found in function 33115")
PY
"$HERMES_DECOMP" asm --function "$ADJUST_FUNC" "$PATCH_DIR/bundle.hbc" "$hasm" \
  -o "$PATCH_DIR/bundle.next.hbc" >/dev/null
mv "$PATCH_DIR/bundle.next.hbc" "$PATCH_DIR/bundle.hbc"

# 2c. Carrier variant only: when host:port cannot fit the 16-char
#     auth.numinar.com entry, point the constants module's AUTH0_DOMAIN load
#     at the repurposed MIXPANEL_TOKEN entry (already carrying host:port).
CARRIER="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["carrier"] or "")' "$PATCH_DIR/patch_plan.json")"
if [[ -n "$CARRIER" ]]; then
  CONSTS_FUNC=18903
  hasm="$PATCH_DIR/f${CONSTS_FUNC}.hasm"
  "$HERMES_DECOMP" asm-check --function "$CONSTS_FUNC" "$PATCH_DIR/bundle.hbc" >/dev/null
  "$HERMES_DECOMP" emit-hasm --function "$CONSTS_FUNC" "$PATCH_DIR/bundle.hbc" -o "$hasm" >/dev/null
  count="$(grep -cE '^[0-9a-f]+  LoadConstString r[0-9]+, "auth\.numinar\.com"$' "$hasm")"
  if [[ "$count" != "1" ]]; then
    printf 'function %s: expected 1 auth.numinar.com load, found %s\n' "$CONSTS_FUNC" "$count" >&2
    exit 1
  fi
  python3 - "$hasm" "$CARRIER" <<'PY'
import re, sys
path, carrier = sys.argv[1], sys.argv[2]
text = open(path).read()
new, n = re.subn(
    r'^([0-9a-f]+  LoadConstString r\d+, )"auth\.numinar\.com"$',
    lambda m: m.group(1) + '"' + carrier.replace('\\', '\\\\').replace('"', '\\"') + '"',
    text, count=1, flags=re.M)
if n != 1:
    raise SystemExit("auth.numinar.com load not patched")
open(path, "w").write(new)
print("repointed AUTH0_DOMAIN to carrier string")
PY
  "$HERMES_DECOMP" asm --function "$CONSTS_FUNC" "$PATCH_DIR/bundle.hbc" "$hasm" \
    -o "$PATCH_DIR/bundle.next.hbc" >/dev/null
  mv "$PATCH_DIR/bundle.next.hbc" "$PATCH_DIR/bundle.hbc"
  # The now-unreferenced auth.numinar.com entry must not survive the leak check.
  "$HERMES_DECOMP" patch-string --old "auth.numinar.com" --new "numinar.invalid/" \
    "$PATCH_DIR/bundle.hbc" -o "$PATCH_DIR/bundle.next.hbc" >/dev/null
  mv "$PATCH_DIR/bundle.next.hbc" "$PATCH_DIR/bundle.hbc"
fi

# ---------------------------------------------------------------------------
# 3. Verify the patched bundle: no vendor origins/telemetry strings remain
# ---------------------------------------------------------------------------
"$HERMES_DECOMP" dump --kind strings --json "$PATCH_DIR/bundle.hbc" > "$PATCH_DIR/strings_after.json"
python3 - "$PATCH_DIR/strings_after.json" <<'PY'
import json, sys
vals = [e["value"] or "" for e in json.load(open(sys.argv[1]))]
forbidden = ["fast-api.numinar.com", "rust-server.numinar.com", "auth.numinar.com",
             "api.mixpanel.com", "ingest.sentry.io", "browser.sentry-cdn.com",
             "idif65k6cl4w", "exp.host"]
leaks = sorted({f for f in forbidden for v in vals if f in v})
if leaks:
    raise SystemExit(f"vendor strings remain in bundle: {leaks}")
kept = ["https://api.numinar.com", "https://numinar.com/roles",
        "https://numinar.com/email_verified", "https://mobile.numinar.com/",
        "https://www.numinar.com/privacy",
        "sk.eyJ1IjoibnVtaW5hciI"]
missing = [k for k in kept if not any(k in v for v in vals)]
if missing:
    raise SystemExit(f"expected keep-list strings missing: {missing}")
print("bundle string verification passed (vendor origins/telemetry gone, JWT claim names kept)")
PY
cp "$PATCH_DIR/bundle.hbc" "$BUNDLE_ORIG"

# ---------------------------------------------------------------------------
# 4. Manifest + resources: cleartext to the mock, no OTA, no SDK autostart
# ---------------------------------------------------------------------------
# base-config cleartext: domain-config entries do not reliably match raw IP
# literals, and this build's whole purpose is plain-HTTP to the mock.
cat > "$WORK_TREE/res/xml/network_security_config.xml" <<'XML'
<?xml version="1.0" encoding="utf-8"?>
<network-security-config>
    <base-config cleartextTrafficPermitted="true" />
</network-security-config>
XML
python3 - "$WORK_TREE/AndroidManifest.xml" "$TARGET_HOST" "$TARGET_PORT" <<'PY'
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

manifest = Path(sys.argv[1])
target_host, target_port = sys.argv[2], sys.argv[3]
text = manifest.read_text(encoding="utf-8")
attribute = 'android:networkSecurityConfig="@xml/network_security_config"'
if attribute not in text:
    needle = "<application "
    if needle not in text:
        raise SystemExit("application element not found")
    text = text.replace(needle, f"<application {attribute} ", 1)

# expo-updates would download the vendor OTA bundle over our patched one.
if '<meta-data android:name="expo.modules.updates.ENABLED" android:value="true"/>' not in text:
    raise SystemExit("expo-updates ENABLED meta-data not found in expected form")
text = text.replace(
    '<meta-data android:name="expo.modules.updates.ENABLED" android:value="true"/>',
    '<meta-data android:name="expo.modules.updates.ENABLED" android:value="false"/>', 1)

# Google Maps is the explicit map-rendering exception added 2026-09-23 per
# user direction. Verify that apktool recovered the stock key, then preserve
# it byte-for-byte in the repointed build.
import re as _re
keys = _re.findall(
    r'<meta-data android:name="com\.google\.android\.geo\.API_KEY" android:value="([^"]+)"/>',
    text)
if len(keys) != 1:
    raise SystemExit(f"expected one non-empty stock google geo API_KEY, found {len(keys)}")
print("preserved stock Google geo API key")

android = "http://schemas.android.com/apk/res/android"
ET.register_namespace("android", android)
root = ET.fromstring(text)
application = root.find("application")
if application is None:
    raise SystemExit("application element not found after parsing")

# SDK-owned autostart components. The app must not phone vendor SDKs from the
# repointed build; JS-side Sentry/Mixpanel/Adjust are neutered in the bundle.
disabled_components = {
    "com.adjust.sdk.AdjustReferrerReceiver",
    "com.adjust.sdk.SystemLifecycleContentProvider",
    "io.sentry.android.core.SentryInitProvider",
    "io.sentry.android.core.SentryPerformanceProvider",
    "io.intercom.android.sdk.IntercomInitializeContentProvider",
    "com.google.firebase.provider.FirebaseInitProvider",
    "com.google.firebase.components.ComponentDiscoveryService",
    "com.google.firebase.iid.FirebaseInstanceIdReceiver",
    "com.google.firebase.messaging.FirebaseMessagingService",
    "expo.modules.notifications.service.ExpoFirebaseMessagingService",
    "com.twiliovoicereactnative.VoiceFirebaseMessagingService",
    "com.google.android.datatransport.runtime.backends.TransportBackendDiscovery",
    "com.google.android.datatransport.runtime.scheduling.jobscheduling.JobInfoSchedulerService",
    "com.google.android.datatransport.runtime.scheduling.jobscheduling.AlarmManagerSchedulerBroadcastReceiver",
}
disabled = set()
for node in application.iter():
    name = node.get(f"{{{android}}}name")
    if name in disabled_components:
        node.set(f"{{{android}}}enabled", "false")
        disabled.add(name)
print(f"disabled {len(disabled)} SDK components; not present: {sorted(disabled_components - disabled)}")

# Universal Login completes via a custom-scheme redirect whose host is the
# Auth0 domain — which the repoint retargets to the mock. The stock intent
# filter only matches host=auth.numinar.com, so add a parallel data spec for
# the mock host (no path constraint: the padded domain leaves '/' runs).
AUTH0_SCHEME = "com.numinar.numinar.auth0"
patched_filter = False
for filt in application.iter("intent-filter"):
    datas = list(filt.findall("data"))
    if any(d.get(f"{{{android}}}scheme") == AUTH0_SCHEME for d in datas):
        data = ET.SubElement(filt, "data")
        data.set(f"{{{android}}}scheme", AUTH0_SCHEME)
        data.set(f"{{{android}}}host", target_host)
        data.set(f"{{{android}}}port", target_port)
        patched_filter = True
if not patched_filter:
    raise SystemExit("auth0 callback intent-filter not found")
print(f"added auth0 callback intent-filter data for {target_host}:{target_port}")

manifest.write_bytes(ET.tostring(root, encoding="utf-8", xml_declaration=True))
PY

# ---------------------------------------------------------------------------
# 5. Native Auth0 SDK: Universal Login must also reach the plain-HTTP mock
# ---------------------------------------------------------------------------
# The JS-side auth builders are patched in the bundle, but the webAuth
# ("Log in with password" / Google) flow builds its /authorize URL natively:
# Auth0$Companion.getDomainUrl prepends "https://" to any scheme-less domain.
# Flip that one const-string to "http://"; scheme-ful domains pass through
# untouched either way.
AUTH0_COMPANION="$WORK_TREE/smali_classes3/com/auth0/android/Auth0\$Companion.smali"
count="$(grep -c 'const-string p1, "https://"' "$AUTH0_COMPANION")"
if [[ "$count" != "1" ]]; then
  printf 'expected 1 native https scheme constant in Auth0$Companion, found %s\n' "$count" >&2
  exit 1
fi
sed -i 's|const-string p1, "https://"|const-string p1, "http://"|' "$AUTH0_COMPANION"
printf 'patched native Auth0 domain scheme -> http\n'

# ---------------------------------------------------------------------------
# 6. Rebuild, align, sign (local throwaway key), verify
# ---------------------------------------------------------------------------
java -jar "$APKTOOL_JAR" build --frame-path "$PATRIOT_TOOLS/framework-device" \
  "$WORK_TREE" -o "$BUILD_DIR/base-unsigned.apk"
"$ZIPALIGN" -f 4 "$BUILD_DIR/base-unsigned.apk" "$OUT_DIR/base-aligned.apk"

KEYSTORE="$BUILD_DIR/repoint-debug.keystore"
if [[ ! -f "$KEYSTORE" ]]; then
  keytool -genkeypair -noprompt \
    -keystore "$KEYSTORE" -storepass android -keypass android \
    -alias repointdebug -keyalg RSA -keysize 2048 -validity 10000 \
    -dname "CN=Numinar Mock Repoint,OU=Instrumentation,O=AlaskaWalker,C=US"
fi

"$APKSIGNER" sign --ks "$KEYSTORE" --ks-key-alias repointdebug \
  --ks-pass pass:android --key-pass pass:android \
  --out "$OUT_DIR/base.apk" "$OUT_DIR/base-aligned.apk"

for split in "$STOCK_DIR"/split_*.apk; do
  name="$(basename "$split")"
  aligned="$OUT_DIR/${name%.apk}-aligned.apk"
  "$ZIPALIGN" -f 4 "$split" "$aligned"
  zip -q -d "$aligned" \
    'META-INF/*.RSA' 'META-INF/*.DSA' 'META-INF/*.EC' \
    'META-INF/*.SF' 'META-INF/MANIFEST.MF' 2>/dev/null || true
  "$APKSIGNER" sign --ks "$KEYSTORE" --ks-key-alias repointdebug \
    --ks-pass pass:android --key-pass pass:android \
    --out "$OUT_DIR/$name" "$aligned"
done

"$APKSIGNER" verify --verbose "$OUT_DIR/base.apk" >/dev/null
for split in "$STOCK_DIR"/split_*.apk; do
  "$APKSIGNER" verify --verbose "$OUT_DIR/$(basename "$split")" >/dev/null
done
printf 'Signature verification passed for base and split APKs.\n'

printf '\nRepointed APK set (mock at http://%s:%s):\n' "$TARGET_HOST" "$TARGET_PORT"
find "$OUT_DIR" -maxdepth 1 -type f -name '*.apk' ! -name '*-aligned.apk' -printf '  %p\n' | sort
printf '\nInstall (remove the vendor-signed app first):\n'
printf '  adb install-multiple %q/base.apk %q/split_config.arm64_v8a.apk %q/split_config.en.apk %q/split_config.xxhdpi.apk\n' "$OUT_DIR" "$OUT_DIR" "$OUT_DIR" "$OUT_DIR"
if [[ "$TARGET_HOST" == "127.0.0.1" || "$TARGET_HOST" == "localhost" ]]; then
  printf '  adb reverse tcp:%s tcp:%s\n' "$TARGET_PORT" "$TARGET_PORT"
fi
