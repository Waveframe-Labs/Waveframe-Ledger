"""Collect immutable issue25 acceptance; invoke only after the required CI finishes."""
import argparse, hashlib, json, pathlib, subprocess, zipfile, xml.etree.ElementTree as ET

def gh(*args):
    return json.loads(subprocess.check_output(['gh', *args]))

def digest(data):
    return hashlib.sha256(data).hexdigest()

def suites(data):
    cases = list(ET.fromstring(data).iter('testcase'))
    failed = [c for c in cases if c.find('failure') is not None or c.find('error') is not None]
    skipped = [c for c in cases if c.find('skipped') is not None]
    return {'passed': len(cases) - len(failed) - len(skipped), 'failed': len(failed), 'skipped': len(skipped), 'skip_reasons': sorted({c.find('skipped').get('message', '') for c in skipped})}
parser = argparse.ArgumentParser()
parser.add_argument('--run', required=True)
parser.add_argument('--head', required=True)
parser.add_argument('--output', required=True)
args = parser.parse_args()
repo = 'Waveframe-Labs/Waveframe-Ledger'
out = pathlib.Path(args.output).resolve()
out.mkdir(parents=True, exist_ok=False)
run = gh('api', f'repos/{repo}/actions/runs/{args.run}')
assert run['head_sha'] == args.head and run['conclusion'] == 'success', run['conclusion']
(out / 'ci-run.json').write_text(json.dumps(run, indent=2), encoding='utf-8')
artifacts = gh('api', f'repos/{repo}/actions/runs/{args.run}/artifacts')['artifacts']
assert len(artifacts) == 4
(out / 'ci-artifacts.json').write_text(json.dumps(artifacts, indent=2), encoding='utf-8')
stack = gh('pr', 'list', '--repo', repo, '--json', 'number,headRefName,headRefOid,baseRefName,isDraft')
(out / 'stack.json').write_text(json.dumps(stack, indent=2), encoding='utf-8')
expected = {18: '54379d9c8044544fc1b8f32109bdfce35c1c6a05', 20: '4dbdfbaee92d43b888cae751ecaee5d9e4ec20b7', 22: '40e0875ee9a973254bb3a4d0c228cad4fdce2bc0', 24: '3cc34e7b3cb6efca5102e0e22d559ec0c0fd583f'}
assert all((next((x for x in stack if x['number'] == n))['headRefOid'] == h for n, h in expected.items()))
handoff = {'head': args.head, 'base': expected[24], 'base_branch': 'feat/issue-23-ledger-090', 'pr': f'https://github.com/{repo}/pull/26', 'guard_head': '0161ef8a52e052d1bc1366cdc93ce13a9bd535ed', 'compiler_head': 'ae590dee058d3481e384dea850d5b7d980f533ff', 'guard_evidence_commit': 'e6008345c9891ec6ffb5088f38177022e3cef4aa', 'ci_run': run['html_url'], 'release_ready': False, 'runtime_activation_ready': False, 'cells': {}, 'archive_sha256': {}, 'downstream': ['Coordination: Guard must repin/revalidate this exact Ledger head and package set, rerun red combined CI, and correct its stale README Ledger 0.7 minimum.', 'Cloud must complete final package-set and Console acceptance; #151 used earlier packages.', 'Publication order Compiler 0.5.0 -> Ledger 0.9.0 -> Guard 0.19.0; ordinary index acceptance and separately authorized Cloud rollout/activation remain pending.'], 'authorization': 'No sibling changes, merges, tags, publication, deployment or activation.'}
(out / 'artifacts').mkdir()
for artifact in artifacts:
    name = artifact['name']
    print('Downloading', name, flush=True)
    raw = subprocess.check_output(['gh', 'api', f"repos/{repo}/actions/artifacts/{artifact['id']}/zip", '--allow-escape-sequences'])
    archive_hash = digest(raw)
    if artifact.get('digest'):
        assert artifact['digest'] == 'sha256:' + archive_hash
    archive_path = out / 'artifacts' / (name + '.zip')
    archive_path.write_bytes(raw)
    handoff['archive_sha256'][archive_path.relative_to(out).as_posix()] = archive_hash
    with zipfile.ZipFile(archive_path) as z:

        def read(suffix):
            matches = [p for p in z.namelist() if p.endswith(suffix)]
            assert len(matches) == 1, (suffix, matches)
            return z.read(matches[0])
        base = json.loads(read('issue25-base/acceptance.json'))
        combined = json.loads(read('issue25-combined/acceptance.json'))
        assert base['head'] == combined['head'] == args.head
        assert base['gates']['base'] == 'passed' and combined['gates']['combined_extra'] == 'passed'
        assert base['release_ready'] is combined['release_ready'] is False
        assert combined['catalog_3_execution_cases'] == 56
        for filename, value in base['package_sha256'].items():
            assert digest(read('issue25-base/dist/' + filename)) == value == combined['package_sha256'][filename]
            assert digest(read('issue25-combined/wheelhouse/' + filename)) == value
        for filename, value in combined['package_sha256'].items():
            assert digest(read('issue25-combined/wheelhouse/' + filename)) == value
        for version in ('0.7.0', '0.8.0'):
            rejection = read('issue25-combined/reject-old-ledger-' + version + '.log').decode()
            assert 'ResolutionImpossible' in rejection and 'waveframe-guard 0.19.0 depends on governance-ledger<0.10.0 and >=0.9.0' in rejection
        assert all((c['exit_code'] == 0 for c in combined['commands'] if not c['label'].startswith('reject-old-ledger-')))
        assert all((c['exit_code'] != 0 for c in combined['commands'] if c['label'].startswith('reject-old-ledger-')))
        assert json.loads(read('issue25-combined/guard-entry-catalog-3.json'))['development_flags_absent']
        assert len(json.loads(read('issue25-combined/guard-entry-catalog-3.json'))['cases']) == 56
        cell = combined['verified_inputs']['cell']
        summaries = {}
        for stage, label in [('base', 'source-default'), ('base', 'source-native'), ('base', 'installed-default'), ('base', 'installed-native'), ('combined', 'combined-extra-default'), ('combined', 'combined-extra-native')]:
            summary = suites(read('issue25-' + stage + '/' + label + '.xml'))
            assert summary['failed'] == 0
            summary.update((base if stage == 'base' else combined)['suites'][label])
            assert summary['release_passed'] == 70
            assert summary['native_passed'] == (44 if label.endswith('native') else 0)
            summaries[label] = summary
        handoff['cells'][cell] = {'platform': base['platform'], 'python': base['python'], 'base_gate': 'passed', 'combined_gate': 'passed', 'suites': summaries, 'package_sha256': combined['package_sha256'], 'catalog_3_execution_cases': 56, 'compiler_source_archive_bytes_equal': base['compiler_source_archive_bytes_equal'], 'guard_manifest': combined['guard_candidate'], 'input_archive_sha256': combined['verified_inputs']['archive_sha256'], 'archive': archive_path.relative_to(out).as_posix(), 'guard_entry_upgrade': 'passed', 'old_ledger_rejection': 'passed'}
        folder = out / 'cells' / cell
        folder.mkdir(parents=True)
        for stage, value in [('base', base), ('combined', combined)]:
            (folder / (stage + '-acceptance.json')).write_text(json.dumps(value, indent=2), encoding='utf-8')
        (folder / 'suites.json').write_text(json.dumps(summaries, indent=2), encoding='utf-8')
