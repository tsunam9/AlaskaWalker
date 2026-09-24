#!/usr/bin/env bash
# Build a stock-derived Numinar APK set for pass-through capture of real backends.
# Real origins, Expo behavior, and Adjust stay stock. Firebase and Sentry do not init.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/../.." && pwd)"
STOCK_DIR="$REPO_ROOT/numinar/stock"
BUILD_DIR="$SCRIPT_DIR/build-stock-capture"
WORK_TREE="$BUILD_DIR/apktool"
OUT_DIR="$BUILD_DIR/out"
TOOLS_DIR="$SCRIPT_DIR/.tools"
PATRIOT_TOOLS="$REPO_ROOT/patriot_grassroots/instrumentation/.tools"
APKTOOL_VERSION="3.0.3"
APKTOOL_JAR="$TOOLS_DIR/apktool_${APKTOOL_VERSION}.jar"
APKTOOL_SHA256="dbf930b076c6b9be08d57c449cacefc3bdd6b71ebd59b3066fc0e1f5b14f9423"
FRAME_DIR="${APKTOOL_FRAME_DIR:-$PATRIOT_TOOLS/framework-device}"
SDK_ROOT="${ANDROID_SDK_ROOT:-${ANDROID_HOME:-$HOME/Android/Sdk}}"
HERMES_DECOMP="${HERMES_DECOMP:-/tmp/hermes-decomp/target/release/hermes-decomp}"

