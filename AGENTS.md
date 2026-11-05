# Review guidance

The fork's performance changes must preserve scientific results for the same
input, complete options and seed in the documented single-thread build.
See `DIKARYA-OPTIMIZATIONS.md` and `DIKARYA-BENCHMARKS.md` for scope and evidence.

## Code Review Rules

### Numerical and random-stream behavior

Check changes to floating-point expression/reduction order, FMA contraction,
Eigen packet selection and RNG draw order. Skipping repeated work is safe only
when the reused values and state match the original computation. Documentation
and passing examples do not replace checking those invariants in the code.

### Memory, caches and parallel work

Check cache lifetime and keys, SIMD alignment/tails, packet boundaries and
ownership of shared partition buffers. MCMCtree must retain its derivative
exports even when ordinary inference omits unused matrix storage. Wider
integer pruning may return a different rejected bound only if every consumer
still makes the same acceptance decision and retains the same mutations.

### Build and deployment boundaries

Keep integer-only CPU flags scoped to the parsimony translation unit. Review
the administrator installer for path, symlink, ownership and atomic-update
errors; installation must not imply permission to interrupt running jobs.
