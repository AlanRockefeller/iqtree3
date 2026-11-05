#!/bin/bash
# Compare two IQ-TREE builds on the same alignment, options and seed, at -T 1.
#
#   test_scripts/exact-speedups/compare-builds.sh REF_BINARY NEW_BINARY [N] [L] [ALIGNMENT]
#
# Without ALIGNMENT, a synthetic family of N sequences x L columns (default
# 150 x 700) is generated with gen-family.awk. For each option set the two
# builds run one after the other; the script prints both wall-clock times and
# whether every output matched (compare-runs.py: trees, consensus trees, splits,
# distances and UFBoot trees byte for byte; .iqtree, .log and .model.gz apart
# from timings, dates and the version banner). Exit status 1 if anything differs.
#
# Option sets: one per line in $OPTS, default below. Set SEED to change the seed.
set -euo pipefail

REF=${1:?reference binary}
NEW=${2:?new binary}
N=${3:-150}
L=${4:-700}
ALN=${5:-}
SEED=${SEED:-20261007}
OPTS=${OPTS:-"-m GTR+G -n 5 --alrt 1000
-m MFP -B 1000 --bnni --alrt 1000
-m HKY+G -B 1000 --alrt 1000"}
HERE=$(cd "$(dirname "$0")" && pwd)

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
if [ -z "$ALN" ]; then
    awk -v N="$N" -v L="$L" -f "$HERE/gen-family.awk" > "$tmp/aln.fasta"
    ALN=$tmp/aln.fasta
    echo "alignment: synthetic, $N x $L (gen-family.awk)"
else
    echo "alignment: $ALN"
fi
echo "reference: $("$REF" --version 2>/dev/null | sed -n 1p)"
echo "new:       $("$NEW" --version 2>/dev/null | sed -n 1p)"
echo
printf '%-38s %9s %9s %8s  %s\n' "options (-T 1, --seed $SEED)" "ref (s)" "new (s)" speedup outputs

status=0
n=0
while IFS= read -r opts; do
    [ -n "$opts" ] || continue
    n=$((n+1))
    declare -A secs
    for side in ref new; do
        bin=$REF; [ "$side" = new ] && bin=$NEW
        mkdir -p "$tmp/$side$n"
        t0=$EPOCHREALTIME
        # shellcheck disable=SC2086
        "$bin" -s "$ALN" $opts -T 1 --seed "$SEED" --redo --prefix "$tmp/$side$n/run" \
            >/dev/null 2>&1 || { echo "$side failed: $opts" >&2; status=1; }
        secs[$side]=$(awk -v a="$t0" -v b="$EPOCHREALTIME" 'BEGIN { printf "%.2f", b - a }')
    done
    if python3 -I "$HERE/compare-runs.py" "$tmp/ref$n/run" "$tmp/new$n/run" > "$tmp/cmp$n" 2>&1; then
        verdict=identical
    else
        verdict="DIFFERENT: $(tr '\n' ' ' < "$tmp/cmp$n")"
        status=1
    fi
    printf '%-38s %9s %9s %7sx  %s\n' "$opts" "${secs[ref]}" "${secs[new]}" \
        "$(awk -v a="${secs[ref]}" -v b="${secs[new]}" 'BEGIN { printf "%.2f", a / b }')" "$verdict"
done <<< "$OPTS"
exit $status
