"""Check the installed development dependency, never infer provenance from version."""
import hashlib
import importlib.metadata as metadata
import json
from pathlib import Path
import sys

import compiler
import governance_ledger

CANDIDATE = "ae590dee058d3481e384dea850d5b7d980f533ff"
URL = "https://github.com/Waveframe-Labs/cricore-contract-compiler.git"
dist = metadata.distribution("cricore-contract-compiler")
direct = json.loads(dist.read_text("direct_url.json") or "null")
assert dist.version == "0.5.0", dist.version
assert direct["url"] == URL, direct
assert direct["vcs_info"] == {
    "vcs": "git", "requested_revision": CANDIDATE, "commit_id": CANDIDATE,
}, direct
assert callable(compiler.compile_action_policy)
assert Path(sys.prefix).resolve() in Path(compiler.__file__).resolve().parents
files = {
    str(entry): hashlib.sha256(Path(dist.locate_file(entry)).read_bytes()).hexdigest()
    for entry in sorted(dist.files, key=str)
    if str(entry).endswith(".py")
}
print(json.dumps({
    "python": sys.version, "executable": sys.executable,
    "ledger_version": metadata.version("governance-ledger"),
    "ledger_import": governance_ledger.__file__, "compiler_version": dist.version,
    "compiler_import": compiler.__file__, "direct_url": direct,
    "installed_compiler_python_sha256": files,
}, indent=2))
