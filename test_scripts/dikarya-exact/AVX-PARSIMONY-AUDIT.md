# Local AVX parsimony trial

The selected refinement is `-DDIKARYA_HYBRID_PARSIMONY=ON`: only
`fastDNAparsimony.c` receives `-mpopcnt -mavx2
-DIQTREE_DIKARYA_HYBRID_PARSIMONY`. It keeps the existing SSE allocation and
four-word padding, uses unaligned AVX2 integer operations for complete
eight-word DNA chunks, then uses the original SSE loop for a four-word tail.
Other state counts retain the original loops. This avoids increasing padding
on short alignments. The option defaults to off in general CMake builds;
the Dikarya build script enables it on an AVX2 host.

Both SSE versus the original AVX trial and SSE versus the hybrid passed
3,800 independent scalar-Fitch cases and 986,179 strict-bound decisions.
The tests include 16-byte-offset rows and widths 12 and 20, which require both
the wide prefix and narrow tail. Structure sizes and offsets were identical.
The common fixture digest is `0e761a6a5fab47be`.

The original whole-width trial remains available for comparison:

`-DDIKARYA_AVX_PARSIMONY=ON` changes only `pll/fastDNAparsimony.c` to
`-mpopcnt -mavx -D__AVX`, on eligible x86-64 builds without `novx`. The option
is off by default and requires a CPU with AVX. It does not add FMA, AVX2 or
architecture flags to the other PLL or IQ-TREE translation units.

## Exactness audit

* The existing SSE and AVX kernels perform the same AND, OR, AND-NOT and
  population-count operations on 32-bit parsimony words. AVX processes eight
  words at a time instead of four. Integer full scores are unchanged for
  Dikarya's alignment sizes, well below unsigned score overflow.
* `compressDNA()` in this same file allocates `parsVect` with the local
  `PLL_BYTE_ALIGNMENT` (32 bytes under AVX), rounds each state/node row to
  `INTS_PER_VECTOR`, and sets every padding position to all possible states.
  Such positions have nonempty intersections at every internal node and add
  zero cost. `parsimonyScore` is also allocated locally; the same file frees
  both allocations.
* `parsimonyLength` and `parsVect` are otherwise initialized to null by
  `pll/utils.c`. The alternate reader/writer implementation in `pll/parsimony.c`
  is not part of the CMake target. `pll.h` changes alignment constants and
  `pllInternal.h` adds AVX function declarations; neither conditionally changes
  shared struct fields or their layout.
* A rejected candidate's early-return bound can differ because the wider
  block adds more nonnegative costs before checking `sum >= bestScore`.
  Both users are local: `stepwiseAddition()` and `testInsertParsimony()` (the
  latter through the static `evaluateParsimony()` wrapper). Both use only the
  strict comparison `mp < tr->bestParsimony`. No rejected bound is printed,
  used for equality-based tie selection or passed to a random-number call.
  An accepted candidate never hits the bound and has its identical full score.
  The traversal's `newview` calculations complete before the bound loop, so
  changing its stopping point does not leave different partials behind.
* Random numbers are drawn only in `makePermutationFast()`. Its loop and
  calls are unchanged. The one floating-point multiplication used to select
  a permutation index gains no FMA instruction or reassociated expression.

## Validation before enabling

1. Compare struct sizes/offsets in SSE and AVX fixture builds.
2. Check independent scalar Fitch scores and all computed internal bitsets
   for state counts 2, 4 and 20, including zero, partial-word and partial-SIMD
   lengths. Check all accepted full scores and strict-bound decisions rather
   than requiring identical rejected early-return bounds.
3. Replay real sanitized alignments with the same seed, single thread and
   app commands. Require exact scientific artifacts and normalized reports,
   including the starting-tree and final parsimony information in the logs.
4. Time interleaved runs, emphasizing the 969-taxon case that spends roughly
   25 seconds constructing its starting parsimony trees. Retain the option only
   if the complete workload improves and all exactness checks pass.
