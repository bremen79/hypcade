#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "$script_dir/.." && pwd)"
variant="${1:-arm}"

case "$variant" in
    arm)
        flavors=(arcade mobile)
        ;;
    all)
        flavors=(arcade mobile arcadeEmulator mobileEmulator)
        ;;
    -h|--help)
        cat <<'USAGE'
Usage: ./sign-apks.sh [arm|all]

Sign release APKs after building them. The default signs the ARM arcade and
mobile APKs; "all" also includes the x86 emulator APKs.
USAGE
        exit 0
        ;;
    *)
        printf 'Usage: %s [arm|all]\n' "$0" >&2
        exit 2
        ;;
esac

sdk_root="${ANDROID_HOME:-${ANDROID_SDK_ROOT:-${HOME}/Android/Sdk}}"
build_tools_version="${ANDROID_BUILD_TOOLS_VERSION:-35.0.0}"
build_tools_dir="$sdk_root/build-tools/$build_tools_version"
apksigner="$build_tools_dir/apksigner"
zipalign="$build_tools_dir/zipalign"

for tool in "$apksigner" "$zipalign"; do
    if [[ ! -x "$tool" ]]; then
        printf 'Required Android build tool is missing or not executable: %s\n' "$tool" >&2
        exit 1
    fi
done

apks=()
for flavor in "${flavors[@]}"; do
    apk="$script_dir/app/build/outputs/apk/$flavor/release/app-$flavor-release.apk"
    if [[ ! -f "$apk" ]]; then
        printf 'Release APK not found: %s\nBuild the requested flavor(s) first.\n' "$apk" >&2
        exit 1
    fi
    apks+=("$apk")
done

unsigned_apks=()
for apk in "${apks[@]}"; do
    if "$apksigner" verify "$apk" >/dev/null 2>&1; then
        printf 'Already signed; leaving unchanged: %s\n' "$apk"
    else
        unsigned_apks+=("$apk")
    fi
done

if ((${#unsigned_apks[@]} == 0)); then
    exit 0
fi

properties_file="${HYPCADE_SIGNING_PROPERTIES:-}"
if [[ -z "$properties_file" ]]; then
    candidates=(
        "$repo_root/local-tools/release-signing/signing.properties"
        "$repo_root/../local-tools/release-signing/signing.properties"
        "$repo_root/release-signing/signing.properties"
    )
    for candidate in "${candidates[@]}"; do
        if [[ -f "$candidate" ]]; then
            properties_file="$candidate"
            break
        fi
    done
fi

if [[ -z "$properties_file" || ! -f "$properties_file" ]]; then
    printf 'Signing properties not found. Set HYPCADE_SIGNING_PROPERTIES or place it in local-tools/release-signing/.\n' >&2
    exit 1
fi

properties_file="$(cd -- "$(dirname -- "$properties_file")" && pwd)/$(basename -- "$properties_file")"
properties_dir="$(dirname -- "$properties_file")"

read_property() {
    local wanted="$1"
    awk -v wanted="$wanted" '
        /^[[:space:]]*[#!]/ { next }
        {
            sub(/\r$/, "")
            separator = index($0, "=")
            if (!separator) next
            name = substr($0, 1, separator - 1)
            gsub(/^[[:space:]]+|[[:space:]]+$/, "", name)
            if (name == wanted) {
                value = substr($0, separator + 1)
                sub(/^[[:space:]]+/, "", value)
                print value
                found = 1
                exit
            }
        }
        END { if (!found) exit 1 }
    ' "$properties_file"
}

configured_store_file="$(read_property storeFile)"
key_alias="$(read_property keyAlias)"
store_password="$(read_property storePassword)"
key_password="$(read_property keyPassword)"

if [[ -z "$configured_store_file" || -z "$key_alias" || -z "$store_password" || -z "$key_password" ]]; then
    printf 'Signing properties must define storeFile, keyAlias, storePassword, and keyPassword.\n' >&2
    exit 1
fi

if [[ "$configured_store_file" = /* ]]; then
    keystore="$configured_store_file"
else
    keystore="$properties_dir/$configured_store_file"
fi

# If the properties file still contains an old absolute path, use the keystore
# beside it when the filename matches. This keeps signing independent of the
# checkout's directory name.
if [[ ! -f "$keystore" ]]; then
    adjacent_keystore="$properties_dir/$(basename -- "$configured_store_file")"
    if [[ -f "$adjacent_keystore" ]]; then
        keystore="$adjacent_keystore"
    fi
fi

if [[ ! -r "$keystore" ]]; then
    printf 'Release keystore not found or unreadable: %s\n' "$keystore" >&2
    exit 1
fi

export HYPCADE_SIGNER_STORE_PASSWORD="$store_password"
export HYPCADE_SIGNER_KEY_PASSWORD="$key_password"
unset store_password key_password

temporary_dir=""
cleanup() {
    if [[ -n "$temporary_dir" && -d "$temporary_dir" ]]; then
        rm -rf -- "$temporary_dir"
    fi
    unset HYPCADE_SIGNER_STORE_PASSWORD HYPCADE_SIGNER_KEY_PASSWORD
}
trap cleanup EXIT

for apk in "${unsigned_apks[@]}"; do
    apk_dir="$(dirname -- "$apk")"
    temporary_dir="$(mktemp -d "$apk_dir/hypcade-sign.XXXXXX")"
    aligned_apk="$temporary_dir/aligned.apk"
    signed_apk="$temporary_dir/signed.apk"

    "$zipalign" -f 4 "$apk" "$aligned_apk"
    "$zipalign" -c 4 "$aligned_apk"
    "$apksigner" sign \
        --ks "$keystore" \
        --ks-key-alias "$key_alias" \
        --ks-pass env:HYPCADE_SIGNER_STORE_PASSWORD \
        --key-pass env:HYPCADE_SIGNER_KEY_PASSWORD \
        --out "$signed_apk" \
        "$aligned_apk"
    "$apksigner" verify "$signed_apk"
    mv -- "$signed_apk" "$apk"
    rm -rf -- "$temporary_dir"
    temporary_dir=""
    printf 'Signed: %s\n' "$apk"
done
