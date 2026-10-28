#!/usr/bin/env python3
"""Thin Claude Code hook entry point; all logic lives in tools/weave_workflow/hooks.py."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.weave_workflow.hooks import main  # noqa: E402

sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else ""))
