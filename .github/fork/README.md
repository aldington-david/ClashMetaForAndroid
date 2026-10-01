# CMFA AnyTLS + REALITY

This independently signed build uses `aldington-david/mihomo`, including its AnyTLS + REALITY implementation. The app ID is `com.github.aldingtondavid.cmfa`; the display name is **CMFA AnyTLS REALITY**. It installs alongside official CMFA and cannot upgrade the official package.

## Releases

The default `anytls-reality` branch is the build controller. Every hour at minute 37, Actions checks the latest **published stable release** from `MetaCubeX/ClashMetaForAndroid` and `aldington-david/mihomo`. A new app or core release creates an immutable source tag such as `v2.11.35-anytls-v1.19.32`. Manual dispatch accepts published stable tags as optional inputs.

The source tag contains the exact upstream app commit, the strictly applied `source.patch`, and the custom core's exact Git submodule commit. `build-info.json` records those commits, the controller commit and the Android version code. Public releases appear only after compilation, signature verification and four-ABI verification pass. Failed runs can retry the same source tag; they never overwrite a public release. If an upstream edit no longer accepts the patch or changes the native Go API, the run fails for review rather than silently publishing an upstream-only build.

Only `cmfa-X.Y.Z-meta-universal-release.apk` is published, plus `SHA256SUMS`, `build-info.json` and `SIGNING-CERTIFICATE.txt`. The package contains arm64-v8a, armeabi-v7a, x86 and x86_64 cores built from the same custom source. Android `versionCode` is `1,000,000,000 + github.run_number`, fixed when a new source tag is created; a core-only release therefore remains installable as an update. Keep this workflow and its signing key when continuing the release series.

## Signing and build

Set repository secrets `ANDROID_KEYSTORE_BASE64`, `ANDROID_KEYSTORE_PASSWORD`, `ANDROID_KEY_ALIAS`, `ANDROID_KEY_PASSWORD`. The keystore must be PKCS12. Set repository variable `ANDROID_CERTIFICATE_SHA256` to the expected certificate's 64-character SHA-256 digest; the signed APK must match this identity before publishing. The public upstream keystore is removed, and a missing signing configuration fails instead of falling back to a debug key. Secrets are decoded only on the runner and removed at the end.

The build follows the upstream Java 21 / patched MetaCubeX Go 1.26 / NDK 29 / Gradle `assembleMetaRelease` recipe. The core is linked into `libclash.so`; a desktop CLI executable cannot replace it. App updates are downloaded from this fork's Releases page; CMFA has no built-in application updater to redirect.

`python3 .github/fork/prepare.py --self-test` checks the release version rewrite and its rejection cases. The initial CMFA v2.11.35 and mihomo v1.19.32 both use upstream core SHA `88dcbf7f1614a67c3b36b848ee3592dfa92ada36`; the custom core changes that SHA by applying the AnyTLS + REALITY patch. A local Android/arm64 cross-compilation of CMFA's Go wrapper packages was checked separately; full APK verification is performed by Actions.
