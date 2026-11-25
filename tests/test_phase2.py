"""Phase 2 tests: lexer, parser and command-line runner."""

import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from lexer import LexerError, tokenize  # noqa: E402
from parser import ParseError, parse  # noqa: E402

EXAMPLES = os.path.join(ROOT, "examples")
CLI = os.path.join(ROOT, "src", "citu.py")


def kinds(src):
    return [t.kind for t in tokenize(src)]


def read_example(name):
    with open(os.path.join(EXAMPLES, name), encoding="utf-8") as f:
        return f.read()


def body(src):
    return parse(tokenize(src))["body"]["statements"]


def expr(text):
    """Parse an expression by placing it inside print(...)."""
    return body(f"main() {{ print({text}); }}")[0]["value"]


class LexerTests(unittest.TestCase):
    def test_keywords(self):
        self.assertEqual(
            kinds("main agar magar jab tak int bool input print true false"),
            ["MAIN", "AGAR", "MAGAR", "JAB", "TAK", "INT", "BOOL", "INPUT", "PRINT", "TRUE", "FALSE", "EOF"])

    def test_identifiers(self):
        toks = tokenize("age _tmp x2 main_value")
        self.assertEqual([t.kind for t in toks[:-1]], ["IDENT"] * 4)
        self.assertEqual(toks[3].lexeme, "main_value")
        self.assertEqual(kinds("integer printer"), ["IDENT", "IDENT", "EOF"])

    def test_integer_literal_value(self):
        t = tokenize("2026")[0]
        self.assertEqual((t.kind, t.value), ("INT_LIT", 2026))

    def test_boolean_literal_values(self):
        toks = tokenize("true false")
        self.assertEqual([t.value for t in toks[:2]], [True, False])

    def test_string_with_escapes(self):
        t = tokenize(r'"a\nb\t\"c\"\\"')[0]
        self.assertEqual(t.kind, "STRING_LIT")
        self.assertEqual(t.value, 'a\nb\t"c"\\')

    def test_operators_longest_match(self):
        self.assertEqual(
            kinds("+ - * / % == != < <= > >= && || ! ++ --"),
            ["PLUS", "MINUS", "STAR", "SLASH", "PERCENT", "EQ", "NE", "LT", "LE", "GT", "GE",
             "AND", "OR", "NOT", "INC", "DEC", "EOF"])

    def test_symbols(self):
        self.assertEqual(kinds("( ) { } ;"), ["LPAREN", "RPAREN", "LBRACE", "RBRACE", "SEMI", "EOF"])

    def test_comments_and_spaces_skipped(self):
        src = "int // line comment\n /* block\n comment */ age ;\t\n"
        self.assertEqual(kinds(src), ["INT", "IDENT", "SEMI", "EOF"])

    def test_token_positions(self):
        toks = tokenize("main()\n{\n    int age;\n}")
        age = toks[5]
        self.assertEqual((age.lexeme, age.line, age.column), ("age", 3, 9))

    def test_eof_token_added(self):
        toks = tokenize("")
        self.assertEqual(len(toks), 1)
        self.assertEqual(toks[0].kind, "EOF")

    def test_assignment_rejected(self):
        with self.assertRaises(LexerError) as cm:
            tokenize("x = 5;")
        self.assertEqual((cm.exception.line, cm.exception.column), (1, 3))

    def test_unknown_symbol_rejected(self):
        with self.assertRaises(LexerError):
            tokenize("int a#;")

    def test_unterminated_string_rejected(self):
        with self.assertRaises(LexerError):
            tokenize('print("hello);')

    def test_unfinished_comment_rejected(self):
        with self.assertRaises(LexerError):
            tokenize("int a; /* never closed")

    def test_example_programs_tokenize(self):
        for name in sorted(os.listdir(EXAMPLES)):
            with self.subTest(name=name):
                self.assertEqual(tokenize(read_example(name))[-1].kind, "EOF")


