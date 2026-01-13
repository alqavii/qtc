"""
QTC Alpha - Team Registry Management

This module handles loading and managing team configurations from the registry YAML file.
"""

import yaml
import shutil
from pathlib import Path
from typing import Dict, Any, List, Optional
from decimal import Decimal

from app.config.paths import STRATEGY_ROOT
from app.core.identifiers import slugify


def prepare_strategy_workspace(team_id: str, source: Path) -> Path:
    """
    Prepare isolated strategy workspace for a team.

    Args:
        team_id: The team identifier
        source: Path to the source strategy directory or file

    Returns:
        Path to the prepared strategy workspace

    Raises:
        FileNotFoundError: If strategy.py cannot be found in the source
    """
    STRATEGY_ROOT.mkdir(parents=True, exist_ok=True)
    dest = STRATEGY_ROOT / team_id
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True, exist_ok=True)

    source = source.resolve()
    if source.is_file():
        candidate = source if source.name == "strategy.py" else None
    else:
        candidate = source / "strategy.py"
        if not candidate.exists():
            matches = list(source.rglob("strategy.py"))
            candidate = matches[0] if matches else None

    if candidate is None:
        raise FileNotFoundError(f"strategy.py not found in {source}")

    shutil.copy2(candidate, dest / "strategy.py")
    return dest


def load_teams_from_registry(
    registry_path: str, do_sync: bool = False
) -> List[Dict[str, Any]]:
    """
    Load team configurations from registry YAML file.

    This function reads the team_registry.yaml file and prepares strategy workspaces
    for each team. It no longer syncs from Git repositories - strategies should be
    uploaded via the web interface.

    Args:
        registry_path: Path to the team registry YAML file
        do_sync: Legacy parameter, no longer used (kept for compatibility)

    Returns:
        List of team configuration dictionaries, each containing:
            - team_id: Slugified team identifier
            - repo_dir: Path to strategy workspace (or None for default strategy)
            - entry_point: Strategy entry point (e.g., "strategy:Strategy")
            - initial_cash: Initial cash amount (Decimal)
            - params: Strategy parameters dictionary
            - run_24_7: Whether to run 24/7 or only during market hours

    Example:
        >>> teams = load_teams_from_registry("team_registry.yaml", do_sync=False)
        >>> for team in teams:
        ...     print(f"Team {team['team_id']}: {team['entry_point']}")
    """
    reg = yaml.safe_load(Path(registry_path).read_text(encoding="utf-8")) or {}
    teams: List[Dict[str, Any]] = reg.get("teams", []) or []
    out: List[Dict[str, Any]] = []

    # Note: Git syncing is disabled - strategies are uploaded via web interface
    # The do_sync parameter is kept for backward compatibility but has no effect

    for item in teams:
        raw_name = item.get("team_id") or item.get("name") or "team"
        name = slugify(raw_name)
        entry_point = item.get("entry_point", "strategy:Strategy")
        cash = Decimal(str(item.get("initial_cash", "10000")))
        run_24_7 = bool(item.get("run_24_7", False))
        params = item.get("params", {}) or {}

        repo_dir: Optional[Path] = None

        # Only use repo_dir from registry - no Git fetching
        repo_val = item.get("repo_dir")
        if repo_val:
            repo_dir = Path(repo_val)
        else:
            # Check if strategy exists in external_strategies from web upload
            web_strategy_path = STRATEGY_ROOT / name
            if (
                web_strategy_path.exists()
                and (web_strategy_path / "strategy.py").exists()
            ):
                repo_dir = web_strategy_path
                print(f"Using web-uploaded strategy for team {name}")
            else:
                print(
                    f"No strategy found for team {name}, will use default empty strategy"
                )
                # Set repo_dir to None - the orchestrator will use default strategy
                repo_dir = None

        try:
            # If repo_dir already points to external_strategies/<team_id>, do not
            # re-prepare (which would delete the folder we just synced). Just use it.
            use_repo = repo_dir

            if use_repo is None:
                # No strategy found - will use default empty strategy
                stable = None
            else:
                try:
                    strat_root = STRATEGY_ROOT.resolve()
                    if use_repo.resolve().is_dir() and (
                        use_repo.resolve() == (strat_root / name).resolve()
                    ):
                        if not (use_repo / "strategy.py").exists():
                            raise FileNotFoundError(
                                f"strategy.py not found in {use_repo}"
                            )
                        stable = use_repo
                    else:
                        stable = prepare_strategy_workspace(name, use_repo)
                except Exception:
                    # Fallback to prepare workspace if any path resolution check fails
                    stable = prepare_strategy_workspace(name, use_repo)
        except Exception as exc:
            print(f"Skipping team {name}: could not prepare strategy ({exc})")
            continue

        combined_params = dict(params)
        combined_params.setdefault("run_24_7", run_24_7)

        out.append(
            {
                "team_id": name,
                "repo_dir": str(stable) if stable else None,
                "entry_point": entry_point,
                "initial_cash": cash,
                "params": combined_params,
                "run_24_7": run_24_7,
            }
        )

    return out


__all__ = ["prepare_strategy_workspace", "load_teams_from_registry"]
