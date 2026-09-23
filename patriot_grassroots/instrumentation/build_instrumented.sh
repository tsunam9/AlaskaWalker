#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/../.." && pwd)"
STOCK_DIR="$REPO_ROOT/patriot_grassroots/stock"
BUILD_VARIANT="${BUILD_VARIANT:-capture}"
CAPTURE_HOOKS="${CAPTURE_HOOKS:-1}"
TARGET_HTTP_ORIGIN="${TARGET_HTTP_ORIGIN:-http://127.0.0.1:18080}"
TARGET_WS_ORIGIN="${TARGET_WS_ORIGIN:-${TARGET_HTTP_ORIGIN/http:/ws:}}"
if [[ "$BUILD_VARIANT" == "capture" ]]; then
  BUILD_DIR="$SCRIPT_DIR/build"
else
  BUILD_DIR="$SCRIPT_DIR/build-$BUILD_VARIANT"
fi
WORK_TREE="$BUILD_DIR/apktool"
OUT_DIR="$BUILD_DIR/out"
TOOLS_DIR="$SCRIPT_DIR/.tools"
APKTOOL_VERSION="3.0.3"
APKTOOL_JAR="$TOOLS_DIR/apktool_${APKTOOL_VERSION}.jar"
FRAME_DIR="${APKTOOL_FRAME_DIR:-$TOOLS_DIR/framework-device}"
APKTOOL_SHA256="dbf930b076c6b9be08d57c449cacefc3bdd6b71ebd59b3066fc0e1f5b14f9423"
SDK_ROOT="${ANDROID_SDK_ROOT:-${ANDROID_HOME:-/home/jjlar/Android/Sdk}}"

if [[ ! -f "$STOCK_DIR/base.apk" ]]; then
  printf 'Stock base APK is missing.\n' >&2
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
  curl -fL --retry 3 -o "$APKTOOL_JAR" \
    "https://github.com/iBotPeaches/Apktool/releases/download/v${APKTOOL_VERSION}/apktool_${APKTOOL_VERSION}.jar"
fi
printf '%s  %s\n' "$APKTOOL_SHA256" "$APKTOOL_JAR" | sha256sum --check --status

# Decode afresh because the checked-in evidence tree was produced with an older,
# locally patched Apktool and is intentionally not a round-trip build input.
if [[ -d "$WORK_TREE" ]]; then
  mv "$WORK_TREE" "$BUILD_DIR/apktool.previous.$(date +%s)"
fi
java -jar "$APKTOOL_JAR" decode --frame-path "$FRAME_DIR" --force --output "$WORK_TREE" "$STOCK_DIR/base.apk"

python3 - "$WORK_TREE/AndroidManifest.xml" "$WORK_TREE/res/values/public.xml" <<'PY'
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

manifest = Path(sys.argv[1])
text = manifest.read_text(encoding="utf-8")
needle = "<application "
attribute = 'android:networkSecurityConfig="@xml/network_security_config"'
if attribute not in text:
    if needle not in text:
        raise SystemExit("application element not found")
    text = text.replace(needle, f"<application {attribute} ", 1)
missing_split_icon = (
    '<meta-data android:name="com.google.firebase.messaging.default_notification_icon" '
    'android:resource="@null"/>'
)
restored_split_icon = (
    '<meta-data android:name="com.google.firebase.messaging.default_notification_icon" '
    'android:resource="@drawable/ic_stat_patriot_notifications"/>'
)
if missing_split_icon not in text:
    raise SystemExit("split notification icon placeholder not found")
text = text.replace(missing_split_icon, restored_split_icon, 1)

# Disable SDK-owned network components. Their protocols cannot be redirected to an
# HTTP fixture with wire parity, so the audit build replaces their app-facing calls
# with local fixtures and prevents the vendor runtimes from opening sockets.
android = "http://schemas.android.com/apk/res/android"
ET.register_namespace("android", android)
root = ET.fromstring(text)
application = root.find("application")
if application is None:
    raise SystemExit("application element not found after parsing")

metadata = {
    "firebase_messaging_auto_init_enabled": "false",
    "firebase_analytics_collection_enabled": "false",
    "firebase_data_collection_default_enabled": "false",
}
for name, value in metadata.items():
    node = next(
        (item for item in application.findall("meta-data") if item.get(f"{{{android}}}name") == name),
        None,
    )
    if node is None:
        node = ET.SubElement(application, "meta-data")
        node.set(f"{{{android}}}name", name)
    node.set(f"{{{android}}}value", value)

