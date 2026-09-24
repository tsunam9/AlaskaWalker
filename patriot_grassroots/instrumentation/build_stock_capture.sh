#!/usr/bin/env bash
# Build a stock-derived Patriot APK set for pass-through capture of real backends.
# Frozen stock APKs and the existing mock/repoint build are never used as work input.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/../.." && pwd)"
STOCK_DIR="$REPO_ROOT/patriot_grassroots/stock"
BUILD_DIR="$SCRIPT_DIR/build-stock-capture"
WORK_TREE="$BUILD_DIR/apktool"
OUT_DIR="$BUILD_DIR/out"
TOOLS_DIR="$SCRIPT_DIR/.tools"
APKTOOL_VERSION="3.0.3"
APKTOOL_JAR="$TOOLS_DIR/apktool_${APKTOOL_VERSION}.jar"
APKTOOL_SHA256="dbf930b076c6b9be08d57c449cacefc3bdd6b71ebd59b3066fc0e1f5b14f9423"
FRAME_DIR="${APKTOOL_FRAME_DIR:-$TOOLS_DIR/framework-device}"
SDK_ROOT="${ANDROID_SDK_ROOT:-${ANDROID_HOME:-$HOME/Android/Sdk}}"
LOGGER_UPLOAD_URL="${LOGGER_UPLOAD_URL:-}"
LOGGER_UPLOAD_TOKEN="${LOGGER_UPLOAD_TOKEN:-}"

case "$LOGGER_UPLOAD_URL" in
  ""|http://*|https://*) ;;
  *)
    printf 'LOGGER_UPLOAD_URL must be empty or an http(s) URL.\n' >&2
    exit 1
    ;;
esac

declare -A EXPECTED_SHA256=(
  [base.apk]="47b19ff8bee2b7f3742253e741273dbeb589c5f04ce864c8b90c7241ecf44bb1"
  [split_config.arm64_v8a.apk]="2144bffb8a6df9186f249c4926734e011d3e42efc5ff572d00b3cce9738dd383"
  [split_config.en.apk]="67a398197358845961c35539a0104444edf04f494996f7f5c167294f7a7ecb4b"
  [split_config.xxhdpi.apk]="87e730ff88cc9225805d36f0b4f33672f2f00f55faff782368fdd7d58ec5e281"
)
for name in "${!EXPECTED_SHA256[@]}"; do
  printf '%s  %s\n' "${EXPECTED_SHA256[$name]}" "$STOCK_DIR/$name" \
    | sha256sum --check --status || {
      printf 'Frozen stock hash mismatch: %s\n' "$name" >&2
      exit 1
    }
done

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

if [[ -d "$WORK_TREE" ]]; then
  mv "$WORK_TREE" "$BUILD_DIR/apktool.previous.$(date +%s)"
fi
java -jar "$APKTOOL_JAR" decode --frame-path "$FRAME_DIR" --force \
  --output "$WORK_TREE" "$STOCK_DIR/base.apk"

# Freeze the shipped web runtime before the audited Sentry configuration change.
find "$WORK_TREE/assets/public" -type f -print0 | sort -z \
  | xargs -0 sha256sum > "$BUILD_DIR/runtime-before.sha256"

python3 - "$WORK_TREE/AndroidManifest.xml" "$WORK_TREE/res/values/public.xml" <<'PY'
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

manifest = Path(sys.argv[1])
text = manifest.read_text(encoding="utf-8")

# This resource lives only in the density split. Restore the stock reference so
# Apktool can round-trip the base manifest, exactly as the existing builder does.
missing_icon = (
    '<meta-data android:name="com.google.firebase.messaging.default_notification_icon" '
    'android:resource="@null"/>'
)
stock_icon = (
    '<meta-data android:name="com.google.firebase.messaging.default_notification_icon" '
    'android:resource="@drawable/ic_stat_patriot_notifications"/>'
)
if text.count(missing_icon) != 1:
    raise SystemExit("split notification icon placeholder not found exactly once")
text = text.replace(missing_icon, stock_icon, 1)

android = "http://schemas.android.com/apk/res/android"
ET.register_namespace("android", android)
root = ET.fromstring(text)
application = root.find("application")
if application is None:
    raise SystemExit("application element not found")

