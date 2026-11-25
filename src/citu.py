"""Command-line runner for the Citu compiler front end.

    python3 src/citu.py examples/01_basic_io.citu
    python3 src/citu.py examples/01_basic_io.citu --tokens-only
    python3 src/citu.py examples/01_basic_io.citu --parse-only

Writes its output to build/<program>/. On an error it writes
diagnostics.json instead and exits with status 1.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lexer import CituError, tokenize  # noqa: E402
from parser import parse  # noqa: E402
from semantic import analyze  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def write_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def compile_file(path, out_root=None, tokens_only=False, parse_only=False):
    """Compile one file. Returns (ok, output_folder)."""
    name = os.path.splitext(os.path.basename(path))[0]
    out_dir = os.path.join(out_root or os.path.join(ROOT, "build"), name)
    os.makedirs(out_dir, exist_ok=True)
    for old in ("tokens.json", "ast.json", "symbols.json", "diagnostics.json"):
        if os.path.exists(os.path.join(out_dir, old)):
            os.remove(os.path.join(out_dir, old))

    with open(path, encoding="utf-8") as f:
        source = f.read()
    try:
        tokens = tokenize(source)
        write_json(os.path.join(out_dir, "tokens.json"), {
            "format": "citu-tokens-v1",
            "source": os.path.basename(path),
            "tokens": [t.to_dict() for t in tokens],
        })
        if not tokens_only:
            ast = parse(tokens)
            if not parse_only:
                ast, analyzer = analyze(ast)
                write_json(os.path.join(out_dir, "symbols.json"), {
                    "format": "citu-symbols-v1",
                    "source": os.path.basename(path),
                    "scopes": analyzer.scopes,
                    "symbols": [s.to_dict() for s in analyzer.symbols],
                })
            write_json(os.path.join(out_dir, "ast.json"), {
                "format": "citu-ast-v1",
                "source": os.path.basename(path),
                "root": ast,
            })
    except CituError as e:
        write_json(os.path.join(out_dir, "diagnostics.json"), {
            "status": "error",
            "source": os.path.basename(path),
            "diagnostic": e.to_dict(),
        })
        # Remove partial output so the folder only holds the diagnostics.
        for old in ("tokens.json", "ast.json", "symbols.json"):
            if os.path.exists(os.path.join(out_dir, old)):
                os.remove(os.path.join(out_dir, old))
        return False, out_dir, e
    return True, out_dir, None


def main(argv=None):
    ap = argparse.ArgumentParser(description="Citu compiler (lexer, parser and semantic analyzer)")
    ap.add_argument("file", help="a .citu source file")
    ap.add_argument("--tokens-only", action="store_true", help="run only the lexer")
    ap.add_argument("--parse-only", action="store_true", help="run the lexer and parser, skip semantic checks")
    ap.add_argument("--out", help="output root folder (default: build/)")
    args = ap.parse_args(argv)

    ok, out_dir, err = compile_file(args.file, args.out, args.tokens_only, args.parse_only)
    rel = os.path.relpath(out_dir)
    if not ok:
        print(f"{args.file}:{err.line}:{err.column}: {err.stage} error: {err.message}", file=sys.stderr)
        print(f"wrote {rel}/diagnostics.json", file=sys.stderr)
        return 1
    if args.tokens_only:
        print(f"wrote {rel}/tokens.json")
    elif args.parse_only:
        print(f"wrote {rel}/tokens.json and {rel}/ast.json")
    else:
        print(f"wrote {rel}/tokens.json, {rel}/ast.json and {rel}/symbols.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
