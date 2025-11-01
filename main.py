import argparse
import os
import sys
import urllib.parse

def validate_repo(repo: str, mode: str) -> bool:
    if mode == "url":
        try:
            result = urllib.parse.urlparse(repo)
            return all([result.scheme, result.netloc])
        except Exception:
            return False
    elif mode == "file":
        return os.path.exists(repo)
    else:
        return False

def main():
    parser = argparse.ArgumentParser(
        description="Visualize package dependency graph (Stage 1: Configurable CLI prototype)"
    )
    parser.add_argument(
        "--package",
        required=True,
        help="Name of the package to analyze"
    )
    parser.add_argument(
        "--repo",
        required=True,
        help="URL of repository or path to test repository file"
    )
    parser.add_argument(
        "--test-mode",
        choices=["file", "url"],
        required=True,
        help="Mode of repository access: 'file' for local file, 'url' for remote repository"
    )
    parser.add_argument(
        "--ascii-tree",
        action="store_true",
        help="Enable ASCII tree output mode"
    )
    parser.add_argument(
        "--filter",
        default="",
        help="Substring to filter package names in output"
    )

    try:
        args = parser.parse_args()
    except SystemExit as e:
        print("Error: Missing or invalid command-line arguments.", file=sys.stderr)
        sys.exit(1)

    if not validate_repo(args.repo, args.test_mode):
        if args.test_mode == "url":
            print(f"Error: Invalid URL provided: {args.repo}", file=sys.stderr)
        else:
            print(f"Error: File not found: {args.repo}", file=sys.stderr)
        sys.exit(1)

    print("Configured parameters:")
    print(f"  package      = {args.package}")
    print(f"  repo         = {args.repo}")
    print(f"  test-mode    = {args.test_mode}")
    print(f"  ascii-tree   = {args.ascii_tree}")
    print(f"  filter       = {repr(args.filter)}")

if __name__ == "__main__":
    main()