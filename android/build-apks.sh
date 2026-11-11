#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
mode="${1:-release}"
abi_set="${2:-arm}"

case "$mode" in
    release) gradle_task='assembleRelease' ;;
    debug) gradle_task='assembleDebug' ;;
    *)
        printf 'Usage: %s [release|debug] [arm|all]\n' "$0" >&2
        exit 2
        ;;
esac

case "$abi_set" in
    arm) abis='arm64-v8a,armeabi-v7a' ;;
    all) abis='arm64-v8a,armeabi-v7a,x86,x86_64' ;;
    *)
        printf 'Usage: %s [release|debug] [arm|all]\n' "$0" >&2
        exit 2
        ;;
esac

if ! command -v python3 >/dev/null 2>&1; then
    printf 'python3 is required to prepare pinned native dependencies.\n' >&2
    exit 1
fi

cd "$script_dir"
python3 bootstrap-deps.py
./gradlew --no-daemon -P"abis=$abis" ":app:$gradle_task"

printf '\nAPK output folders:\n'
if [[ "$abi_set" == all ]]; then
    printf '  %s/app/build/outputs/apk/{arcade,mobile,arcadeEmulator,mobileEmulator}/%s/\n' \
        "$script_dir" "$mode"
else
    printf '  %s/app/build/outputs/apk/{arcade,mobile}/%s/\n' "$script_dir" "$mode"
fi
if [[ "$mode" == release && -z "${HYPCADE_SIGNING_PROPERTIES:-}" ]]; then
    printf 'Release APKs are unsigned. Run ./sign-apks.sh after the build, or set HYPCADE_SIGNING_PROPERTIES to sign during the build.\n'
fi
