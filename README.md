# IQ-TREE 3.1.4 with exact speedups (unofficial fork)

**Same trees, faster.** This fork runs IQ-TREE 3.1.4 about **1.6-1.8x faster** on typical
SH-aLRT and UFBoot analyses, and every output is **byte-identical to the official 3.1.4
release** for the same input, options and seed at `-T 1`: the trees, branch supports, model
parameters, log-likelihoods, report and log (apart from timings and the version line).
Nothing about the results changes, only how long you wait for them.

## Why this repo exists

[Dikarya](https://dikarya.us) is a web service that builds phylogenetic trees from fungal ITS
barcode sequences with IQ-TREE: over a thousand quick trees a month
(`-m GTR+G -n 5 --alrt 1000`) plus longer ModelFinder and ultrafast bootstrap analyses
(`-m MFP -B 1000 --bnni --alrt 1000`). Profiling the official binary showed that a large part
of its time went to work whose result is thrown away. We removed that work without changing
any arithmetic, have run the result in production since 2026-10-08, and publish it here so
that the IQ-TREE developers can consider the changes for the official release and anyone else
can use or check them.

## How much faster

| analysis (real Dikarya alignments, `-T 1`) | median speedup per run | range |
|---|---|---|
| quick tree, `-m GTR+G -n 5 --alrt 1000` (48 alignments) | **1.63x** (3.94 s to 2.49 s) | 1.28x-2.29x |
| ModelFinder + UFBoot, `-m MFP -B 1000 --bnni --alrt 1000` (19 alignments) | **1.75x** | 1.18x-2.66x |
| very large trees (400-1,000 sequences), mostly likelihood computation | 1.2-1.5x | |

Intel Xeon E5-2690 v4 (Broadwell), official `iqtree-3.1.4-Linux-intel` binary against this
fork. Reproducible benchmarks on synthetic data and on IQ-TREE's own `example.phy` are in
[Results](#results) below.

## How we did it

- **SH-aLRT:** for every branch, stock IQ-TREE re-seeds its random streams and so redraws the
  same 1000 bootstrap resamples, one random number per alignment site each time. They are now
  drawn once and replayed (about 20% of a quick tree run).
- **Ultrafast bootstrap:** every candidate tree was formatted as text before checking whether
  any bootstrap replicate keeps it (about 27% of a UFBoot run); now only kept trees are
  formatted, and without a string stream per subtree. The whole bootstrap state was also
  re-serialized into the checkpoint after every refined tree, although the file is written at
  most once a minute (about 10%); now it is serialized only when it is written.
- **Likelihood kernels:** tip data was assembled with scalar stores that the CPU cannot forward
  to the vector loads that follow (7-11%); the OpenMP runtime was entered even with one thread
  (2%); two pattern blocks now share their coefficient loads.
- **Proving nothing changed:** we first rebuilt the official binary with its own toolchain
  (clang 22, static) and confirmed it reproduces the release, then compared every output file
  of 67 real runs and of 36 runs covering every option combination we use, and checked the
  multi-threaded SH-aLRT path with a debug build that re-draws and compares every replayed
  resample. No floating-point operation is reordered, fused or split.

**[EXACT-SPEEDUPS.md](EXACT-SPEEDUPS.md) has the full story:** each change with the argument
for why it cannot alter a result and its measured effect, how identity was verified, what we
tried and dropped, and some observations about stock IQ-TREE.

> [!WARNING]
> **This is an unofficial fork of IQ-TREE. It is not affiliated with or endorsed by the
> IQ-TREE authors.**
>
> - Official IQ-TREE: **http://www.iqtree.org**
> - Official source: **https://github.com/iqtree/iqtree3**
>
> For general use, install the official release. Please don't report problems with this
> fork to the IQ-TREE developers. Open an issue here instead.

## Results

Measured on the server that runs [Dikarya](https://dikarya.us), a phylogenetics web service
for fungal ITS barcodes: Intel Xeon E5-2690 v4 (Broadwell-EP), 2 vCPUs of a VM, AVX2 + FMA,
no AVX-512. Official `iqtree-3.1.4-Linux-intel` binary against `v3.1.4-dikarya1`, `-T 1`,
the two builds run alternately on each input.

Real alignments submitted to the service (DNA, ITS; not published):

| workload | official 3.1.4 | this fork | speedup |
|---|---|---|---|
| `-m GTR+G -n 5 --alrt 1000`, 48 alignments (8-969 sequences) | median 3.94 s | median 2.49 s | median 1.63x (1.28x-2.29x) |
| `-m MFP -B 1000 --bnni --alrt 1000` (and K2P, `-B 5000`), 19 alignments | 4,288 s total | 2,783 s total | median 1.75x (1.18x-2.66x) |
| `-m GTR+F+R6 -n 3`, 489 sequences (kernel-bound; baseline: stock rebuild) | 257.9 s | 210.9 s | 1.22x |

All 67 real runs produced identical outputs, as did 36 runs covering every option
combination the service uses.

Synthetic alignments, reproducible with `test_scripts/exact-speedups/compare-builds.sh`:

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

The gain is largest where IQ-TREE did avoidable work (SH-aLRT, UFBoot) and smallest on
large trees and pattern-rich alignments, whose time is almost all in the likelihood
kernels; those cannot change their arithmetic without changing results.

## Branches and tags

| ref | contents |
|---|---|
| [`speedups`](https://github.com/AlanRockefeller/iqtree3/tree/speedups) | v3.1.4 (`63c330d`, also upstream `master` on 2026-10-08) + the eleven code commits + the test harness and this documentation. The version string stays `3.1.4`. |
| [`upstream-pr`](https://github.com/AlanRockefeller/iqtree3/tree/upstream-pr) | v3.1.4 + the eleven code commits only: the branch to merge or open a pull request from |
| [`exact-speedups`](https://github.com/AlanRockefeller/iqtree3/tree/exact-speedups) (default) | the eleven code commits + a version commit (`3.1.4-dikarya1`) + the test harness and this documentation |
| [`v3.1.4-dikarya1`](https://github.com/AlanRockefeller/iqtree3/tree/v3.1.4-dikarya1) | the exact source of the build running in production: the eleven code commits + the version commit |

The eleven commits, each with its exactness argument and measurement in the message:

1. SH-aLRT: draw the replicate pattern frequencies once per traversal
2. UFBoot: print a candidate tree only if some replicate takes it
3. PLL parsimony: compile `fastDNAparsimony.c` with `-mpopcnt` on x86-64
4. UFBoot: refresh the checkpoint only when it is about to be dumped
5. UFBoot: print sorted topology strings without per-subtree streams
6. SH-aLRT: `IQTREE_ALRT_CACHE_CHECK` debug build for the replicate cache
7. Node: define `isLeaf()`, `degree()` and `findNeighbor()` in the header
8. Kernels: skip the OpenMP runtime when the tree has one thread
9. Kernels: interleave tip partial likelihoods with vector transposes
10. Kernels: capture the Derv packet's inputs by value
11. Kernels: two pattern blocks per pass for internal-internal partials

## Building and checking

Build exactly as the release is built (see `.github/workflows/ci.yaml`): clang 22,
`-DIQTREE_FLAGS=static`, Ubuntu 22.04's Eigen and Boost headers.

```bash
git clone --branch exact-speedups --recurse-submodules https://github.com/AlanRockefeller/iqtree3.git
cd iqtree3 && mkdir build && cd build
cmake .. -DIQTREE_FLAGS=static -DUSE_MUTSEL=OFF -DCMAKE_POLICY_VERSION_MINIMUM=3.5 \
    -DCMAKE_C_COMPILER=clang-22 -DCMAKE_CXX_COMPILER=clang++-22
make -j iqtree3
cd .. && test_scripts/exact-speedups/compare-builds.sh /path/to/official/iqtree3 build/iqtree3
```

The compiler matters for the identity check: the release is built with clang, whose
default `-ffp-contract=on` fuses `a*b+c` differently from gcc's default, so compare against
a reference built with the same compiler and flags. The changes themselves are
compiler-independent; the x86 kernel code is guarded by `__AVX__`, and `-mpopcnt` applies
only to x86-64. Multi-threaded runs (`-T` > 1) are not reproducible run to run even in stock
IQ-TREE, so the guarantee covers `-T 1`.

## For the IQ-TREE maintainers

`git diff master upstream-pr` is the whole code change against upstream: 14 files, 477 lines
added and 86 removed. (`speedups` adds only `EXACT-SPEEDUPS.md`, this README section and
`test_scripts/exact-speedups/`.)
The commits are independent enough to take one at a time; 1, 2 and 4 are where most of the
time goes. Commit 6 is an optional debug aid, and commit 3 assumes POPCNT (every x86-64 CPU
since about 2008); drop it if the release must run on older CPUs. Some files use CRLF line
endings, so apply the series with `git am --keep-cr`.

`EXACT-SPEEDUPS.md` also lists a few things noticed in stock 3.1.4 and left alone, among
them a hang of the official binary when an LLVM toolchain is on `LD_LIBRARY_PATH`, and RapidNJ
using every core under `-T 1`.

## Credits

- The changes in this fork were designed, implemented, verified and benchmarked by Claude
  Code (Claude Opus 5.5, Anthropic), with Alan Rockefeller directing the work for Dikarya.
- IQ-TREE is by Bui Quang Minh, Thomas Wong, Nhan Ly-Trong, Huaiyan Ren and many
  contributors (see below). Please cite IQ-TREE as its authors ask.
- License: GPL-2.0, the same as IQ-TREE.

---

IQ-TREE
=======

[![Github IQ-TREE 1 Releases](https://img.shields.io/github/downloads/Cibiv/IQ-TREE/total.svg?style=social&logo=github&label=iqtree1%20download)](https://github.com/Cibiv/IQ-TREE/releases)
[![Github IQ-TREE 2 Releases](https://img.shields.io/github/downloads/iqtree/iqtree2/total.svg?style=social&logo=github&label=iqtree2%20download)](https://github.com/iqtree/iqtree2/releases)
[![Github IQ-TREE 3 Releases](https://img.shields.io/github/downloads/iqtree/iqtree3/total.svg?style=social&logo=github&label=iqtree3%20download)](https://github.com/iqtree/iqtree3/releases)

[![BioConda downloads](https://img.shields.io/conda/dn/bioconda/iqtree.svg?style=flag&label=BioConda%20install)](https://anaconda.org/bioconda/iqtree)
[![BioConda platforms](https://img.shields.io/conda/pn/bioconda/iqtree?style=flag)](https://github.com/bioconda/bioconda-recipes/tree/master/recipes/iqtree)
[![Build Status](https://github.com/iqtree/iqtree3/workflows/Build/badge.svg)](https://github.com/iqtree/iqtree3/actions)
[![License: GPL v2](https://img.shields.io/badge/License-GPL%20v2-blue.svg)](https://www.gnu.org/licenses/old-licenses/gpl-2.0.en.html)

Efficient and versatile phylogenomic software by maximum likelihood <http://www.iqtree.org>

Introduction
------------

The IQ-TREE software was created as the successor of IQPNNI and [TREE-PUZZLE](http://www.tree-puzzle.de) (thus the name IQ-TREE). IQ-TREE was motivated by the rapid accumulation of phylogenomic data, leading to a need for efficient phylogenomic software that can handle a large amount of data and provide more complex models of sequence evolution. To this end, IQ-TREE can utilize multicore computers and distributed parallel computing to speed up the analysis. IQ-TREE automatically performs checkpointing to resume an interrupted analysis.

As input IQ-TREE accepts all common sequence alignment formats including PHYLIP, FASTA, Nexus, Clustal and MSF. As output IQ-TREE will write a self-readable report file (name suffix `.iqtree`), a NEWICK tree file (`.treefile`)  which can be visualized by tree viewer programs such as [FigTree](http://tree.bio.ed.ac.uk/software/figtree/), [Dendroscope](http://dendroscope.org) or [iTOL](http://itol.embl.de).


Key features of IQ-TREE
-----------------------

* __Efficient search algorithm__: Fast and effective stochastic algorithm to reconstruct phylogenetic trees by maximum likelihood. IQ-TREE compares favorably to RAxML and PhyML in terms of likelihood while requiring similar amount of computing time ([Nguyen et al., 2015]).
* __Ultrafast bootstrap__: An ultrafast bootstrap approximation (UFBoot) to assess branch supports. UFBoot is 10 to 40 times faster than RAxML rapid bootstrap and obtains less biased support values ([Minh et al., 2013]).
* __Accurate model selection__: An ultrafast and automatic model selection (ModelFinder) which is 10 to 100 times faster than jModelTest and ProtTest. ModelFinder also finds best-fit partitioning scheme like PartitionFinder ([Kalyaanamoorthy et al., 2017]).
* __Alignment simulation__: A flexible simulator (AliSim) which
    allows to simulate sequence alignments under more realistic models than
    Seq-Gen and INDELible ([Ly-Trong et al., 2023]).
* __Phylogenetic testing__: Several fast branch tests like SH-aLRT and aBayes test ([Anisimova et al., 2011]) and tree topology tests like the approximately unbiased (AU) test ([Shimodaira, 2002]).


The strength of IQ-TREE is the availability of a wide variety of phylogenetic models:

* __Common models__: All [common substitution models](http://www.iqtree.org/doc/Substitution-Models) for DNA, protein, codon, binary and morphological data with [rate heterogeneity among sites](http://www.iqtree.org/doc/Substitution-Models#rate-heterogeneity-across-sites) and [ascertainment bias correction](http://www.iqtree.org/doc/Substitution-Models#ascertainment-bias-correction) for e.g. SNP data.
* __[Partition models](http://www.iqtree.org/doc/Complex-Models/#partition-models)__: Allowing individual models for different genomic loci (e.g. genes or codon positions), mixed data types, mixed rate heterogeneity types, linked or unlinked branch lengths between partitions.
* __Mixture Models__: [fully customizable mixture models](http://www.iqtree.org/doc/Complex-Models#mixture-models) and [empirical protein mixture models](http://www.iqtree.org/doc/Substitution-Models#protein-models) and.
* __Polymorphism-aware models (PoMo)__: <http://www.iqtree.org/doc/Polymorphism-Aware-Models>


IQ-TREE web service
-------------------

For a quick start you can also try the IQ-TREE web server, which performs 
online computation using a dedicated computing cluster. It is very easy to use 
with as few as just 3 clicks! Try it out at:

* Vienna Bioinformatics Cluster: <http://iqtree.cibiv.univie.ac.at>
* CIPRES Gateway: <https://www.phylo.org>
* Los Alamos Laboratories: <https://www.hiv.lanl.gov/content/sequence/IQTREE/iqtree.html>

User support
------------

Please refer to the [user documentation](http://www.iqtree.org/doc/) and 
[frequently asked questions](http://www.iqtree.org/doc/Frequently-Asked-Questions). 
If you have further questions and feedback, please create a topic at 
[Github discussions](https://github.com/iqtree/iqtree2/discussions).
For feature requests bug reports please post a topic at
[Github issues](https://github.com/iqtree/iqtree2/issues).

Citations
---------

General citation for IQ-TREE 3:

* T.K.F. Wong, N. Ly-Trong, H. Ren, P. Demotte, H. Banos,
  A.J. Roger, E. Susko, C. Bielow, N. De Maio,
  N. Goldman, M.W. Hahn, M. dos Reis, L.S. Vinh, G. Huttley, R. Lanfear, B.Q. Minh (2026)
  IQ-TREE 3: Phylogenomic Inference Software using Complex Evolutionary Models.
  _Mol. Biol. Evol._, msag117. <https://doi.org/10.1093/molbev/msag117>
  

Moreover, there are other papers associated with notable features in IQ-TREE,
which are normally mentioned in the corresponding documentation. We ask that you also
cite these papers, which are important for us to obtain fundings to 
continuously maintain the code of IQ-TREE. These papers are also listed below.

> **NOTE**: You can also obtain the citations in `.iqtree` output file.

When using MixtureFinder please cite:

* H. Ren, T.K.F. Wong, B.Q. Minh, R. Lanfear (2025) 
  MixtureFinder: Estimating DNA mixture models for phylogenetic analyses.
  _Mol. Biol. Evol._, 42:msae264. <https://doi.org/10.1093/molbev/msae264>

When using GTRpmix model please cite:

* H. Banos, T.K.F. Wong, J. Daneau, E. Susko, B.Q. Minh, R. Lanfear, M.W. Brown, L. Eme, A.J. Roger (2024)
  GTRpmix: A linked general-time reversible model for profile mixture models.
  _Mol. Biol. Evol._, 92:msae174. <https://doi.org/10.1093/molbev/msae174>

When using CMAPLE please cite:

* N. Ly-Trong, C. Bielow, N. De Maio, B.Q. Minh (2024)
  CMAPLE: Efficient phylogenetic inference in the pandemic era.
  _Mol. Biol. Evol._, 41:msae134. <https://doi.org/10.1093/molbev/msae134>

When using tree mixture models (MAST) please cite:

* T.K.F. Wong, C. Cherryh, A.G. Rodrigo, M.W. Hahn, B.Q. Minh, R. Lanfear (2024)
  MAST: Phylogenetic Inference with Mixtures Across Sites and Trees.
  _Syst. Biol._, 73:375–391. <https://doi.org/10.1093/sysbio/syae008>

When computing concordance factors please cite:

* Y.K. Mo, R. Lanfear, M.W. Hahn, B.Q. Minh (2023)
  Updated site concordance factors minimize effects of homoplasy and taxon sampling.
  _Bioinformatics_, 39:btac741. <https://doi.org/10.1093/bioinformatics/btac741>

When using AliSim to simulate alignments please cite:

* N. Ly-Trong, G.M.J. Barca, B.Q. Minh (2023)
  AliSim-HPC: parallel sequence simulator for phylogenetics.
  _Bioinformatics_, 39:btad540. <https://doi.org/10.1093/bioinformatics/btad540>

When estimating amino-acid Q matrix please cite:

* B.Q. Minh, C. Cao Dang, L.S. Vinh, R. Lanfear (2021)
  QMaker: Fast and accurate method to estimate empirical models of protein evolution.
  _Syst. Biol._, 70:1046–1060. <https://doi.org/10.1093/sysbio/syab010>

When using the heterotachy GHOST model "+H" please cite:

* S.M. Crotty, B.Q. Minh, N.G. Bean, B.R. Holland, J. Tuke, L.S. Jermiin, A. von Haeseler (2020)
  GHOST: Recovering Historical Signal from Heterotachously Evolved Sequence Alignments.
  _Syst. Biol._, 69:249-264. <https://doi.org/10.1093/sysbio/syz051>

When using the tests of symmetry please cite:

* S. Naser-Khdour, B.Q. Minh, W. Zhang, E.A. Stone, R. Lanfear (2019) 
  The Prevalence and Impact of Model Violations in Phylogenetic Analysis. 
  *Genome Biol. Evol.*, 11:3341-3352. <https://doi.org/10.1093/gbe/evz193>

When using polymorphism-aware models please cite:

* D. Schrempf, B.Q. Minh, A. von Haeseler, C. Kosiol (2019) 
  Polymorphism-aware species trees with advanced mutation models, bootstrap, and rate heterogeneity. 
  *Mol. Biol. Evol.*, 36:1294–1301. <https://doi.org/10.1093/molbev/msz043>

For the ultrafast bootstrap (UFBoot) please cite:

* D.T. Hoang, O. Chernomor, A. von Haeseler, B.Q. Minh, and L.S. Vinh (2018) 
  UFBoot2: Improving the ultrafast bootstrap approximation. 
  *Mol. Biol. Evol.*, 35:518–522. <https://doi.org/10.1093/molbev/msx281>

When using posterior mean site frequency model (PMSF) please cite:

* H.C. Wang, B.Q. Minh, S. Susko, A.J. Roger (2018) 
  Modeling site heterogeneity with posterior mean site frequency profiles 
  accelerates accurate phylogenomic estimation. 
  *Syst. Biol.*, 67:216–235. <https://doi.org/10.1093/sysbio/syx068>

When using ModelFinder please cite:

* S. Kalyaanamoorthy, B.Q. Minh, T.K.F. Wong, A. von Haeseler, L.S. Jermiin (2017) 
  ModelFinder: Fast model selection for accurate phylogenetic estimates. 
  *Nat. Methods*, 14:587-589. <https://doi.org/10.1038/nmeth.4285>

When using partition models please cite:

* O. Chernomor, A. von Haeseler, B.Q. Minh (2016) 
  Terrace aware data structure for phylogenomic inference from supermatrices. 
  *Syst. Biol.*, 65:997-1008. <https://doi.org/10.1093/sysbio/syw037>

When using IQ-TREE web server please cite:

* J. Trifinopoulos, L.-T. Nguyen, A. von Haeseler, B.Q. Minh (2016) 
  W-IQ-TREE: a fast online phylogenetic tool for maximum likelihood analysis.
  *Nucleic Acids Res.*, 44:W232-W235. <https://doi.org/10.1093/nar/gkw256>

When using IQ-TREE version 1 please cite:

* L. Nguyen, H.A. Schmidt, A. von Haeseler, B.Q. Minh (2015)
  IQ-TREE: A Fast and Effective Stochastic Algorithm for Estimating Maximum-Likelihood Phylogenies.
  _Mol. Biol. and Evol._, 32:268-274. <https://doi.org/10.1093/molbev/msu300>

When using IQ-TREE version 2 please cite:

* B.Q. Minh, H.A. Schmidt, O. Chernomor, D. Schrempf, M.D. Woodhams, A. von Haeseler, R. Lanfear (2020) 
  IQ-TREE 2: New models and efficient methods for phylogenetic inference in the genomic era.
  *Mol. Biol. Evol.*, 37:1530-1534. <https://doi.org/10.1093/molbev/msaa015>


#### Credits and Acknowledgements

Some parts of the code were taken from the following packages/libraries: [Phylogenetic likelihood library](http://www.libpll.org), [TREE-PUZZLE](http://www.tree-puzzle.de), 
[BIONJ](http://dx.doi.org/10.1093/oxfordjournals.molbev.a025808), [Nexus Class Libary](http://dx.doi.org/10.1093/bioinformatics/btg319), [Eigen library](http://eigen.tuxfamily.org/),
[SPRNG library](http://www.sprng.org), [Zlib library](http://www.zlib.net), [gzstream library](http://www.cs.unc.edu/Research/compgeom/gzstream/), [vectorclass library](http://www.agner.org/optimize/), [GNU scientific library](https://www.gnu.org/software/gsl/).


IQ-TREE was funded by the [Austrian Science Fund - FWF](http://www.fwf.ac.at/) 
(grant no. I 760-B17 from 2012-2015 and and I 2508-B29 from 2016-2019),
the [University of Vienna](https://www.univie.ac.at/) (Initiativkolleg I059-N),
the [Australian National University](https://www.anu.edu.au),
[Chan-Zuckerberg Initiative](https://chanzuckerberg.com) (open source software for science grants),
[Simons Foundation](https://www.simonsfoundation.org), [Moore Foundation](https://www.moore.org),
and [Australian Research Council](https://www.arc.gov.au).


[Anisimova et al., 2011]: http://dx.doi.org/10.1093/sysbio/syr041
[Guindon et al., 2010]: http://dx.doi.org/10.1093/sysbio/syq010
[Kalyaanamoorthy et al., 2017]: https://doi.org/10.1038/nmeth.4285
[Ly-Trong et al., 2023]: https://doi.org/10.1093/bioinformatics/btad540
[Minh et al., 2013]: http://dx.doi.org/10.1093/molbev/mst024
[Nguyen et al., 2015]: http://dx.doi.org/10.1093/molbev/msu300
[Shimodaira, 2002]: http://dx.doi.org/10.1080/10635150290069913