assert set(handoff['cells']) == {'windows-3.10', 'windows-3.14', 'ubuntu-3.10', 'ubuntu-3.14'}
(out / 'handoff.json').write_text(json.dumps(handoff, indent=2), encoding='utf-8')
(out / '.gitattributes').write_text('* -text\n', encoding='utf-8')
(out / 'README.md').write_text(f"# Ledger issue #25 durable acceptance\n\nCandidate `{args.head}`, draft [#26](https://github.com/{repo}/pull/26), stacked on `{expected[24]}`.\nRequired [final-head CI]({run['html_url']}) passed all four Windows/Linux × Python 3.10/3.14 cells.\nSee handoff.json for per-suite JUnit outcomes, package SHA-256 hashes and downstream coordination.\n\nEach retained CI ZIP contains fresh Ledger wheel/sdist bytes, the same bytes used in base/combined acceptance,\ncomplete command logs and exit codes, JUnit, source/installed import paths, exact Compiler Git and verified\narchive provenance, Guard candidate provenance, ordinary pip resolver reports, package/example checks,\n56 required real execution probes, Guard upgrade and old-Ledger rejection checks. Nested immutable Guard\narchives retain the original failed combined evidence and prior install/upgrade and supplemental probes.\nSHA256SUMS covers every retained file except itself. These archives are committed here independently of\nexpiring CI retention; the candidate branch and older PR stack heads are unchanged.\n\n`release_ready=false`, `runtime_activation_ready=false`. Guard repinning/revalidation and Cloud final-set/\nConsole acceptance remain pending coordination. Publication order remains Compiler → Ledger → Guard.\nNo merge, tag, publication, deployment or activation is authorized.\n", encoding='utf-8')
files = sorted((p for p in out.rglob('*') if p.is_file()))
(out / 'SHA256SUMS').write_text(''.join((digest(p.read_bytes()) + '  ' + p.relative_to(out).as_posix() + '\n' for p in files)), encoding='utf-8')
print(json.dumps(handoff, indent=2))
