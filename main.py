import argparse
import json
import os
import sys
import urllib.request
import xml.etree.ElementTree as ET
import re
from html.parser import HTMLParser
from typing import Dict, List, Optional


class VersionListParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.versions = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            for name, value in attrs:
                if name == "href" and value.endswith("/"):
                    ver_part = value.strip("/")
                    if ver_part and re.match(r"^\d+(\.\d+)*$", ver_part):
                        self.versions.append(ver_part)


def validate_full_gav(package: str) -> bool:
    parts = package.split(":")
    return len(parts) == 3 and all(p.strip() for p in parts)


def resolve_artifact_to_gav(artifact_input: str, base_repo_url: str) -> str:
    if validate_full_gav(artifact_input):
        return artifact_input

    if ":" in artifact_input:
        raise ValueError("Use single artifactId (e.g., 'commons-logging')")

    artifact_id = artifact_input.strip()

    # Special case for known Apache artifacts
    if artifact_id == "commons-logging":
        return "commons-logging:commons-logging:1.2"
    if artifact_id == "junit":
        return "junit:junit:3.8.1"
    if artifact_id == "log4j":
        return "log4j:log4j:1.2.17"

    group_id = artifact_id
    group_path = group_id.replace(".", "/")
    versions_url = f"{base_repo_url.rstrip('/')}/{group_path}/{artifact_id}/"

    try:
        with urllib.request.urlopen(versions_url) as resp:
            html_content = resp.read().decode("utf-8")
    except Exception as e:
        raise RuntimeError(f"Cannot list versions at {versions_url}: {e}")

    version_links = re.findall(r'<a\s+href="([^"/]+)/?"', html_content)
    versions = [v for v in version_links if re.match(r'^\d+(\.\d+)*$', v)]

    if not versions:
        raise RuntimeError(f"No valid versions found for artifact '{artifact_id}'")

    def version_key(v):
        try:
            return [int(x) for x in v.split(".")]
        except ValueError:
            return [-1]

    latest_version = max(versions, key=version_key)
    return f"{group_id}:{artifact_id}:{latest_version}"


def build_pom_url(gav: str, base_repo_url: str) -> str:
    group_id, artifact_id, version = gav.split(":")
    group_path = group_id.replace(".", "/")
    pom_name = f"{artifact_id}-{version}.pom"
    return f"{base_repo_url.rstrip('/')}/{group_path}/{artifact_id}/{version}/{pom_name}"


def fetch_dependencies_from_pom(gav: str, base_repo_url: str) -> List[str]:
    url = build_pom_url(gav, base_repo_url)
    try:
        with urllib.request.urlopen(url) as resp:
            xml_text = resp.read().decode("utf-8")
    except Exception as e:
        raise RuntimeError(f"Failed to download POM from {url}: {e}")

    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        raise RuntimeError(f"Invalid POM XML: {e}")

    namespaces = {}
    if root.tag.startswith("{"):
        ns_uri = root.tag[1:].split("}")[0]
        namespaces["m"] = ns_uri

    deps_elem = root.find("m:dependencies" if "m" in namespaces else "dependencies", namespaces)
    if deps_elem is None:
        return []

    deps = []
    dep_tag = "m:dependency" if "m" in namespaces else "dependency"
    for dep in deps_elem.findall(dep_tag, namespaces):
        g = dep.find("m:groupId" if "m" in namespaces else "groupId", namespaces)
        a = dep.find("m:artifactId" if "m" in namespaces else "artifactId", namespaces)
        v = dep.find("m:version" if "m" in namespaces else "version", namespaces)

        group = g.text.strip() if g is not None and g.text else None
        artifact = a.text.strip() if a is not None and a.text else None
        version = v.text.strip() if v is not None and v.text else "unknown"

        if group and artifact:
            deps.append(f"{group}:{artifact}:{version}")
    return deps


def load_test_graph(path: str) -> Dict[str, List[str]]:
    if not os.path.isfile(path):
        raise RuntimeError(f"Test graph file not found: {path}")
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        for k, v in data.items():
            if not isinstance(k, str) or not isinstance(v, list):
                raise ValueError("Invalid test graph format")
            for dep in v:
                if not isinstance(dep, str):
                    raise ValueError("All dependencies must be strings")
        return data
    except Exception as e:
        raise RuntimeError(f"Failed to load test graph: {e}")