metadata = {
    "firebase_messaging_auto_init_enabled": "false",
    "firebase_analytics_collection_enabled": "false",
    "firebase_data_collection_default_enabled": "false",
    "io.sentry.auto-init": "false",
}
for name, value in metadata.items():
    node = next(
        (item for item in application.findall("meta-data")
         if item.get(f"{{{android}}}name") == name),
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
for node in application.iter():
    name = node.get(f"{{{android}}}name")
    if name in disabled_components:
        node.set(f"{{{android}}}enabled", "false")
        disabled.add(name)
missing = disabled_components - disabled
if missing:
    raise SystemExit(f"expected Firebase/Sentry components missing: {sorted(missing)}")

manifest.write_bytes(ET.tostring(root, encoding="utf-8", xml_declaration=True))

public_xml = Path(sys.argv[2])
public = public_xml.read_text(encoding="utf-8")
entry = '    <public type="drawable" name="ic_stat_patriot_notifications" id="0x7f0800b4" />\n'
if entry not in public:
    public = public.replace("</resources>", entry + "</resources>", 1)
public_xml.write_text(public, encoding="utf-8")
PY

mkdir -p "$WORK_TREE/res/drawable"
unzip -p "$STOCK_DIR/split_config.xxhdpi.apk" \
  res/drawable-xxhdpi-v4/ic_stat_patriot_notifications.png \
  > "$WORK_TREE/res/drawable/ic_stat_patriot_notifications.png"

# PairIP binds startup to the Play-installed vendor signature. A locally signed APK
# cannot pass that gate. This is the only executable-code change in this variant.
PAIRIP_FILE="$(find "$WORK_TREE" -path '*/com/pairip/licensecheck/LicenseClient.smali' -print -quit)"
if [[ -z "$PAIRIP_FILE" ]]; then
  printf 'PairIP LicenseClient.smali was not found.\n' >&2
  exit 1
fi
python3 - "$PAIRIP_FILE" <<'PY'
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
PY

# Patriot's browser Sentry DSN is already empty in stock. Its native plugin
# explicitly treats an empty platform DSN as "skip init", so blank only those
# two runtime fields and preserve every real backend origin.
python3 - "$WORK_TREE/assets/public" <<'PY'
from pathlib import Path
import re
import sys

root = Path(sys.argv[1])
patterns = {
    "dsnIos": re.compile(r'dsnIos:"[^"]*"'),
    "dsnAndroid": re.compile(r'dsnAndroid:"[^"]*"'),
}
counts = {name: 0 for name in patterns}
for path in root.rglob("*"):
    if not path.is_file() or path.suffix not in {".html", ".js", ".json", ".webmanifest"}:
        continue
    raw = path.read_text(encoding="utf-8")
    changed = raw
    for name, pattern in patterns.items():
        changed, count = pattern.subn(f'{name}:""', changed)
        counts[name] += count
    if changed != raw:
        path.write_text(changed, encoding="utf-8")
if not all(counts.values()):
    raise SystemExit(f"Sentry platform DSNs were not found: {counts}")
print(f"blanked Patriot native Sentry DSNs: {counts}")
PY

"$REPO_ROOT/traffic_capture/inject_android_recorder.sh" \
  "$WORK_TREE" smali_classes5 "$TOOLS_DIR" "$SDK_ROOT"

MAIN_ACTIVITY="$(find "$WORK_TREE" -path '*/com/patriotgrassroots/validnation/MainActivity.smali' -print -quit)"
CAPACITOR_BRIDGE="$(find "$WORK_TREE" -path '*/com/getcapacitor/Bridge.smali' -print -quit)"
if [[ -z "$MAIN_ACTIVITY" || -z "$CAPACITOR_BRIDGE" ]]; then
  printf 'Required Patriot activity/bridge smali was not found.\n' >&2
  exit 1
fi
python3 - "$MAIN_ACTIVITY" "$CAPACITOR_BRIDGE" \
  "$LOGGER_UPLOAD_URL" "$LOGGER_UPLOAD_TOKEN" <<'PY'
from pathlib import Path
import sys

activity_path, bridge_path = map(Path, sys.argv[1:3])
logger_url, logger_token = sys.argv[3:5]

def smali_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r")

activity = activity_path.read_text(encoding="utf-8")
if ".method protected load()V" in activity:
    raise SystemExit("Patriot MainActivity already overrides load")
activity += f"""

.method protected load()V
    .locals 3

    const-string v0, "patriot"

    const-string v1, "{smali_string(logger_url)}"

    const-string v2, "{smali_string(logger_token)}"

    invoke-static {{p0, v0, v1, v2}}, Lai/alaskawalker/capture/InAppTrafficRecorder;->configure(Landroid/content/Context;Ljava/lang/String;Ljava/lang/String;Ljava/lang/String;)V

    invoke-super {{p0}}, Lcom/getcapacitor/BridgeActivity;->load()V

    return-void
.end method
"""
activity_path.write_text(activity, encoding="utf-8")

bridge = bridge_path.read_text(encoding="utf-8")
needle = """.method private loadWebView()V
    .locals 8
"""
replacement = """.method private loadWebView()V
    .locals 8

    iget-object v0, p0, Lcom/getcapacitor/Bridge;->webView:Landroid/webkit/WebView;

    invoke-static {v0}, Lai/alaskawalker/capture/InAppTrafficRecorder;->attachWebView(Landroid/webkit/WebView;)V
"""
if bridge.count(needle) != 1:
    raise SystemExit("unexpected Capacitor Bridge.loadWebView shape")
bridge_path.write_text(bridge.replace(needle, replacement, 1), encoding="utf-8")
PY

cp "$REPO_ROOT/traffic_capture/patriot_in_app_capture.js" \
  "$WORK_TREE/assets/public/alaska-in-app-capture.js"
python3 - "$WORK_TREE/assets/public" <<'PY'
from pathlib import Path
import sys

root = Path(sys.argv[1])
tag = '<script src="/alaska-in-app-capture.js"></script>'
count = 0
for path in root.rglob("*.html"):
    text = path.read_text(encoding="utf-8")
    if tag in text:
        raise SystemExit(f"capture script already present: {path}")
    needle = '<script type="module"'
    if needle not in text:
        continue
    path.write_text(text.replace(needle, tag + needle, 1), encoding="utf-8")
    count += 1
if count == 0:
    raise SystemExit("no Patriot HTML entry points accepted the capture script")
print(f"injected Patriot in-app capture into {count} HTML entry points")
PY

find "$WORK_TREE/assets/public" -type f -print0 | sort -z \
  | xargs -0 sha256sum > "$BUILD_DIR/runtime-after.sha256"
grep -Rqs 'https://api.validnation.ai' "$WORK_TREE/assets/public"
grep -Rqs 'https://tfnnpqpvdjisoizvciyr.supabase.co' "$WORK_TREE/assets/public"
if grep -RqsE 'dsn(Ios|Android):"https://' "$WORK_TREE/assets/public"; then
  printf 'A native Patriot Sentry DSN remains enabled.\n' >&2
  exit 1
fi
if [[ ! -f "$WORK_TREE/assets/public/alaska-in-app-capture.js" ]]; then
  printf 'Patriot in-app capture script is missing.\n' >&2
  exit 1
fi
grep -Rqs '/alaska-in-app-capture.js' "$WORK_TREE/assets/public" --include='*.html'
printf 'Verified in-app recorder injection, disabled native Sentry DSNs, and retained real origins.\n'

java -jar "$APKTOOL_JAR" build --frame-path "$FRAME_DIR" \
  "$WORK_TREE" -o "$BUILD_DIR/base-unsigned.apk"
"$ZIPALIGN" -f 4 "$BUILD_DIR/base-unsigned.apk" "$OUT_DIR/base-aligned.apk"

KEYSTORE="$BUILD_DIR/stock-capture.keystore"
if [[ ! -f "$KEYSTORE" ]]; then
  keytool -genkeypair -noprompt \
    -keystore "$KEYSTORE" -storepass android -keypass android \
    -alias stockcapture -keyalg RSA -keysize 2048 -validity 10000 \
    -dname "CN=Patriot Stock Capture,OU=Instrumentation,O=AlaskaWalker,C=US"
fi
"$APKSIGNER" sign --ks "$KEYSTORE" --ks-key-alias stockcapture \
  --ks-pass pass:android --key-pass pass:android \
  --out "$OUT_DIR/base.apk" "$OUT_DIR/base-aligned.apk"

for split in "$STOCK_DIR"/split_*.apk; do
  name="$(basename "$split")"
  aligned="$OUT_DIR/${name%.apk}-aligned.apk"
  "$ZIPALIGN" -f 4 "$split" "$aligned"
  zip -q -d "$aligned" \
    'META-INF/*.RSA' 'META-INF/*.DSA' 'META-INF/*.EC' \
    'META-INF/*.SF' 'META-INF/MANIFEST.MF' 2>/dev/null || true
  "$APKSIGNER" sign --ks "$KEYSTORE" --ks-key-alias stockcapture \
    --ks-pass pass:android --key-pass pass:android \
    --out "$OUT_DIR/$name" "$aligned"
done

"$APKSIGNER" verify --verbose "$OUT_DIR/base.apk" >/dev/null
for split in "$STOCK_DIR"/split_*.apk; do
  "$APKSIGNER" verify --verbose "$OUT_DIR/$(basename "$split")" >/dev/null
done
{
  printf 'variant=patriot-stock-derived-real-backend-capture\n'
  printf 'built_at=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  printf 'runtime_assets=stock-plus-in-app-network-recorder-and-empty-native-sentry-dsns\n'
  printf 'differences=in-app-network-recorder,private-delayed-upload,pairip-checkLicense-noop,firebase-disabled,sentry-disabled,local-signature\n'
  if [[ -n "$LOGGER_UPLOAD_URL" ]]; then
    printf 'logger_upload=configured\n'
  else
    printf 'logger_upload=disabled-local-queue-only\n'
  fi
  sha256sum "$STOCK_DIR"/*.apk "$OUT_DIR/base.apk"
  for split in "$STOCK_DIR"/split_*.apk; do
    sha256sum "$OUT_DIR/$(basename "$split")"
  done
  "$APKSIGNER" verify --print-certs "$OUT_DIR/base.apk"
} > "$BUILD_DIR/BUILD-MANIFEST.txt"

printf '\nBuilt stock-derived real-backend capture APKs:\n'
find "$OUT_DIR" -maxdepth 1 -type f -name '*.apk' ! -name '*-aligned.apk' -printf '  %p\n' | sort
printf '\nThis build is locally signed and observable; it is not literally stock.\n'
printf 'Remove the vendor-signed app before adb install-multiple.\n'
printf 'Install command:\n'
printf '  adb install-multiple %q/base.apk %q/split_config.arm64_v8a.apk %q/split_config.en.apk %q/split_config.xxhdpi.apk\n' \
  "$OUT_DIR" "$OUT_DIR" "$OUT_DIR" "$OUT_DIR"
