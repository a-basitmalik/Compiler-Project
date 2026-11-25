"""Citu lexer.

Reads Citu source one character at a time and produces a list of tokens.
Spaces and comments are skipped, the longest valid operator is always
chosen, and an EOF token is added at the end.
"""


class CituError(Exception):
    """An error found while compiling a Citu program."""

    def __init__(self, stage, message, line, column):
        super().__init__(f"{stage} error at {line}:{column}: {message}")
        self.stage = stage
        self.message = message
        self.line = line
        self.column = column

    def to_dict(self):
        return {
            "stage": self.stage,
            "message": self.message,
            "line": self.line,
            "column": self.column,
        }


class LexerError(CituError):
    def __init__(self, message, line, column):
        super().__init__("lexer", message, line, column)


class Token:
    """One token: its kind, the exact source text, where it starts, and
    its value for literals (int for INT_LIT, decoded text for STRING_LIT)."""

    __slots__ = ("kind", "lexeme", "line", "column", "value")

    def __init__(self, kind, lexeme, line, column, value=None):
        self.kind = kind
        self.lexeme = lexeme
        self.line = line
        self.column = column
        self.value = value

    def to_dict(self):
        return {
            "kind": self.kind,
            "lexeme": self.lexeme,
            "line": self.line,
            "column": self.column,
            "value": self.value,
        }

    def __repr__(self):
        return f"Token({self.kind}, {self.lexeme!r}, {self.line}:{self.column})"


KEYWORDS = {
    "main": "MAIN",
    "agar": "AGAR",
    "magar": "MAGAR",
    "jab": "JAB",
    "tak": "TAK",
    "int": "INT",
    "bool": "BOOL",
    "input": "INPUT",
    "print": "PRINT",
    "true": "TRUE",
    "false": "FALSE",
}

# Two-character operators are tried before one-character ones so the
# longest valid operator always wins ("<=" is never read as "<" "=").
TWO_CHAR = {
    "==": "EQ",
    "!=": "NE",
    "<=": "LE",
    ">=": "GE",
    "&&": "AND",
    "||": "OR",
    "++": "INC",
    "--": "DEC",
}

ONE_CHAR = {
    "+": "PLUS",
    "-": "MINUS",
    "*": "STAR",
    "/": "SLASH",
    "%": "PERCENT",
    "<": "LT",
    ">": "GT",
    "!": "NOT",
    "(": "LPAREN",
    ")": "RPAREN",
    "{": "LBRACE",
    "}": "RBRACE",
    ";": "SEMI",
}

ESCAPES = {"n": "\n", "t": "\t", '"': '"', "\\": "\\"}


class Lexer:
    def __init__(self, source):
        self.src = source
        self.pos = 0
        self.line = 1
        self.col = 1

    def peek(self, offset=0):
        i = self.pos + offset
        return self.src[i] if i < len(self.src) else ""

    def advance(self):
        ch = self.src[self.pos]
        self.pos += 1
        if ch == "\n":
            self.line += 1
            self.col = 1
        else:
            self.col += 1
        return ch

    def skip_space_and_comments(self):
        while self.pos < len(self.src):
            ch = self.peek()
            if ch in " \t\r\n":
                self.advance()
            elif ch == "/" and self.peek(1) == "/":
                while self.pos < len(self.src) and self.peek() != "\n":
                    self.advance()
            elif ch == "/" and self.peek(1) == "*":
                line, col = self.line, self.col
                self.advance()
                self.advance()
                while True:
                    if self.pos >= len(self.src):
                        raise LexerError("Unfinished block comment", line, col)
                    if self.peek() == "*" and self.peek(1) == "/":
                        self.advance()
                        self.advance()
                        break
                    self.advance()
            else:
                break

    def read_string(self, line, col):
        self.advance()  # opening quote
        text = []
        while True:
            if self.pos >= len(self.src) or self.peek() == "\n":
                raise LexerError("Unterminated string literal", line, col)
            ch = self.advance()
            if ch == '"':
                break
            if ch == "\\":
                if self.pos >= len(self.src):
                    raise LexerError("Unterminated string literal", line, col)
                esc = self.advance()
                if esc not in ESCAPES:
                    raise LexerError(f"Unknown escape sequence \\{esc}", self.line, self.col - 2)
                text.append(ESCAPES[esc])
            else:
                text.append(ch)
        lexeme = self.src[self.start:self.pos]
        return Token("STRING_LIT", lexeme, line, col, "".join(text))

    def tokenize(self):
        tokens = []
        while True:
            self.skip_space_and_comments()
            if self.pos >= len(self.src):
                tokens.append(Token("EOF", "", self.line, self.col))
                return tokens
            line, col = self.line, self.col
            self.start = self.pos
            ch = self.peek()

            if ch.isascii() and (ch.isalpha() or ch == "_"):
                while self.peek() and self.peek().isascii() and (self.peek().isalnum() or self.peek() == "_"):
                    self.advance()
                word = self.src[self.start:self.pos]
                kind = KEYWORDS.get(word, "IDENT")
                value = {"TRUE": True, "FALSE": False}.get(kind)
                tokens.append(Token(kind, word, line, col, value))
            elif ch.isascii() and ch.isdigit():
                while self.peek() and self.peek().isascii() and self.peek().isdigit():
                    self.advance()
                if self.peek() and self.peek().isascii() and (self.peek().isalpha() or self.peek() == "_"):
                    raise LexerError("Invalid number: digits followed by letters", line, col)
                text = self.src[self.start:self.pos]
                tokens.append(Token("INT_LIT", text, line, col, int(text)))
            elif ch == '"':
                tokens.append(self.read_string(line, col))
            elif ch + self.peek(1) in TWO_CHAR:
                pair = ch + self.peek(1)
                self.advance()
                self.advance()
                tokens.append(Token(TWO_CHAR[pair], pair, line, col))
            elif ch == "=":
                raise LexerError("Assignment '=' is not allowed in Citu", line, col)
            elif ch in "&|":
                raise LexerError(f"Unexpected character '{ch}' (did you mean '{ch * 2}'?)", line, col)
            elif ch in ONE_CHAR:
                self.advance()
                tokens.append(Token(ONE_CHAR[ch], ch, line, col))
            else:
                raise LexerError(f"Unknown symbol '{ch}'", line, col)


def tokenize(source):
    return Lexer(source).tokenize()
