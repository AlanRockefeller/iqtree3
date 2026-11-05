# Deterministic synthetic DNA alignment for comparing IQ-TREE builds.
#
#   awk -v N=150 -v L=700 -v SEED=20261007 -f gen-family.awk > family.fasta
#
# N sequences of L columns descend through a random tree (each sequence copies a
# random earlier one and mutates it), with site-rate variation (40% invariant
# sites), a gap run in every 9th sequence, an ambiguity code in every 7th and
# three exact duplicates, so duplicate removal, gaps and ambiguous states are
# exercised. The same N, L and SEED always give the same file.
BEGIN {
    if (N == "") N = 80; if (L == "") L = 700; if (SEED == "") SEED = 20261007
    srand(SEED); split("ACGT", b, ""); split("RYKMSWN", amb, "")
    for (i = 1; i <= L; i++) { anc = anc b[int(rand()*4)+1]; r[i] = rand() < 0.4 ? 0.0 : rand()^2 }
    seq[1] = anc
    for (s = 2; s <= N; s++) {
        p = seq[int(rand()*(s-1))+1]; out = ""
        for (i = 1; i <= L; i++) {
            c = substr(p, i, 1)
            if (c != "-" && rand() < 0.12 * r[i]) c = b[int(rand()*4)+1]
            out = out c
        }
        seq[s] = out
    }
    for (s = 1; s <= N; s++) {
        x = seq[s]
        if (s % 9 == 0) { g = int(rand()*(L-30)) + 1; x = substr(x, 1, g-1) sprintf("%25s", "") substr(x, g+25); gsub(/ /, "-", x) }
        if (s % 7 == 0) { a = int(rand()*L) + 1; x = substr(x, 1, a-1) amb[int(rand()*7)+1] substr(x, a+1) }
        seq[s] = x
    }
    if (N >= 6) { seq[N-1] = seq[3]; seq[N-2] = seq[5]; seq[N-3] = seq[5] }
    for (s = 1; s <= N; s++) printf(">taxon%04d\n%s\n", s, seq[s])
}
