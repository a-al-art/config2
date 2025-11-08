import argparse
import os
import sys
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from typing import List, Tuple

MAVEN_CENTRAL_BASE = "https://repo1.maven.org/maven2"


def validate_package_name(package: str) -> bool:
    parts = package.split(":")
    return len(parts) == 3 and all(parts)


def validate_repo(repo: str, mode: str) -> bool:
    if mode == "url":
        try:
            result = urllib.parse.urlparse(repo)
            return all([result.scheme, result.netloc])
        except Exception:
            return False
    elif mode == "file":
        return os.path.isfile(repo)
    else:
        return False


def build_pom_url(package: str) -> str:
    group_id, artifact_id, version = package.split(":")
    group_path = group_id.replace(".", "/")
    pom_filename = f"{artifact_id}-{version}.pom"
    return f"{MAVEN_CENTRAL_BASE}/{group_path}/{artifact_id}/{version}/{pom_filename}"


def fetch_pom_content(repo: str, mode: str, package: str) -> str:
    if mode == "url":
        url = build_pom_url(package)
        try:
            with urllib.request.urlopen(url) as response:
                return response.read().decode("utf-8")
        except Exception as e:
            raise RuntimeError(f"Failed to fetch POM from {url}: {e}")
    elif mode == "file":
        try:
            with open(repo, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            raise RuntimeError(f"Failed to read POM file {repo}: {e}")
    else:
        raise ValueError("Invalid mode")


def parse_dependencies_from_pom(pom_xml: str) -> List[str]:
    try:
        root = ET.fromstring(pom_xml)
    except ET.ParseError as e:
        raise RuntimeError(f"Invalid XML in POM: {e}")

    namespaces = {}
    if root.tag.startswith("{"):
        ns = root.tag[1:].split("}")[0]
        namespaces["maven"] = ns

    deps = []
    deps_path = ".//maven:dependency" if "maven" in namespaces else ".//dependency"
    for dep in root.findall(deps_path, namespaces):
        group_elem = dep.find("maven:groupId" if "maven" in namespaces else "groupId", namespaces)
        artifact_elem = dep.find("maven:artifactId" if "maven" in namespaces else "artifactId", namespaces)
        version_elem = dep.find("maven:version" if "maven" in namespaces else "version", namespaces)

        group = group_elem.text.strip() if group_elem is not None and group_elem.text else None
        artifact = artifact_elem.text.strip() if artifact_elem is not None and artifact_elem.text else None
        version = version_elem.text.strip() if version_elem is not None and version_elem.text else None

        if group and artifact:
            if not version:
                version = "unknown"
            deps.append(f"{group}:{artifact}:{version}")
    return deps


def main():
    parser = argparse.ArgumentParser(
        description="Visualize package dependency graph (Stage 2: Fetch direct dependencies)"
    )
    parser.add_argument(
        "--package",
        required=True,
        help="Package in format 'groupId:artifactId:version' (e.g., com.google.guava:guava:32.0.0-jre)"
    )
    parser.add_argument(
        "--repo",
        required=True,
        help="Path to local POM file (in 'file' mode) OR ignored in 'url' mode (uses Maven Central)"
    )
    parser.add_argument(
        "--test-mode",
        choices=["file", "url"],
        required=True,
        help="Mode: 'file' to read POM from local path, 'url' to fetch from Maven Central"
    )
    parser.add_argument(
        "--ascii-tree",
        action="store_true",
        help="Ignored in Stage 2 (reserved for future)"
    )
    parser.add_argument(
        "--filter",
        default="",
        help="Ignored in Stage 2 (reserved for future)"
    )

    args = parser.parse_args()

    if not validate_package_name(args.package):
        print("Error: --package must be in format 'groupId:artifactId:version'", file=sys.stderr)
        sys.exit(1)

    if not validate_repo(args.repo, args.test_mode):
        if args.test_mode == "file":
            print(f"Error: POM file not found: {args.repo}", file=sys.stderr)
        else:
            print(f"Error: Invalid URL provided: {args.repo}", file=sys.stderr)
        sys.exit(1)

    try:
        pom_content = fetch_pom_content(args.repo, args.test_mode, args.package)
        dependencies = parse_dependencies_from_pom(pom_content)
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    print("Direct dependencies:")
    if not dependencies:
        print("  (none)")
    for dep in dependencies:
        print(f"  {dep}")


if __name__ == "__main__":
    main()
