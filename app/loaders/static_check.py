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


def ast_sanity_check(
    repo_dir: Path, entry_point: Optional[str] = None, blacklist: Set[str] = BLACKLISTED_IMPORTS
) -> None:
    """Scan for blacklisted imports; if entry_point is provided, only scan that file."""
    if entry_point:
        file_name = entry_point.split(":")[0]
        target = repo_dir / f"{file_name}.py"
        if not target.exists():
            raise RuntimeError(
                f"Entry file {target} not found for entry_point '{entry_point}'"
            )
        _scan_file(target, blacklist)
        return

    for py in repo_dir.rglob("*.py"):
        _scan_file(py, blacklist)
