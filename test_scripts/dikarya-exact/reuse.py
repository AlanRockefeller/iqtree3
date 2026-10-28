#!/usr/bin/env python3
"""Validate a new candidate against hashed results from a completed real replay.

This is correctness validation only. Historical reference timings are never
used for performance ratios or included in the new execution results.
"""

import argparse
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
import time


HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('dikarya_replay', HERE / 'run.py')
replay = importlib.util.module_from_spec(spec)
spec.loader.exec_module(replay)


def required(condition, message):
    if not condition:
        raise ValueError(message)


def command(binary, case, input_path, prefix):
    return [str(binary), '-s', str(input_path), '-m', case['model'], '-T', '1',
            '--prefix', str(prefix), '--seed', str(case['seed']), '--redo'] + case['options']


def verify_artifacts(entry):
    """Verify the complete raw reference inventory, including compressed bytes."""
    comparison = entry['comparison']
    required(comparison.get('identical') is True and comparison.get('differences') == [],
             'Reference report contains an unsuccessful comparison')
    required(comparison.get('excluded_operational_artifacts') == sorted(replay.IGNORED_SUFFIXES),
             'Reference report used a different artifact exclusion policy')
    prefix = Path(entry['reference']['prefix'])
    checks = comparison.get('checks')
    required(isinstance(checks, list) and checks, 'Reference artifact hashes are missing')
    expected = {}
    for check in checks:
        suffix = check.get('suffix')
        required(isinstance(suffix, str) and re.fullmatch(r'\.[A-Za-z0-9][A-Za-z0-9._-]*', suffix),
                 'Unsafe reference artifact suffix')
        required(suffix not in expected, 'Duplicate reference artifact suffix')
        required(check.get('identical') is True, 'Reference report contains an unequal artifact')
        mode = 'normalized operational metadata' if suffix in replay.TEXT_SUFFIXES else 'byte-identical'
        required(check.get('mode') == mode, 'Reference artifact comparison policy changed')
        digest = check.get('reference_sha256')
        required(isinstance(digest, str) and re.fullmatch(r'[0-9a-f]{64}', digest),
                 'Invalid reference artifact SHA-256')
        expected[suffix] = check
    actual = replay.outputs(prefix)
    required(set(actual) == set(expected), 'Reference artifact inventory changed: ' + str(prefix))
    required({'.treefile', '.iqtree', '.log'} <= set(actual), 'Reference required outputs are missing')
    for suffix, path in actual.items():
        data = path.read_bytes()
        required(replay.sha256(data) == expected[suffix]['reference_sha256']
                 and len(data) == expected[suffix]['bytes'],
                 'Reference artifact changed: ' + str(path))


def validate_reference(report_path, manifest_path, work):
    """Reject partial reports, changed commands/inputs, or stale reference files."""
    report_bytes = report_path.read_bytes()
    report = json.loads(report_bytes)
    required(report.get('all_identical') is True, 'Reference report is not entirely identical')
    summary = report.get('summary')
    runs = report.get('runs')
    required(isinstance(summary, dict) and isinstance(runs, list) and runs,
             'Reference report is incomplete: completed summary and runs are required')
    required(type(summary.get('comparisons')) is int and summary['comparisons'] == len(runs),
             'Reference summary does not match the number of completed comparisons')
    manifest_bytes = manifest_path.read_bytes()
    required(report.get('manifest_sha256') == replay.sha256(manifest_bytes),
             'Reference report does not match the expected manifest SHA-256')
    cases = json.loads(manifest_bytes)['cases']
    by_id = {case['id']: case for case in cases}
    required(len(by_id) == len(cases) and cases, 'Manifest has duplicate or missing cases')
    reference = Path(report['reference'])
    required(reference.is_file() and replay.sha256(reference.read_bytes()) == report['reference_sha256'],
             'Reference executable differs from the binary recorded in the report')
    repeats = {}
    selected = {}
    for entry in runs:
        case_id = entry.get('case')
        required(case_id in by_id, 'Unknown case in reference report')
        case = by_id[case_id]
        iteration = entry.get('repeat')
        required(type(iteration) is int and iteration >= 1, 'Invalid reference repetition')
        completed = repeats.setdefault(iteration, set())
        required(case_id not in completed, 'Duplicate case in reference repetition')
        completed.add(case_id)
        execution = entry['reference']
        required(type(execution.get('returncode')) is int and execution['returncode'] == 0,
                 'Reference execution did not succeed')
        required(entry.get('job') == case['job'] and entry.get('group') == case['group'],
                 'Reference case identity differs from manifest')
        input_path = (work / 'inputs' / (case_id + '.fasta')).resolve()
        required(replay.sha256(input_path.read_bytes()) == case['input_sha256'],
                 'Prepared input does not match manifest: ' + str(input_path))
        required(execution.get('command') == command(reference, case, input_path, execution['prefix']),
                 'Reference command does not match manifest: ' + case_id)
        verify_artifacts(entry)
        if case.get('stored_tree_comparable'):
            tree = Path(execution['prefix'] + '.treefile')
            required(replay.sha256(tree.read_bytes()) == case['stored_tree_sha256'],
                     'Reference differs from retained production tree: ' + case_id)
        if case_id not in selected or iteration < selected[case_id]['repeat']:
            selected[case_id] = entry
    required(set(repeats) == set(range(1, len(repeats) + 1)), 'Reference repetitions are incomplete')
    required(all(completed == set(by_id) for completed in repeats.values()),
             'Reference report does not cover the complete manifest in every repetition')
    return report, replay.sha256(report_bytes), cases, selected


