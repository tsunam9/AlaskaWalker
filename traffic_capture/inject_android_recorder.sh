#!/usr/bin/env bash
# Compile the app-internal recorder and add it as one new dex/smali partition.
set -euo pipefail

if [[ "$#" -lt 4 || "$#" -gt 5 ]]; then
  printf 'Usage: %s WORK_TREE SMALI_PARTITION TOOLS_DIR SDK_ROOT [with-okhttp]\n' "$0" >&2
  exit 2
fi

WORK_TREE="$1"
SMALI_PARTITION="$2"
TOOLS_DIR="$3"
SDK_ROOT="$4"
MODE="${5:-recorder-only}"
if [[ "$MODE" != recorder-only && "$MODE" != with-okhttp ]]; then
  printf 'Unknown recorder injection mode: %s\n' "$MODE" >&2
  exit 2
fi
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_DIR="$SCRIPT_DIR/android"
BUILD_DIR="$WORK_TREE/.in-app-recorder-build"

ANDROID_JAR="$(find "$SDK_ROOT/platforms" -path '*/android.jar' -type f | sort -V | tail -1)"
D8="$(find "$SDK_ROOT/build-tools" -path '*/d8' -type f | sort -V | tail -1)"
if [[ ! -f "$ANDROID_JAR" || ! -x "$D8" ]]; then
  printf 'Android platform/build tools not found under %s\n' "$SDK_ROOT" >&2
  exit 1
fi
for tool in javac jar baksmali; do
  command -v "$tool" >/dev/null || { printf 'Required tool missing: %s\n' "$tool" >&2; exit 1; }
done

mkdir -p "$TOOLS_DIR" "$BUILD_DIR/classes" "$BUILD_DIR/dex" "$BUILD_DIR/smali"

CLASSPATH="$ANDROID_JAR"
SOURCES=("$SOURCE_DIR/ai/alaskawalker/capture/InAppTrafficRecorder.java")
D8_CLASSPATH=()
if [[ "$MODE" == with-okhttp ]]; then
  declare -A URLS=(
    [okhttp-4.12.0.jar]="https://repo1.maven.org/maven2/com/squareup/okhttp3/okhttp/4.12.0/okhttp-4.12.0.jar"
    [okio-jvm-3.6.0.jar]="https://repo1.maven.org/maven2/com/squareup/okio/okio-jvm/3.6.0/okio-jvm-3.6.0.jar"
    [kotlin-stdlib-2.1.0.jar]="https://repo1.maven.org/maven2/org/jetbrains/kotlin/kotlin-stdlib/2.1.0/kotlin-stdlib-2.1.0.jar"
  )
  declare -A HASHES=(
    [okhttp-4.12.0.jar]="b1050081b14bb7a3a7e55a4d3ef01b5dcfabc453b4573a4fc019767191d5f4e0"
    [okio-jvm-3.6.0.jar]="67543f0736fc422ae927ed0e504b98bc5e269fda0d3500579337cb713da28412"
    [kotlin-stdlib-2.1.0.jar]="d6f91b7b0f306cca299fec74fb7c34e4874d6f5ec5b925a0b4de21901e119c3f"
  )
  for name in "${!URLS[@]}"; do
    target="$TOOLS_DIR/$name"
    if [[ ! -f "$target" ]]; then
      curl -fL --retry 3 -o "$target" "${URLS[$name]}"
    fi
    printf '%s  %s\n' "${HASHES[$name]}" "$target" | sha256sum --check --status
  done
  for name in okhttp-4.12.0.jar okio-jvm-3.6.0.jar kotlin-stdlib-2.1.0.jar; do
    CLASSPATH="$CLASSPATH:$TOOLS_DIR/$name"
    D8_CLASSPATH+=(--classpath "$TOOLS_DIR/$name")
  done
  SOURCES+=("$SOURCE_DIR/ai/alaskawalker/capture/CaptureInterceptor.java")
fi

javac -source 8 -target 8 -Xlint:-options -cp "$CLASSPATH" \
  -d "$BUILD_DIR/classes" "${SOURCES[@]}"
jar --create --file "$BUILD_DIR/recorder.jar" -C "$BUILD_DIR/classes" .
"$D8" --lib "$ANDROID_JAR" \
  "${D8_CLASSPATH[@]}" \
  --output "$BUILD_DIR/dex" "$BUILD_DIR/recorder.jar"
baksmali disassemble "$BUILD_DIR/dex/classes.dex" -o "$BUILD_DIR/smali"

if [[ -e "$WORK_TREE/$SMALI_PARTITION/ai/alaskawalker/capture" ]]; then
  printf 'Recorder package already exists in fresh work tree: %s\n' "$WORK_TREE/$SMALI_PARTITION" >&2
  exit 1
fi
mkdir -p "$WORK_TREE/$SMALI_PARTITION/ai/alaskawalker"
cp -R "$BUILD_DIR/smali/ai/alaskawalker/capture" \
  "$WORK_TREE/$SMALI_PARTITION/ai/alaskawalker/capture"

find "$WORK_TREE/$SMALI_PARTITION/ai/alaskawalker/capture" -type f -name '*.smali' | grep -q .
printf 'Injected app-internal recorder into %s\n' "$SMALI_PARTITION"
