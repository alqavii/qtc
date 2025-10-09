from __future__ import annotations

from pathlib import Path
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
import subprocess
import shutil
import yaml
import json
from typing import Dict, Any, Tuple

ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = ROOT / ".cache" / "strategies"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
STATE_FILE = Path(".strategy_sync_state.json")  # remembers last synced SHAs


def _run(cmd: list[str], cwd: Path | None = None) -> str:
    """Run a shell command and return stdout or raise CalledProcessError."""
    res = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if res.returncode != 0:
        raise subprocess.CalledProcessError(res.returncode, cmd, res.stdout, res.stderr)
    return res.stdout.strip()


def _repo_name_from_url(url: str) -> str:
    name = url.rstrip("/").split("/")[-1]
    return name[:-4] if name.endswith(".git") else name


def _ls_remote_head(url: str, ref: str) -> str:
    """
    Return the commit SHA for the given ref (branch or tag).
    If ref already looks like a SHA (40 hex chars), just return it.
    """
    ref = ref.strip()
    if len(ref) == 40 and all(c in "0123456789abcdef" for c in ref.lower()):
        return ref  # it's already a SHA

    # Ask remote for the ref
    out = _run(["git", "ls-remote", url, ref])
    if not out:
        raise RuntimeError(f"Could not find ref '{ref}' on remote {url}")
    # Typical line: "<sha>\trefs/heads/<ref>" or "<sha>\t<ref>"
    first_line = out.splitlines()[0]
    sha = first_line.split("\t", 1)[0]
    if len(sha) != 40:
        raise RuntimeError(f"Unexpected ls-remote output for {url} {ref}: {first_line}")
    return sha


def _ensure_clean_dir(p: Path):
    if p.exists():
        shutil.rmtree(p)
    # create the target directory itself, not just its parent
    p.mkdir(parents=True, exist_ok=True)


def _with_token(url: str) -> str:
    """Inject an auth token into a GitHub https URL if provided via env.

    Supports GIT_AUTH_TOKEN or GITHUB_TOKEN.
    """
    token = os.getenv("GIT_AUTH_TOKEN") or os.getenv("GITHUB_TOKEN")
    if not token:
        return url
    if url.startswith("https://") and "@" not in url:
        # https://github.com/owner/repo.git -> https://TOKEN@github.com/owner/repo.git
        return url.replace("https://", f"https://{token}@", 1)
    return url


def shallow_clone_at_sha(url: str, sha: str, dest: Path):
    """
    Create a minimal checkout at the exact commit SHA in 'dest' using a shallow fetch.
    """
    _ensure_clean_dir(dest)
    _run(["git", "init"], cwd=dest)
    _run(["git", "remote", "add", "origin", _with_token(url)], cwd=dest)
    # fetch only the commit we need
    _run(["git", "fetch", "--depth=1", "origin", sha], cwd=dest)
    _run(["git", "checkout", "--detach", sha], cwd=dest)


def load_state() -> Dict[str, Any]:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {}


def save_state(state: Dict[str, Any]) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def sync_all_from_registry(
    registry_path: str = "team_registry.yaml",
    *,
    workers: int = 8,
    run_ast_check: bool = True,
) -> Dict[str, Dict[str, Any]]:
    """
    Read team_registry.yaml, sync all repos, return a dict:
    { team_id: {repo_dir, entry_point, sha, skipped} }
    """
    reg = yaml.safe_load(Path(registry_path).read_text(encoding="utf-8"))
    teams = reg.get("teams", [])
    state = load_state()
    results: Dict[str, Dict[str, Any]] = {}

    tasks = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for item in teams:
            team_id = item["team_id"]
            url = item["git_url"]
            # prefer 'branch' if provided; allow 'ref' or 'sha' as alternates
            ref = item.get("branch") or item.get("ref") or item.get("sha") or "main"
            entry_point = item["entry_point"]

            try:
                sha = _ls_remote_head(url, ref)
            except Exception as e:
                # record failure inline; continue with others
                results[team_id] = {
                    "error": f"ls-remote failed: {e}",
                    "repo_dir": None,
                    "entry_point": entry_point,
                    "sha": None,
                    "skipped": False,
                }
                continue

            prev = (state.get(team_id) or {}).get("sha")
            repo_dir = CACHE_DIR / f"{_repo_name_from_url(url)}"

            if prev == sha and repo_dir.exists():
                # Up-to-date; no work
                results[team_id] = {
                    "repo_dir": str(repo_dir),
                    "entry_point": entry_point,
                    "sha": sha,
                    "skipped": True,
                }
                continue

            # Schedule a fetch job
            tasks.append(
                ex.submit(
                    _fetch_one, team_id, url, sha, repo_dir, entry_point, run_ast_check
                )
            )

        for fut in as_completed(tasks):
            tid, info = fut.result()
            results[tid] = info
            if "error" not in info:
                state[tid] = {"sha": info["sha"], "repo_dir": info["repo_dir"]}

    save_state(state)
    return results


def _fetch_one(
    team_id: str,
    url: str,
    sha: str,
    repo_dir: Path,
    entry_point: str,
    run_ast_check: bool,
) -> Tuple[str, Dict[str, Any]]:
    try:
        shallow_clone_at_sha(url, sha, repo_dir)
        if run_ast_check:
            try:
                # Optional safety check (allow-list of imports)
                from app.loaders.static_check import ast_sanity_check  # type: ignore

                # Narrow the check to the declared entry-point module only
                ast_sanity_check(repo_dir, entry_point)
            except Exception as e:
                # quarantine bad repo to avoid accidental use
                bad = repo_dir.with_suffix(".blocked")
                if bad.exists():
                    shutil.rmtree(bad)
                repo_dir.rename(bad)
                return team_id, {
                    "error": f"AST check failed: {e}",
                    "repo_dir": str(bad),
                    "entry_point": entry_point,
                    "sha": sha,
                    "skipped": False,
                }

        return team_id, {
            "repo_dir": str(repo_dir),
            "entry_point": entry_point,
            "sha": sha,
            "skipped": False,
        }

    except Exception as e:
        return team_id, {
            "error": f"clone/checkout failed: {e}",
            "repo_dir": None,
            "entry_point": entry_point,
            "sha": sha,
            "skipped": False,
        }
