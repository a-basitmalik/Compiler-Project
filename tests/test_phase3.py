"""Phase 3 tests: semantic analyzer, symbol table and CLI output."""

import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from lexer import tokenize  # noqa: E402
from parser import parse  # noqa: E402
from semantic import SemanticError, analyze  # noqa: E402

EXAMPLES = os.path.join(ROOT, "examples")
ERRORS = os.path.join(ROOT, "tests", "semantic_errors")
CLI = os.path.join(ROOT, "src", "citu.py")


def check(src):
    """Run the whole front end; returns (annotated AST, analyzer)."""
    return analyze(parse(tokenize(src)))


def check_body(body):
    return check("main() {\n" + body + "\n}")


def error_of(body):
    """Return the SemanticError raised for `body`; fail if none is raised."""
    try:
        check_body(body)
    except SemanticError as e:
        return e
    raise AssertionError("expected a SemanticError")


class DeclarationTests(unittest.TestCase):
    def test_symbols_get_ids_types_and_scopes(self):
        _, a = check_body("int age; bool ok;")
        self.assertEqual([(s.symbol_id, s.name, s.datatype, s.scope_id) for s in a.symbols],
                         [("SY001", "age", "int", "SC001"), ("SY002", "ok", "bool", "SC001")])

    def test_declared_at_position(self):
        _, a = check_body("    int age;")
        self.assertEqual(a.symbols[0].declared_at, {"line": 2, "column": 5})

    def test_use_before_declaration(self):
        e = error_of("print(total); int total;")
        self.assertIn("before it is declared", e.message)
        self.assertEqual(e.stage, "semantic")

    def test_input_needs_declared_variable(self):
        self.assertIn("'x'", error_of("input(x);").message)

    def test_redeclaration_in_same_block(self):
        e = error_of("int a;\nbool a;")
        self.assertIn("already declared", e.message)
        self.assertEqual((e.line, e.column), (3, 1))

    def test_shadowing_in_inner_block_allowed(self):
        _, a = check_body("int a; { bool a; }")
        self.assertEqual([(s.symbol_id, s.datatype, s.scope_id) for s in a.symbols],
                         [("SY001", "int", "SC001"), ("SY002", "bool", "SC002")])

    def test_inner_variable_not_visible_outside(self):
        self.assertIn("'inner'", error_of("{ int inner; } print(inner);").message)

    def test_sibling_blocks_reuse_name(self):
        _, a = check_body("{ int t; } { bool t; }")
        self.assertEqual([s.scope_id for s in a.symbols], ["SC002", "SC003"])

    def test_variable_use_links_to_nearest_symbol(self):
        ast, _ = check_body("int a; { bool a; print(a); } print(a);")
        stmts = ast["body"]["statements"]
        self.assertEqual(stmts[1]["statements"][1]["value"]["symbol_id"], "SY002")
        self.assertEqual(stmts[2]["value"]["symbol_id"], "SY001")

    def test_use_counts(self):
        _, a = check_body("int n; input(n); print(n + n); n--;")
        self.assertEqual(a.symbols[0].uses, 4)

    def test_scope_tree(self):
        _, a = check_body("{ { } } agar (true) { }")
        self.assertEqual([(s["scope_id"], s["parent"], s["depth"]) for s in a.scopes],
                         [("SC001", None, 0), ("SC002", "SC001", 1), ("SC003", "SC002", 2), ("SC004", "SC001", 1)])


