import argparse
import json
import os
import sys
import urllib.request
import xml.etree.ElementTree as ET
from typing import Dict, List

MAVEN_CENTRAL_BASE = "https://repo1.maven.org/maven2"


def validate_real_package(package: str) -> bool:
    parts = package.split(":")
    return len(parts) == 3 and all(parts)


def build_pom_url(package: str) -> str:
    group_id, artifact_id, version = package.split(":")
    group_path = group_id.replace(".", "/")
    pom_filename = f"{artifact_id}-{version}.pom"
    return f"{MAVEN_CENTRAL_BASE}/{group_path}/{artifact_id}/{version}/{pom_filename}"


def fetch_and_parse_real_deps(package: str) -> List[str]:
    url = build_pom_url(package)
    try:
        with urllib.request.urlopen(url) as resp:
            content = resp.read().decode("utf-8")
    except Exception as e:
        raise RuntimeError(f"Cannot fetch POM for {package}: {e}")

    try:
        root = ET.fromstring(content)
    except ET.ParseError as e:
        raise RuntimeError(f"Invalid XML in POM of {package}: {e}")

    namespaces = {}
    if root.tag.startswith("{"):
        ns = root.tag[1:].split("}")[0]
        namespaces["m"] = ns

    deps_section = root.find("m:dependencies" if "m" in namespaces else "dependencies", namespaces)
    if deps_section is None:
        return []

    deps = []
    dep_tag = "m:dependency" if "m" in namespaces else "dependency"
    for dep in deps_section.findall(dep_tag, namespaces):
        g = dep.find("m:groupId" if "m" in namespaces else "groupId", namespaces)
        a = dep.find("m:artifactId" if "m" in namespaces else "artifactId", namespaces)
        v = dep.find("m:version" if "m" in namespaces else "version", namespaces)

        group = g.text.strip() if g is not None and g.text else None
        artif = a.text.strip() if a is not None and a.text else None
        version = v.text.strip() if v is not None and v.text else "unknown"

        if group and artif:
            deps.append(f"{group}:{artif}:{version}")
    return deps


def load_test_graph(path: str) -> Dict[str, List[str]]:
    if not os.path.isfile(path):
        raise RuntimeError(f"Test graph file not found: {path}")
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        for k, v in data.items():
            if not isinstance(k, str) or not isinstance(v, list):
                raise ValueError("Invalid format")
            for dep in v:
                if not isinstance(dep, str):
                    raise ValueError("Dependency must be string")
        return data
    except Exception as e:
        raise RuntimeError(f"Failed to load test graph: {e}")


def get_test_deps(package: str, graph: Dict[str, List[str]]) -> List[str]:
    return graph.get(package, [])


def print_ascii_tree(
        package: str,
        get_deps_func,
        test_graph: dict = None,
        prefix: str = "",
        is_last: bool = True,
        current_path: List[str] = None,
        filter_sub: str = ""
):
    if current_path is None:
        current_path = []

    if filter_sub and filter_sub in package:
        return

    if package in current_path:
        connector = "└── " if is_last else "├── "
        print(f"{prefix}{connector}{package} (.cycle.)")
        return

    connector = "└── " if is_last else "├── "
    print(f"{prefix}{connector}{package}")

    try:
        if test_graph is not None:
            deps = get_deps_func(package, test_graph)
        else:
            deps = get_deps_func(package)
    except Exception:
        deps = []

    deps = [d for d in deps if not (filter_sub and filter_sub in d)]

    new_path = current_path + [package]
    for i, child in enumerate(deps):
        is_last_child = (i == len(deps) - 1)
        extension = "    " if is_last else "│   "
        print_ascii_tree(
            child,
            get_deps_func,
            test_graph,
            prefix + extension,
            is_last_child,
            new_path,
            filter_sub
        )


def main():
    parser = argparse.ArgumentParser(
        description="Stage 3: Build and visualize full dependency graph"
    )
    parser.add_argument("--package", required=True, help="Root package to analyze")
    parser.add_argument("--repo", required=True, help="URL (ignored in real mode) or path to test graph JSON")
    parser.add_argument("--test-mode", choices=["file", "url"], required=True,
                        help="'file': use test graph (A, B, C); 'url': real Maven package")
    parser.add_argument("--ascii-tree", action="store_true", help="Enable ASCII tree output")
    parser.add_argument("--filter", default="", help="Exclude packages containing this substring")

    args = parser.parse_args()

    test_graph = None
    get_deps_func = None
    root_package = args.package

    if args.test_mode == "file":
        if not (root_package.isalpha() and root_package.isupper()):
            print("Error: In test mode, package must be uppercase Latin letters (e.g., A, B)", file=sys.stderr)
            sys.exit(1)
        try:
            test_graph = load_test_graph(args.repo)
            if root_package not in test_graph:
                print(f"Error: Package '{root_package}' not found in test graph", file=sys.stderr)
                sys.exit(1)
        except RuntimeError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        get_deps_func = get_test_deps
    else:  # url mode
        if not validate_real_package(args.package):
            print("Error: In 'url' mode, package must be 'groupId:artifactId:version'", file=sys.stderr)
            sys.exit(1)
        get_deps_func = fetch_and_parse_real_deps
        from urllib.parse import urlparse
        try:
            result = urlparse(args.repo)
            if not (result.scheme and result.netloc):
                raise ValueError()
        except Exception:
            print(f"Error: Invalid repository URL: {args.repo}", file=sys.stderr)
            sys.exit(1)

    if args.ascii_tree:
        print(f"Dependency tree for '{root_package}':")
        print("=" * 60)
        print_ascii_tree(
            root_package,
            get_deps_func,
            test_graph=test_graph,
            filter_sub=args.filter
        )
    else:
        try:
            direct_deps = get_deps_func(root_package) if test_graph is None else get_deps_func(root_package, test_graph)
            print("Direct dependencies:")
            if direct_deps:
                for dep in direct_deps:
                    print(f"  {dep}")
            else:
                print("  (none)")
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
