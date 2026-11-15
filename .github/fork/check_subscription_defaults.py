"""Exercise the actual Kotlin creation expression and deep-link block without Android state."""
import argparse
import os
from pathlib import Path
import re
import subprocess
import tempfile
import textwrap


def extract(source):
    manager = (source / "service/src/main/java/com/github/kr328/clash/service/ProfileManager.kt").read_text(encoding="utf-8")
    create = manager.split("override suspend fun create(", 1)[1].split("override suspend fun clone(", 1)[0]
    expression = re.search(r"\binterval = (.*?),\s*upload = 0,", create, re.DOTALL)
    if not expression or "TimeUnit.HOURS.toMillis(6)" not in expression[1]:
        raise ValueError("Missing six-hour creation default")
    activity = (source / "app/src/main/java/com/github/kr328/clash/ExternalControlActivity.kt").read_text(encoding="utf-8")
    start = activity.index("                        val type = when")
    end = activity.index("\n                    }\n                    startActivity", start)
    block = textwrap.dedent(activity[start:end])
    if "create(type, name, url)" not in block or "if (explicitInterval != null)" not in block:
        raise ValueError("Deep links must retain defaults only when their interval is absent")
    return expression[1], block


def check(source, run_jvm=False):
    expression, block = extract(source)
    if not run_jvm:
        print("Subscription source contracts checked; JVM execution is reserved for CI")
        return
    harness = '''
import java.util.Locale
class Profile { enum class Type { Url, File, External } }
fun initialInterval(type: Profile.Type, source: String): Long = EXPRESSION
class TestUri(private val values: Map<String, String>) {
    fun getQueryParameter(key: String): String? = values[key]
}
object R { object string { const val new_profile = 1 } }
fun getString(id: Int): String = "New profile $id"
data class Record(var interval: Long)
class TestManager {
    fun create(type: Profile.Type, name: String, source: String): Record = Record(initialInterval(type, source))
    fun patch(record: Record, name: String, source: String, interval: Long, key: String?) { record.interval = interval }
}
fun importLink(values: Map<String, String>): Long {
    val uri = TestUri(values)
    val url = values.getValue("url")
    return with(TestManager()) {
BLOCK
    }.interval
}
fun main() {
    val sixHours = 21_600_000L
    for (type in listOf(Profile.Type.Url, Profile.Type.External)) {
        for (source in listOf("http://example.invalid/sub", "https://example.invalid/sub", "HTTPS://example.invalid/sub")) {
            check(initialInterval(type, source) == sixHours)
        }
        check(initialInterval(type, "content://fixture/profile") == 0L)
        check(initialInterval(type, "ftp://example.invalid/profile") == 0L)
    }
    check(initialInterval(Profile.Type.Url, "") == sixHours)
    check(initialInterval(Profile.Type.External, "") == 0L)
    check(initialInterval(Profile.Type.File, "https://example.invalid/sub") == 0L)
    check(initialInterval(Profile.Type.File, "") == 0L)
    val remote = mapOf("url" to "https://example.invalid/sub")
    check(importLink(remote) == sixHours)
    check(importLink(mapOf("url" to "content://fixture/profile")) == 0L)
    check(importLink(remote + ("type" to "file")) == 0L)
    for ((text, expected) in listOf("360" to sixHours, "30" to 1_800_000L, "1" to 900_000L, "0" to 0L, "-1" to 0L, "invalid" to 0L, "" to 0L)) {
        check(importLink(remote + ("update-interval" to text)) == expected)
    }
    println("CMFA Kotlin subscription defaults and explicit deep-link intervals passed")
}
'''.replace("EXPRESSION", expression).replace("BLOCK", textwrap.indent(block, "        "))
    temporary = Path(os.environ.get("RUNNER_TEMP", tempfile.gettempdir())).resolve()
    with tempfile.TemporaryDirectory(prefix="cmfa-subscription-check-", dir=temporary) as directory:
        root = Path(directory).resolve()
        assert root.parent == temporary
        entry = root / "Main.kt"
        entry.write_text(harness, encoding="utf-8")
        jar = root / "checks.jar"
        subprocess.run(["kotlinc", str(entry), "-include-runtime", "-d", str(jar)], check=True)
        subprocess.run(["java", "-jar", str(jar)], check=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=Path("."))
    parser.add_argument("--run-jvm", action="store_true")
    args = parser.parse_args()
    check(args.source, args.run_jvm)