class ParserTests(unittest.TestCase):
    def test_minimal_program(self):
        ast = parse(tokenize("main() { }"))
        self.assertEqual(ast["kind"], "Program")
        self.assertEqual(ast["body"]["statements"], [])

    def test_var_decls(self):
        stmts = body("main() { int a; bool b; }")
        self.assertEqual([(s["datatype"], s["name"]) for s in stmts], [("int", "a"), ("bool", "b")])

    def test_input_and_print(self):
        stmts = body('main() { int a; input(a); print("hi"); print(a); }')
        self.assertEqual([s["kind"] for s in stmts], ["VarDecl", "Input", "Print", "Print"])
        self.assertEqual(stmts[2]["value"]["kind"], "StringLiteral")
        self.assertEqual(stmts[3]["value"]["kind"], "Variable")

    def test_if_else(self):
        s = body("main() { agar (true) { } magar { } }")[0]
        self.assertEqual(s["kind"], "If")
        self.assertIsNotNone(s["otherwise"])

    def test_if_without_else(self):
        s = body("main() { agar (true) { } }")[0]
        self.assertIsNone(s["otherwise"])

    def test_while_loop(self):
        s = body("main() { int n; jab tak (n > 0) { n--; } }")[1]
        self.assertEqual(s["kind"], "While")
        update = s["body"]["statements"][0]
        self.assertEqual((update["kind"], update["op"]), ("Update", "--"))

    def test_update_statements(self):
        stmts = body("main() { int n; n++; n--; }")
        self.assertEqual([s["op"] for s in stmts[1:]], ["++", "--"])

    def test_nested_blocks_get_scope_ids(self):
        ast = parse(tokenize("main() { { { } } agar (true) { } }"))
        outer = ast["body"]
        inner = outer["statements"][0]
        self.assertEqual(outer["scope_id"], "SC001")
        self.assertEqual(inner["scope_id"], "SC002")
        self.assertEqual(inner["statements"][0]["scope_id"], "SC003")
        self.assertEqual(outer["statements"][1]["then"]["scope_id"], "SC004")

    def test_precedence_mul_over_add(self):
        e = expr("age + 2 * 3")
        self.assertEqual(e["op"], "+")
        self.assertEqual(e["right"]["op"], "*")

    def test_precedence_logical(self):
        e = expr("a || b && c == d")
        self.assertEqual(e["op"], "||")
        self.assertEqual(e["right"]["op"], "&&")
        self.assertEqual(e["right"]["right"]["op"], "==")

    def test_left_associative(self):
        e = expr("10 - 4 - 3")
        self.assertEqual(e["op"], "-")
        self.assertEqual(e["left"]["op"], "-")
        self.assertEqual(e["right"]["value"], 3)

    def test_unary_and_brackets(self):
        e = expr("!(a > -1)")
        self.assertEqual((e["kind"], e["op"]), ("Unary", "!"))
        self.assertEqual(e["operand"]["op"], ">")
        self.assertEqual(e["operand"]["right"]["kind"], "Unary")

    def test_missing_semicolon(self):
        with self.assertRaises(ParseError) as cm:
            parse(tokenize("main() { int a }"))
        self.assertIn("';'", cm.exception.message)

    def test_missing_closing_brace(self):
        with self.assertRaises(ParseError):
            parse(tokenize("main() { int a;"))

    def test_tokens_after_program(self):
        with self.assertRaises(ParseError):
            parse(tokenize("main() { } print(1);"))

    def test_jab_without_tak(self):
        with self.assertRaises(ParseError):
            parse(tokenize("main() { jab (true) { } }"))

    def test_example_programs_parse(self):
        expected = {"01_basic_io.citu": 8, "02_eligibility.citu": 5, "03_even_odd_countdown.citu": 4}
        for name, count in expected.items():
            with self.subTest(name=name):
                ast = parse(tokenize(read_example(name)))
                self.assertEqual(len(ast["body"]["statements"]), count)


class CliTests(unittest.TestCase):
    def run_cli(self, path, *extra):
        out = tempfile.mkdtemp()
        proc = subprocess.run([sys.executable, CLI, path, "--out", out, *extra],
                              capture_output=True, text=True)
        name = os.path.splitext(os.path.basename(path))[0]
        return proc, os.path.join(out, name)

    def test_cli_writes_tokens_and_ast(self):
        proc, folder = self.run_cli(os.path.join(EXAMPLES, "02_eligibility.citu"))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        with open(os.path.join(folder, "tokens.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f)["format"], "citu-tokens-v1")
        with open(os.path.join(folder, "ast.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f)["format"], "citu-ast-v1")

    def test_cli_error_writes_diagnostics(self):
        with tempfile.NamedTemporaryFile("w", suffix=".citu", delete=False) as f:
            f.write("main() {\n  int a;\n  a = 3;\n}\n")
        proc, folder = self.run_cli(f.name)
        self.assertEqual(proc.returncode, 1)
        with open(os.path.join(folder, "diagnostics.json"), encoding="utf-8") as fh:
            diag = json.load(fh)
        self.assertEqual(diag["status"], "error")
        self.assertEqual(diag["diagnostic"]["stage"], "lexer")
        self.assertEqual((diag["diagnostic"]["line"], diag["diagnostic"]["column"]), (3, 5))


if __name__ == "__main__":
    unittest.main()
