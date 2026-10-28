#!/usr/bin/env python3
"""Compile the scalar Fitch oracle with the configured production C toolchain."""
import argparse
import os
from pathlib import Path
import shlex
import subprocess
import tempfile


def main():
    source_dir = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-dir", type=Path, default=source_dir.parent / "build")
    args = parser.parse_args()
    build = args.build_dir.resolve()
    cache = (build / "CMakeCache.txt").read_text()
    compiler = next(
        line.split("=", 1)[1]
        for line in cache.splitlines()
        if line.startswith("CMAKE_C_COMPILER:")
    )
    settings = {}
    for line in (build / "pll/CMakeFiles/pll.dir/flags.make").read_text().splitlines():
        if " = " in line:
            key, value = line.split(" = ", 1)
            settings[key] = shlex.split(value)
    base = sum((settings[key] for key in ("C_DEFINES", "C_INCLUDES", "C_FLAGS")), [])
    if "-D__SSE3" not in base or any(
        flag == "-D__AVX" or "IQTREE_DIKARYA_HYBRID_PARSIMONY" in flag
        for flag in base
    ):
        raise RuntimeError("Use an SSE-configured production build; per-file trial flags are supplied here.")

    compile_env = os.environ.copy()
    cc = Path(compiler).resolve()
    if cc.parent.name == "bin" and cc.parent.parent.name.startswith("llvm-"):
        library_dirs = [cc.parent.parent / "lib", cc.parents[3] / "lib/x86_64-linux-gnu"]
        paths = [str(path) for path in library_dirs if path.is_dir()]
        if compile_env.get("LD_LIBRARY_PATH"):
            paths.append(compile_env["LD_LIBRARY_PATH"])
        compile_env["LD_LIBRARY_PATH"] = ":".join(paths)
    run_env = os.environ.copy()
    run_env.pop("LD_LIBRARY_PATH", None)
    fixture = Path(__file__).with_name("parsimony_oracle.c").resolve()
    variants = {
        "sse": [],
        "avx": ["-mavx", "-D__AVX"],
        "hybrid": ["-mavx2", "-DIQTREE_DIKARYA_HYBRID_PARSIMONY"],
    }
    expected = None
    with tempfile.TemporaryDirectory(prefix="iqtree-parsimony-oracle-") as directory:
        for name, flags in variants.items():
            executable = Path(directory) / name
            subprocess.run(
                [compiler, *base, "-mpopcnt", *flags, "-Wl,--gc-sections",
                 "-o", str(executable), str(fixture), "-lm"],
                env=compile_env, check=True,
            )
            output = subprocess.check_output([str(executable)], env=run_env, text=True)
            if "PASS cases3800 bound_decisions986179 hash0e761a6a5fab47be" not in output:
                raise RuntimeError(f"Unexpected {name} oracle result: {output}")
            if expected is not None and output != expected:
                raise RuntimeError(f"{name} differs from SSE struct layout or oracle digest")
            expected = output
            print(f"{name}: {output.strip()}", flush=True)
    print("PASS: SSE, AVX, and hybrid oracle results are byte-identical")


if __name__ == "__main__":
    main()
