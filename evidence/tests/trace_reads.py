# SPDX-FileCopyrightText: 2026 Thomas F. Hagelien
# SPDX-License-Identifier: MIT
"""Run a producer script under an audit hook and print the repository files it opens for reading.

Usage: python3 trace_reads.py ROOT SCRIPT. Run it on a copy of the repository: the
producer writes its outputs there. Reads by child processes are not observed.
"""
import json
import os
import runpy
import sys

root, script = os.path.realpath(sys.argv[1]), sys.argv[2]
seen = set()


def hook(event, args):
    if event != "open" or not isinstance(args[0], (str, bytes, os.PathLike)):
        return
    path = os.path.realpath(os.fsdecode(args[0]))
    mode, flags = args[1], args[2] or 0
    writing = (mode and any(c in mode for c in "wax+")) or flags & (os.O_WRONLY | os.O_RDWR)
    if path.startswith(root + os.sep) and "__pycache__" not in path and not writing and os.path.isfile(path):
        seen.add(os.path.relpath(path, root).replace(os.sep, "/"))


sys.dont_write_bytecode = True
target = os.path.join(root, script)
os.chdir(os.path.dirname(target))
sys.path.insert(0, os.path.dirname(target))
sys.argv = [target]
sys.addaudithook(hook)
with open(os.devnull, "w") as quiet:
    stdout, sys.stdout = sys.stdout, quiet
    try:
        runpy.run_path(target, run_name="__main__")
    except SystemExit as exit_:
        if exit_.code not in (0, None):
            raise
    finally:
        sys.stdout = stdout
print(json.dumps(sorted(seen)))
