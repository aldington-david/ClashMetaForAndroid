"""Small, checked source rewrites that do not depend on neighbouring translations."""
import configparser
import re
import xml.etree.ElementTree as ET

APP_ID = "com.github.aldingtondavid.cmfa"
APP_NAME = "CMFA AnyTLS REALITY"
LINKS = {
    "meta_github_url": "https://github.com/aldington-david/ClashMetaForAndroid",
    "clash_meta_core_url": "https://github.com/aldington-david/mihomo",
}


def set_version(source, tag, code):
    if not re.fullmatch(r"v\d+\.\d+\.\d+", tag) or not 1_000_000_000 < code < 2_100_000_000:
        raise ValueError("Invalid Android release version")
    source, names = re.subn(r'versionName = "[^"]+"', f'versionName = "{tag[1:]}"', source)
    source, codes = re.subn(r"versionCode = \d+", f"versionCode = {code}", source)
    if (names, codes) != (1, 1):
        raise ValueError("Upstream version declaration changed; review required")
    return source


def customize(source):
    gradle = source / "build.gradle.kts"
    text = gradle.read_text(encoding="utf-8")
    for field in ("launch_name", "application_name"):
        text, count = re.subn(
            rf'resValue\(\s*"string"\s*,\s*"{field}"\s*,\s*"@string/{field}_meta"\s*\)',
            f'resValue("string", "{field}", "{APP_NAME}")', text)
        if count != 1:
            raise ValueError(f"Expected one meta {field} declaration, got {count}")
    gradle.write_text(text, encoding="utf-8", newline="\n")
    resources = source / "design/src/main/res"
    found = set()
    for path in resources.glob("values*/*.xml"):
        text = path.read_text(encoding="utf-8")
        for element in ET.fromstring(text).findall("string"):
            name = element.get("name")
            if name not in LINKS:
                continue
            key = (path.parent.name, name)
            if key in found:
                raise ValueError(f"Duplicate resource {key}")
            found.add(key)
            pattern = rf'(<string\b[^>]*\bname\s*=\s*[\'\"]{name}[\'\"][^>]*>).*?(</string\s*>)'
            text, count = re.subn(pattern, lambda match: match[1] + LINKS[name] + match[2], text, flags=re.DOTALL)
            if count != 1:
                raise ValueError(f"Cannot safely rewrite {name} in {path}")
        if text != path.read_text(encoding="utf-8"):
            path.write_text(text, encoding="utf-8", newline="\n")
    if not all(("values", name) in found for name in LINKS):
        raise ValueError("Default repository link resources are missing")


def validate_source(source):
    config = configparser.ConfigParser(interpolation=None)
    config.read(source / ".gitmodules", encoding="utf-8")
    expected = {"path": "core/src/foss/golang/clash", "url": LINKS["clash_meta_core_url"], "branch": "anytls-reality"}
    if dict(config['submodule "clash-foss"']) != expected:
        raise ValueError("Custom core submodule configuration changed")
    for path, target in (("foss", "./clash"), ("main", "../../foss/golang/clash")):
        text = (source / f"core/src/{path}/golang/go.mod").read_text(encoding="utf-8")
        if re.findall(r"(?m)^replace github\.com/metacubex/mihomo => (\S+)\s*$", text) != [target]:
            raise ValueError(f"{path} Go module must use the pinned local core")
    text = (source / "build.gradle.kts").read_text(encoding="utf-8")
    for value in (APP_ID, 'storeType = "PKCS12"', '?: error("Release signing.properties is required; debug signing is forbidden")'):
        if text.count(value) != 1:
            raise ValueError(f"Missing or duplicate required build setting: {value}")
    if 'applicationIdSuffix = ".meta"' in text or 'signingConfigs["debug"]' in text:
        raise ValueError("Official package suffix or debug signing fallback remains")
    for field in ("launch_name", "application_name"):
        if text.count(f'resValue("string", "{field}", "{APP_NAME}")') != 1:
            raise ValueError("Custom meta display name is missing")
    manifest = source / "app/src/main/AndroidManifest.xml"
    actions = [node.get("{http://schemas.android.com/apk/res/android}name") for node in ET.parse(manifest).iter("action")]
    for action in ("START_CLASH", "STOP_CLASH", "TOGGLE_CLASH"):
        if actions.count("${applicationId}.action." + action) != 1:
            raise ValueError("External control action must follow the custom application ID")
    for path in source.glob("*/src/**/AndroidManifest.xml"):
        if "com.github.metacubex.clash" in path.read_text(encoding="utf-8"):
            raise ValueError(f"Official application ID remains in {path}")
    for path in (source / "design/src/main/res").glob("values*/*.xml"):
        for element in ET.parse(path).getroot().findall("string"):
            if element.get("name") in LINKS and element.text != LINKS[element.get("name")]:
                raise ValueError(f"Repository resource still targets upstream: {path}")
    if any((source / name).exists() for name in ("release.keystore", "signing.properties", "local.properties")):
        raise ValueError("Build source must not include signing material or local overrides")
