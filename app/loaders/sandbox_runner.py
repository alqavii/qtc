#!/usr/bin/env python3
"""
Sandbox runner script - executed as a subprocess.

This script:
1. Reads strategy parameters from stdin (JSON)
2. Sets resource limits (memory, no file creation)
3. Loads and executes the strategy
4. Outputs the result to stdout (JSON)

DO NOT import any modules that could be abused.
"""

import importlib.util
import json
import sys
from pathlib import Path


def set_resource_limits(memory_mb: int) -> None:
    """
    Set resource limits for the subprocess.
    
    Only works on Unix systems (Linux, macOS).
    """
    try:
        import resource
        
        # Memory limit (virtual memory)
        memory_bytes = memory_mb * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))
        
        # No core dumps
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        
        # Limit file size creation (0 = no new files)
        # Note: This only affects new files, not reading
        resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
        
        # Limit number of child processes (0 = can't fork)
        resource.setrlimit(resource.RLIMIT_NPROC, (0, 0))
        
    except (ImportError, AttributeError, ValueError):
        # resource module not available (Windows) or limit not supported
        pass


def load_strategy(strategy_path: str, entry_point: str):
    """
    Load a strategy class from a file.
    
    Args:
        strategy_path: Directory containing strategy files
        entry_point: Format "file:ClassName" (e.g., "strategy:Strategy")
    
    Returns:
        Instantiated strategy object
    """
    path = Path(strategy_path)
    file_name, class_name = entry_point.split(":")
    module_file = path / f"{file_name}.py"
    
    if not module_file.exists():
        raise FileNotFoundError(f"Strategy file not found: {module_file}")
    
    # Add strategy directory to path so imports work
    sys.path.insert(0, str(path))
    
    try:
        spec = importlib.util.spec_from_file_location(file_name, module_file)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load module from {module_file}")
        
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        
        strategy_class = getattr(module, class_name)
        return strategy_class()
    finally:
        # Remove from path
        if str(path) in sys.path:
            sys.path.remove(str(path))


def main():
    """Main entry point for sandbox execution."""
    try:
        # Read input from stdin
        input_text = sys.stdin.read()
        if not input_text:
            print("null")
            return
        
        data = json.loads(input_text)
        
        # Set resource limits before loading untrusted code
        memory_mb = data.get("memory_mb", 256)
        set_resource_limits(memory_mb)
        
        # Load the strategy
        strategy = load_strategy(
            data["strategy_path"],
            data["entry_point"],
        )
        
        # Execute the strategy
        result = strategy.generate_signal(
            data["team"],
            data["bars"],
            data["prices"],
        )
        
        # Output result as JSON
        if result is None:
            print("null")
        else:
            # Convert Decimal to float for JSON serialization
            def convert_decimals(obj):
                if hasattr(obj, "__float__"):
                    return float(obj)
                elif isinstance(obj, dict):
                    return {k: convert_decimals(v) for k, v in obj.items()}
                elif isinstance(obj, (list, tuple)):
                    return [convert_decimals(v) for v in obj]
                return obj
            
            print(json.dumps(convert_decimals(result)))
            
    except Exception as e:
        # Write error to stderr
        sys.stderr.write(f"{type(e).__name__}: {e}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
