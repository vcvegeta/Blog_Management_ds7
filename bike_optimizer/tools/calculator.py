"""
MRKL Tool 3: calculator
Safe arithmetic evaluator — no eval(), uses ast module with whitelist.

Input:  { "expression": string, "units"?: string }
Output: { "success": bool, "data": { "value": number, "units"?: string },
          "error"?: string, "source": string, "ts": string }
"""

import ast
import datetime
import hashlib
import operator
import re
import time
from typing import Any

# Whitelist of allowed characters in the expression
ALLOWED_PATTERN = re.compile(r"^[0-9+\-*/().\s]+$")

# Supported operators
OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _safe_eval(node: ast.AST) -> float:
    """Recursively evaluate an AST node using only whitelisted operators."""
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return float(node.value)
        raise ValueError(f"Unsupported constant type: {type(node.value)}")

    if isinstance(node, ast.BinOp):
        op_type = type(node.op)
        if op_type not in OPERATORS:
            raise ValueError(f"Unsupported operator: {op_type.__name__}")
        left = _safe_eval(node.left)
        right = _safe_eval(node.right)
        if op_type == ast.Div and right == 0:
            raise ZeroDivisionError("Division by zero")
        return OPERATORS[op_type](left, right)

    if isinstance(node, ast.UnaryOp):
        op_type = type(node.op)
        if op_type not in OPERATORS:
            raise ValueError(f"Unsupported unary operator: {op_type.__name__}")
        operand = _safe_eval(node.operand)
        return OPERATORS[op_type](operand)

    raise ValueError(f"Unsupported AST node: {type(node).__name__}")


def calculator(expression: str, units: str | None = None) -> dict[str, Any]:
    """
    Safely evaluate a mathematical expression.
    Only allows: digits, +, -, *, /, (, ), ., whitespace.
    """
    ts = datetime.datetime.utcnow().isoformat() + "Z"
    start = time.time()
    args_hash = hashlib.md5(expression.encode()).hexdigest()[:8]

    # Whitelist check
    if not ALLOWED_PATTERN.match(expression):
        return {
            "success": False,
            "error": (
                f"Expression contains disallowed characters: '{expression}'. "
                "Only digits and +, -, *, /, (, ), . are allowed."
            ),
            "source": "calculator",
            "ts": ts,
        }

    try:
        tree = ast.parse(expression, mode="eval")
        value = _safe_eval(tree.body)
        result = round(value, 4)

        data: dict[str, Any] = {"value": result}
        if units:
            data["units"] = units

        return {
            "success": True,
            "data": data,
            "source": "calculator",
            "ts": ts,
            "latency_s": round(time.time() - start, 4),
            "args_hash": args_hash,
        }

    except ZeroDivisionError:
        return {
            "success": False,
            "error": "Division by zero.",
            "source": "calculator",
            "ts": ts,
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Could not evaluate expression: {e}",
            "source": "calculator",
            "ts": ts,
        }
