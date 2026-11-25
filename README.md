# Citu Compiler Project

Abdul Basit · BSCS23023

Citu is a small teaching language with `int` and `bool` variables, `input`/`print`,
`agar`/`magar` (if/else) and `jab tak` (while) loops. The language design is in
[doc/BSCS23023_Compiler_Project.pdf](doc/BSCS23023_Compiler_Project.pdf).

## Phase 2 - Lexer + Parser

Requires Python 3 only (no outside libraries).

```
python3 src/citu.py examples/01_basic_io.citu
python3 src/citu.py examples/02_eligibility.citu
python3 src/citu.py examples/03_even_odd_countdown.citu
python3 src/citu.py examples/01_basic_io.citu --tokens-only
python3 -m unittest discover -s tests -v
```

Output goes to `build/<program>/`: `tokens.json` (`citu-tokens-v1`) and `ast.json`
(`citu-ast-v1`). On an error, `diagnostics.json` records the stage, message, line and column.

| File | Purpose |
|------|---------|
| `src/lexer.py` | Converts source characters to tokens and reports lexical errors |
| `src/parser.py` | Checks grammar and creates the AST |
| `src/citu.py` | Command-line runner that writes JSON output |
| `examples/` | The three Phase 1 example programs |
| `tests/test_phase2.py` | Lexer, parser and CLI tests |

## Phase 3 - Semantic Analyzer

`src/semantic.py` walks the AST and checks the rules the grammar cannot: variables are
declared before use and only once per block, inner blocks may hide outer names,
`agar` / `jab tak` conditions are `bool`, `++` / `--` need an `int`, operators get operands of
the right type, and dividing by the constant 0 is an error.

```
python3 src/citu.py examples/04_scopes.citu
python3 src/citu.py tests/semantic_errors/bool_update.citu
python3 src/citu.py examples/02_eligibility.citu --parse-only
```

A successful run now also writes `symbols.json` (`citu-symbols-v1`), and `ast.json` carries
each expression's `datatype` and each variable's `symbol_id`.

| File | Purpose |
|------|---------|
| `src/semantic.py` | Scope stack, symbol table and type checks |
| `examples/04_scopes.citu` | Nested blocks and a hidden (shadowed) variable |
| `tests/semantic_errors/` | Six programs that must fail the semantic stage |
| `tests/test_phase3.py` | Semantic analyzer, symbol table and CLI tests |
