#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
export ANDROID_HOME="${ANDROID_HOME:-$HOME/Android/Sdk}"
export ANDROID_SDK_ROOT="${ANDROID_SDK_ROOT:-$ANDROID_HOME}"

"$ROOT/gradlew" -p "$ROOT" --no-daemon :app:assembleDebug
mkdir -p "$ROOT/dist"
cp "$ROOT/app/build/outputs/apk/debug/app-debug.apk" "$ROOT/dist/AlaskaWalker.apk"

echo "built: $ROOT/dist/AlaskaWalker.apk"
echo "install: adb install -r $ROOT/dist/AlaskaWalker.apk"
