# Dikarya IQ-TREE benchmarks and validation

## Measured comparison

The final `3.1.4-dikarya2` build took **93.308 seconds**, compared with
**100.238 seconds** for the already optimized `3.1.4-dikarya1` build, across
five selected real workloads: **6.9% less wall time**, or **1.074× speedup**.
Combined user/system CPU time fell from **99.123 s to 92.565 s**.

These are **five distinct inputs with one fresh paired replay each**, measured
on 2026-10-28 on mycolab: Intel Xeon E5-2690 v4, Ubuntu 24.04, two vCPUs,
AVX2/FMA. Each IQ-TREE invocation used `-T 1`; the benchmark process inherited
CPU affinity restricted to CPU 1. Reference and candidate ran sequentially,
alternating their order between inputs, with identical sanitized alignments,
complete options and recorded seeds. Builds and other benchmark suites were
idle during these timings. This is a shared-server sample, not a confidence
interval or a guarantee for every workload.

| Retained job | Taxa | Command shape | `dikarya1` | `dikarya2` | Speedup |
|---|---:|---|---:|---:|---:|
| `5lhf` | 39 | Quick Tree | 0.668 s | 0.618 s | 1.082× |
| `i56c` | 103 | Quick Tree | 2.733 s | 2.372 s | 1.152× |
| `7vi0` | 144 | Quick Tree | 13.259 s | 12.153 s | 1.091× |
| `0qc0` | 969 | Quick Tree | 74.586 s | 69.422 s | 1.074× |
| `uowk` | 28 | Advanced MFP/UFBoot | 8.992 s | 8.743 s | 1.028× |
| **Total** | | | **100.238 s** | **93.308 s** | **1.074×** |

Quick Tree uses `-m GTR+G -n 5 --alrt 1000`. Advanced uses
`-m MFP -B 1000 --bnni --alrt 1000`. Both add `-T 1 --seed N --redo`.
The median of the five per-job speedup ratios is **1.082×**; it is a different
statistic from the ratio of total times above.

## Baselines and attribution

`dikarya1` already contained the earlier exact-speedup series. Its separate
[public report](https://github.com/AlanRockefeller/iqtree3/blob/exact-speedups/EXACT-SPEEDUPS.md)
compares it with official IQ-TREE 3.1.4 on different datasets. The **6.9% here is
additional improvement over that optimized baseline**. It is not a new timing
of final `dikarya2` against the official release. Multiplying ratios from those
different experiments would not be a directly measured combined speedup.

The timing table measures the complete final build. It does not establish a
separate percentage contribution for each optimization. Other intermediate
experiments helped select the implementation but are not substituted for these
five final pairs. Candidate runs using cached reference outputs provide
correctness evidence only, not fresh paired timing evidence.

## Exactness evidence

| Check group | Cases | What it exercises |
|---|---:|---|
| Retained real workloads | 23 | 18 Quick Tree inputs (8–1042 taxa), five advanced inputs (6–58 taxa); **6–1042 taxa overall** |
| Additional real-input variants | 3 | K2P with UFBoot/refinement/SH-aLRT; HKY+G with UFBoot/refinement and no SH-aLRT; GTR+F+R6 limited search with SH-aLRT |
| Synthetic edge cases | 19 | Bootstrap/resampling modes, ambiguity, safe likelihood, ascertainment correction, proteins, codons, binary data, partitions, heterotachy, PoMo and a deterministic parallel fallback |
| MCMCtree exports | 4 | Single, proportional, equal and unlinked partition modes; complete numerical Hessians and tree files |
| **Total workload/edge checks** | **49** | **All passed for the final executable** |

The 23 real replays use the same sanitized inputs, options and recorded seeds
as their reference invocations at `-T 1`. Eligible results also match the SHA-256
of the retained production tree. Several older advanced jobs originally used
other thread/support options; their historical trees are not expected results
for the changed replay command.

The comparator requires trees, supports, distances and other scientific files
to match as bytes, including unknown result extensions. `.iqtree`, `.log` and
decompressed `.model.gz` undergo only the documented timing/build/path
normalization. Seeds, kernel choice, likelihoods, fitted models and search
iteration counts remain checked. `.ckp.gz` is excluded because its recovery
snapshots follow a wall-clock schedule. MCMCtree control files normalize paths;
Hessian numbers are never normalized.

Additional checks, **not included in the 49-case total**:

- The independent scalar-Fitch oracle passes **3,800 fixtures and 986,179
  pruning decisions**, including unaligned rows and four-word tails. SSE,
  legacy AVX and hybrid outputs have identical structure layouts and digest
  `0e761a6a5fab47be`.
- **17 comparator/installer tests** pass. These test the checking and deployment
  tools, rather than adding scientific workload samples.
- The installed-path smoke replay matches the prior binary and retained
  production tree. Activation checks observed real jobs completing with the
  installed `dikarya2` path.

This does not establish reproducibility for arbitrary multithreaded searches
or arbitrary compiler/library combinations. See the
[exactness contract and build guide](DIKARYA-OPTIMIZATIONS.md).

## Reproduce the timing procedure

The real inputs are private retained submissions. Their manifests expose
hashes, options and seeds, not the sequences themselves. Exact replay requires
access to those job files; public synthetic checks are documented separately
in the [validation guide](test_scripts/dikarya-exact/README.md).

After preparing the retained inputs as that guide describes, the measured
case selection and affinity can be repeated on mycolab with a new run label:

```sh
taskset -c 1 nice -n 10 python3 test_scripts/dikarya-exact/run.py run \
  --reference /opt/iqtree-3.1.4-dikarya1/bin/iqtree3 \
  --candidate /opt/iqtree-3.1.4-dikarya2/bin/iqtree3 \
  --case 5lhf --case i56c --case 7vi0 --case 0qc0 --case uowk \
  --repeat 1 --check-stored --label reproduce-final-1
```

`run.py` alternates executable order but does not set CPU affinity itself;
`taskset` above supplies it. Use matching affinity/environment for both builds.
For the synthetic two-thread case, allow at least two CPUs. Choose a fresh
label for each invocation; use `--repeat 3` or more for additional measurements
before drawing conclusions about small differences. No new timings are implied
by this example.

## Build and release provenance

Use the [pinned build recipe](DIKARYA-OPTIMIZATIONS.md#build-with-the-validated-toolchain-recipe)
and read its package-cache and host-library requirements. The validated build
has `USE_MUTSEL=OFF`, static linking and no global native-architecture or
fast-math changes. AVX2 is enabled only for the hybrid integer parsimony C file.

Verified executable SHA-256:

```text
07111b617f367a33ffa72c413c51842e165e64776f2fb709109c41c979bceced
```

This fingerprints the packaged binary, not every rebuild: embedded build dates
and host runtime libraries can change executable bytes. Output comparison,
rather than a rebuild hash alone, establishes the claimed numerical behavior.

The workspace release bundle is `../artifacts/iqtree-3.1.4-dikarya2/`;
installed provenance is `/opt/iqtree-3.1.4-dikarya2/share/`. Its
`verification.json` contains complete comparison/timing reports and hashes.
The exported `source.patch` was reverse-checked at packaging time; subsequent
source documentation edits are maintained separately and are not part of that
immutable patch. The separate activation record confirms deployment on
2026-10-28. The old `/opt/iqtree-3.1.4-dikarya1` release remains available for
rollback.
