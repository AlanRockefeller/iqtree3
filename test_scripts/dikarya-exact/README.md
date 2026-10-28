# Build validation and exact-output replay

Start with the [build and optimization guide](../../DIKARYA-OPTIMIZATIONS.md)
for prerequisites, the pinned compiler packages, build options and release
lineage. The [benchmark report](../../DIKARYA-BENCHMARKS.md) explains the measured
results. Commands below run from the IQ-TREE source directory.

The public synthetic checks work without the Dikarya application, its database,
or its retained jobs. They generate their own inputs and use Python's standard
library. Set two executable paths before comparing builds:

```sh
IQTREE_REFERENCE=/absolute/path/to/reference/iqtree3
IQTREE_CANDIDATE=/absolute/path/to/candidate/iqtree3
IQTREE_TEST_WORK=/tmp/iqtree-exact-validation
```

The measured reference for this release was the already optimized
`3.1.4-dikarya1`; the candidate was `3.1.4-dikarya2`. Prefer a reference built with
the same documented compiler, dependency versions and numerical flags. Results
apply to the selected binaries, inputs, seeds and options. They do not establish
byte identity for arbitrary compilers, architecture flags or upstream builds.

## Public synthetic checks

The 19-case suite covers ordinary, multinomial, gene, gene-site, resized,
jackknife, standard and AU multi-scale bootstrap paths; ambiguous and lower-case
DNA; safe likelihood; ascertainment correction; amino acids; codons and
translated codons; binary data; partitioned models; heterotachy; and PoMo. A
198-pattern DNA input exercises the tip-state cache threshold and ambiguity
fallback.

Run both binaries under the same CPU affinity mask and environment. The suite
includes a fixed-tree `-T 2` case, so leave at least two CPUs available. Its other
cases use `-T 1`. The fixed topology checks the parallel packet fallback without
stochastic parallel tree search.

```sh
python3 test_scripts/dikarya-exact/edge.py \
  --reference "$IQTREE_REFERENCE" --candidate "$IQTREE_CANDIDATE" \
  --work "$IQTREE_TEST_WORK" --label synthetic-pair --keep-going
```

A new label is required for each run. Generated inputs live under
`$IQTREE_TEST_WORK/inputs/`, and the comparison report is
`$IQTREE_TEST_WORK/runs/synthetic-pair/results.json`. To generate inputs without
launching either executable:

```sh
python3 test_scripts/dikarya-exact/edge.py \
  --work "$IQTREE_TEST_WORK" --prepare-only
```

The two gene-resampling cases omit `--bnni`, because the reference implementation
rejects `GENE`/`GENESITE` during that refinement step. Ordinary, multinomial and
resized UFBoot cases retain refinement coverage.

For separate reference and candidate stages, keep the same work directory:

```sh
python3 test_scripts/dikarya-exact/edge.py \
  --reference "$IQTREE_REFERENCE" --reference-only \
  --work "$IQTREE_TEST_WORK" --label synthetic-reference --keep-going

python3 test_scripts/dikarya-exact/edge.py \
  --candidate "$IQTREE_CANDIDATE" \
  --reuse-reference "$IQTREE_TEST_WORK/runs/synthetic-reference/results.json" \
  --work "$IQTREE_TEST_WORK" --label synthetic-candidate --keep-going
```

These synthetic cases provide correctness evidence. Use representative real
inputs and fresh interleaved measurements for performance claims.

## MCMCTree exports, harness tests and parsimony oracle

Four additional generated cases check `--dating mcmctree` on a single alignment
and proportional (`-p`), equal (`-q`) and unlinked (`-Q`) partition models. The
complete derivative/Hessian and tree files must match as bytes; embedded paths
are normalized only in the generated control file.

```sh
python3 test_scripts/dikarya-exact/check_mcmctree.py \
  --reference "$IQTREE_REFERENCE" --candidate "$IQTREE_CANDIDATE" \
  --workdir "$IQTREE_TEST_WORK/mcmctree"
```

Run the 17 comparator and installer tests without either IQ-TREE binary. The
installer tests use temporary directories and require no administrator access:

```sh
python3 -m unittest discover -s test_scripts/dikarya-exact -p 'test_*.py'
```

On an x86-64 host with AVX2 and POPCNT, the scalar-Fitch oracle compares SSE,
legacy AVX and hybrid integer parsimony. It checks every internal bit and full
Fitch score over 3,800 fixtures, including 986,179 pruning decisions. Use the
configured Makefile build from the pinned-toolchain build instructions:

```sh
python3 test_scripts/dikarya-exact/check_parsimony.py --build-dir ../build
```

Replace `../build` if you selected another build directory. The checker reads the
configured compiler and production C flags, adds each variant's file flags, and
keeps compiler libraries out of fixture execution. It requires identical
structure layouts and digest `0e761a6a5fab47be`. Fixture binaries use a temporary
directory and are removed after the check.

The reported validation total is **49 workload checks**: 19 synthetic cases,
four MCMCTree cases, 23 retained real cases and three real-input variants. The
17 harness tests and 3,800 oracle fixtures are additional checks with separate
counts.

## Retained Dikarya workloads: private input access required

`manifest.json` describes 23 real jobs captured on 2026-10-27: 18 Quick Tree
inputs with 8–1042 taxa and five advanced ModelFinder inputs with 6–58 taxa.
It pins the original alignment and exact sanitized input by SHA-256, and records
seeds, models and options. The repository contains these manifests and test
code; it does not contain the private retained FASTA files, original headers,
name mappings, application database or production job directories. A public
checkout alone cannot replay these particular jobs.

