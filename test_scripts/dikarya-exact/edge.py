#!/usr/bin/env python3
"""Generate and replay small deterministic cases for generic IQ-TREE paths.

These synthetic regression cases complement, rather than replace, real Dikarya
workloads. Run with --prepare-only to generate inputs without consuming CPU.
"""

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import random
import subprocess
import sys
import time


HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('dikarya_replay', HERE / 'run.py')
replay = importlib.util.module_from_spec(spec)
spec.loader.exec_module(replay)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def fasta(rows):
    return ''.join(f'>SEQ{i:06d}\n{row}\n' for i, row in enumerate(rows, 1)).encode()


def nucleotide_rows(length=120, taxa=8, seed=20261027, variable_only=False):
    rng = random.Random(seed)
    ancestor = [rng.choice('ACGT') for _ in range(length)]
    rows = []
    for taxon in range(taxa):
        row = ancestor.copy()
        for site in range(length):
            # Include both clade-shared and independent substitutions.
            if site % 13 == (taxon // 2) % 13 or rng.random() < 0.14:
                row[site] = rng.choice('ACGT')
        rows.append(row)
    if variable_only:
        for site in range(length):
            rows[1][site] = 'ACGT'[('ACGT'.index(rows[0][site]) + 1) % 4]
    return [''.join(row) for row in rows]


def make_cases(work):
    inputs = work / 'inputs'
    inputs.mkdir(parents=True, exist_ok=True)
    cases = []
    aux = {}
    base = nucleotide_rows()
    # 16 or fewer patterns at 320 sites forces nsite/8 >= nptn: the
    # multinomial resampling path. The ordinary dataset has >15 patterns.
    low_patterns = [row[:16] * 20 for row in base]
    ambiguous = [list(row) for row in base]
    for index, char in enumerate('RYSWKMBDHVNX?-~.'):
        ambiguous[index % 8][(index * 7) % 120] = char
    for row in ambiguous:
        row[119] = '-'
    ambiguous = [''.join(row).lower() for row in ambiguous]
    rng = random.Random(712345)
    aa_alphabet = 'ARNDCQEGHILKMFPSTWYV'
    aa_ancestor = [aa_alphabet[i % 20] for i in range(120)]
    aa = []
    for taxon in range(8):
        row = aa_ancestor.copy()
        for site in range(120):
            if rng.random() < 0.16:
                row[site] = rng.choice(aa_alphabet)
        aa.append(''.join(row))
    # Codons avoid stop states under the standard genetic code. A few codons
    # include ambiguity and complete gaps to test three-column state mapping.
    codons = ['GCT', 'TTC', 'GAA', 'CAG', 'AAG', 'ATC', 'GGT', 'TAC',
              'TGC', 'CTG', 'AAC', 'GAC', 'CCG', 'ACG', 'TGG', 'AGC']
    codon = []
    for taxon in range(6):
        row = [codons[i % len(codons)] for i in range(48)]
        for site in range(48):
            if (site + taxon) % 11 == 0:
                row[site] = codons[(site + taxon + 3) % len(codons)]
        if taxon == 0:
            row[7] = 'GCN'
        if taxon == 1:
            row[23] = '---'
        codon.append(''.join(row))
    binary = [''.join(str((site // (taxon + 1) + taxon + site % 3) % 2)
                      for site in range(96)) for taxon in range(8)]
    # Counts format uses weighted binomial PoMo observations, with both fixed
    # states and biallelic counts. N3 keeps the generic state space small.
    counts = ['COUNTSFILE NPOP 6 NSITES 64',
              'CHROM POS ' + ' '.join(f'SEQ{i:06d}' for i in range(1, 7))]
    for site in range(64):
        fields = []
        for taxon in range(6):
            state = (site + (taxon // 2 if site % 5 == 0 else 0)) % 4
            values = [0, 0, 0, 0]
            values[state] = 5
            if (site + taxon) % 7 == 0:
                values[state] = 3
                values[(state + 1) % 4] = 2
            fields.append(','.join(map(str, values)))
        counts.append('1 ' + str(site + 1) + ' ' + ' '.join(fields))

    def auxiliary(name, data):
        path = inputs / name
        path.write_bytes(data)
        aux[name] = digest(data)
        return str(path.resolve())

    partition = auxiliary('edge-partitions.nex', (
        '#nexus\nbegin sets;\n'
        ' charset first = 1-60;\n charset second = 61-120;\n'
        ' charpartition models = GTR+G4:first, HKY+G4:second;\nend;\n').encode())
    tree = auxiliary('edge-fixed.tree', (
        '(SEQ000001:0.1,SEQ000002:0.1,((SEQ000003:0.1,SEQ000004:0.1):0.1,'
        '((SEQ000005:0.1,SEQ000006:0.1):0.1,(SEQ000007:0.1,SEQ000008:0.1):0.1):0.1):0.1);\n'
    ).encode())
    trees = auxiliary('edge-topologies.trees', (
        '(SEQ000001,SEQ000002,((SEQ000003,SEQ000004),((SEQ000005,SEQ000006),(SEQ000007,SEQ000008))));\n'
        '(SEQ000001,SEQ000003,((SEQ000002,SEQ000004),((SEQ000005,SEQ000006),(SEQ000007,SEQ000008))));\n'
        '(SEQ000001,SEQ000002,((SEQ000003,SEQ000005),((SEQ000004,SEQ000006),(SEQ000007,SEQ000008))));\n'
    ).encode())

    def case(name, data, model, options, covers):
        name = 'edge-' + name
        (inputs / (name + '.fasta')).write_bytes(data)
        cases.append({'id': name, 'job': 'synthetic', 'group': 'edge',
                      'input_sha256': digest(data), 'input_bytes': len(data),
                      'seed': 20261027, 'model': model, 'options': options,
                      'covers': covers, 'stored_tree_comparable': False})

    quick = ['-n', '2', '--alrt', '1000']
    ufboot = ['-B', '1000', '--bnni', '--alrt', '1000']
    case('ordinary', fasta(base), 'GTR+G4', ufboot,
         ['ordinary histogram resampling', 'UFBoot vector buffer', 'SH-aLRT cache'])
    case('multinomial', fasta(low_patterns), 'HKY+G4', ufboot,
         ['multinomial bootstrap', 'repeated-pattern construction', 'SH-aLRT cache'])
    for name, sampling in [('gene', 'GENE,40,40,40'),
                           ('genesite', 'GENESITE,40,40,40'),
                           ('resized', '40,30,40,50,40,40')]:
        # The upstream Alignment*-building implementation rejects GENE and
        # GENESITE during --bnni. Omitting refinement for those two exercises
        # the supported frequency-vector special path without that old error.
        special_options = [option for option in ufboot if option != '--bnni'] if name != 'resized' else ufboot
        case(name, fasta(base), 'HKY+G4', special_options + ['--bsam', sampling],
             ['special bootstrap specification', 'UFBoot vector buffer'])
    case('au-scale', fasta(base), 'HKY+G4',
         ['-n', '2', '--trees', trees, '--test', '1000', '--test-au'],
         ['SCALE= bootstrap frequencies', 'approximately unbiased topology test'])
    cherry = [list(row) for row in nucleotide_rows(length=320, seed=20261028)]
    for index, char in enumerate('ACGTNRY?-'):
        cherry[index % 8][index * 29] = char
    case('cherry-ambiguity', fasta([''.join(row) for row in cherry]), 'GTR+G4', quick,
         ['at least 128 patterns', 'canonical/unknown tip-state cache', 'ambiguous-state fallback'])
    case('jackknife', fasta(base), 'HKY+G4',
         ['-J', '1000', '--bnni', '--alrt', '1000'],
         ['jackknife resampling', 'UFBoot vector buffer'])
    case('standard-bootstrap', fasta(base), 'JC', ['-b', '2', '-n', '2'],
         ['standard-bootstrap alignment construction'])
    case('ambiguity-safe', fasta(ambiguous), 'GTR+I+G4', quick + ['--safe', '-st', 'DNA'],
         ['all DNA IUPAC states', 'gaps-only column', 'lower-case parsing', 'safe likelihood'])
    case('ascertainment-safe', fasta(nucleotide_rows(variable_only=True)),
         'GTR+ASC+G4', quick + ['--safe'],
         ['ASC_Lewis constant-pattern probability', 'single packet all_prob', 'safe likelihood'])
    case('amino-acid', fasta(aa), 'LG+G4', quick + ['--safe'],
         ['amino-acid type detection', '20-state pattern construction', 'generic safe kernel'])
    case('codon', fasta(codon), 'GY+F3X4', ['-n', '2', '-st', 'CODON', '--safe'],
         ['three-column codon state mapping', 'ambiguous codon', '61-state kernel'])
    case('translated', fasta(codon), 'LG+G4', ['-n', '2', '-st', 'NT2AA'],
         ['translated-codon pattern construction'])
    case('binary', fasta(binary), 'GTR2+G4', quick,
         ['binary type detection', 'two-state pattern construction', 'fixed-state generic dispatch'])
    case('partitioned', fasta(base), 'GTR+G4', quick + ['--partition', partition],
         ['partitioned DNA', 'partition-specific pattern construction'])
    case('heterotachy', fasta(base), 'GTR+H2', ['-n', '2'],
         ['mixture branch lengths', 'computeLikelihoodDervMixlenGenericSIMD'])
    case('pomo', ('\n'.join(counts) + '\n').encode(), 'HKY+P+N3+WB', ['-n', '2', '--safe'],
         ['counts-file parser', 'PoMo weighted observations', '16-state safe likelihood'])
    case('two-thread-fixed-tree', fasta(base), 'GTR+G4',
         ['-te', tree, '-T', '2', '--safe'],
         ['PatternBounds multiple-packet fallback', 'fixed topology avoids stochastic parallel search'])
    result = {'description': 'Deterministic small regression cases for generic alignment/kernel paths; '
              'synthetic cases are not Dikarya timing evidence.',
              'auxiliary_file_sha256': aux, 'cases': cases}
    path = work / 'edge-manifest.json'
    path.write_text(json.dumps(result, indent=2) + '\n')
    return path, cases


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, default=Path('/tmp/iqtree-dikarya-bench'))
    parser.add_argument('--manifest', type=Path,
                        help='Use an existing prepared manifest, e.g. variants.json, instead of generating synthetic cases')
    parser.add_argument('--prepare-only', action='store_true')
    parser.add_argument('--reference-only', action='store_true',
                        help='Collect reference artifacts once; later reuse with --reuse-reference')
    parser.add_argument('--reuse-reference', type=Path,
                        help='Compare a candidate with results.json from --reference-only')
    parser.add_argument('--reference', type=lambda s: Path(s).resolve())
    parser.add_argument('--candidate', type=lambda s: Path(s).resolve())
    parser.add_argument('--case', action='append')
    parser.add_argument('--repeat', type=int, default=1)
    parser.add_argument('--timeout', type=float, default=120)
    parser.add_argument('--label', default='edges-' + time.strftime('%Y%m%d-%H%M%S', time.gmtime()))
    parser.add_argument('--keep-going', action='store_true')
    args = parser.parse_args()
    if args.manifest:
        cases = replay.manifest(args.manifest)['cases']
    else:
        args.manifest, cases = make_cases(args.work)
    if args.prepare_only:
        print(json.dumps({'manifest': str(args.manifest), 'cases': [c['id'] for c in cases]}, indent=2))
        return 0
    if args.reference_only or args.reuse_reference:
        if args.reference_only and args.reuse_reference:
            parser.error('--reference-only and --reuse-reference are mutually exclusive')
        if args.reference_only and not args.reference:
            parser.error('--reference-only requires --reference')
        if args.reuse_reference and not args.candidate:
            parser.error('--reuse-reference requires --candidate')
        return collected_run(args, cases)
    if not args.reference or not args.candidate:
        parser.error('--reference and --candidate are required unless --prepare-only is used')
    args.group = None
    args.check_stored = False
    return replay.run(args)


def collected_run(args, cases):
    """Keep correctness runs separate from interleaved timing benchmarks."""
    if args.case:
        missing = set(args.case) - {case['id'] for case in cases}
        if missing:
            raise ValueError('Unknown case(s): ' + ', '.join(sorted(missing)))
        cases = [case for case in cases if case['id'] in args.case]
    if not cases:
        raise ValueError('No cases selected')
    root = args.work / 'runs' / args.label
    root.mkdir(parents=True, exist_ok=False)
    source = json.loads(args.reuse_reference.read_text()) if args.reuse_reference else None
    binary = args.candidate if source else args.reference
    report = {'binary': str(binary), 'binary_sha256': digest(binary.read_bytes()),
              'purpose': 'correctness only; timings may overlap compilation', 'runs': []}
    references = {entry['case']['id']: entry for entry in source['runs']} if source else {}
    failed = False
    for case in cases:
        input_path = (args.work / 'inputs' / (case['id'] + '.fasta')).resolve()
        if digest(input_path.read_bytes()) != case['input_sha256']:
            raise ValueError('Prepared edge input changed: ' + str(input_path))
        result = {'case': case}
        try:
            if source and references[case['id']]['case'] != case:
                raise ValueError('Case or options changed since reference was collected')
            result['execution'] = replay.invoke(binary, case, input_path,
                                                 root / case['id'] / 'run', args.timeout)
            if source:
                previous = references[case['id']]
                result['comparison'] = replay.compare(previous['execution']['prefix'],
                                                       result['execution']['prefix'], input_path)
                if not result['comparison']['identical']:
                    failed = True
            print(case['id'] + ': ' + ('COLLECTED' if not source else
                  ('IDENTICAL' if result['comparison']['identical'] else 'DIFFERS')), flush=True)
            if source and not result['comparison']['identical']:
                print(json.dumps(result['comparison']['differences'], indent=2), flush=True)
        except (RuntimeError, subprocess.TimeoutExpired) as error:
            result['error'] = str(error)
            failed = True
            print(case['id'] + ': ' + str(error), flush=True)
        report['runs'].append(result)
        report['all_passed'] = not failed
        (root / 'results.json').write_text(json.dumps(report, indent=2) + '\n')
        if failed and not args.keep_going:
            return 1
    print(str(root / 'results.json'), flush=True)
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