def run(args):
    source, source_hash, cases, references = validate_reference(
        args.reference_report, args.manifest, args.work)
    if args.case:
        wanted = set(args.case)
        required(wanted <= {case['id'] for case in cases}, 'Unknown requested case')
        cases = [case for case in cases if case['id'] in wanted]
    required(cases, 'No cases selected')
    required(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]*', args.label), 'Label must be a plain directory name')
    candidate_hash = replay.sha256(args.candidate.read_bytes())
    root = args.work / 'runs' / args.label
    root.mkdir(parents=True, exist_ok=False)
    results = []
    report = {
        'purpose': 'correctness validation only; no performance ratios from reused reference runs',
        'reference_reused': True, 'reference_report': str(args.reference_report),
        'reference_report_sha256': source_hash, 'reference': source['reference'],
        'reference_sha256': source['reference_sha256'], 'candidate': str(args.candidate),
        'candidate_sha256': candidate_hash, 'manifest_sha256': source['manifest_sha256'],
        'manifest_case_count': len(references), 'selected_case_ids': [case['id'] for case in cases],
        'covers_full_manifest': len(cases) == len(references), 'complete': False,
        'all_identical': False, 'runs': results,
    }
    destination = root / 'results.json'
    destination.write_text(json.dumps(report, indent=2) + '\n')
    for case in cases:
        case_id = case['id']
        previous = references[case_id]
        input_path = (args.work / 'inputs' / (case_id + '.fasta')).resolve()
        prefix = root / case_id / 'candidate/run'
        result = {'case': case_id, 'job': case['job'], 'group': case['group'],
                  'reference_reused': True, 'reference': {'prefix': previous['reference']['prefix'],
                                                        'original_repeat': previous['repeat']}}
        started = time.perf_counter()
        try:
            required(replay.sha256(args.candidate.read_bytes()) == candidate_hash,
                     'Candidate executable changed during validation')
            required(replay.sha256(input_path.read_bytes()) == case['input_sha256'],
                     'Prepared input changed during validation')
            result['candidate'] = replay.invoke(args.candidate, case, input_path, prefix, args.timeout)
            required(replay.sha256(args.candidate.read_bytes()) == candidate_hash,
                     'Candidate executable changed during validation')
            required(replay.sha256(input_path.read_bytes()) == case['input_sha256'],
                     'Prepared input changed during validation')
            verify_artifacts(previous)
            result['comparison'] = replay.compare(previous['reference']['prefix'], prefix, input_path)
            result['stored_tree_checked'] = bool(case.get('stored_tree_comparable'))
            if case.get('stored_tree_comparable'):
                if replay.sha256(Path(str(prefix) + '.treefile').read_bytes()) != case['stored_tree_sha256']:
                    result['comparison']['identical'] = False
                    result['comparison']['differences'].append({
                        'suffix': '.treefile', 'reason': 'Candidate differs from retained production tree'})
        except (RuntimeError, ValueError, OSError, subprocess.TimeoutExpired) as error:
            result['error'] = str(error)
            result.setdefault('candidate', {'prefix': str(prefix), 'wall_seconds': time.perf_counter() - started})
            result['comparison'] = {'identical': False, 'differences': [{'reason': str(error)}]}
        results.append(result)
        destination.write_text(json.dumps(report, indent=2) + '\n')
        identical = result['comparison']['identical']
        print(f"{case_id}: candidate {result['candidate']['wall_seconds']:.3f}s; "
              f"{'IDENTICAL' if identical else 'DIFFERS'} (reference reused)", flush=True)
        if not identical:
            print(json.dumps(result['comparison']['differences'], indent=2), flush=True)
            if not args.keep_going:
                break
    report['complete'] = len(results) == len(cases)
    report['all_identical'] = report['complete'] and all(result['comparison']['identical'] for result in results)
    report['summary'] = {
        'comparisons': len(results), 'expected_comparisons': len(cases),
        'passed': sum(result['comparison']['identical'] for result in results),
        'candidate_total_seconds': sum(result['candidate']['wall_seconds'] for result in results),
        'candidate_total_user_seconds': sum(result['candidate'].get('user_seconds', 0) for result in results),
        'candidate_total_system_seconds': sum(result['candidate'].get('system_seconds', 0) for result in results),
        'reference_reused': True, 'covers_full_manifest': report['covers_full_manifest'],
    }
    destination.write_text(json.dumps(report, indent=2) + '\n')
    print(str(destination), flush=True)
    return 0 if report['all_identical'] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference-report', type=lambda value: Path(value).resolve(), required=True)
    parser.add_argument('--candidate', type=lambda value: Path(value).resolve(), required=True)
    parser.add_argument('--label', required=True)
    parser.add_argument('--work', type=lambda value: Path(value).resolve(), default=replay.DEFAULT_WORK)
    parser.add_argument('--manifest', type=Path, default=HERE / 'manifest.json')
    parser.add_argument('--case', action='append')
    parser.add_argument('--timeout', type=float, default=1800)
    parser.add_argument('--keep-going', action='store_true')
    return run(parser.parse_args())


if __name__ == '__main__':
    sys.exit(main())