class TypeTests(unittest.TestCase):
    def test_expression_types_annotated(self):
        ast, _ = check_body("int a; print(a + 2 > 3);")
        e = ast["body"]["statements"][1]["value"]
        self.assertEqual((e["datatype"], e["left"]["datatype"], e["left"]["left"]["datatype"]), ("bool", "int", "int"))

    def test_string_print_is_string(self):
        ast, _ = check_body('print("hi");')
        self.assertEqual(ast["body"]["statements"][0]["value"]["datatype"], "string")

    def test_if_condition_must_be_bool(self):
        self.assertIn("'agar' condition must be bool", error_of("int n; agar (n) { }").message)

    def test_while_condition_must_be_bool(self):
        self.assertIn("'jab tak' condition must be bool", error_of("jab tak (1 + 1) { }").message)

    def test_update_needs_int(self):
        e = error_of("bool f; f++;")
        self.assertIn("needs an int variable", e.message)

    def test_arithmetic_needs_ints(self):
        self.assertIn("two int values", error_of("bool b; print(b * 2);").message)

    def test_relational_needs_ints(self):
        self.assertIn("two int values", error_of("print(true < 1);").message)

    def test_logical_needs_bools(self):
        self.assertIn("two bool values", error_of("int a; print(a && true);").message)

    def test_equality_needs_same_type(self):
        self.assertIn("cannot compare int with bool", error_of("print(1 == true);").message)

    def test_equality_on_bools_allowed(self):
        ast, _ = check_body("bool p; print(p == true);")
        self.assertEqual(ast["body"]["statements"][1]["value"]["datatype"], "bool")

    def test_unary_operators(self):
        self.assertIn("Unary '!'", error_of("print(!5);").message)
        self.assertIn("Unary '-'", error_of("print(-false);").message)
        ast, _ = check_body("print(-(3) > 0 && !false);")
        self.assertEqual(ast["body"]["statements"][0]["value"]["datatype"], "bool")

    def test_division_by_constant_zero(self):
        e = error_of("int a;\nprint(a / 0);")
        self.assertEqual((e.message, e.line, e.column), ("Division by zero", 3, 11))
        self.assertEqual(error_of("print(7 % 0);").message, "Division by zero")

    def test_error_position_points_at_operator(self):
        e = error_of("int a; bool b;\nprint(a + b);")
        self.assertEqual((e.line, e.column), (3, 9))


class ProgramTests(unittest.TestCase):
    def test_example_programs_pass(self):
        expected = {"01_basic_io.citu": 2, "02_eligibility.citu": 2,
                    "03_even_odd_countdown.citu": 1, "04_scopes.citu": 3}
        for name, count in expected.items():
            with self.subTest(name=name):
                with open(os.path.join(EXAMPLES, name), encoding="utf-8") as f:
                    _, a = check(f.read())
                self.assertEqual(len(a.symbols), count)

    def test_error_programs_fail(self):
        files = sorted(f for f in os.listdir(ERRORS) if f.endswith(".citu"))
        self.assertEqual(len(files), 6)
        for name in files:
            with self.subTest(name=name):
                with open(os.path.join(ERRORS, name), encoding="utf-8") as f:
                    with self.assertRaises(SemanticError):
                        check(f.read())

    def test_cli_writes_symbols_json(self):
        out = tempfile.mkdtemp()
        proc = subprocess.run([sys.executable, CLI, os.path.join(EXAMPLES, "04_scopes.citu"), "--out", out],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        with open(os.path.join(out, "04_scopes", "symbols.json"), encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["format"], "citu-symbols-v1")
        self.assertEqual([s["datatype"] for s in data["symbols"]], ["int", "bool", "bool"])
        with open(os.path.join(out, "04_scopes", "ast.json"), encoding="utf-8") as f:
            self.assertIn('"symbol_id": "SY003"', f.read())

    def test_cli_semantic_error_diagnostics(self):
        out = tempfile.mkdtemp()
        proc = subprocess.run([sys.executable, CLI, os.path.join(ERRORS, "bool_update.citu"), "--out", out],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 1)
        folder = os.path.join(out, "bool_update")
        with open(os.path.join(folder, "diagnostics.json"), encoding="utf-8") as f:
            diag = json.load(f)["diagnostic"]
        self.assertEqual((diag["stage"], diag["line"], diag["column"]), ("semantic", 4, 5))
        self.assertEqual(sorted(os.listdir(folder)), ["diagnostics.json"])

    def test_cli_parse_only_skips_semantics(self):
        out = tempfile.mkdtemp()
        proc = subprocess.run([sys.executable, CLI, os.path.join(ERRORS, "bool_update.citu"), "--out", out,
                               "--parse-only"], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(sorted(os.listdir(os.path.join(out, "bool_update"))), ["ast.json", "tokens.json"])


if __name__ == "__main__":
    unittest.main()
