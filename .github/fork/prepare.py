"""Prepare an immutable, patched upstream release; never overwrite a release tag."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import urllib.error
import urllib.parse
import urllib.request

from customize import APP_ID, customize, set_version, validate_source

UPSTREAM = "MetaCubeX/ClashMetaForAndroid"
CORE = "aldington-david/mihomo"
CORE_PATH = "core/src/foss/golang/clash"
CONTROLLER = Path(__file__).resolve().parents[2]


def api(path, missing_ok=False):
    request = urllib.request.Request("https://api.github.com/" + path, headers={
        "Authorization": "Bearer " + os.environ["GH_TOKEN"],
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        if missing_ok and error.code == 404:
            return None
        raise


def git(*args, cwd=None, capture=False, authenticated=False):
    env = os.environ.copy()
    if authenticated:
        credential = base64.b64encode(("x-access-token:" + env["GH_TOKEN"]).encode()).decode()
        env.update(GIT_CONFIG_COUNT="1", GIT_CONFIG_KEY_0="http.https://github.com/.extraheader",
                   GIT_CONFIG_VALUE_0="AUTHORIZATION: basic " + credential)
    result = subprocess.run(["git", *args], cwd=cwd, env=env, text=True,
                            stdout=subprocess.PIPE if capture else None, check=True)
    return result.stdout.strip() if capture else None


def release(repository, requested):
    endpoint = "tags/" + urllib.parse.quote(requested, safe="") if requested else "latest"
    item = api(f"repos/{repository}/releases/{endpoint}")
    if item["draft"] or item["prerelease"] or not re.fullmatch(r"v\d+\.\d+\.\d+", item["tag_name"]):
        raise ValueError(f"Not a stable semantic-version release: {repository}")
    return item["tag_name"]


def commit(repository, tag):
    item = api(f"repos/{repository}/git/ref/tags/{urllib.parse.quote(tag, safe='')}")["object"]
    while item["type"] == "tag":
        item = api(f"repos/{repository}/git/tags/{item['sha']}")["object"]
    if item["type"] != "commit" or not re.fullmatch("[0-9a-f]{40}", item["sha"]):
        raise ValueError("Release tag must resolve to a commit")
    return item["sha"]


def source_fingerprint(controller=CONTROLLER):
    digest = hashlib.sha256()
    for name in ("source.patch", "customize.py"):
        digest.update(name.encode() + b"\0" + (controller / ".github/fork" / name).read_bytes())
    return digest.hexdigest()


def validate_public_release(item, tag, upstream_tag):
    names = {f"cmfa-{upstream_tag[1:]}-meta-universal-release.apk", "SHA256SUMS", "build-info.json", "SIGNING-CERTIFICATE.txt"}
    assets = item.get("assets", [])
    if (item.get("tag_name") != tag or item.get("draft") or item.get("prerelease")
            or len(assets) != len(names) or {asset["name"] for asset in assets} != names
            or any(asset.get("state") != "uploaded" or asset.get("size", 0) <= 0 for asset in assets)):
        raise ValueError("Published release is incomplete or unexpected; inspect it manually, never overwrite it")


def validate_retry(manifest, expected):
    if any(manifest.get(name) != value for name, value in expected.items()):
        raise ValueError("Unpublished source tag provenance or source fingerprint changed; review the failed tag before retrying")


def output(**values):
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as stream:
        for name, value in values.items():
            stream.write(f"{name}={str(value).lower() if isinstance(value, bool) else value}\n")


def prepare(args):
    repository = os.environ["GITHUB_REPOSITORY"]
    upstream_tag = release(UPSTREAM, args.upstream_tag)
    core_tag = release(CORE, args.core_tag)
    tag = f"{upstream_tag}-anytls-{core_tag}"
    existing_release = api(f"repos/{repository}/releases/tags/{tag}", missing_ok=True)
    if existing_release and not existing_release["draft"]:
        validate_public_release(existing_release, tag, upstream_tag)
        output(build=False, tag=tag)
        print(f"Already published: {tag}")
        return
    destination = Path(args.source).resolve()
    if destination.exists():
        raise ValueError("Build source directory must not already exist")
    upstream_sha, core_sha = commit(UPSTREAM, upstream_tag), commit(CORE, core_tag)
    expected = {
        "upstream_repository": UPSTREAM, "upstream_tag": upstream_tag, "upstream_sha": upstream_sha,
        "core_repository": CORE, "core_tag": core_tag, "core_sha": core_sha,
        "release_tag": tag, "application_id": APP_ID, "source_fingerprint": source_fingerprint(),
    }
    existing_tag = api(f"repos/{repository}/git/ref/tags/{tag}", missing_ok=True)
    if existing_tag:
        git("clone", "--depth", "1", "--branch", tag, f"https://github.com/{repository}.git", str(destination))
        manifest = json.loads((destination / "build-info.json").read_text(encoding="utf-8"))
        validate_retry(manifest, expected)
        if source_fingerprint(destination) != expected["source_fingerprint"]:
            raise ValueError("Unpublished tag source-rewrite files do not match its recorded fingerprint")
        validate_source(destination)
        if git("ls-files", "--stage", CORE_PATH, cwd=destination, capture=True).split()[:2] != ["160000", core_sha]:
            raise ValueError("Core gitlink does not match the pinned core commit")
    else:
        git("clone", "--filter=blob:none", "--single-branch", "--branch", upstream_tag, f"https://github.com/{UPSTREAM}.git", str(destination))
        if git("rev-parse", "HEAD", cwd=destination, capture=True) != upstream_sha:
            raise ValueError("Upstream release tag moved during checkout")
        git("apply", "--check", str(CONTROLLER / ".github/fork/source.patch"), cwd=destination)
        git("apply", str(CONTROLLER / ".github/fork/source.patch"), cwd=destination)
        customize(destination)
        # Upstream signing material and workflows must never enter our release build.
        (destination / "release.keystore").unlink(missing_ok=True)
        shutil.rmtree(destination / ".github/workflows")
        shutil.copytree(CONTROLLER / ".github/workflows", destination / ".github/workflows")
        shutil.copytree(CONTROLLER / ".github/fork", destination / ".github/fork", ignore=shutil.ignore_patterns("__pycache__"))
        code = 1_000_000_000 + int(os.environ["GITHUB_RUN_NUMBER"])
        gradle = destination / "build.gradle.kts"
        gradle.write_text(set_version(gradle.read_text(encoding="utf-8"), upstream_tag, code), encoding="utf-8")
        manifest = {**expected,
            "version_code": code, "controller_sha": os.environ["GITHUB_SHA"],
        }
        (destination / "build-info.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        git("config", "user.name", "github-actions[bot]", cwd=destination)
        git("config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com", cwd=destination)
        git("add", "-A", cwd=destination)
        git("update-index", "--add", "--cacheinfo", f"160000,{core_sha},{CORE_PATH}", cwd=destination)
        validate_source(destination)
        if git("ls-files", "--stage", CORE_PATH, cwd=destination, capture=True).split()[:2] != ["160000", core_sha]:
            raise ValueError("Core gitlink does not match the pinned core commit")
        git("commit", "-m", f"Build {upstream_tag} with AnyTLS REALITY core {core_tag}", cwd=destination)
        git("remote", "set-url", "origin", f"https://github.com/{repository}.git", cwd=destination)
        git("tag", tag, cwd=destination)
        git("push", "origin", f"refs/tags/{tag}", cwd=destination, authenticated=True)
    output(build=True, tag=tag, version=upstream_tag[1:], core_sha=manifest["core_sha"],
           core_tag=manifest["core_tag"], source_sha=git("rev-parse", "HEAD", cwd=destination, capture=True))


def self_test():
    import copy
    import tempfile

    def rejects(action):
        try:
            action()
        except ValueError:
            return
        raise AssertionError("Invalid input accepted")

    updated = set_version('versionName = "2.11.34"\nversionCode = 211034\n', "v2.11.35", 1_000_000_005)
    assert updated == 'versionName = "2.11.35"\nversionCode = 1000000005\n'
    for source, tag, code in [("", "v2.11.35", 1_000_000_005),
                              ('versionName = "x"\nversionCode = 1', "../../bad", 1_000_000_005),
                              ('versionName = "x"\nversionCode = 1', "v2.11.35", 2_100_000_000)]:
        rejects(lambda: set_version(source, tag, code))
    tag, app_tag = "v2.11.35-anytls-v1.19.32", "v2.11.35"
    item = {"tag_name": tag, "draft": False, "prerelease": False, "assets": [
        {"name": name, "size": 1, "state": "uploaded"} for name in (
            "cmfa-2.11.35-meta-universal-release.apk", "SHA256SUMS", "build-info.json", "SIGNING-CERTIFICATE.txt")
    ]}
    validate_public_release(item, tag, app_tag)
    for field, value in (("assets", item["assets"][:-1]), ("assets", item["assets"] * 2), ("draft", True), ("prerelease", True)):
        rejects(lambda: validate_public_release(dict(item, **{field: value}), tag, app_tag))
    for field, value in (("state", "new"), ("size", 0)):
        invalid = copy.deepcopy(item)
        invalid["assets"][0][field] = value
        rejects(lambda: validate_public_release(invalid, tag, app_tag))
    expected = {"core_sha": "a" * 40, "source_fingerprint": "b" * 64}
    validate_retry(dict(expected), expected)
    rejects(lambda: validate_retry({"core_sha": "a" * 40}, expected))
    rejects(lambda: validate_retry(dict(expected, core_sha="c" * 40), expected))
    rejects(lambda: validate_retry(dict(expected, source_fingerprint="c" * 64), expected))

    with tempfile.TemporaryDirectory(prefix="cmfa-self-test-", dir=CONTROLLER) as directory:
        source = Path(directory).resolve()
        assert source.parent == CONTROLLER
        for name in (".gitmodules", "build.gradle.kts", "app/src/main/AndroidManifest.xml", "core/src/foss/golang/go.mod", "core/src/main/golang/go.mod"):
            target = source / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((CONTROLLER / name).read_bytes())
        gradle = source / "build.gradle.kts"
        original = gradle.read_text(encoding="utf-8")
        for field in ("launch_name", "application_name"):
            original = original.replace(f'resValue("string", "{field}", "CMFA AnyTLS REALITY")',
                                        f'resValue("string", "{field}", "@string/{field}_meta")')
        gradle.write_text(original, encoding="utf-8")
        # Changed neighbouring translations and a newly added locale must not affect link rewriting.
        xml = '<resources>\n<string name="neighbour"><![CDATA[changed <b>translation</b>]]></string>\n<string translatable="false" name="meta_github_url">https://github.com/MetaCubeX/ClashMetaForAndroid</string>\n<string name="clash_meta_core_url" translatable="false">https://github.com/MetaCubeX/Clash.Meta</string>\n</resources>\n'
        for locale in ("values", "values-new"):
            path = source / f"design/src/main/res/{locale}/links.xml"
            path.parent.mkdir(parents=True)
            path.write_text(xml, encoding="utf-8")
        customize(source)
        validate_source(source)
        for path in (source / "design/src/main/res").glob("values*/*.xml"):
            assert path.read_text(encoding="utf-8") == xml.replace("MetaCubeX/ClashMetaForAndroid", "aldington-david/ClashMetaForAndroid").replace("MetaCubeX/Clash.Meta", "aldington-david/mihomo")
        for name, before, after in (
            (".gitmodules", "aldington-david/mihomo", "MetaCubeX/mihomo"),
            ("core/src/foss/golang/go.mod", "=> ./clash", "=> ./other"),
            ("build.gradle.kts", APP_ID, "com.github.metacubex.clash"),
            ("build.gradle.kts", 'storeType = "PKCS12"', 'storeType = "JKS"'),
            ("build.gradle.kts", '?: error("Release signing.properties is required; debug signing is forbidden")', '?: signingConfigs["debug"]'),
            ("app/src/main/AndroidManifest.xml", "${applicationId}.action.START_CLASH", "com.github.metacubex.clash.meta.action.START_CLASH"),
        ):
            path = source / name
            saved = path.read_text(encoding="utf-8")
            assert before in saved
            path.write_text(saved.replace(before, after), encoding="utf-8")
            rejects(lambda: validate_source(source))
            path.write_text(saved, encoding="utf-8")
        (source / "release.keystore").write_bytes(b"public upstream signing material")
        rejects(lambda: validate_source(source))
        (source / "release.keystore").unlink()
        gradle.write_text(original, encoding="utf-8")
        duplicate = source / "design/src/main/res/values/links.xml"
        duplicate.write_text(xml.replace("</resources>", '<string name="meta_github_url">duplicate</string></resources>'), encoding="utf-8")
        rejects(lambda: customize(source))
        for name in ("source.patch", "customize.py"):
            path = source / ".github/fork" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes((CONTROLLER / ".github/fork" / name).read_bytes())
        digest = source_fingerprint(source)
        (source / ".github/fork/README.md").write_text("documentation only")
        (source / ".github/workflows").mkdir()
        (source / ".github/workflows/anytls-release.yml").write_text("workflow only")
        assert source_fingerprint(source) == digest
        path = source / ".github/fork/customize.py"
        path.write_bytes(path.read_bytes() + b"\n# changed source rewrite\n")
        assert source_fingerprint(source) != digest
    print("prepare self-test passed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default="source")
    parser.add_argument("--upstream-tag", default="")
    parser.add_argument("--core-tag", default="")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    self_test() if args.self_test else prepare(args)
