#!/usr/bin/env python3
"""Check core structure against 4631f48, ignoring only localized messages.

The expected hashes come from parsing the baseline sources. Human messages and
tr() wrappers are normalized; commands, branches, paths, calls, imports (except
tr), cleanup and protocol tokens must retain their exact AST structure.
"""
import ast
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class NormalizeMessages(ast.NodeTransformer):
    def visit_ImportFrom(self, node):
        return None if node.module == "phonetransfer.i18n" else node

    def visit_Call(self, node):
        if isinstance(node.func, ast.Name) and node.func.id == "tr":
            return ast.Constant(value="<message>")
        return self.generic_visit(node)

    def visit_JoinedStr(self, node):
        if any(isinstance(v, ast.Constant) and isinstance(v.value, str)
               and re.search("[\u4e00-\u9fff]", v.value) for v in node.values):
            return ast.Constant(value="<message>")
        return self.generic_visit(node)

    def visit_Constant(self, node):
        if isinstance(node.value, str) and re.search("[\u4e00-\u9fff]", node.value):
            return ast.Constant(value="<message>")
        return node


def verify():
    expected = json.loads((ROOT / "tests/fixtures/i18n-baseline-core-ast.json").read_text())
    for file, digest in expected.items():
        source = (ROOT / file).read_text(encoding="utf-8")
        normalized = ast.dump(NormalizeMessages().visit(ast.parse(source)), include_attributes=False)
        actual = hashlib.sha256(normalized.encode()).hexdigest()
        if actual != digest:
            raise AssertionError(f"Non-message core structure changed: {file}")
    return len(expected)


if __name__ == "__main__":
    print(f"PASS: {verify()} core files match baseline 4631f48 after message normalization")