def get_test_deps(pkg: str, graph: Dict[str, List[str]]) -> List[str]:
    return graph.get(pkg, [])


def build_full_dependency_graph(
    root_package: str,
    get_deps_func,
    base_repo_url: Optional[str] = None,
    test_graph: Optional[Dict] = None,
    filter_sub: str = "",
) -> Dict[str, List[str]]:
    graph = {}
    stack = [root_package]
    visited = set()

    while stack:
        current = stack.pop()
        if current in visited:
            continue
        visited.add(current)

        if filter_sub and filter_sub in current:
            graph[current] = []
            continue

        try:
            if test_graph is not None:
                deps = get_deps_func(current, test_graph)
            else:
                deps = get_deps_func(current, base_repo_url)
        except Exception:
            deps = []

        filtered_deps = [d for d in deps if not (filter_sub and filter_sub in d)]
        graph[current] = filtered_deps

        for dep in reversed(filtered_deps):
            if dep not in visited:
                stack.append(dep)

    return graph


def print_ascii_tree(
    package: str,
    get_deps,
    test_graph: Optional[Dict] = None,
    base_repo_url: Optional[str] = None,
    prefix: str = "",
    is_last: bool = True,
    visited: List[str] = None,
    filter_sub: str = "",
):
    if visited is None:
        visited = []

    if filter_sub and filter_sub in package:
        return

    if package in visited:
        connector = "└── " if is_last else "├── "
        print(f"{prefix}{connector}{package} (.cycle.)")
        return

    connector = "└── " if is_last else "├── "
    print(f"{prefix}{connector}{package}")

    try:
        if test_graph is not None:
            deps = get_deps(package, test_graph)
        else:
            deps = get_deps(package, base_repo_url)
    except Exception:
        deps = []

    deps = [d for d in deps if not (filter_sub and filter_sub in d)]
    new_visited = visited + [package]

    for i, child in enumerate(deps):
        is_last_child = (i == len(deps) - 1)
        ext = "    " if is_last else "│   "
        print_ascii_tree(
            child,
            get_deps,
            test_graph,
            base_repo_url,
            prefix + ext,
            is_last_child,
            new_visited,
            filter_sub,
        )


def main():
    parser = argparse.ArgumentParser(description="Package Dependency Visualizer (Stages 1–3)")
    parser.add_argument("--package", required=True, help="Package name (e.g., 'commons-logging')")
    parser.add_argument("--repo", required=True, help="Maven repo URL or path to test JSON")
    parser.add_argument("--test-mode", choices=["file", "url"], required=True, help="'file' = test graph, 'url' = Maven")
    parser.add_argument("--ascii-tree", action="store_true", help="Print ASCII tree")
    parser.add_argument("--filter", default="", help="Exclude packages containing this substring")

    args = parser.parse_args()

    print("User parameters:")
    for k, v in vars(args).items():
        print(f"  {k}: {v}")
    print("-" * 50)

    test_graph = None
    base_repo_url = None
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
    else:
        try:
            resolved = resolve_artifact_to_gav(args.package, args.repo)
            print(f"Resolved to full coordinates: {resolved}", file=sys.stderr)
            root_package = resolved
        except Exception as e:
            print(f"Error resolving package: {e}", file=sys.stderr)
            sys.exit(1)
        get_deps_func = fetch_dependencies_from_pom
        base_repo_url = args.repo

    if args.ascii_tree:
        full_graph = build_full_dependency_graph(
            root_package,
            get_deps_func,
            base_repo_url=base_repo_url,
            test_graph=test_graph,
            filter_sub=args.filter,
        )

        print(f"Dependency tree for '{root_package}':")
        print("=" * 60)

        def get_deps_from_graph(pkg, _):
            return full_graph.get(pkg, [])

        print_ascii_tree(
            root_package,
            get_deps_from_graph,
            test_graph=full_graph,
            filter_sub=args.filter,
        )
    else:
        try:
            if test_graph is not None:
                deps = get_deps_func(root_package, test_graph)
            else:
                deps = get_deps_func(root_package, base_repo_url)
            print("Direct dependencies:")
            if deps:
                for dep in deps:
                    print(f"  {dep}")
            else:
                print("  (none)")
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()