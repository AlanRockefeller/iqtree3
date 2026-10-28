#!/usr/bin/env python3
"""Replay retained Dikarya alignments and compare exact IQ-TREE results.

Use Dikarya's Python interpreter for ``prepare`` (BioPython is required).
``run`` and ``compare`` use only the Python standard library. No production
files are written and no jobs are submitted to Dikarya.
"""

import argparse
import difflib
import gzip
import hashlib
import json
from pathlib import Path
import re
import resource
import statistics
import subprocess
import sys
import time


HERE = Path(__file__).resolve().parent
DEFAULT_WORK = Path('/tmp/iqtree-dikarya-bench')
# These are operational recovery snapshots, written on a wall-clock schedule.
# They are deliberately not claimed to be byte-identical scientific results.
IGNORED_SUFFIXES = {'.ckp.gz'}
TEXT_SUFFIXES = {'.log', '.iqtree', '.model.gz'}
NUMBER = r'[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?'
# Only metadata whose meaning is explicitly elapsed time, date, executable, or
# build identity is omitted. Seeds, likelihoods, support values, model choices,
# kernel selection and iteration counts remain part of the comparison.
DROP_LINE = re.compile(
    r'^(?:IQ-TREE (?:version |multicore version |\d)|Command:|Time:|'
    r'Date and [Tt]ime:| start_real_time:| version:)'
)
TIMING_SUBS = [
    (re.compile(r'-?\d+h:-?\d+m:-?\d+s'), '<elapsed>'),
    (re.compile(NUMBER + r'(\s*)(sec(?:ond)?s?)\b'), r'<elapsed>\1\2'),
    (re.compile(r' using ' + NUMBER + r'% CPU'), ''),
    (re.compile(r'((?:CPU time|wall-clock time|Wall-clock time|time used)'
                r'(?: for [A-Za-z ]+)?:\s*)' + NUMBER), r'\1<elapsed>'),
]


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def read_bytes(path):
    return gzip.decompress(path.read_bytes()) if path.suffix == '.gz' else path.read_bytes()


def normalize(data, prefix, input_path=None):
    text = data.decode('utf-8', errors='strict').replace(str(prefix.resolve()), '<prefix>')
    if input_path is not None:
        text = text.replace(str(Path(input_path).resolve()), '<input>')
    lines = []
    for line in text.splitlines():
        if DROP_LINE.match(line):
            continue
        for pattern, replacement in TIMING_SUBS:
            line = pattern.sub(replacement, line)
        lines.append(line)
    return lines


def outputs(prefix):
    prefix = Path(prefix)
    return {p.name[len(prefix.name):]: p for p in prefix.parent.glob(prefix.name + '.*')
            if p.is_file() and p.name[len(prefix.name):] not in IGNORED_SUFFIXES}


def compare(a, b, input_path=None):
    a, b = Path(a), Path(b)
    aa, bb = outputs(a), outputs(b)
    differences = []
    checks = []
    for suffix in sorted(aa.keys() | bb.keys()):
        if suffix not in aa or suffix not in bb:
            differences.append({'suffix': suffix, 'reason': 'present in only one run'})
            continue
        pa, pb = aa[suffix], bb[suffix]
        left, right = pa.read_bytes(), pb.read_bytes()
        check = {'suffix': suffix, 'reference_sha256': sha256(left),
                 'candidate_sha256': sha256(right), 'bytes': len(left)}
        if suffix in TEXT_SUFFIXES:
            la, lb = normalize(read_bytes(pa), a, input_path), normalize(read_bytes(pb), b, input_path)
            same = la == lb
            check['mode'] = 'normalized operational metadata'
            if not same:
                differences.append({'suffix': suffix, 'reason': 'text differs',
                                    'diff': '\n'.join(list(difflib.unified_diff(la, lb))[:100])})
        else:
            same = left == right
            check['mode'] = 'byte-identical'
            if not same:
                differences.append({'suffix': suffix, 'reason': 'bytes differ'})
        check['identical'] = same
        checks.append(check)
    # A pair of empty directories can never pass; require primary scientific
    # results, the fitted model report and the complete execution trace.
    for suffix in ('.treefile', '.iqtree', '.log'):
        if suffix not in aa or suffix not in bb:
            differences.append({'suffix': suffix, 'reason': 'required result missing'})
    return {'identical': not differences, 'checks': checks, 'differences': differences,
            'excluded_operational_artifacts': sorted(IGNORED_SUFFIXES)}


