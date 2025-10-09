import ast
from pathlib import Path
from typing import Set, Optional

ALLOWED_IMPORTS: Set[str] = {
    # stdlib (safe)
    "math", "statistics", "decimal", "collections", "typing",
    # scientific stack (allowed)
    "numpy", "pandas", "scipy",
}

def _scan_file(py: Path, allowlist: Set[str]) -> None:
    code = py.read_text(encoding="utf-8")
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        raise RuntimeError(f"Syntax error in {py}: {e}") from e
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for n in node.names:
                root = n.name.split(".")[0]
                if root not in allowlist:
                    raise RuntimeError(f"Disallowed import: {n.name} in {py}")
        if isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            if root and root not in allowlist:
                raise RuntimeError(f"Disallowed import: {node.module} in {py}")
        # Disallow dangerous builtins usage (open, exec, eval, __import__)
        if isinstance(node, ast.Call):
            fn = node.func
            if isinstance(fn, ast.Name) and fn.id in {"open", "exec", "eval", "__import__"}:
                raise RuntimeError(f"Disallowed builtin call '{fn.id}' in {py}")


def ast_sanity_check(
    repo_dir: Path, entry_point: Optional[str] = None, allowlist: Set[str] = ALLOWED_IMPORTS
) -> None:
    """Scan for safe imports; if entry_point is provided, only scan that file."""
    if entry_point:
        file_name = entry_point.split(":")[0]
        target = repo_dir / f"{file_name}.py"
        if not target.exists():
            raise RuntimeError(
                f"Entry file {target} not found for entry_point '{entry_point}'"
            )
        _scan_file(target, allowlist)
        return

    for py in repo_dir.rglob("*.py"):
        _scan_file(py, allowlist)