disabled_components = {
    "io.capawesome.capacitorjs.plugins.firebase.messaging.MessagingService",
    "com.google.firebase.iid.FirebaseInstanceIdReceiver",
    "com.google.firebase.messaging.FirebaseMessagingService",
    "com.google.firebase.components.ComponentDiscoveryService",
    "com.google.android.gms.measurement.AppMeasurementReceiver",
    "com.google.android.gms.measurement.AppMeasurementService",
    "com.google.android.gms.measurement.AppMeasurementJobService",
    "com.google.firebase.provider.FirebaseInitProvider",
    "io.sentry.android.core.SentryInitProvider",
    "io.sentry.android.core.SentryPerformanceProvider",
    "com.google.android.datatransport.runtime.backends.TransportBackendDiscovery",
    "com.google.android.datatransport.runtime.scheduling.jobscheduling.JobInfoSchedulerService",
    "com.google.android.datatransport.runtime.scheduling.jobscheduling.AlarmManagerSchedulerBroadcastReceiver",
}
disabled = set()
for node in application:
    name = node.get(f"{{{android}}}name")
    if name in disabled_components:
        node.set(f"{{{android}}}enabled", "false")
        disabled.add(name)
missing = disabled_components - disabled
if missing:
    raise SystemExit(f"expected SDK components missing from manifest: {sorted(missing)}")

manifest.write_bytes(ET.tostring(root, encoding="utf-8", xml_declaration=True))

# The notification icon's definition and only file configuration live in the
# xxhdpi split. Apktool otherwise decodes the base manifest reference as @null,
# which Android rejects as malformed. Restore its original stable resource ID.
public_xml = Path(sys.argv[2])
public = public_xml.read_text(encoding="utf-8")
entry = '    <public type="drawable" name="ic_stat_patriot_notifications" id="0x7f0800b4" />\n'
if entry not in public:
    public = public.replace("</resources>", entry + "</resources>", 1)
public_xml.write_text(public, encoding="utf-8")
PY
cp "$SCRIPT_DIR/network_security_config.xml" "$WORK_TREE/res/xml/network_security_config.xml"
mkdir -p "$WORK_TREE/res/drawable"
unzip -p "$STOCK_DIR/split_config.xxhdpi.apk" \
  res/drawable-xxhdpi-v4/ic_stat_patriot_notifications.png \
  > "$WORK_TREE/res/drawable/ic_stat_patriot_notifications.png"

# PairIP binds the store signature to its Play license response. An audit build is
# necessarily re-signed, so make the shared license entry point a no-op.
python3 - "$WORK_TREE/smali/com/pairip/licensecheck/LicenseClient.smali" <<'PY'
from pathlib import Path
import re
import sys

target = Path(sys.argv[1])
text = target.read_text(encoding="utf-8")
pattern = re.compile(
    r"\.method public static checkLicense\(Landroid/content/Context;\)V\n.*?\n\.end method",
    re.DOTALL,
)
replacement = """.method public static checkLicense(Landroid/content/Context;)V
    .locals 0

    return-void
.end method"""
text, count = pattern.subn(replacement, text, count=1)
if count != 1:
    raise SystemExit(f"PairIP checkLicense patch count was {count}, expected 1")
target.write_text(text, encoding="utf-8")
print("Disabled PairIP license entry point for the locally signed audit build.")
PY

# Capture the exact FCM objects delivered into the app. The transport socket belongs
# to Google Play Services and may not be decryptable by an app-scoped CA trust patch.
if [[ "$CAPTURE_HOOKS" == "1" ]]; then
  cp "$SCRIPT_DIR/capture_inbound.js" "$WORK_TREE/assets/public/capture-inbound.js"
fi
python3 - "$WORK_TREE/assets/public" "$CAPTURE_HOOKS" "$TARGET_HTTP_ORIGIN" "$TARGET_WS_ORIGIN" <<'PY'
from pathlib import Path
import sys

public = Path(sys.argv[1])
capture_hooks = sys.argv[2] == "1"
target_http = sys.argv[3].rstrip("/")
target_ws = sys.argv[4].rstrip("/")
if not target_http.startswith(("http://", "https://")):
    raise SystemExit(f"invalid TARGET_HTTP_ORIGIN: {target_http}")