Quick Tree uses `-m GTR+G -n 5 --alrt 1000`; advanced replay uses
`-m MFP -B 1000 --bnni --alrt 1000`. All real-case replays use `-T 1`. Several
historical jobs originally used two threads or omitted `--bnni`; their original
trees are eligible as expected outputs only when the recorded command matches
the replay conditions.

An authorized holder of the retained job files can prepare them with BioPython:

```sh
python3 test_scripts/dikarya-exact/run.py prepare \
  --jobs /path/to/retained/jobs --work "$IQTREE_TEST_WORK"

python3 test_scripts/dikarya-exact/run.py run \
  --reference "$IQTREE_REFERENCE" --candidate "$IQTREE_CANDIDATE" \
  --work "$IQTREE_TEST_WORK" --repeat 3 --check-stored --label real-paired
```

On the Dikarya host, the preparation interpreter is
`/var/www/dikarya/.venv/bin/python` and the retained-job directory is
`/var/www/dikarya/var/jobs`. Public users can install BioPython in their own
Python environment if they have access to equivalent retained files. The
comparison and execution stages use only the Python standard library.

Preparation reads plain or compressed alignments and uses the application's
BioPython FASTA parsing/writing convention. Advanced jobs with a recorded
identical-sequence collapse remove those duplicate headers before numbering
remaining records `SEQ000001`, etc. Hash checks reject changed retained data or
changed sanitized inputs. Generated input files and name mappings stay in the
chosen work directory.

Use repeatable `--case i56c` selections or `--group quick`/`--group advanced` for
subsets. `i56c` has 103 taxa, 836 sites and 344 patterns; `7vi0` has 144 taxa,
1710 sites and 1213 patterns. `0qc0` and `buh4` exercise large trees, and `dhmq`
exercises duplicate-collapse reconstruction.

`variants.json` adds three command shapes on the real 39-taxon `5lhf` input:
K2P with UFBoot/refinement/SH-aLRT, HKY+G with UFBoot/refinement and no SH-aLRT,
and GTR+F+R6 with three search iterations and SH-aLRT. It also requires the
private retained input:

```sh
python3 test_scripts/dikarya-exact/run.py prepare \
  --manifest test_scripts/dikarya-exact/variants.json \
  --jobs /path/to/retained/jobs --work "$IQTREE_TEST_WORK"

python3 test_scripts/dikarya-exact/run.py run \
  --manifest test_scripts/dikarya-exact/variants.json \
  --reference "$IQTREE_REFERENCE" --candidate "$IQTREE_CANDIDATE" \
  --work "$IQTREE_TEST_WORK" --label variants-paired
```

The same `--manifest` also works with `edge.py`'s separate reference/candidate
stages. The original Quick Tree result is not an expected result for these
changed model/support options.

## Comparison rules and performance measurements

Every generated `run.*` artifact is compared, including unknown extensions.
Trees, bootstrap samples, consensus trees, splits, distances and unique-sequence
files must match byte for byte. The full `.iqtree` report, `.log` and decompressed
`.model.gz` are compared after an explicit allowlist removes build/version
headers, command echoes, timestamps, elapsed times and CPU percentages; paths
are normalized. Scientific numbers, model selection, kernel choice, RNG seed,
search iteration counts and log messages remain checked. The excluded artifact
is `.ckp.gz`, an operational recovery snapshot written on a wall-clock schedule.
A missing `.treefile`, `.iqtree` or `.log` is always an error.

The real-workload runner executes reference and candidate sequentially,
alternating their order by case and repetition. It records commands, binary and
input hashes, wall/user/system time, file hashes and comparison details. Reports
are updated after each pair. An output mismatch stops execution unless
`--keep-going` is selected. `--check-stored` also checks eligible results against
the original production `.treefile` hash.

Measure while other builds and benchmark runs are idle, under matching CPU
affinity and execution settings. Single-thread real replays can share a chosen
single-core affinity mask; the complete synthetic suite needs its two CPUs.
Repeated, interleaved measurements are needed before claiming small gains.

To compare an existing pair without running IQ-TREE:

```sh
python3 test_scripts/dikarya-exact/run.py compare \
  "$IQTREE_TEST_WORK/runs/real-paired/01/i56c/reference/run" \
  "$IQTREE_TEST_WORK/runs/real-paired/01/i56c/candidate/run" \
  --input "$IQTREE_TEST_WORK/inputs/i56c.fasta"
```

## Reusing a completed real reference

`reuse.py` checks a new candidate against original reference artifacts from a
completed full real-workload report, without rerunning the reference binary:

```sh
python3 test_scripts/dikarya-exact/reuse.py \
  --reference-report "$IQTREE_TEST_WORK/runs/real-paired/results.json" \
  --candidate "$IQTREE_CANDIDATE" --work "$IQTREE_TEST_WORK" \
  --label candidate-correctness
```

It requires the complete matching manifest, original reference executable,
prepared inputs and reference output artifacts to remain available. It rejects
incomplete reports, changed commands/inputs, missing cases and changed artifact
inventories or hashes before starting a candidate. Eligible results are also
checked against original production tree hashes. `--case` selects case IDs, and
the JSON explicitly records whether all manifest cases were covered.

This report records `reference_reused: true` and candidate execution times. It
makes no performance comparison with historical reference timings. Use fresh
interleaved runs for performance measurements. The same distinction applies to
the synthetic suite's separate reference/candidate stages.

Validation commands do not install a release or change application settings.
Deployment, rollback, packaged snapshot provenance and platform-specific build
requirements are described in the [main guide](../../DIKARYA-OPTIMIZATIONS.md).
