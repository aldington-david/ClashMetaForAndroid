"""Prepare an immutable, patched upstream release; never overwrite a release tag."""
import argparse
import base64
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import urllib.error
import urllib.parse
import urllib.request

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


def set_version(source, tag, code):
    if not re.fullmatch(r"v\d+\.\d+\.\d+", tag) or not 1_000_000_000 < code < 2_100_000_000:
        raise ValueError("Invalid Android release version")
    source, names = re.subn(r'versionName = "[^"]+"', f'versionName = "{tag[1:]}"', source)
    source, codes = re.subn(r"versionCode = \d+", f"versionCode = {code}", source)
    if (names, codes) != (1, 1):
        raise ValueError("Upstream version declaration changed; review required")
    return source


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
        output(build=False, tag=tag)
        print(f"Already published: {tag}")
        return
    destination = Path(args.source).resolve()
    if destination.exists():
        raise ValueError("Build source directory must not already exist")
    existing_tag = api(f"repos/{repository}/git/ref/tags/{tag}", missing_ok=True)
    if existing_tag:
        git("clone", "--depth", "1", "--branch", tag, f"https://github.com/{repository}.git", str(destination))
        manifest = json.loads((destination / "build-info.json").read_text(encoding="utf-8"))
        if manifest["upstream_tag"] != upstream_tag or manifest["core_tag"] != core_tag:
            raise ValueError("Existing tag provenance does not match this build")
    else:
        upstream_sha, core_sha = commit(UPSTREAM, upstream_tag), commit(CORE, core_tag)
        git("clone", "--filter=blob:none", "--single-branch", "--branch", upstream_tag, f"https://github.com/{UPSTREAM}.git", str(destination))
        if git("rev-parse", "HEAD", cwd=destination, capture=True) != upstream_sha:
            raise ValueError("Upstream release tag moved during checkout")
        git("apply", "--check", str(CONTROLLER / ".github/fork/source.patch"), cwd=destination)
        git("apply", str(CONTROLLER / ".github/fork/source.patch"), cwd=destination)
        # Upstream signing material and workflows must never enter our release build.
        (destination / "release.keystore").unlink(missing_ok=True)
        shutil.rmtree(destination / ".github/workflows")
        shutil.copytree(CONTROLLER / ".github/workflows", destination / ".github/workflows")
        shutil.copytree(CONTROLLER / ".github/fork", destination / ".github/fork", ignore=shutil.ignore_patterns("__pycache__"))
        code = 1_000_000_000 + int(os.environ["GITHUB_RUN_NUMBER"])
        gradle = destination / "build.gradle.kts"
        gradle.write_text(set_version(gradle.read_text(encoding="utf-8"), upstream_tag, code), encoding="utf-8")
        manifest = {
            "upstream_repository": UPSTREAM, "upstream_tag": upstream_tag, "upstream_sha": upstream_sha,
            "core_repository": CORE, "core_tag": core_tag, "core_sha": core_sha,
            "release_tag": tag, "application_id": "com.github.aldingtondavid.cmfa",
            "version_code": code, "controller_sha": os.environ["GITHUB_SHA"],
        }
        (destination / "build-info.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        git("config", "user.name", "github-actions[bot]", cwd=destination)
        git("config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com", cwd=destination)
        git("add", "-A", cwd=destination)
        git("update-index", "--add", "--cacheinfo", f"160000,{core_sha},{CORE_PATH}", cwd=destination)
        git("commit", "-m", f"Build {upstream_tag} with AnyTLS REALITY core {core_tag}", cwd=destination)
        git("remote", "set-url", "origin", f"https://github.com/{repository}.git", cwd=destination)
        git("tag", tag, cwd=destination)
        git("push", "origin", f"refs/tags/{tag}", cwd=destination, authenticated=True)
    output(build=True, tag=tag, version=upstream_tag[1:], core_sha=manifest["core_sha"],
           core_tag=manifest["core_tag"], source_sha=git("rev-parse", "HEAD", cwd=destination, capture=True))


def self_test():
    updated = set_version('versionName = "2.11.34"\nversionCode = 211034\n', "v2.11.35", 1_000_000_005)
    assert updated == 'versionName = "2.11.35"\nversionCode = 1000000005\n'
    for source, tag, code in [("", "v2.11.35", 1_000_000_005),
                              ('versionName = "x"\nversionCode = 1', "../../bad", 1_000_000_005),
                              ('versionName = "x"\nversionCode = 1', "v2.11.35", 2_100_000_000)]:
        try:
            set_version(source, tag, code)
        except ValueError:
            pass
        else:
            raise AssertionError("Invalid version accepted")
    print("prepare self-test passed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default="source")
    parser.add_argument("--upstream-tag", default="")
    parser.add_argument("--core-tag", default="")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    self_test() if args.self_test else prepare(args)