if not target_ws.startswith(("ws://", "wss://")):
    raise SystemExit(f"invalid TARGET_WS_ORIGIN: {target_ws}")
loader = '<script src="/capture-inbound.js"></script>'
html_files = list(public.rglob("*.html"))
if capture_hooks:
    for html in html_files:
        text = html.read_text(encoding="utf-8")
        if loader not in text:
            marker = '<script type="module"'
            if marker not in text:
                raise SystemExit(f"Nuxt module marker not found in {html}")
            text = text.replace(marker, loader + marker, 1)
            html.write_text(text, encoding="utf-8")

callbacks = {
    'jr.addListener("tokenReceived",async i=>{': "tokenReceived",
    'jr.addListener("notificationReceived",async i=>{': "notificationReceived",
    'jr.addListener("notificationActionPerformed",async i=>{': "notificationActionPerformed",
}
matches = {marker: [] for marker in callbacks}
if capture_hooks:
    for javascript in (public / "_nuxt").glob("*.js"):
        text = javascript.read_text(encoding="utf-8")
        changed = False
        for marker, event_name in callbacks.items():
            if marker in text:
                injection = marker + f'globalThis.__patriotCaptureInbound?.("{event_name}",i);'
                text = text.replace(marker, injection, 1)
                matches[marker].append(javascript)
                changed = True
        if changed:
            javascript.write_text(text, encoding="utf-8")

    bad = {marker: files for marker, files in matches.items() if len(files) != 1}
    if bad:
        details = ", ".join(f"{marker}: {len(files)}" for marker, files in bad.items())
        raise SystemExit(f"FCM callback patch count mismatch ({details})")

# Route every recovered runtime origin to the selected isolated backend. Source maps
# are evidence only and are deliberately left intact; executable HTML/JS is audited.
origin_replacements = {
    "wss://api.validnation.ai/api/ws": f"{target_ws}/api/ws",
    "https://api.validnation.ai": target_http,
    "https://tfnnpqpvdjisoizvciyr.supabase.co": target_http,
    "https://google.com/generate_204": f"{target_http}/generate_204",
    "https://maps.googleapis.com/maps/api/js?": f"{target_http}/maps/api/js?",
    "https://fcmregistrations.googleapis.com/v1": f"{target_http}/firebase/fcmregistrations/v1",
    "https://firebaseremoteconfig.googleapis.com": f"{target_http}/firebase/remoteconfig",
    "https://firebaseinstallations.googleapis.com/v1": f"{target_http}/firebase/installations/v1",
    "https://browser.sentry-cdn.com": f"{target_http}/sentry-cdn",
    "https://o447951.ingest.sentry.io": f"{target_http}/api/sentry",
    "https://unpkg.com": f"{target_http}/unpkg",
    "https://www.gstatic.com/firebasejs": f"{target_http}/firebasejs",
    "https://apps.apple.com": f"{target_http}/external/apple-store",
    "https://play.google.com": f"{target_http}/external/play-store",
}
runtime_files = [
    path
    for path in public.rglob("*")
    if path.is_file()
    and path.suffix in {".html", ".js", ".json", ".webmanifest"}
    and not path.name.endswith(".js.map")
]
replacement_counts = {origin: 0 for origin in origin_replacements}
for path in runtime_files:
    text = path.read_text(encoding="utf-8", errors="strict")
    original = text
    for origin, local in origin_replacements.items():
        count = text.count(origin)
        if count:
            replacement_counts[origin] += count
            text = text.replace(origin, local)
    # Disable platform-specific Sentry DSNs copied into every prerendered page.
    text = __import__("re").sub(r'dsn(Ios|Android):"[^"]*"', lambda m: f'dsn{m.group(1)}:""', text)
    # Keep the embedded policy page available as stock content, but make the one
    # consent-form hyperlink inert so it cannot navigate to any policy destination.
    text = text.replace('href:"/privacy-policy"', 'href:"#"')
    text = text.replace("privacy@patriotgrassroots.com", "Privacy contact unavailable in this isolated build")
    if text != original:
        path.write_text(text, encoding="utf-8")

