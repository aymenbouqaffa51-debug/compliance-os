"""Safe expression evaluation for control applicability conditions.

Why this module exists
----------------------
Framework YAML files contain lines like:

    applicability: conditional
    condition: "client.handles_cin or client.handles_sensitive_data"

Evaluating that with Python's `eval()` is an injection surface: a malicious or
merely careless framework file could reach `__builtins__`, dunder attributes, or
arbitrary calls. Framework files are data, not code, and this module treats
them that way.

What is allowed
---------------
Only a tiny, closed grammar:

  BoolOp        and / or
  UnaryOp       not
  Compare       == != < <= > >= in / not in
  Constant      str, int, float, bool, None
  Name          a client field, or one of the whitelisted helpers
  Attribute     <name>.<field> restricted to the `client` object
  Call          only whitelisted helper functions, positional args only

Everything else -- comprehensions, lambdas, subscripts, dunder attributes,
attribute access on anything but `client`, starargs, f-strings -- raises
ConditionError.

Design note: an unknown attribute on `client` resolves to False rather than
raising, so a typo in a framework file degrades to 'control not applicable'
instead of crashing an assessment. But a *malformed expression* always raises,
because silently swallowing a syntax error could hide a control the client
should have been assessed against.
"""

from __future__ import annotations

import ast
from typing import Any, Dict


class ConditionError(Exception):
    """Raised when a condition cannot be safely parsed or evaluated."""


# Helpers callable from a condition. Nothing else is reachable.
ALLOWED_CALLS = {
    "len": len,
    "int": int,
    "bool": bool,
    "str": str,
    "any": any,
    "all": all,
    "min": min,
    "max": max,
    "abs": abs,
}

_ALLOWED_NODES = (
    ast.Expression,
    ast.BoolOp,
    ast.And,
    ast.Or,
    ast.UnaryOp,
    ast.Not,
    ast.USub,  # for negative numeric constants
    ast.Compare,
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
    ast.In,
    ast.NotIn,
    ast.Constant,
    ast.Name,
    ast.Load,
    ast.Attribute,
    ast.Call,
    ast.Tuple,  # literal tuples only, for `x in ('a', 'b')`
)


def _check_constant(node: ast.Constant) -> None:
    if not isinstance(node.value, (str, int, float, bool, type(None))):
        raise ConditionError(
            "constant of type %s is not allowed in a condition" % type(node.value).__name__
        )


class _Validator(ast.NodeVisitor):
    """Reject any node or shape outside the allowed grammar."""

    def __init__(self) -> None:
        self.referenced_client = False
        self.referenced_names: set[str] = set()

    def generic_visit(self, node: ast.AST) -> None:  # pragma: no cover - defensive
        if not isinstance(node, _ALLOWED_NODES):
            raise ConditionError(
                "disallowed syntax in condition: %s" % type(node).__name__
            )
        super().generic_visit(node)

    def visit_Expression(self, node: ast.Expression) -> None:
        self.visit(node.body)

    def visit_Constant(self, node: ast.Constant) -> None:
        _check_constant(node)

    def visit_Name(self, node: ast.Name) -> None:
        name = node.id
        if name.startswith("__") or name.endswith("__"):
            raise ConditionError("dunder name %r is not allowed" % name)
        if name in ALLOWED_CALLS:
            # Helpers are only meaningful when called. Reaching here means the
            # expression used e.g. a bare `len`, which leaks a function object.
            # visit_Call validates its own func without recursing into it.
            raise ConditionError(
                "helper %r may only be used as a call, e.g. %s(...)" % (name, name)
            )
        # A bare client field name (or `client`) is resolved at eval time.
        self.referenced_names.add(name)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        attr = node.attr
        if attr.startswith("__"):
            raise ConditionError("dunder attribute %r is not allowed" % attr)
        # Only `client.<field>` is reachable.
        if not (isinstance(node.value, ast.Name) and node.value.id == "client"):
            raise ConditionError(
                "attribute access is only allowed on `client`, got %s"
                % type(node.value).__name__
            )
        self.referenced_client = True

    def visit_Call(self, node: ast.Call) -> None:
        if not isinstance(node.func, ast.Name):
            raise ConditionError("only whitelisted helper functions may be called")
        if node.func.id not in ALLOWED_CALLS:
            raise ConditionError("call to %r is not allowed" % node.func.id)
        if node.keywords:
            raise ConditionError("keyword arguments are not allowed in conditions")
        self.referenced_names.add(node.func.id)
        # Note: node.func is deliberately NOT visited, so the ALLOWED_CALLS
        # guard in visit_Name does not fire on the callee itself.
        for arg in node.args:
            self.visit(arg)

    def visit_Tuple(self, node: ast.Tuple) -> None:
        """Literal tuples are allowed only as constant containers."""
        if getattr(node, "ctx", None) is not None and not isinstance(node.ctx, ast.Load):
            raise ConditionError("tuple unpacking is not allowed in conditions")
        for elt in node.elts:
            if not isinstance(elt, ast.Constant):
                raise ConditionError(
                    "tuples in conditions may only contain literal values"
                )
            _check_constant(elt)

    def visit_BoolOp(self, node: ast.BoolOp) -> None:
        for value in node.values:
            self.visit(value)

    def visit_UnaryOp(self, node: ast.UnaryOp) -> None:
        self.visit(node.operand)

    def visit_Compare(self, node: ast.Compare) -> None:
        self.visit(node.left)
        for comparator in node.comparators:
            self.visit(comparator)


class ClientView:
    """Attribute view over a flattened client dict.

    Missing attributes resolve to False so a typo cannot silently hide a control
    behind an exception. `repr` is deliberately unhelpful to keep client facts
    out of logs.
    """

    __slots__ = ("_data",)

    def __init__(self, data: Dict[str, Any]) -> None:
        object.__setattr__(self, "_data", data)

    def __getattr__(self, name: str) -> Any:
        if name.startswith("__"):
            raise AttributeError(name)
        return self._data.get(name, False)

    def __repr__(self) -> str:  # pragma: no cover
        return "<ClientView>"


def compile_condition(expr: str) -> ast.Expression:
    """Parse and validate a condition, returning a compiled AST.

    Raises ConditionError on syntax errors or disallowed grammar.
    """
    if expr is None:
        raise ConditionError("condition is empty")
    text = expr.strip()
    if not text:
        raise ConditionError("condition is empty")
    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError as exc:
        raise ConditionError("condition is not valid syntax: %s" % exc) from exc
    _Validator().visit(tree)
    return tree


def evaluate(expr: str, client_data: Dict[str, Any]) -> bool:
    """Safely evaluate a condition against a client field dict."""
    tree = compile_condition(expr)
    namespace: Dict[str, Any] = dict(client_data)
    namespace["client"] = ClientView(client_data)
    namespace.update(ALLOWED_CALLS)
    try:
        return bool(eval(compile(tree, "<condition>", "eval"), {"__builtins__": {}}, namespace))
    except ConditionError:
        raise
    except Exception as exc:  # pragma: no cover - defensive
        raise ConditionError("condition could not be evaluated: %s" % exc) from exc
