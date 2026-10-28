#!/usr/bin/env bash
# Reproduce the release's numerical toolchain without installing system packages.
set -euo pipefail
here=$(cd -- "$(dirname -- "$0")" && pwd)
source_dir=$(cd -- "$here/../.." && pwd)
workspace=$(dirname -- "$source_dir")
cache=${IQTREE_TOOLCHAIN_CACHE:-/var/www/dikarya/cache/iqtree-toolchain}
toolchain=${IQTREE_TOOLCHAIN:-$workspace/toolchain}
build_dir=${IQTREE_BUILD_DIR:-$workspace/build}
hybrid_parsimony=${IQTREE_HYBRID_PARSIMONY:-ON}
if [[ "$hybrid_parsimony" == ON ]] && ! rg -qw avx2 /proc/cpuinfo; then
    hybrid_parsimony=OFF
fi

# Verify exactly the pinned packages, rather than trusting a compiler's name.
(cd -- "$cache" && sha256sum --check --quiet "$here/toolchain.sha256")
mkdir -p -- "$toolchain" "$build_dir"
while read -r digest package; do
    [[ -n "$package" ]] || continue
    dpkg-deb -x "$cache/${package#\*}" "$toolchain"
done < "$here/toolchain.sha256"

llvm=$toolchain/usr/lib/llvm-22
# Scope the toolchain libraries to compilation. IQ-TREE's static OpenMP runtime
# must not see these libraries when the resulting executable is run.
tc() {
    LD_LIBRARY_PATH="$llvm/lib:$toolchain/usr/lib/x86_64-linux-gnu" \
        PATH="$llvm/bin:$PATH" "$@"
}
tc cmake -S "$source_dir" -B "$build_dir" \
    -DCMAKE_POLICY_VERSION_MINIMUM=3.5 -DIQTREE_FLAGS='static nostrip' \
    -DUSE_MUTSEL=OFF \
    -DCMAKE_C_COMPILER="$llvm/bin/clang" \
    -DCMAKE_CXX_COMPILER="$llvm/bin/clang++" \
    -DEIGEN3_INCLUDE_DIR="$toolchain/usr/include/eigen3" \
    -DBoost_INCLUDE_DIR="$toolchain/usr/include" \
    -DDIKARYA_AVX_PARSIMONY=OFF \
    -DDIKARYA_HYBRID_PARSIMONY="$hybrid_parsimony" \
    -DCMAKE_EXE_LINKER_FLAGS=-fuse-ld=lld "$@"
tc nice -n 10 cmake --build "$build_dir" --target iqtree3 -j "${IQTREE_BUILD_JOBS:-2}"
"$build_dir/iqtree3" --version