def manifest(path):
    return json.loads(Path(path).read_text())


def selected_cases(args):
    cases = manifest(args.manifest)['cases']
    if getattr(args, 'group', None):
        cases = [c for c in cases if c['group'] in args.group]
    if getattr(args, 'case', None):
        wanted = set(args.case)
        cases = [c for c in cases if c['id'] in wanted or c['job'] in wanted]
        missing = wanted - {c['id'] for c in cases} - {c['job'] for c in cases}
        if missing:
            raise ValueError('Unknown case(s): ' + ', '.join(sorted(missing)))
    return cases


def prepare(args):
    from Bio import SeqIO
    args.work.mkdir(parents=True, exist_ok=True)
    inputs = args.work / 'inputs'
    inputs.mkdir(exist_ok=True)
    prepared = []
    for case in selected_cases(args):
        source = args.jobs / case['job'] / case['alignment']
        if not source.is_file():
            source = Path(str(source) + '.gz')
        raw = read_bytes(source)
        if sha256(raw) != case['source_sha256']:
            raise ValueError(f"Retained alignment changed: {source}")
        import io
        records = list(SeqIO.parse(io.StringIO(raw.decode()), 'fasta'))
        if case.get('collapse_identical'):
            metadata = json.loads((args.jobs / case['job'] / 'tree/tree_metadata.json').read_text())
            groups = metadata['identical_sequences']['groups']
            removed = {header for group in groups for header in group['removed']}
            records = [record for record in records if record.description not in removed]
        names = {}
        for index, record in enumerate(records, 1):
            safe = f'SEQ{index:06d}'
            names[safe] = record.description
            record.id = record.name = safe
            record.description = ''
        path = inputs / (case['id'] + '.fasta')
        SeqIO.write(records, path, 'fasta')
        if sha256(path.read_bytes()) != case['input_sha256']:
            raise ValueError(f"Sanitized alignment does not match manifest: {path}")
        (inputs / (case['id'] + '.names.json')).write_text(json.dumps(names, indent=2) + '\n')
        prepared.append({'id': case['id'], 'path': str(path), 'taxa': len(records),
                         'bytes': path.stat().st_size, 'sha256': case['input_sha256']})
    (args.work / 'prepared.json').write_text(json.dumps(prepared, indent=2) + '\n')
    print(json.dumps({'prepared': len(prepared), 'work': str(args.work)}, indent=2))


def invoke(binary, case, input_path, prefix, timeout):
    prefix.parent.mkdir(parents=True, exist_ok=False)
    cmd = [str(binary), '-s', str(input_path), '-m', case['model'], '-T', '1',
           '--prefix', str(prefix), '--seed', str(case['seed']), '--redo'] + case['options']
    before = resource.getrusage(resource.RUSAGE_CHILDREN)
    start = time.perf_counter()
    with (prefix.parent / 'stdout.txt').open('wb') as stdout, (prefix.parent / 'stderr.txt').open('wb') as stderr:
        proc = subprocess.run(cmd, stdout=stdout, stderr=stderr, timeout=timeout, check=False)
    elapsed = time.perf_counter() - start
    after = resource.getrusage(resource.RUSAGE_CHILDREN)
    result = {'command': cmd, 'returncode': proc.returncode, 'wall_seconds': elapsed,
              'user_seconds': after.ru_utime - before.ru_utime,
              'system_seconds': after.ru_stime - before.ru_stime,
              'prefix': str(prefix)}
    if proc.returncode:
        raise RuntimeError(f"IQ-TREE exited {proc.returncode}; see {prefix.parent}")
    return result