required_origins = {
    "wss://api.validnation.ai/api/ws",
    "https://api.validnation.ai",
    "https://tfnnpqpvdjisoizvciyr.supabase.co",
    "https://google.com/generate_204",
}
missing_required = [origin for origin in required_origins if replacement_counts[origin] == 0]
if missing_required:
    raise SystemExit(f"required runtime origins were not found: {missing_required}")

forbidden = (
    "api.validnation.ai",
    "tfnnpqpvdjisoizvciyr.supabase.co",
    "ingest.sentry.io",
    "google.com/generate_204",
    "maps.googleapis.com",
    "fcmregistrations.googleapis.com",
    "firebaseremoteconfig.googleapis.com",
    "firebaseinstallations.googleapis.com",
    "browser.sentry-cdn.com",
    "unpkg.com",
    "apps.apple.com",
    "play.google.com",
    "patriotgrassroots.com",
)
leaks = []
for path in runtime_files:
    text = path.read_text(encoding="utf-8", errors="strict")
    hits = [host for host in forbidden if host in text]
    if hits:
        leaks.append(f"{path.relative_to(public)}: {', '.join(hits)}")
if leaks:
    raise SystemExit("vendor runtime origins remain:\n" + "\n".join(leaks))

hook_summary = (
    f"injected capture loader into {len(html_files)} HTML files and instrumented three FCM callbacks"
    if capture_hooks else "left stock application callbacks untouched"
)
print(
    f"{hook_summary}; rerouted {sum(replacement_counts.values())} runtime origins "
    f"to {target_http}."
)
PY

java -jar "$APKTOOL_JAR" build --frame-path "$FRAME_DIR" "$WORK_TREE" -o "$BUILD_DIR/base-unsigned.apk"
"$ZIPALIGN" -f 4 "$BUILD_DIR/base-unsigned.apk" "$OUT_DIR/base-aligned.apk"

KEYSTORE="$BUILD_DIR/capture-debug.keystore"
if [[ ! -f "$KEYSTORE" ]]; then
  keytool -genkeypair -noprompt \
    -keystore "$KEYSTORE" -storepass android -keypass android \
    -alias capturedebug -keyalg RSA -keysize 2048 -validity 10000 \
    -dname "CN=Local Traffic Capture,OU=Instrumentation,O=AlaskaWalker,C=US"
fi

"$APKSIGNER" sign --ks "$KEYSTORE" --ks-key-alias capturedebug \
  --ks-pass pass:android --key-pass pass:android \
  --out "$OUT_DIR/base.apk" "$OUT_DIR/base-aligned.apk"

for split in "$STOCK_DIR"/split_*.apk; do
  name="$(basename "$split")"
  aligned="$OUT_DIR/${name%.apk}-aligned.apk"
  "$ZIPALIGN" -f 4 "$split" "$aligned"
  # apksigner does not remove the copied split's old JAR/v1 signature files.
  # Leaving them in place makes verification correctly report a stripped v2/v3
  # signature. Remove them from this copied artifact before locally signing it.
  zip -q -d "$aligned" \
    'META-INF/*.RSA' 'META-INF/*.DSA' 'META-INF/*.EC' \
    'META-INF/*.SF' 'META-INF/MANIFEST.MF'
  "$APKSIGNER" sign --ks "$KEYSTORE" --ks-key-alias capturedebug \
    --ks-pass pass:android --key-pass pass:android \
    --out "$OUT_DIR/$name" "$aligned"
done

"$APKSIGNER" verify --verbose "$OUT_DIR/base.apk" >/dev/null
for split in "$STOCK_DIR"/split_*.apk; do
  "$APKSIGNER" verify --verbose "$OUT_DIR/$(basename "$split")" >/dev/null
done
printf 'Signature verification passed for base and split APKs.\n'
printf '\nRebuilt and consistently signed APK set:\n'
find "$OUT_DIR" -maxdepth 1 -type f -name '*.apk' ! -name '*-aligned.apk' -printf '  %p\n' | sort
printf '\nInstall on a disposable emulator/device after removing the vendor-signed app:\n'
printf '  adb install-multiple %q/base.apk %q/split_config.arm64_v8a.apk %q/split_config.en.apk %q/split_config.xxhdpi.apk\n' "$OUT_DIR" "$OUT_DIR" "$OUT_DIR" "$OUT_DIR"
