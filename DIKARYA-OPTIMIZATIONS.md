# Dikarya optimized IQ-TREE 3.1.4

`3.1.4-dikarya2` speeds up the IQ-TREE commands used by
[Dikarya](https://dikarya.us) while preserving the scientific results in the
validated workloads. It was activated on Dikarya on **2026-10-28**.

Five fresh paired replays took **100.238 s → 93.308 s**, or **6.9% less wall
time**, compared with the already optimized `3.1.4-dikarya1` build. This is an
incremental gain over `dikarya1`, not a new comparison with stock IQ-TREE.
See [benchmarks and validation](DIKARYA-BENCHMARKS.md) for the individual jobs,
comparison rules and sample sizes.

## Versions and availability

| Version | Role | Source/status |
|---|---|---|
| Upstream `3.1.4` | Original IQ-TREE release | [Official source](https://github.com/iqtree/iqtree3/tree/v3.1.4) |
| `3.1.4-dikarya1` | Earlier optimization series; baseline for this work | [Earlier branch](https://github.com/AlanRockefeller/iqtree3/tree/exact-speedups) and [historical technical write-up](EXACT-SPEEDUPS.md) |
| `3.1.4-dikarya2` | Changes described here; deployed on Dikarya | [Source branch](https://github.com/AlanRockefeller/iqtree3/tree/codex/dikarya2-exact-speedups), proposed for this fork's `master` branch |

This branch preserves the earlier optimization commits through `33c00b8c`
and adds the `dikarya2` changes. It includes both rounds above the fork's
stock `master` baseline. The fork's default branch remains `exact-speedups`;
select `codex/dikarya2-exact-speedups` explicitly to obtain this version.
No downloadable GitHub release or `dikarya2` release tag is claimed here.
The deployment bundle's `source.patch` records the original changes relative
to `33c00b8c`; current source documentation can be newer than that immutable
bundle.

## Run the installed build

On Dikarya, the selected executable is
`/opt/iqtree-3.1.4-dikarya2/bin/iqtree3`. These examples match the command shapes
in `app/services/tree_builder_service.py::_run_iqtree`:

```sh
IQTREE=/opt/iqtree-3.1.4-dikarya2/bin/iqtree3

# Quick Tree: five search iterations and SH-aLRT support.
"$IQTREE" -s alignment.fasta -m GTR+G -T 1 --seed 20261028 \
  -n 5 --alrt 1000 --prefix quick --redo

# Advanced: ModelFinder, UFBoot refinement and SH-aLRT support.
"$IQTREE" -s alignment.fasta -m MFP -T 1 --seed 20261028 \
  -B 1000 --bnni --alrt 1000 --prefix advanced --redo
```

For a comparison, use the same input, complete option set, seed and thread count.
`--redo` starts a fresh analysis rather than resuming an old checkpoint.
Dikarya records each job's actual seed; the seed above is only an example.
Quick Tree deliberately omits UFBoot.

## What changed, and why results are preserved

| Area | Optimization | Exactness argument |
|---|---|---|
| Alignment input | A 256-byte alphabet table replaces four hash lookups per character; column construction reuses a sized pattern buffer. | The independent character counts and every pattern state are unchanged. |
| Bootstrap frequencies | Fill the destination vector directly and add sampled integer multiplicities once per site. | Random draws stay in the same order; the same nonnegative counts are accumulated. |
| Single-packet likelihood work | Keep bounds and small reductions on the stack; capture bounds by reference. | Packet endpoints and operands are unchanged; references remain alive through joined work. |
| One-thread execution | Bypass the OpenMP runtime in branch and buffered likelihood paths. | The same packet bodies run in the same serial order. |
| Buffered reductions | Stream scalar contributions without temporary arrays. | Addition order, including the original trailing zero slot, is retained. |
| Derivative storage | Allocate and fill the large per-pattern branch matrix only for `--dating mcmctree`. | Ordinary inference never consumes it. MCMCtree still receives the matrix, including partitioned models. |
| Partial invalidation | Skip recursive calls into leaves after clearing their incoming edge. | The skipped call had no remaining edges to visit or writes to perform. |
| Tip/internal likelihoods | Use four local SIMD intermediates. | Arithmetic expressions are retained; local storage lets the compiler avoid scratch-buffer traffic. |
| DNA tip pairs | Cache the original SIMD output for repeated canonical/unknown pairs within one call. | Values come from the original computation; the cache ends before model, branch-length or row changes. Ambiguity pairs use the original path. |
| DNA parsimony | Process full eight-word chunks with AVX2 integer operations, then retain the four-word SSE tail. | Layout and padding are unchanged. Full scores and strict acceptance decisions match the scalar oracle. |

The derivative matrix avoided in ordinary inference occupies roughly
`8 × branches × padded_patterns` bytes, in addition to its repeated stores.
The small reduced derivative vectors remain available.

The wider parsimony loop can return a different intermediate bound for a
rejected candidate. Its callers accept only `score < best_score`; accepted
candidates still receive their identical complete score. Starting-tree
selection and random draws are unchanged. The
[parsimony audit](test_scripts/dikarya-exact/AVX-PARSIMONY-AUDIT.md) explains
bound checks, layout and alignment.

## What “byte-identical” covers

The validated `dikarya2` executable was compared with `dikarya1` using the
same sanitized alignment, options and recorded seed at `-T 1`:

- Trees, branch supports, distance files and other scientific artifacts must
  match as bytes. Unknown result extensions are checked too.
- `.iqtree`, `.log` and decompressed `.model.gz` are compared after the explicit
  timing/build/path normalization in the comparator. Seeds, kernel choice,
  model parameters, likelihoods and search iteration counts remain checked.
- `.ckp.gz` is excluded: recovery snapshots are written on a wall-clock schedule.
  MCMCtree control files normalize output paths; numerical Hessian files are
  compared without numerical normalization.

The suite passed **23 real workloads (6–1042 taxa), three additional real-input
model/support variants, 19 synthetic edge cases and four MCMCtree export cases**.
The earlier `dikarya1` series has its own documented comparison with stock
IQ-TREE. These are separate validation and benchmark datasets.

The evidence does not establish reproducibility for arbitrary multithreaded
searches. One deterministic two-thread fixed-tree regression case checks the
parallel fallback; it is not a general `-T 2` guarantee. A different compiler,
math/runtime library, packet width or floating-point build flag needs its own
comparison before claiming byte identity.

## Build with the validated toolchain recipe

The helper is for **Linux x86-64**, tested on Ubuntu 24.04. It needs Bash,
`rg`, `sha256sum`, `dpkg-deb`, CMake, Make, and host C/C++ development and static
runtime libraries. Initialize source submodules first:

```sh
git clone --branch codex/dikarya2-exact-speedups --recurse-submodules \
  https://github.com/AlanRockefeller/iqtree3.git
cd iqtree3

# For an existing clone:
git submodule update --init --recursive
```

The package cache must already contain **all 11 exact `.deb` files** listed in
[toolchain.sha256](test_scripts/dikarya-exact/toolchain.sha256). These supply
Clang/LLVM 22.1.8, Eigen 3.4.0 and Boost 1.74, among other compiler components.
The helper verifies their hashes and extracts them locally. It **does not
download packages**. Its default cache is specific to Dikarya:
`/var/www/dikarya/cache/iqtree-toolchain`. An external checkout alone does not
provide this cache; obtain the exact listed packages before using the recipe.

From this source checkout, choose fresh build and extracted-toolchain
directories and an existing package cache:

```sh
export IQTREE_TOOLCHAIN_CACHE=/absolute/path/to/pinned-debs
export IQTREE_TOOLCHAIN="$PWD/../toolchain-dikarya2"
export IQTREE_BUILD_DIR="$PWD/../build-dikarya2"

bash test_scripts/dikarya-exact/build.sh \
  -DCMAKE_BUILD_TYPE=Release \
  -DDIKARYA_CHERRY_CACHE=ON \
  -DDIKARYA_CHERRY_CACHE_CHECK=OFF \
  -DDIKARYA_LOCAL_TIP_PARTIAL=ON

"$IQTREE_BUILD_DIR/iqtree3" --version
```

Existing CMake cache values can persist; a directory with a new example name
above is only fresh if it does not already exist. The helper defaults to two
build jobs; `IQTREE_BUILD_JOBS` overrides that budget.

The recipe selects `IQTREE_FLAGS='static nostrip'` and **`USE_MUTSEL=OFF`**:
Rust mutation-selection models are not included in this validated build.
It pins the compiler and Eigen/Boost packages but still consumes host system
headers and static libraries; it is not a complete OS/sysroot snapshot.
The test host supplied GCC 13/libstdc++ development files. Matching the recipe
on another host therefore still requires result validation.

The helper enables hybrid parsimony when `/proc/cpuinfo` reports AVX2; set
`IQTREE_HYBRID_PARSIMONY=OFF` to disable it. Only the integer parsimony C file
receives `-mavx2`. The inherited x86 build also uses POPCNT. Global
`-march=native`, LTO or fast-math flags can change likelihood arithmetic and
Eigen packet selection and are outside the validated configuration.

Compiler library paths are scoped to compilation by the helper. Do not leave
its LLVM library directory on `LD_LIBRARY_PATH` when running IQ-TREE: the
statically linked OpenMP runtime can load incompatible tool plugins there.

The executable embeds build-date information. Its published SHA-256 identifies
the tested packaged executable; rebuilding on another date or host need not
produce the same executable bytes.

### Ordinary development build

With a supported C/C++ compiler, CMake, Eigen and Boost installed, an ordinary
build can be used for development without the private package cache:

```sh
cmake -S . -B ../build-development -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_POLICY_VERSION_MINIMUM=3.5 \
  -DUSE_MUTSEL=OFF -DDIKARYA_HYBRID_PARSIMONY=OFF
cmake --build ../build-development --target iqtree3 -j 2
```

This is not the configuration certified by the Dikarya comparisons. Disabling
the new AVX2 option does not remove the inherited POPCNT requirement on eligible
x86 builds. The upstream [build workflow](.github/workflows/ci.yaml) documents
other compiler/platform configurations.

## Optimization switches

| CMake option | Default | Purpose |
|---|---|---|
| `DIKARYA_CHERRY_CACHE` | `ON` | Reuse repeated DNA tip-pair values within one call. |
| `DIKARYA_CHERRY_CACHE_CHECK` | `OFF` | Rerun the original arithmetic and compare cached doubles bit for bit instead of taking the shortcut. It also enables the cache-check code. |
| `DIKARYA_LOCAL_TIP_PARTIAL` | `ON` | Keep four-state tip/internal intermediates local. |
| `DIKARYA_HYBRID_PARSIMONY` | `OFF` in general CMake; auto-enabled by the helper on AVX2 hosts | AVX2 integer prefixes with original SSE layout and tails. |
| `DIKARYA_AVX_PARSIMONY` | `OFF` | Earlier whole-width AVX experiment retained for comparison. The production recipe leaves it off. |

Set the cache and local-intermediate options to `OFF` to compare those kernel
changes. This does not revert the allocation, alignment, derivative-storage or
other `dikarya2` changes. Hybrid parsimony takes precedence over the legacy AVX
experiment if both are enabled. Forced loop unrolling and Broadwell scheduling
were investigated but not adopted.

## Validate without private job data

The [validation guide](test_scripts/dikarya-exact/README.md) starts with the
synthetic edge suite, MCMCtree export comparisons, scalar parsimony oracle and
harness tests. These can run without Dikarya accounts or stored submissions.
Use two executables built with the intended matching numerical configuration.

The retained-job manifests publish case metadata, hashes, options and seeds,
not submitted sequences or original headers. Exact replay requires access to
the retained Dikarya job files; the hashes cannot recreate the inputs.
Cached-reference runs test correctness only. Performance claims require fresh
interleaved runs with matching CPU affinity and idle build/benchmark processes.

## Deployed release and rollback

The verified executable is installed at
`/opt/iqtree-3.1.4-dikarya2/bin/iqtree3`, with SHA-256:

```text
07111b617f367a33ffa72c413c51842e165e64776f2fb709109c41c979bceced
```

Versioned release metadata is in `/opt/iqtree-3.1.4-dikarya2/share/`.
The workspace also retains `../artifacts/iqtree-3.1.4-dikarya2/` and the separate
`../artifacts/iqtree-3.1.4-dikarya2-activation.json` record. The original bundle
describes its packaging-time state; its checksummed documents are not rewritten
after activation. Current source documentation is maintained separately.

`install-release.py` is a **mycolab-specific administrator helper**, not a
general installer. It validates a prepared `release.json`, installs a new
versioned prefix and can update exactly one `IQTREE_BINARY` environment setting
while saving a protected backup. It never restarts services or interrupts jobs.
The build helper itself does not install or activate anything.

Dikarya's administrator selected the new binary on 2026-10-28. Preflight and
guarded web/worker restarts subsequently passed; both phylogenetic queues were
idle at restart, and real jobs were observed completing with the new path.
For rollback, an administrator selects
`/opt/iqtree-3.1.4-dikarya1/bin/iqtree3` and uses the same preflight and guarded
restart procedure. An active-job report requires the user's decision to wait
or interrupt; selecting a binary does not grant interruption consent.