def run(args):
    root = args.work / 'runs' / args.label
    if root.exists():
        raise ValueError(f'Refusing to mix new results with existing run: {root}')
    cases = selected_cases(args)
    if not cases:
        raise ValueError('No cases selected')
    results = []
    report = {'reference': str(args.reference), 'candidate': str(args.candidate),
              'reference_sha256': sha256(args.reference.read_bytes()),
              'candidate_sha256': sha256(args.candidate.read_bytes()),
              'manifest_sha256': sha256(Path(args.manifest).read_bytes()),
              'runs': results, 'all_identical': True}
    root.mkdir(parents=True)
    for repeat in range(args.repeat):
        for index, case in enumerate(cases):
            input_path = (args.work / 'inputs' / (case['id'] + '.fasta')).resolve()
            if sha256(input_path.read_bytes()) != case['input_sha256']:
                raise ValueError(f'Prepared input changed: {input_path}')
            runs = {}
            # Alternate order across both cases and repetitions; never run
            # binaries concurrently, so neither competes with the other.
            order = ('reference', 'candidate') if (index + repeat) % 2 == 0 else ('candidate', 'reference')
            for side in order:
                binary = getattr(args, side)
                prefix = root / f'{repeat + 1:02d}' / case['id'] / side / 'run'
                runs[side] = invoke(binary, case, input_path, prefix, args.timeout)
            comparison = compare(runs['reference']['prefix'], runs['candidate']['prefix'], input_path)
            if args.check_stored and case.get('stored_tree_comparable'):
                for side in ('reference', 'candidate'):
                    tree = Path(runs[side]['prefix'] + '.treefile')
                    if sha256(tree.read_bytes()) != case['stored_tree_sha256']:
                        comparison['identical'] = False
                        comparison['differences'].append({
                            'suffix': '.treefile', 'reason': side + ' differs from retained production result'})
            entry = {'case': case['id'], 'job': case['job'], 'group': case['group'],
                     'repeat': repeat + 1, 'order': list(order), **runs, 'comparison': comparison,
                     'speedup': runs['reference']['wall_seconds'] / runs['candidate']['wall_seconds']}
            results.append(entry)
            report['all_identical'] &= comparison['identical']
            (root / 'results.json').write_text(json.dumps(report, indent=2) + '\n')
            print(f"{case['id']}: {runs['reference']['wall_seconds']:.3f}s -> "
                  f"{runs['candidate']['wall_seconds']:.3f}s ({entry['speedup']:.3f}x), "
                  f"{'IDENTICAL' if comparison['identical'] else 'DIFFERS'}", flush=True)
            if not comparison['identical']:
                print(json.dumps(comparison['differences'], indent=2), flush=True)
                if not args.keep_going:
                    return 1
    reference_total = sum(x['reference']['wall_seconds'] for x in results)
    candidate_total = sum(x['candidate']['wall_seconds'] for x in results)
    report['summary'] = {'comparisons': len(results), 'reference_total_seconds': reference_total,
                         'candidate_total_seconds': candidate_total,
                         'aggregate_speedup': reference_total / candidate_total,
                         'median_case_speedup': statistics.median(x['speedup'] for x in results)}
    (root / 'results.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report['summary'], indent=2))
    return 0 if report['all_identical'] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    for action in ('prepare', 'run'):
        p = sub.add_parser(action)
        p.add_argument('--manifest', type=Path, default=HERE / 'manifest.json')
        p.add_argument('--work', type=Path, default=DEFAULT_WORK)
        p.add_argument('--case', action='append', help='Case id or job id, repeatable')
        p.add_argument('--group', action='append', choices=('quick', 'advanced'))
    p = sub.choices['prepare']
    p.add_argument('--jobs', type=Path, default=Path('/var/www/dikarya/var/jobs'))
    p = sub.choices['run']
    p.add_argument('--reference', type=lambda s: Path(s).resolve(), required=True)
    p.add_argument('--candidate', type=lambda s: Path(s).resolve(), required=True)
    p.add_argument('--label', default=time.strftime('%Y%m%d-%H%M%S', time.gmtime()))
    p.add_argument('--repeat', type=int, default=1)
    p.add_argument('--timeout', type=float, default=1800)
    p.add_argument('--keep-going', action='store_true')
    p.add_argument('--check-stored', action='store_true',
                   help='Also match retained production tree hashes for cases originally run with these options at -T 1')
    p = sub.add_parser('compare')
    p.add_argument('reference', type=Path)
    p.add_argument('candidate', type=Path)
    p.add_argument('--input', type=Path)
    args = parser.parse_args()
    if args.action == 'prepare':
        prepare(args)
        return 0
    if args.action == 'run':
        return run(args)
    result = compare(args.reference, args.candidate, args.input)
    print(json.dumps(result, indent=2))
    return 0 if result['identical'] else 1


if __name__ == '__main__':
    sys.exit(main())
