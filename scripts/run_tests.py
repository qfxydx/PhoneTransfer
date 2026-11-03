#!/usr/bin/env python3
"""Run original safety regressions and isolated six-language UI tests, no device."""
import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from phonetransfer.i18n import initialize

# Original regressions assert Chinese diagnostics. Their intent and all 53 tests
# stay unchanged; each i18n test restores this language after its isolated run.
initialize(selection="zh-CN")
suite = unittest.defaultTestLoader.discover(str(Path(__file__).resolve().parents[1] / "tests"))
result = unittest.TextTestRunner(verbosity=2).run(suite)
sys.exit(not result.wasSuccessful())
