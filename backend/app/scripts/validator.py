import re
import ast
import logging

logger = logging.getLogger(__name__)

# Blacklisted patterns that would indicate malicious intent
FORBIDDEN_PATTERNS = [
    (r"import\s+os", "os module import is forbidden"),
    (r"import\s+sys", "sys module import is forbidden"),
    (r"import\s+subprocess", "subprocess import is forbidden"),
    (r"import\s+shutil", "shutil import is forbidden"),
    (r"import\s+socket", "socket import is forbidden"),
    (r"import\s+requests", "requests import is forbidden"),
    (r"import\s+http", "http import is forbidden"),
    (r"__import__\s*\(", "__import__ calls are forbidden"),
    (r"exec\s*\(.*\)", "exec() calls are forbidden"),
    (r"eval\s*\(.*\)", "eval() calls are forbidden"),
    (r"compile\s*\(.*\)", "compile() calls are forbidden"),
    (r"open\s*\(.*\)", "open() file access is forbidden"),
    (r"getattr\s*\(\s*__builtins__", "getattr on builtins is forbidden"),
    (r"globals\s*\(\s*\)", "globals() access is forbidden"),
    (r"locals\s*\(\s*\)", "locals() access is forbidden"),
]


def validate_script(code: str) -> tuple[bool, list[str]]:
    errors = []

    # Check length
    if len(code) > 50000:
        errors.append("Script exceeds 50KB limit")
        return False, errors

    # Check for forbidden patterns
    lower_code = code.lower()
    for pattern, message in FORBIDDEN_PATTERNS:
        if re.search(pattern, lower_code):
            errors.append(f"Security: {message}")

    if errors:
        return False, errors

    # Try parsing
    try:
        tree = ast.parse(code)

        # Check for dangerous AST nodes
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] not in ("json", "math", "random", "collections", "itertools", "datetime"):
                        errors.append(f"Import of '{alias.name}' is not allowed")

            elif isinstance(node, ast.ImportFrom):
                if node.module and node.module.split(".")[0] not in ("json", "math", "random", "collections", "itertools", "datetime"):
                    errors.append(f"Import from '{node.module}' is not allowed")

            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    if node.func.id in ("eval", "exec", "compile", "open", "__import__", "globals", "locals"):
                        errors.append(f"Call to '{node.func.id}()' is forbidden")

    except SyntaxError as e:
        errors.append(f"Syntax error at line {e.lineno}: {e.msg}")

    return len(errors) == 0, errors


def extract_functions(code: str) -> list[str]:
    funcs = []
    try:
        tree = ast.parse(code)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                funcs.append(node.name)
    except SyntaxError:
        pass
    return funcs


def extract_symbols(code: str) -> list[str]:
    symbols = set()
    # Find all string literals that look like trading pairs
    for node in ast.walk(ast.parse(code)):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if re.match(r'^[A-Z]{2,10}USDT$', str(node.value)):
                symbols.add(str(node.value))
    return sorted(symbols)