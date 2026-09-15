"""Record actual installed module paths, PEP 610 and wheel/source hashes."""
import hashlib
import importlib
import importlib.metadata as metadata
import json
from pathlib import Path
import sys
import zipfile

expected = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
result = {"python": sys.version, "executable": sys.executable, "distributions": {}}
for name, version, module in (("governance-ledger", "0.9.0", "governance_ledger"),
                              ("cricore-contract-compiler", "0.5.0", "compiler"),
                              ("waveframe-guard", "0.19.0", "waveframe_guard")):
    dist = metadata.distribution(name)
    assert dist.version == version
    path = Path(importlib.import_module(module).__file__).resolve()
    assert Path(sys.prefix).resolve() in path.parents
    wheel, = [Path(p) for p in expected["wheels"] if Path(p).name.startswith(name.replace("-", "_") + "-")]
    digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
    direct = json.loads(dist.read_text("direct_url.json"))
    assert direct["archive_info"]["hashes"]["sha256"] == digest
    files = {}
    with zipfile.ZipFile(wheel) as archive:
        for member in archive.namelist():
            if member.endswith(".py"):
                data = archive.read(member)
                assert Path(dist.locate_file(member)).read_bytes() == data, member
                files[member] = hashlib.sha256(data).hexdigest()
    result["distributions"][name] = {"version": dist.version, "module_path": str(path),
        "wheel_sha256": digest, "direct_url": direct, "python_sha256": files}
assert callable(importlib.import_module("compiler").compile_action_policy)
print(json.dumps(result, indent=2))
