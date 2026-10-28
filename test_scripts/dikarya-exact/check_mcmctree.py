#!/usr/bin/env python3
"""Compare MCMCTree derivative exports from reference and candidate binaries.

Exercises the consumer of the optional G_matrix, including shared partition
storage. Requires no production data or dependencies beyond Python and IQ-TREE.
"""

import argparse
import hashlib
import json
from pathlib import Path
import random
import subprocess
import tempfile


def make_inputs(directory):
    directory.mkdir(parents=True, exist_ok=True)
    rng = random.Random(812739)
    ancestor = "".join(rng.choice("ACGT") for _ in range(240))
    sequences = []
    for index in range(8):
        sequence = "".join(
            rng.choice([base for base in "ACGT" if base != state])
            if rng.random() < 0.08 + 0.015 * index else state
            for state in ancestor
        )
        sequences.append(f">t{index + 1}\n{sequence}\n")
    (directory / "alignment.fasta").write_text("".join(sequences))
    (directory / "rooted.nwk").write_text(
        "(((t1:0.1,t2:0.1):0.1,(t3:0.1,t4:0.1):0.1):0.1,"
        "((t5:0.1,t6:0.1):0.1,(t7:0.1,t8:0.1):0.1):0.1);\n"
    )
    (directory / "partitions.nex").write_text(
        "#nexus\nbegin sets;\ncharset first = 1-120;\n"
        "charset second = 121-240;\n"
        "charpartition models = GTR+G4:first, HKY+G4:second;\nend;\n"
    )


def run(executable, inputs, output, partition_flag):
    output.mkdir(parents=True, exist_ok=True)
    prefix = output / "run"
    command = [
        str(executable), "-s", str(inputs / "alignment.fasta"),
        "-te", str(inputs / "rooted.nwk"), "--dating", "mcmctree",
        "-nt", "1", "-seed", "12345", "-m", "GTR+G4",
        "-pre", str(prefix), "-redo",
    ]
    if partition_flag:
        command += [partition_flag, str(inputs / "partitions.nex")]
    (output / "command.json").write_text(json.dumps(command, indent=2) + "\n")
    with (output / "stdout.txt").open("wb") as stdout:
        subprocess.run(command, stdout=stdout, stderr=subprocess.STDOUT, check=True)
    return prefix


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--workdir", type=Path)
    args = parser.parse_args()
    directory = (args.workdir or Path(tempfile.mkdtemp(prefix="iqtree-mcmctree-"))).resolve()
    inputs = directory / "input"
    make_inputs(inputs)
    results = []
    for case, flag in (("single", None), ("proportional", "-p"),
                       ("equal", "-q"), ("unlinked", "-Q")):
        prefixes = [
            run(executable.resolve(), inputs, directory / label / case, flag)
            for label, executable in (("reference", args.reference), ("candidate", args.candidate))
        ]
        hashes = {}
        for suffix in (".mcmctree.hessian", ".dummy.phy", ".rooted.nwk", ".treefile", ".mcmctree.ctl"):
            data = [Path(str(prefix) + suffix).read_bytes() for prefix in prefixes]
            if suffix == ".mcmctree.ctl":
                # Control files embed their respective output paths. No numerical
                # result is normalized: the complete Hessian is compared as bytes.
                data = [value.replace(str(prefix).encode(), b"RUN_PREFIX")
                        for prefix, value in zip(prefixes, data)]
            if not data[0] or data[0] != data[1]:
                raise AssertionError(f"{case}{suffix}: empty or different output; inspect {directory}")
            hashes[suffix] = hashlib.sha256(data[0]).hexdigest()
        results.append({"case": case, "sha256": hashes})
        print(f"PASS {case}: derivative export and tree files match")
    (directory / "results.json").write_text(json.dumps(results, indent=2) + "\n")
    print(f"Results: {directory / 'results.json'}")


if __name__ == "__main__":
    main()
