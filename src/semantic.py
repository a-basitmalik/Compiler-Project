"""Citu semantic analyzer.

Walks the AST made by the parser and checks the rules that grammar alone
cannot check:

  * a variable must be declared before it is used, and only once per block
  * a name declared in an inner block may hide one from an outer block
  * agar / jab tak conditions must be bool
  * ++ and -- work only on int variables
  * arithmetic and comparison operators need int operands,
    && || ! need bool operands, == and != need two values of the same type
  * dividing by the constant 0 is reported as an error

While checking, it builds the symbol table (one entry per declaration,
each with its own symbol ID) and annotates the AST: every expression gets
its datatype and every variable use gets the symbol_id it refers to.
"""

from lexer import CituError


class SemanticError(CituError):
    def __init__(self, message, line, column):
        super().__init__("semantic", message, line, column)


ARITHMETIC = {"+", "-", "*", "/", "%"}
RELATIONAL = {"<", "<=", ">", ">="}
EQUALITY = {"==", "!="}
LOGICAL = {"&&", "||"}


class Symbol:
    __slots__ = ("symbol_id", "name", "datatype", "scope_id", "declared_at", "uses")

    def __init__(self, symbol_id, name, datatype, scope_id, line, column):
        self.symbol_id = symbol_id
        self.name = name
        self.datatype = datatype
        self.scope_id = scope_id
        self.declared_at = {"line": line, "column": column}
        self.uses = 0

    def to_dict(self):
        return {
            "symbol_id": self.symbol_id,
            "name": self.name,
            "datatype": self.datatype,
            "scope_id": self.scope_id,
            "declared_at": self.declared_at,
            "uses": self.uses,
        }


class Analyzer:
    def __init__(self):
        self.symbols = []          # symbol table, in declaration order
        self.scope_stack = []      # list of (scope_id, {name: Symbol})
        self.scopes = []           # every scope with its parent, for symbols.json

    # ---- scopes ----------------------------------------------------------
    def push_scope(self, scope_id):
        parent = self.scope_stack[-1][0] if self.scope_stack else None
        self.scopes.append({"scope_id": scope_id, "parent": parent,
                            "depth": len(self.scope_stack)})
        self.scope_stack.append((scope_id, {}))

    def pop_scope(self):
        self.scope_stack.pop()

    def declare(self, node):
        scope_id, names = self.scope_stack[-1]
        name = node["name"]
        if name in names:
            first = names[name].declared_at
            raise SemanticError(
                f"Variable '{name}' is already declared in this block (line {first['line']})",
                node["line"], node["column"])
        sym = Symbol(f"SY{len(self.symbols) + 1:03d}", name, node["datatype"],
                     scope_id, node["line"], node["column"])
        names[name] = sym
        self.symbols.append(sym)
        return sym

    def lookup(self, name, node):
        for _, names in reversed(self.scope_stack):
            if name in names:
                sym = names[name]
                sym.uses += 1
                return sym
        raise SemanticError(f"Variable '{name}' is used before it is declared",
                            node["line"], node["column"])

    # ---- statements ------------------------------------------------------
    def check_program(self, program):
        self.block(program["body"])
        return program

    def block(self, node):
        self.push_scope(node["scope_id"])
        for stmt in node["statements"]:
            self.statement(stmt)
        self.pop_scope()

    def statement(self, node):
        kind = node["kind"]
        if kind == "VarDecl":
            node["symbol_id"] = self.declare(node).symbol_id
        elif kind == "Input":
            node["symbol_id"] = self.lookup(node["name"], node).symbol_id
        elif kind == "Print":
            if node["value"]["kind"] == "StringLiteral":
                node["value"]["datatype"] = "string"
            else:
                self.expression(node["value"])
        elif kind == "If":
            self.condition(node["condition"], "agar")
            self.block(node["then"])
            if node["otherwise"] is not None:
                self.block(node["otherwise"])
        elif kind == "While":
            self.condition(node["condition"], "jab tak")
            self.block(node["body"])
        elif kind == "Update":
            sym = self.lookup(node["name"], node)
            if sym.datatype != "int":
                raise SemanticError(
                    f"'{node['op']}' needs an int variable, but '{sym.name}' is {sym.datatype}",
                    node["line"], node["column"])
            node["symbol_id"] = sym.symbol_id
        elif kind == "Block":
            self.block(node)
        else:  # pragma: no cover - the parser never produces anything else
            raise SemanticError(f"Unknown statement '{kind}'", node["line"], node["column"])

    def condition(self, expr, word):
        t = self.expression(expr)
        if t != "bool":
            raise SemanticError(f"The '{word}' condition must be bool, not {t}",
                                expr["line"], expr["column"])

    # ---- expressions -----------------------------------------------------
    def expression(self, node):
        node["datatype"] = self._type_of(node)
        return node["datatype"]

    def _type_of(self, node):
        kind = node["kind"]
        if kind == "IntLiteral":
            return "int"
        if kind == "BoolLiteral":
            return "bool"
        if kind == "Variable":
            sym = self.lookup(node["name"], node)
            node["symbol_id"] = sym.symbol_id
            return sym.datatype
        if kind == "Unary":
            t = self.expression(node["operand"])
            want = "bool" if node["op"] == "!" else "int"
            if t != want:
                raise SemanticError(f"Unary '{node['op']}' needs a {want} value, not {t}",
                                    node["line"], node["column"])
            return want
        if kind == "Binary":
            op = node["op"]
            lt = self.expression(node["left"])
            rt = self.expression(node["right"])
            if op in ARITHMETIC or op in RELATIONAL:
                if lt != "int" or rt != "int":
                    raise SemanticError(f"'{op}' needs two int values, not {lt} and {rt}",
                                        node["line"], node["column"])
                if op in ("/", "%") and node["right"]["kind"] == "IntLiteral" and node["right"]["value"] == 0:
                    raise SemanticError("Division by zero", node["right"]["line"], node["right"]["column"])
                return "int" if op in ARITHMETIC else "bool"
            if op in LOGICAL:
                if lt != "bool" or rt != "bool":
                    raise SemanticError(f"'{op}' needs two bool values, not {lt} and {rt}",
                                        node["line"], node["column"])
                return "bool"
            if op in EQUALITY:
                if lt != rt:
                    raise SemanticError(f"'{op}' cannot compare {lt} with {rt}",
                                        node["line"], node["column"])
                return "bool"
        raise SemanticError(f"Unknown expression '{kind}'", node["line"], node["column"])  # pragma: no cover


def analyze(program):
    """Check `program` (annotating it in place). Returns (program, analyzer)."""
    a = Analyzer()
    a.check_program(program)
    return program, a
