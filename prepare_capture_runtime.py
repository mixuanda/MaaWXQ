"""Download a hash-pinned official runtime locally; no pip/global/system installation."""
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parent


def prepare(root=ROOT):
    pin = json.loads((root / "capture-runtime.lock.json").read_text(encoding="utf-8"))
    target = root / "local" / ("maafw-" + pin["version"])
    if target.exists():
        raise ValueError("runtime_directory_exists; verify or choose a clean checkout, do not overwrite it")
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="maawxq-runtime-", dir=target.parent) as temp:
        temp = Path(temp)
        wheel = temp / pin["filename"]
        with urllib.request.urlopen(pin["url"], timeout=30) as response, wheel.open("xb") as output:
            shutil.copyfileobj(response, output)
        if hashlib.sha256(wheel.read_bytes()).hexdigest() != pin["sha256"]:
            raise ValueError("runtime_checksum_mismatch")
        extracted = temp / "runtime"
        extracted.mkdir()
        with zipfile.ZipFile(wheel) as archive:
            for member in archive.infolist():
                path = Path(member.filename)
                if path.is_absolute() or ".." in path.parts or "\\" in member.filename:
                    raise ValueError("unsafe_runtime_archive")
                archive.extract(member, extracted)
        hashes = {str(path.relative_to(extracted)).replace("\\", "/"): hashlib.sha256(path.read_bytes()).hexdigest()
                  for path in extracted.rglob("*.dll")}
        if not hashes:
            raise ValueError("runtime_dlls_missing")
        (extracted / "receipt.json").write_text(json.dumps({"version": pin["version"], "wheel_sha256": pin["sha256"],
                                                           "dll_sha256": hashes}, indent=2), encoding="utf-8")
        extracted.rename(target)
    return {"status": "prepared", "version": pin["version"], "location": str(target)}


if __name__ == "__main__":
    try:
        print(json.dumps(prepare(), indent=2))
    except (OSError, ValueError, zipfile.BadZipFile) as error:
        print(json.dumps({"status": "unavailable", "reason": str(error)}))
        raise SystemExit(1)
