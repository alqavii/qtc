import ast
from pathlib import Path
from typing import Set, Optional

# Blacklist of dangerous imports that could compromise system security
BLACKLISTED_IMPORTS: Set[str] = {
    # Process & System Control
    "os",
    "subprocess",
    "multiprocessing",
    
    # Dynamic Code Execution
    "importlib",
    "pkgutil",
    "runpy",
    "code",
    "codeop",
    
    # File System Access
    "shutil",
    "tempfile",
    "pathlib",
    "glob",
    "fnmatch",
    
    # Network Access
    "socket",
    "urllib",
    "urllib3",
    "requests",
    "http",
    "ftplib",
    "smtplib",
    "poplib",
    "imaplib",
    "telnetlib",
    "socketserver",
    
    # Serialization/Deserialization (RCE risks)
    "pickle",
    "shelve",
    "marshal",
    "dill",
    
    # System Information & Introspection
    "sys",
    "ctypes",
    "cffi",
    "platform",
    "pwd",
    "grp",
    "resource",
    
    # Compiler & AST Manipulation
    "ast",
    "compile",
    "dis",
    "inspect",
    
    # Database Access
    "sqlite3",
    "dbm",
    
    # External Services & Cloud APIs
    "boto3",
    "botocore",
    "azure",
    "google",
    "kubernetes",
    "docker",
    
    # Web Scraping & Browser Automation
    "selenium",
    "scrapy",
    
    # GUI Libraries
    "tkinter",
    "pygame",
    
    # Other Risky Modules
    "webbrowser",
    "xmlrpc",
    "pty",
    "tty",
    "readline",
    "rlcompleter",
    "pdb",
    "trace",
    "traceback",
    "warnings",
    "logging",
    "builtins",
    "gc",
    "weakref",
}

def _scan_file(py: Path, blacklist: Set[str]) -> None:
    code = py.read_text(encoding="utf-8")
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        raise RuntimeError(f"Syntax error in {py}: {e}") from e
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for n in node.names:
                root = n.name.split(".")[0]
                if root in blacklist:
                    raise RuntimeError(f"Blacklisted import: {n.name} in {py}")
        if isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            if root and root in blacklist:
                raise RuntimeError(f"Blacklisted import: {node.module} in {py}")
        # Disallow dangerous builtins usage (open, exec, eval, __import__)
        if isinstance(node, ast.Call):
            fn = node.func
            if isinstance(fn, ast.Name) and fn.id in {"open", "exec", "eval", "__import__"}:
                raise RuntimeError(f"Disallowed builtin call '{fn.id}' in {py}")


def _verify_class_exists(py: Path, class_name: str) -> None:
    """Verify that a class with the given name exists in the file."""
    code = py.read_text(encoding="utf-8")
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        raise RuntimeError(f"Syntax error in {py}: {e}") from e
    
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            # Check for generate_signal method
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == "generate_signal":
                    return
            raise RuntimeError(
                f"Class '{class_name}' in {py} missing 'generate_signal' method"
            )
    
    raise RuntimeError(f"Class '{class_name}' not found in {py}")


def ast_sanity_check(
    repo_dir: Path, entry_point: Optional[str] = None, blacklist: Set[str] = BLACKLISTED_IMPORTS
) -> None:
    """
    Scan all .py files for blacklisted imports.
    
    If entry_point is provided, also verify the Strategy class exists.
    Always scans ALL .py files in the directory (not just entry file).
    """
    # Always scan all Python files in the directory
    py_files = list(repo_dir.rglob("*.py"))
    if not py_files:
        raise RuntimeError(f"No Python files found in {repo_dir}")
    
    for py in py_files:
        _scan_file(py, blacklist)
    
    # If entry point specified, verify the class exists
    if entry_point:
        file_name, class_name = entry_point.split(":")
        target = repo_dir / f"{file_name}.py"
        if not target.exists():
            raise RuntimeError(
                f"Entry file {target} not found for entry_point '{entry_point}'"
            )
        _verify_class_exists(target, class_name)
