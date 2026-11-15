# ICMFA

This independently signed build uses `aldington-david/mihomo`, including its AnyTLS + REALITY implementation. The display name is **ICMFA**. The existing app ID `com.github.aldingtondavid.cmfa` and signing identity are unchanged, so it upgrades the previous custom **CMFA AnyTLS REALITY** build. It still installs alongside official CMFA and cannot upgrade the official package.

## Releases

The default `anytls-reality` branch is the build controller. Every hour at minute 37, Actions checks the latest **published stable release** from `MetaCubeX/ClashMetaForAndroid` and `aldington-david/mihomo`. A new app or core release creates an immutable source tag such as `v2.11.37-anytls-v1.19.34-r4`. Revision 4 retains the approved initial Meta and VPN settings and adds six-hour defaults for new remote subscriptions. Manual dispatch accepts published stable upstream and core tags as optional inputs. CMFA has no in-app release-tag parser or application updater affected by the revision suffix.

The source tag contains the exact upstream app commit, the strictly applied structural `source.patch`, checked display-name and resource-link rewrites in `customize.py`, and the custom core's exact Git submodule commit. Resource links are selected by their XML resource names across all locales, without rewriting unrelated XML or depending on neighbouring translations. Package identity, signing settings, external-control actions, and the local core module paths are checked before creating a source tag.

`build-info.json` records source commits, the controller commit, Android version code and a fingerprint of `source.patch`, `default-settings.patch`, `customize.py` and `check_subscription_defaults.py`. An unpublished failed tag can be retried only when its source provenance and this fingerprint still match; documentation and workflow-only edits do not change that fingerprint. A mismatched failed tag stops for review and is never rewritten automatically. Existing public releases do not need the new fingerprint, but their four required assets must still be present, uploaded and nonempty before synchronization skips them. Public releases appear only after compilation, signature verification and four-ABI verification pass; the publishing step refuses to overwrite an already-public release. Structural patch or native Go API conflicts continue to stop the build for review.

Only `cmfa-X.Y.Z-meta-universal-release.apk` is published, plus `SHA256SUMS`, `build-info.json` and `SIGNING-CERTIFICATE.txt`; renaming the application does not change the requested APK filename. The package contains arm64-v8a, armeabi-v7a, x86 and x86_64 cores built from the same custom source. Android `versionCode` is `1,000,000,000 + github.run_number`, fixed when a new source tag is created, and must exceed the previous custom build's `1,000,000,002`. The packaged application and launcher labels, version code, package ID and signing certificate are verified before publishing. Keep this workflow and its signing key when continuing the release series.

## Initial settings

Revision 3 changes only five approved defaults. The Meta features Unified Delay
and TCP Concurrent default to on when the persisted settings file is absent.
The VPN settings System Proxy and Allow Apps to Bypass VPN default to off, while
Allow IPv6 defaults to on. The System Proxy control remains available only on
Android 10 and later.

The Override / General page, kernel IPv6, session overrides and shared nullable
configuration model keep their existing behavior. Saved overrides are read
unchanged: an empty object or null fields still inherit the profile, and explicit
false/true choices remain in effect. Stored VPN preferences retain their values;
only missing preference keys use the new defaults. Resetting global overrides
restores the two new Meta defaults through the existing reset behavior.

The strict `default-settings.patch` is applied before source tagging. Preparation
checks all five values and the empty session override. Release CI runs the actual
native configuration read/apply tests for absent, empty, null, false and true
settings, including preservation of the profile's kernel IPv6, before building
the signed four-ABI APK.

## Signing and build

Set repository secrets `ANDROID_KEYSTORE_BASE64`, `ANDROID_KEYSTORE_PASSWORD`, `ANDROID_KEY_ALIAS`, `ANDROID_KEY_PASSWORD`. The keystore must be PKCS12. Set repository variable `ANDROID_CERTIFICATE_SHA256` to the expected certificate's 64-character SHA-256 digest; the signed APK must match this identity before publishing. The public upstream keystore is removed, and a missing signing configuration fails instead of falling back to a debug key. Secrets are decoded only on the runner and removed at the end.

The build follows the upstream Java 21 / patched MetaCubeX Go 1.26 / NDK 29 / Gradle `assembleMetaRelease` recipe. The core is linked into `libclash.so`; a desktop CLI executable cannot replace it. App updates are downloaded from this fork's Releases page; CMFA has no built-in application updater to redirect.

Source pinning does not promise byte-for-byte reproducibility: the inherited upstream build downloads current Geo databases and bundles the runner's current CA certificates. Release checksums identify the actual published files; `build-info.json` identifies the exact app and core source commits.

`python3 .github/fork/prepare.py --self-test` checks version rewriting, new or changed translations, duplicate resources, core/package/signing guards, failed-tag provenance, and published asset completeness. The initial CMFA v2.11.35 and mihomo v1.19.32 both use upstream core SHA `88dcbf7f1614a67c3b36b848ee3592dfa92ada36`; the custom core changes that SHA by applying the AnyTLS + REALITY patch. A local Android/arm64 cross-compilation of CMFA's Go wrapper packages was checked separately; full APK verification is performed by Actions.

## New remote subscriptions in revision 4

New HTTP(S) URL and externally provided subscriptions default to a six-hour
interval (21600000 milliseconds / 360 minutes in the editor). An empty URL draft
uses the same default; its editor accepts only HTTP(S). File and content sources
retain their previous behavior. Deep links pass their source to creation and only
patch the interval when update-interval is explicitly present, preserving the
original minute parsing and 15-minute minimum for positive explicit values.
Existing profiles, clones, edits and updates retain their saved schedules.
The new nonzero interval prevents the first response's suggested interval from
overriding the six-hour default. Explicit zero retains its original response-header
meaning. AlarmManager and existing background/failure handling are unchanged.
CI compiles and runs the actual creation expression and deep-link block with
synthetic inputs through the runner's Kotlin compiler, then builds the full APK.
