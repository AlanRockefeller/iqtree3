# Exact speedups for IQ-TREE 3.1.4

This document describes eleven changes to IQ-TREE 3.1.4 that make it faster without
changing what it computes. For the same alignment, options and seed, run with `-T 1`, the
patched binary writes the same files as the official 3.1.4 release binary, byte for byte:
tree, UFBoot consensus and split supports, SH-aLRT values, fitted model parameters,
distances, the `.iqtree` report and the log (apart from wall/CPU times, dates and the
version banner).

The work was done for [Dikarya](https://dikarya.us), a web service that builds trees from
fungal ITS barcode alignments, and has been running there in production since 2026-10-08
as `3.1.4-dikarya1`. It was designed, implemented, verified and benchmarked by Claude Code
(Claude Opus 5.5, Anthropic), with Alan Rockefeller directing the work.

- [The workload and the machine](#the-workload-and-the-machine)
- [How exactness was established](#how-exactness-was-established)
- [The changes](#the-changes)
- [Results](#results)
- [Tried and not adopted](#tried-and-not-adopted)
- [Things we noticed in stock IQ-TREE and did not change](#things-we-noticed-in-stock-iq-tree-and-did-not-change)
- [Reproducing](#reproducing)

## The workload and the machine

Dikarya runs two IQ-TREE command shapes, always on DNA:

| name | command | share of runs (30 days) |
|---|---|---|
| Quick Tree | `-m GTR+G -n 5 --alrt 1000` | ~96% (1,216 runs) |
| advanced | `-m MFP -B 1000 --bnni --alrt 1000`, sometimes `-m K2P` or `-B 5000` | ~4% (50 runs), but most of the CPU time |

Typical alignments have 100-200 sequences and 100-700 distinct patterns; a few have
300-1,000 sequences. The server is an Intel Xeon E5-2690 v4 (Broadwell-EP) virtual
machine with 2 vCPUs: AVX2 and FMA, no AVX-512, so IQ-TREE uses its `AVX+FMA` kernel. Two
of its three workers run IQ-TREE with `-T 1`, one with `-T 2`.

Profiles of the official 3.1.4 binary (`perf`, symbols from a rebuilt unstripped binary)
showed where the time went before any change:

- **Quick Tree** (130 sequences, 422 patterns): likelihood kernels ~52%, generating the
  1000 SH-aLRT bootstrap resamples ~20%, PLL parsimony (starting trees) ~12%.
- **Advanced** (125 sequences, 154 patterns, `-m MFP -B 1000 --bnni --alrt 1000`):
  formatting candidate trees as strings inside `IQTree::saveCurrentTree()` ~27% (mostly
  `printf` of doubles via iostreams, plus `malloc`), likelihood kernels ~30%, serializing
  the UFBoot state into the checkpoint ~8-10%.

Much of that was work whose result was thrown away, which is why it could be removed
without touching the arithmetic.

## How exactness was established

**1. Reproduce the release before changing it.** The official `iqtree-3.1.4-Linux-intel`
binary is what the GitHub Actions `build-linux-x86-64` job produces: clang 22 (apt.llvm.org,
jammy), `-DIQTREE_FLAGS=static`, glibc 2.35 linked statically, IQ-TREE's bundled `libomp.a`
and `libz.a`, Ubuntu 22.04's Eigen 3.4.0 and Boost 1.74 headers. (The `GNU CC 11.4.0`
string in the binary is glibc's own banner, not the compiler.) A rebuild of v3.1.4 with
clang 22.1.8 and those headers and flags (`-DUSE_MUTSEL=OFF`, since the Rust models are not
used) produced the same outputs as the official binary on every input we tried, so the
patched build could be compared against the official binary itself. Matching the compiler
matters: clang's default `-ffp-contract=on` fuses `a*b+c` only within an expression, and only
in the FMA kernel translation unit, which is compiled with `-mfma`; gcc's default
(`-ffp-contract=fast`) fuses differently, so a gcc build is not expected to reproduce the
release, and we did not use one.

**2. Real inputs, exactly as the service runs them.** Inputs were rebuilt from the
service's stored alignments with the same header sanitizing it applies before calling
IQ-TREE. As a check on that, re-running a stored job's command with its recorded `--seed` on
the official binary reproduced that job's `.treefile` byte for byte (10 of 10 jobs tried,
Quick Tree and advanced). The alignments are user submissions and are not published; the
synthetic generator below is for anyone who wants to repeat the comparison.

**3. Compare every output file.** `test_scripts/exact-speedups/compare-runs.py` requires
`.treefile`, `.contree`, `.splits.nex`, `.mldist`, `.bionj`, `.ufboot` and
`.uniqueseq.phy` to be byte-identical, and the `.iqtree` report, `.log` and `.model.gz` to
be identical after dropping only timing values, dates, the command line and the version
banner. The log check catches any change in the search trajectory (every iteration's
log-likelihood is in it), not just in the final tree.

**4. What was compared**, official 3.1.4 against the patched build, `-T 1`:

- 67 real alignments: 48 Quick Tree runs (8-969 sequences) and 19 advanced runs (MFP or K2P,
  UFBoot 1000 or 5000 with `--bnni`, SH-aLRT): all identical.
- 36 runs covering every option shape the service can produce, on four alignments: Quick
  Tree; MFP, K2P, HKY+G and GTR+F+R4; `-B 1000` and `-B 5000`, with and without `--bnni`;
  with and without `--alrt`; `--fast`: all identical.
- The synthetic families in [Results](#results): all identical.

**5. Multi-threaded runs.** `-T 2` runs are not reproducible run to run even with the
official binary (two runs with a fixed topology, `-te`, gave different tree files), so they
cannot be compared by output. The one change with thread-dependent logic (the SH-aLRT
cache) has a debug build, `-DIQTREE_ALRT_CACHE_CHECK`, that draws every replayed replicate
again the original way and aborts if it differs. It compared 413,000 replicates on five
alignments (three Quick Tree runs at both `-T 1` and `-T 2`, two advanced runs at `-T 2`),
covering both of `createBootstrapAlignment()`'s resampling paths (per-site and multinomial)
and SH-aLRT after UFBoot: no differences.

**6. Arguments, not only tests.** Each commit message states why the change cannot alter a
result. In short: the changes skip work whose result is discarded or recomputed identically,
move data without arithmetic, or interleave independent computations; no floating-point
operation is reordered, fused or split.

## The changes

The branch [`upstream-pr`](https://github.com/AlanRockefeller/iqtree3/tree/upstream-pr) is exactly these eleven commits on top of
v3.1.4 (`63c330d`, which is also `master` as of 2026-10-08): the branch to merge or open a
pull request from. [`speedups`](https://github.com/AlanRockefeller/iqtree3/tree/speedups) is the same plus this documentation and the
test harness. Gains quoted per change are from interleaved runs on the machine above, which
is shared and noisy at the 2-4% level.

### 1. SH-aLRT: draw the bootstrap resamples once per traversal

`tree/phylotree.cpp`, `tree/phylotree.h`

`PhyloTree::testOneBranch()` opens an OpenMP region in which every thread re-seeds its
stream with `params->ran_seed + omp_get_thread_num()`, and the 1000-replicate loop is
statically scheduled. So every internal branch draws exactly the same 1000
pattern-frequency vectors, each costing `nsite` calls to the random number generator
through `createBootstrapAlignment()`. For a 130-taxon tree that is about 127 identical
redraws, ~20% of a Quick Tree run.

The vectors are now drawn while testing the first branch of a `testAllBranches()`
traversal and replayed for the others. The cache is keyed on the replicate count, the
pattern count, the alignment and the OpenMP team size (a different team size assigns
different replicates to different streams, so it is redrawn), cleared at the start of
each traversal, freed at its end, and skipped above 128 MB. The RELL sums were factored
into one helper used by both paths, so each replicate's frequencies go into the same sums in
the same order. The serial (non-OpenMP) build keeps advancing one global stream between
branches and is unchanged. SPRNG streams depend only on (stream number, seed, parameter),
so skipping `init_sprng` for a replayed branch changes nothing but a stream counter.

Effect: the SH-aLRT phase of a Quick Tree run fell from ~20% of the run to ~2%.

### 2. UFBoot: format a candidate tree only if a replicate keeps it

`tree/iqtree.cpp` (`IQTree::saveCurrentTree`)

`saveCurrentTree()` runs for every tree the search scores, including both alternatives of
every NNI it evaluates, and it printed the tree to a string before looking at the 1000
replicates. With `--bnni` (`print_ufboot_trees = 2`) that print sorts every subtree through a
fresh `ostringstream` and formats every branch length through iostreams; it was ~27% of an
advanced run, and most candidate trees are kept by no replicate. The replicate loop now
runs first, marking the replicates that keep the tree, and the tree is printed once
afterwards only if any did. The loop reads nothing that printing changes and makes the same
random draws in the same order.

### 3. PLL parsimony: compile `fastDNAparsimony.c` with `-mpopcnt`

`pll/CMakeLists.txt`

The parsimony kernels behind the starting trees are integer code that sums
`__builtin_popcount` over every vector; in the generic (`-msse3`) build that is a
bit-twiddling sequence per word, with POPCNT a single instruction. Integer results cannot
change. Note for a portable release: this assumes POPCNT (x86-64-v2, every x86-64 CPU since
about 2008); a release that must run on older CPUs would need runtime dispatch instead.

### 4. UFBoot: serialize the checkpoint only when it is about to be written

`utils/checkpoint.cpp`, `utils/checkpoint.h`, `tree/iqtree.cpp`

`refineBootTrees()` called `saveCheckpoint()` after each of the 1000 refined trees, and
`doTreeSearch()` after each iteration. With UFBoot that serializes all 1000 boot trees,
their log-likelihoods (iostream double formatting) and the split graphs, so the cost grows
with replicates x trees (~10% of an advanced run; most of a run on a 6-taxon alignment).
`Checkpoint::dump()` writes the file at most once per dump interval (60 s), so almost all of
it was discarded. `Checkpoint::isDumpDue()` was added, and both loops now save (and dump)
only when the dump will write.

Why this is safe: nothing reads these keys of the in-memory checkpoint during the run. The
boot trees restore only the model, which neither `IQTree::saveCheckpoint()` nor a refining
boot tree (`on_refine_btree`) writes, and the MPI readers use their own `Checkpoint`
objects. Whenever the file is written it is written right after a full save, as before;
`refined_samples` is still recorded every iteration; and `refineBootTrees()` and
`runTreeReconstruction()` save the full state after the loops, so the final checkpoint is
the same.

### 5. UFBoot: build sorted topology strings without a stream per subtree

`tree/mtree.cpp`, `tree/mtree.h`; opt-outs in `tree/iqtreemix.h`,
`tree/phylosupertreeunlinked.h`, `tree/phylotreemixlen.h`; used in `tree/iqtree.cpp`

`MTree::printTree()` with `WT_SORT_TAXA` prints every subtree into its own
`ostringstream`, collects them in a heap-allocated `set` and, with `--bnni`, formats each
branch length through iostreams (glibc `printf` with multiprecision digit generation).
`MTree::printSortedTreeString()` appends the same text to a `std::string`: subtrees are
built as strings and ordered by smallest taxon ID (keeping the first of equal IDs, as the
`set` does), taxon IDs use `std::to_string`, and branch lengths use `std::to_chars` with the
precision and notation the stream would have used. `std::to_chars` with a precision is
specified to produce what `printf("%.*f")` / `printf("%.*g")` produces, which is what the
stream does; it was checked against `ostream <<` on 10.6 million values (random bit
patterns, branch-length magnitudes, decimal rounding ties, signed zero, precisions 1-17,
both notations) with no difference. Non-finite values fall back to a stream.

It handles only `WT_SORT_TAXA` with `WT_TAXON_ID`, `WT_BR_LEN`, `WT_BR_LEN_SHORT` and
`WT_NEWLINE`, and returns `false` otherwise; `IQTreeMix`, `PhyloSuperTreeUnlinked` and
`PhyloTreeMixlen`, which print their own way, always return `false`, and the callers then
use `printTree()` as before. (One quirk it has to reproduce: in these strings a leaf's
branch length is in fixed notation and an internal branch length in default notation,
because `printTree()` switches only the leaf's stream to `std::fixed`.)

### 6. SH-aLRT: `IQTREE_ALRT_CACHE_CHECK` debug build

`tree/phylotree.cpp`

Compiled with `-DIQTREE_ALRT_CACHE_CHECK`, every replayed replicate is also drawn the
original way and compared; any difference aborts, and `testAllBranches()` reports how many
were compared. Not needed for normal builds; it is how change 1 was checked at `-T 2`.

### 7. Define `Node::isLeaf()`, `degree()` and `findNeighbor()` in the header

`tree/node.h`, `tree/node.cpp`

These one-line accessors were out-of-line calls from the search and the kernels, millions
per run (`findNeighbor` alone was ~4% of an advanced run). They are now defined in the class;
`findNeighbor` keeps its search order and moves only its error report out of line. No
arithmetic is involved. About 1%.

### 8. Kernels: skip the OpenMP runtime when the tree has one thread

`tree/phylokernelnew.h`

`computeLikelihoodDervSIMD()` enters a parallel region on every Newton step of every branch,
and `computeTraversalInfo()` on every traversal; with `-T 1` each is a serialized region
(`__kmp_fork_call`, `__kmp_serialized_parallel`, a dynamic-schedule dispatch per packet),
~5% of an advanced run. When `num_threads` is 1 the same loops now run directly. The Derv
packet body became a lambda that takes the reduction variables as parameters, so inside the
OpenMP loop they still bind to the threads' reduction copies. Exactness: a one-thread team
runs the packets in order into copies that start at +0.0 and then adds them to variables that
are still +0.0. Under round-to-nearest a sum started at +0.0 can never end at -0.0, so adding
it to +0.0 leaves it unchanged, and summing directly gives the same values. The serialized
team's thread number is 0, so the traversal's scratch buffer is the same too. About 2%.

### 9. Kernels: interleave tip partial likelihoods with vector transposes

`tree/phylokernelnew.h`

Where a child is a leaf, the kernels look up the precomputed partial likelihood of each of
the 4 patterns' tip states and interleave them pattern by pattern into a buffer that is then
read as vectors. The interleave was one double at a time (clang emits scalar `vmovq`
load/store pairs), so each 256-bit vector read back had been written by four separate 8-byte
stores, which the CPU cannot forward to the load. `interleaveTipLh()` now does it with four
vector loads, a 4x4 transpose (`unpacklo/hi`, `permute2f128`) and four vector stores when
there are 4 patterns per vector on an AVX target, and with the old loop otherwise. The same
doubles land in the same places. Used for the tip-tip and tip-internal partials,
`computeLikelihoodBufferSIMD` and `computeLikelihoodBranchSIMD`; the rare multifurcating case
is unchanged. The helper is file-local (anonymous namespace) because the header is compiled
once per instruction set. About 7% on Quick Tree and 11% on advanced runs.

### 10. Kernels: capture the Derv packet's inputs by value

`tree/phylokernelnew.h`

Follow-up to change 8: the lambda only writes its sums and arrays reached through pointers,
so the other locals are captured by value and the pattern loop does not reload them through
the closure. A non-mutable lambda cannot assign a by-value capture, so the compiler confirms
that none is written. Small.

### 11. Kernels: two pattern blocks per pass for internal-internal partials

`tree/phylokernelnew.h`

For every 4-pattern block and rate category the internal-internal case broadcasts the same
48 coefficients (both children's eigenvector x exp rows and the inverse eigenvectors) from
memory. In the fixed-4-state, non-safe, non-site-model instantiation, two blocks are now
processed per pass: each block makes exactly the `dotProductDualVec` / `productVecMat` calls
of the single-block loop on the same operands, with its temporaries in registers, and then
runs the same scaling check; only the coefficient loads are shared. The blocks write
disjoint patterns. 0.7% on Quick Tree, 2% on advanced runs, 6% on a 489-taxon GTR+F+R6 tree.

### Version (not part of `upstream-pr` or `speedups`)

The [`exact-speedups`](https://github.com/AlanRockefeller/iqtree3/tree/exact-speedups) branch and the
[`v3.1.4-dikarya1`](https://github.com/AlanRockefeller/iqtree3/tree/v3.1.4-dikarya1) tag add one commit that changes
`iqtree_VERSION_PATCH` to `.4-dikarya1`, so a run's log names the build. Drop it when merging.

## Results

### Real alignments (official 3.1.4 vs `v3.1.4-dikarya1`, `-T 1`)

| workload | official 3.1.4 | dikarya1 | speedup |
|---|---|---|---|
| Quick Tree, 48 alignments (8-969 sequences), total | 285.0 s | 191.9 s | 1.48x |
| Quick Tree, per alignment | median 3.94 s | median 2.49 s | median 1.63x (range 1.28x-2.29x) |
| advanced, 19 alignments, total | 4,288 s | 2,783 s | 1.54x |
| advanced, per alignment | | | median 1.75x (range 1.18x-2.66x; 9x on a 6-taxon alignment) |
| largest Quick Tree (969 sequences, 627 patterns) | 101.1 s | 79.0 s | 1.28x |
| 489 sequences, GTR+F+R6, `-n 3` (baseline: stock rebuild) | 257.9 s | 210.9 s | 1.22x |

The gains are largest where IQ-TREE was doing work it then discarded (SH-aLRT resamples,
UFBoot bookkeeping) and smallest on large trees and pattern-rich alignments, whose time is
almost all in the likelihood kernels.

### Synthetic alignments (reproducible)

`test_scripts/exact-speedups/compare-builds.sh <official> <dikarya1> N L` on this machine:

| alignment | options | official 3.1.4 | this fork | speedup | outputs |
|---|---|---|---|---|---|
| synthetic, 150 x 700 | `-m GTR+G -n 5 --alrt 1000` | 6.04 s | 4.04 s | 1.50x | identical |
| synthetic, 150 x 700 | `-m MFP -B 1000 --bnni --alrt 1000` | 260.9 s | 178.7 s | 1.46x | identical |
| synthetic, 150 x 700 | `-m HKY+G -B 1000 --alrt 1000` | 65.5 s | 48.7 s | 1.34x | identical |
| `example/example.phy`, 17 x 1998 | `-m GTR+G -n 5 --alrt 1000` | 1.39 s | 0.91 s | 1.53x | identical |
| `example/example.phy`, 17 x 1998 | `-m MFP -B 1000 --bnni --alrt 1000` | 25.6 s | 19.0 s | 1.35x | identical |
| `example/example.phy`, 17 x 1998 | `-m HKY+G -B 1000 --alrt 1000` | 6.53 s | 5.44 s | 1.20x | identical |
| synthetic, 400 x 700 | `-m GTR+G -n 5 --alrt 1000` | 24.5 s | 17.4 s | 1.41x | identical |
| synthetic, 400 x 700 | `-m GTR+G -B 1000 --bnni --alrt 1000` | 996.8 s | 660.4 s | 1.51x | identical |

Commands: `compare-builds.sh OFFICIAL NEW 150 700`; `compare-builds.sh OFFICIAL NEW 0 0
example/example.phy`; `OPTS=$'-m GTR+G -n 5 --alrt 1000\n-m GTR+G -B 1000 --bnni --alrt 1000'
compare-builds.sh OFFICIAL NEW 400 700` (seed 20261007, single runs).

### Contribution of each change

Interleaved runs as the changes were added, on subsets of the real alignments (8-12 Quick
Tree and 2-5 advanced alignments; totals in seconds, then the change from the previous
build on the same subset):

| after change | Quick Tree | advanced |
|---|---|---|
| 3.1.4 (stock rebuild, same outputs as the official binary) | 55.9 | 115.8 (2 alignments) / 140.6 (5) |
| 1-3 (SH-aLRT cache, lazy UFBoot print, popcnt) | 37.4 (1.50x) | 85.9 (1.35x) / 103.4 |
| 4-5 (checkpoint, sorted strings) | | 76.7 (5 alignments: 1.83x) |
| 7 (inline accessors) | -1.4% | -0.6% |
| 8 (no OpenMP runtime at one thread) | -1.8% | -1.9% |
| 9 (tip transposes) | -6.6% | -11.4% |
| 10 (capture by value) | -0.3% | -0.4% |
| 11 (two blocks per pass) | -0.7% | -2.2% (GTR+F+R6, 489 taxa: -5.8%) |

### Where the time goes now

In the same Quick Tree profile, after the changes: likelihood kernels ~67%
(`computePartialLikelihoodSIMD` ~40%, Derv ~15%, buffer ~6%), PLL parsimony ~13%. In the
advanced run: kernels ~50%, the UFBoot RELL dot products ~8%, `clearReversePartialLh` ~4%,
`malloc`/`free` ~5%. On a 489-taxon GTR+F+R6 search the partial-likelihood kernel alone is
~75%.

## Tried and not adopted

- **PGO** (clang `-fprofile-instr-use`, trained on runs not used for measuring): 3% on Quick
  Tree, nothing on advanced runs. Not worth shipping a profile.
- **`-march=native` for the generic translation units.** Eigen and vectorclass choose packet
  width and FMA use from `__AVX2__`/`__FMA__`, so this changes results (for example in the
  eigendecomposition). Enabling only integer extensions would be exact but buys little.
- **LTO.** It could inline a non-FMA `a*b+c` from a generic translation unit into an FMA
  kernel function, where the `fmuladd` would then be fused, changing results.
- **Storing UFBoot replicate counts as `uint16_t`** for `dotProductSIMD` (~8% of an advanced
  run, bound by memory traffic). Widening needs AVX2 (`vpmovzxwd`), which the FMA kernel
  translation unit (`-mavx -mfma`) does not enable; the SSE4.1 fallback costs about as much
  as it saves.
- **Stopping `PhyloNode::clearReversePartialLh()` at an entry that is already cleared**
  (O(n) per optimized branch, so O(n^2) per pass; 15% of a 969-taxon Quick Tree run). Not
  provably exact: memory-slot eviction (`LM_MEM_SAVE`) and the single-entry
  `clearPartialLh()` calls can leave a cleared entry whose dependants are still marked
  computed.
- **Computing tip tables only for states a leaf has** (`computePartialInfo` builds all 19
  DNA codes for every leaf child; est. 2-4%). Exact in principle, but needs per-leaf state
  masks and a poison test to prove nothing reads the skipped entries; not done.
- **Sharing more coefficient loads or using wider vectors in the main kernel.** On Broadwell
  that kernel is limited by both its FP and its load ports, so this buys little beyond
  change 11.

## Things we noticed in stock IQ-TREE and did not change

1. **Hang with an LLVM toolchain on `LD_LIBRARY_PATH`.** The official 3.1.4 binary (and any
   build with the bundled `libomp.a`) spins at 100% CPU forever, printing nothing after the
   `Seed:` line, when `LD_LIBRARY_PATH` includes an LLVM 22 `lib/` directory (as during a
   build). The binary contains the names `libompd.so` and `libarcher.so` (OpenMP tool and
   debugging plugins the runtime looks for at startup), and that directory provides
   `libompd.so`; we did not trace further. Unsetting `LD_LIBRARY_PATH` avoids it.
2. **`-T 1` is not quite one core.** The RapidNJ step uses all cores regardless of `-T`
   (the log reports e.g. "Constructing RapidNJ tree: done in 0.0013 secs using 221.5% CPU"),
   and the OpenMP worker then spin-waits for the default 200 ms block time. Harmless for one
   job, noticeable on a shared server running many small ones.
3. **SH-aLRT resamples.** With `-T 1` every branch is tested against the same 1000 RELL
   resamples (each test re-seeds the stream). With `-T n`, thread t uses `ran_seed + t`, so
   SH-aLRT values depend on the thread count. Change 1 preserves both behaviours exactly.
4. **`-T 2` is not reproducible run to run**, even with a fixed topology (`-te`), presumably
   because OpenMP reductions over dynamically scheduled packets combine partial sums in a
   run-dependent order.
5. **Line endings.** `tree/phylotree.h` (and some other files) use CRLF line endings, so
   this series must be applied with `git am --keep-cr`.

## Reproducing

Build the way the release is built (Linux x86-64; this matches `.github/workflows/ci.yaml`):

```bash
git clone --branch exact-speedups --recurse-submodules https://github.com/AlanRockefeller/iqtree3.git
cd iqtree3 && mkdir build && cd build
# clang 22 (apt.llvm.org), libeigen3-dev and libboost-dev from Ubuntu 22.04
cmake .. -DIQTREE_FLAGS=static -DUSE_MUTSEL=OFF -DCMAKE_POLICY_VERSION_MINIMUM=3.5 \
    -DCMAKE_C_COMPILER=clang-22 -DCMAKE_CXX_COMPILER=clang++-22
make -j iqtree3
```

Then compare it with the official binary (`iqtree-3.1.4-Linux-intel`, or your own build of
v3.1.4 made the same way):

```bash
test_scripts/exact-speedups/compare-builds.sh /path/to/official/iqtree3 build/iqtree3 150 700
OPTS="-m GTR+G -n 5 --alrt 1000" test_scripts/exact-speedups/compare-builds.sh \
    /path/to/official/iqtree3 build/iqtree3 400 700
```

Each option set runs once per build at `-T 1` with the same seed; the script reports both
times and whether every output file matched, and exits non-zero on any difference. The
synthetic families come from `gen-family.awk` (`N` sequences x `L` columns, fixed seed).

For the SH-aLRT cache check at more than one thread, build with
`-DCMAKE_CXX_FLAGS=-DIQTREE_ALRT_CACHE_CHECK` and run anything with `--alrt 1000 -T 2`; the
log ends the SH-aLRT section with `ALRT_CACHE_CHECK: N replayed replicates matched`.
