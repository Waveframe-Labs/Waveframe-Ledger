"""Resolve and exercise the real combined wheel set after Guard 0.19 is supplied.

Requires retained base evidence for this head and a coordinator-supplied manifest;
see docs/LEDGER_090_ACCEPTANCE.md. Never synthesizes a package or bypasses pip.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import tarfile
from email.parser import BytesParser
import zipfile

from run_action_policy_acceptance import Acceptance, ROOT


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def guard_candidate(manifest_path):
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["source_url"] == "https://github.com/Waveframe-Labs/Waveframe-Guard"
    assert re.fullmatch(r"[0-9a-f]{40}", manifest["source_commit"])
    assert re.fullmatch(r"[0-9a-f]{64}", manifest["wheel_sha256"])
    assert manifest["provenance_kind"] == "coordinator-supplied-exact-candidate"
    wheel = (manifest_path.parent / manifest["wheel"]).resolve()
    assert wheel.suffix == ".whl" and sha256(wheel) == manifest["wheel_sha256"]
    with zipfile.ZipFile(wheel) as archive:
        metadata_names = [n for n in archive.namelist() if n.endswith(".dist-info/METADATA")]
        assert len(metadata_names) == 1
        metadata = BytesParser().parsebytes(archive.read(metadata_names[0]))
        assert metadata["Name"] == "waveframe-guard" and metadata["Version"] == "0.19.0"
        from packaging.requirements import Requirement
        requirements = [Requirement(r) for r in metadata.get_all("Requires-Dist", [])]
        assert all(r.url is None for r in requirements), "Runtime metadata must use version requirements"
        ledger, = [r for r in requirements if r.name == "governance-ledger" and r.marker is None]
        assert str(ledger.specifier) == "<0.10.0,>=0.9.0"
    return wheel, manifest


def execute(gate, expected_head, base_path, manifest_path):
    assert re.fullmatch(r"[0-9a-f]{40}", expected_head)
    assert gate.run("head", "git", "rev-parse", "HEAD").strip() == expected_head
    gate.run("clean-checkout", "git", "diff", "--exit-code", "HEAD")
    base = json.loads((base_path / "acceptance.json").read_text(encoding="utf-8"))
    assert base["head"] == base["expected_head"] == expected_head
    assert base["gates"]["base"] == "passed"
    assert base["python"].split()[0] == sys.version.split()[0], "Use this interpreter's base evidence"
    gate.report.update(head=expected_head, expected_head=expected_head,
                       base_evidence_sha256=sha256(base_path / "acceptance.json"))
    gate.report["gates"]["base"] = "passed"
    wheelhouse = gate.output / "wheelhouse"
    wheelhouse.mkdir()
    for filename, digest in base["package_sha256"].items():
        path = base_path / "dist" / filename
        assert sha256(path) == digest
        shutil.copyfile(path, wheelhouse / filename)
    ledger = wheelhouse / "governance_ledger-0.9.0-py3-none-any.whl"
    compiler = base_path / base["compiler_wheel"]["filename"]
    assert base["compiler_wheel"]["origin"]["vcs_info"]["commit_id"] == "ae590dee058d3481e384dea850d5b7d980f533ff"
    assert sha256(compiler) == base["compiler_wheel"]["sha256"]
    shutil.copyfile(compiler, wheelhouse / compiler.name)
    compiler = wheelhouse / compiler.name
    guard, manifest = guard_candidate(manifest_path)
    shutil.copyfile(guard, wheelhouse / guard.name)
    guard = wheelhouse / guard.name
    gate.report["guard_candidate"] = manifest
    gate.report["compiler_origin"] = base["compiler_wheel"]
    gate.report["package_sha256"] = {p.name: sha256(p) for p in wheelhouse.iterdir()}
    gate.report["combined_extra"] = {"status": "incomplete", "executed": True}
    gate.report["gates"]["combined_extra"] = "incomplete"
    gate.save()
    # Restore the exact packaged support tree, without Ledger source, even when
    # the original CI virtual environments/support directory have expired.
    support = gate.output / "installed-support"
    support.mkdir()
    with tarfile.open(wheelhouse / "governance_ledger-0.9.0.tar.gz") as archive:
        for member in archive.getmembers():
            if not member.isfile():
                continue
            path = Path(*Path(member.name).parts[1:])
            assert path.parts and not path.is_absolute() and ".." not in path.parts
            if path.parts[0] in {"tests", "schemas", "examples", "tools", "docs"} or len(path.parts) == 1:
                target = support / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.extractfile(member).read())
    for path, digest in base["sdist_resource_sha256"].items():
        assert sha256(support / path) == digest
    (support / "runtime").mkdir()
    gate.env["WAVEFRAME_LEDGER_TEST_WHEEL"] = str(ledger)
    python = gate.environment("combined-extra", f"{ledger}[dev,guard]", compiler, guard)
    expected = gate.output / "wheel-set.json"
    expected.write_text(json.dumps({"wheels": [str(p) for p in (ledger, compiler, guard)]}), encoding="utf-8")
    gate.probe(python, support, "combined-provenance", "check_installed_wheel_set.py", expected)
    gate.suites(python, support, "combined-extra", installed=True, guard=True)
    gate.probe(python, support, "release-package", "check_release_catalog_package.py")
    gate.probe(python, support, "development-package", "check_action_policy_package.py", native=True)
    gate.run("legacy-v3-example", python, "-I", support / "examples/native_v3_multi_control.py", "--candidate", cwd=support)
    gate.probe(python, support, "catalog-3-execution", "check_guard_release_execution.py")
    assert gate.run("final-head", "git", "rev-parse", "HEAD").strip() == expected_head
    gate.run("final-clean-checkout", "git", "diff", "--exit-code", "HEAD")
    gate.report["gates"]["combined_extra"] = "passed"
    gate.report["combined_extra"] = {"status": "passed", "executed": True,
        "scope": "this operating system/interpreter only; all four matrix cells required"}
    gate.report["status"] = "combined-extra-passed"
    gate.save()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--base-evidence", type=Path, required=True)
    parser.add_argument("--guard-candidate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    gate = Acceptance(args.output)
    try:
        execute(gate, args.expected_head, args.base_evidence.resolve(), args.guard_candidate.resolve())
    except BaseException as exc:
        gate.report.update(status="failed", error=str(exc))
        gate.report["gates"]["combined_extra"] = "failed"
        gate.save()
        raise


if __name__ == "__main__":
    main()
