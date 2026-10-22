"""CLI entry point for omarchy-eva."""

import os
import runpy
import sys


def main():
    """Execute the omarchy-eva CLI."""
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cli_script = os.path.join(repo_root, "bin", "omarchy-eva")
    if os.path.exists(cli_script):
        # Run script with current sys.argv
        sys.argv[0] = cli_script
        runpy.run_path(cli_script, run_name="__main__")
    else:
        print(f"Error: Could not locate CLI script at {cli_script}")
        sys.exit(1)


if __name__ == "__main__":
    main()