declare -A EXPECTED_SHA256=(
  [base.apk]="d4e5370dcd970ac463cf6cc1c6b8e3426a2994b09e69e6a6711c4ad15ebf2e94"
  [split_config.arm64_v8a.apk]="2d4a21155fb4519ce8f9bb961e5663bfd6aeb1b80d80bfbef6eed5e47a7f4f9a"
  [split_config.en.apk]="d92dbef5b121223cd2fea895509a458c8e90518fee73afc220ba8527d654c6eb"
  [split_config.xxhdpi.apk]="af729be81ba99937b663e7947999abf9d6a5d292fc536dce7d172cd45fc8febc"
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
if [[ ! -x "$HERMES_DECOMP" ]]; then
  printf 'hermes-decomp not found at %s\n' "$HERMES_DECOMP" >&2
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
java -jar "$APKTOOL_JAR" decode --frame-path "$FRAME_DIR" --force \
  --output "$WORK_TREE" "$STOCK_DIR/base.apk"

BUNDLE="$WORK_TREE/assets/index.android.bundle"
BUNDLE_STOCK_SHA256="$(sha256sum "$BUNDLE" | cut -d' ' -f1)"
cp "$BUNDLE" "$BUILD_DIR/index.android.stock.hbc"

# The app's own startup guard is the clean no-init boundary: make
# USING_SENTRY return false. This skips Sentry.init, Mobile Replay, and the
# recent-exit reporter while leaving all unrelated Hermes code unchanged.
SENTRY_FLAG_FUNC=18911
SENTRY_HASM="$BUILD_DIR/f${SENTRY_FLAG_FUNC}.hasm"
"$HERMES_DECOMP" asm-check --function "$SENTRY_FLAG_FUNC" "$BUNDLE" >/dev/null
"$HERMES_DECOMP" emit-hasm --function "$SENTRY_FLAG_FUNC" "$BUNDLE" \
  -o "$SENTRY_HASM" >/dev/null
python3 - "$SENTRY_HASM" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
expected = """0000  GetEnvironment r0, 0
0003  LoadFromEnvironment r0, r0, 8
0007  Ret r0
"""
replacement = """0000  LoadConstFalse r0
0002  Ret r0
"""
if text != expected:
    raise SystemExit("unexpected USING_SENTRY getter bytecode")
path.write_text(replacement, encoding="utf-8")
PY
"$HERMES_DECOMP" asm --function "$SENTRY_FLAG_FUNC" "$BUNDLE" \
  "$SENTRY_HASM" -o "$BUILD_DIR/index.android.sentry-disabled.hbc" >/dev/null
cp "$BUILD_DIR/index.android.sentry-disabled.hbc" "$BUNDLE"
BUNDLE_CAPTURE_SHA256="$(sha256sum "$BUNDLE" | cut -d' ' -f1)"
if [[ "$BUNDLE_CAPTURE_SHA256" == "$BUNDLE_STOCK_SHA256" ]]; then
  printf 'Sentry guard patch did not change the Hermes bundle.\n' >&2
  exit 1
fi

# Guard Adjust explicitly: the stock token, initSdk call, signer library, and
# manifest components must survive this build. Save its function body for a
# post-patch identity check.
ADJUST_FUNC=33115
"$HERMES_DECOMP" emit-hasm --function "$ADJUST_FUNC" \
  "$BUILD_DIR/index.android.stock.hbc" -o "$BUILD_DIR/f${ADJUST_FUNC}.stock.hasm" >/dev/null
"$HERMES_DECOMP" emit-hasm --function "$ADJUST_FUNC" \
  "$BUNDLE" -o "$BUILD_DIR/f${ADJUST_FUNC}.capture.hasm" >/dev/null
cmp "$BUILD_DIR/f${ADJUST_FUNC}.stock.hasm" "$BUILD_DIR/f${ADJUST_FUNC}.capture.hasm"
grep -q '"initSdk"' "$BUILD_DIR/f${ADJUST_FUNC}.capture.hasm"

python3 - "$WORK_TREE/AndroidManifest.xml" <<'PY'
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

manifest = Path(sys.argv[1])
text = manifest.read_text(encoding="utf-8")
needle = "<application "
attribute = 'android:networkSecurityConfig="@xml/stock_capture_network_security_config"'
if attribute in text or needle not in text:
    raise SystemExit("unexpected application/network security manifest state")
if '<meta-data android:name="expo.modules.updates.ENABLED" android:value="true"/>' not in text:
    raise SystemExit("stock Expo Updates enablement not found")
if '<meta-data android:name="expo.modules.updates.EXPO_UPDATES_CHECK_ON_LAUNCH" android:value="ALWAYS"/>' not in text:
    raise SystemExit("stock Expo update cadence not found")
text = text.replace(needle, f"<application {attribute} ", 1)

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
    "io.sentry.android.core.SentryInitProvider",
    "io.sentry.android.core.SentryPerformanceProvider",
    "com.google.firebase.provider.FirebaseInitProvider",
    "com.google.firebase.components.ComponentDiscoveryService",
    "com.google.firebase.iid.FirebaseInstanceIdReceiver",
    "com.google.firebase.messaging.FirebaseMessagingService",
    "com.numinar.numinar.MainNotificationService",
    "expo.modules.notifications.service.ExpoFirebaseMessagingService",
    "io.intercom.android.sdk.fcm.IntercomFcmMessengerService",
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
missing = disabled_components - disabled
if missing:
    raise SystemExit(f"expected Firebase/Sentry components missing: {sorted(missing)}")

# Adjust remains stock. Do not set android:enabled on either autostart component.
adjust_components = {
    "com.adjust.sdk.AdjustReferrerReceiver",
    "com.adjust.sdk.SystemLifecycleContentProvider",
}
found_adjust = set()
for node in application.iter():
    name = node.get(f"{{{android}}}name")
    if name in adjust_components:
        if node.get(f"{{{android}}}enabled") == "false":
            raise SystemExit(f"Adjust component was disabled: {name}")
        found_adjust.add(name)
if found_adjust != adjust_components:
    raise SystemExit(f"Adjust components missing: {sorted(adjust_components - found_adjust)}")

manifest.write_bytes(ET.tostring(root, encoding="utf-8", xml_declaration=True))
PY

cp "$SCRIPT_DIR/stock_capture_network_security_config.xml" \
  "$WORK_TREE/res/xml/stock_capture_network_security_config.xml"

if [[ "$(sha256sum "$BUNDLE" | cut -d' ' -f1)" != "$BUNDLE_CAPTURE_SHA256" ]]; then
  printf 'Hermes bundle changed after the audited Sentry patch.\n' >&2
  exit 1
fi
python3 - "$HERMES_DECOMP" "$BUNDLE" <<'PY'
import json
from pathlib import Path
import subprocess
import sys

tool, bundle = sys.argv[1:]
strings = subprocess.check_output(
    [tool, "dump", "--kind", "strings", "--json", bundle], text=True
)
for value in (
    "https://api.numinar.com",
    "https://fast-api.numinar.com/api",
    "wss://rust-server.numinar.com/websocket",
    "auth.numinar.com",
    "idif65k6cl4w",
):
    if value not in strings:
        raise SystemExit(f"required stock Numinar/Adjust string missing: {value}")
PY
printf 'Verified Sentry startup guard off; Firebase native startup off; Adjust retained.\n'

java -jar "$APKTOOL_JAR" build --frame-path "$FRAME_DIR" \
  "$WORK_TREE" -o "$BUILD_DIR/base-unsigned.apk"
"$ZIPALIGN" -f 4 "$BUILD_DIR/base-unsigned.apk" "$OUT_DIR/base-aligned.apk"

KEYSTORE="$BUILD_DIR/stock-capture.keystore"
if [[ ! -f "$KEYSTORE" ]]; then
  keytool -genkeypair -noprompt \
    -keystore "$KEYSTORE" -storepass android -keypass android \
    -alias stockcapture -keyalg RSA -keysize 2048 -validity 10000 \
    -dname "CN=Numinar Stock Capture,OU=Instrumentation,O=AlaskaWalker,C=US"
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
# Adjust Signature V3 lives in the ABI split. Re-signing must not alter it.
cmp \
  <(unzip -p "$STOCK_DIR/split_config.arm64_v8a.apk" lib/arm64-v8a/libsigner.so) \
  <(unzip -p "$OUT_DIR/split_config.arm64_v8a.apk" lib/arm64-v8a/libsigner.so)
{
  printf 'variant=numinar-stock-derived-real-backend-capture\n'
  printf 'built_at=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  printf 'hermes_stock_sha256=%s\n' "$BUNDLE_STOCK_SHA256"
  printf 'hermes_capture_sha256=%s\n' "$BUNDLE_CAPTURE_SHA256"
  printf 'differences=user-ca-trust,firebase-disabled,sentry-disabled,local-signature\n'
  printf 'adjust=stock-token-init-function-native-signer-and-components-retained\n'
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
