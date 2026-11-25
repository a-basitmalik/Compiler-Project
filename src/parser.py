"""Citu recursive-descent parser.

One method per grammar area. Parsing starts at main(), reads a block and
then checks that only EOF is left. Expressions are parsed from the lowest
precedence (||) to the highest (unary ! and -). The result is an AST made
of plain dictionaries so it can be written straight to ast.json.
"""

from lexer import CituError


class ParseError(CituError):
    def __init__(self, message, line, column):
        super().__init__("parser", message, line, column)


TYPE_KEYWORDS = {"INT": "int", "BOOL": "bool"}

BINARY_LEVELS = [
    ("OR", {"OR": "||"}),
    ("AND", {"AND": "&&"}),
    ("EQ", {"EQ": "==", "NE": "!="}),
    ("REL", {"LT": "<", "LE": "<=", "GT": ">", "GE": ">="}),
    ("ADD", {"PLUS": "+", "MINUS": "-"}),
    ("MUL", {"STAR": "*", "SLASH": "/", "PERCENT": "%"}),
]

DESCRIBE = {
    "LPAREN": "'('", "RPAREN": "')'", "LBRACE": "'{'", "RBRACE": "'}'",
    "SEMI": "';'", "IDENT": "a variable name", "EOF": "end of file",
    "MAIN": "'main'", "TAK": "'tak'",
}


def node(kind, tok, **fields):
    n = {"kind": kind, "line": tok.line, "column": tok.column}
    n.update(fields)
    return n


class Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.i = 0
        self.scope_count = 0

    # ---- helpers -------------------------------------------------------
    @property
    def cur(self):
        return self.tokens[self.i]

    def at(self, *kinds):
        return self.cur.kind in kinds

    def take(self):
        tok = self.cur
        if tok.kind != "EOF":
            self.i += 1
        return tok

    def expect(self, kind, context=""):
        if self.cur.kind != kind:
            found = "end of file" if self.cur.kind == "EOF" else repr(self.cur.lexeme)
            where = f" {context}" if context else ""
            raise ParseError(f"Expected {DESCRIBE.get(kind, kind)}{where} but found {found}",
                             self.cur.line, self.cur.column)
        return self.take()

    def new_scope(self):
        self.scope_count += 1
        return f"SC{self.scope_count:03d}"

    # ---- program and statements ---------------------------------------
    def parse_program(self):
        start = self.expect("MAIN", "at the start of the program")
        self.expect("LPAREN", "after 'main'")
        self.expect("RPAREN", "after 'main('")
        body = self.parse_block()
        if not self.at("EOF"):
            raise ParseError(f"Unexpected {self.cur.lexeme!r} after the end of main()",
                             self.cur.line, self.cur.column)
        return node("Program", start, body=body)

    def parse_block(self):
        open_tok = self.expect("LBRACE", "to start a block")
        scope = self.new_scope()
        statements = []
        while not self.at("RBRACE"):
            if self.at("EOF"):
                raise ParseError("Missing '}' to close the block", open_tok.line, open_tok.column)
            statements.append(self.parse_statement())
        self.take()
        return node("Block", open_tok, scope_id=scope, statements=statements)

    def parse_statement(self):
        k = self.cur.kind
        if k in TYPE_KEYWORDS:
            return self.parse_var_decl()
        if k == "INPUT":
            return self.parse_input()
        if k == "PRINT":
            return self.parse_print()
        if k == "AGAR":
            return self.parse_if()
        if k == "JAB":
            return self.parse_while()
        if k == "IDENT":
            return self.parse_update()
        if k == "LBRACE":
            return self.parse_block()
        if k == "MAGAR":
            raise ParseError("'magar' without a matching 'agar'", self.cur.line, self.cur.column)
        found = "end of file" if k == "EOF" else repr(self.cur.lexeme)
        raise ParseError(f"Expected a statement but found {found}", self.cur.line, self.cur.column)

    def parse_var_decl(self):
        t = self.take()
        name = self.expect("IDENT", f"after '{t.lexeme}'")
        self.expect("SEMI", "after the declaration")
        return node("VarDecl", t, datatype=TYPE_KEYWORDS[t.kind], name=name.lexeme)

    def parse_input(self):
        t = self.take()
        self.expect("LPAREN", "after 'input'")
        name = self.expect("IDENT", "inside input()")
        self.expect("RPAREN", "after the variable name")
        self.expect("SEMI", "after input(...)")
        return node("Input", t, name=name.lexeme)

    def parse_print(self):
        t = self.take()
        self.expect("LPAREN", "after 'print'")
        if self.at("STRING_LIT"):
            s = self.take()
            value = node("StringLiteral", s, value=s.value)
        else:
            value = self.parse_expression()
        self.expect("RPAREN", "to close print(...)")
        self.expect("SEMI", "after print(...)")
        return node("Print", t, value=value)

    def parse_if(self):
        t = self.take()
        self.expect("LPAREN", "after 'agar'")
        cond = self.parse_expression()
        self.expect("RPAREN", "after the condition")
        then_block = self.parse_block()
        else_block = None
        if self.at("MAGAR"):
            self.take()
            else_block = self.parse_block()
        return node("If", t, condition=cond, then=then_block, otherwise=else_block)

    def parse_while(self):
        t = self.take()
        self.expect("TAK", "after 'jab' (the loop is 'jab tak')")
        self.expect("LPAREN", "after 'jab tak'")
        cond = self.parse_expression()
        self.expect("RPAREN", "after the condition")
        body = self.parse_block()
        return node("While", t, condition=cond, body=body)

    def parse_update(self):
        name = self.take()
        if not self.at("INC", "DEC"):
            raise ParseError(f"Expected '++' or '--' after {name.lexeme!r}", self.cur.line, self.cur.column)
        op = self.take()
        self.expect("SEMI", f"after '{op.lexeme}'")
        return node("Update", name, name=name.lexeme, op=op.lexeme)

    # ---- expressions ---------------------------------------------------
    def parse_expression(self):
        return self.parse_level(0)

    def parse_level(self, level):
        if level == len(BINARY_LEVELS):
            return self.parse_unary()
        ops = BINARY_LEVELS[level][1]
        left = self.parse_level(level + 1)
        while self.cur.kind in ops:
            op = self.take()
            right = self.parse_level(level + 1)
            left = node("Binary", op, op=ops[op.kind], left=left, right=right)
        return left

    def parse_unary(self):
        if self.at("NOT", "MINUS"):
            op = self.take()
            return node("Unary", op, op=op.lexeme, operand=self.parse_unary())
        return self.parse_primary()

    def parse_primary(self):
        t = self.cur
        if t.kind == "INT_LIT":
            self.take()
            return node("IntLiteral", t, value=t.value)
        if t.kind in ("TRUE", "FALSE"):
            self.take()
            return node("BoolLiteral", t, value=t.value)
        if t.kind == "IDENT":
            self.take()
            return node("Variable", t, name=t.lexeme)
        if t.kind == "LPAREN":
            self.take()
            inner = self.parse_expression()
            self.expect("RPAREN", "to close the bracket")
            return inner
        if t.kind == "STRING_LIT":
            raise ParseError("Text can only be printed on its own, not used in an expression", t.line, t.column)
        found = "end of file" if t.kind == "EOF" else repr(t.lexeme)
        raise ParseError(f"Expected an expression but found {found}", t.line, t.column)


def parse(tokens):
    return Parser(tokens).parse_program()
