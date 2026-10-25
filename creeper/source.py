import base64
import hashlib
import json
import os
import re
import urllib.parse
import urllib.request
from pathlib import PurePosixPath


MAX_FILES = 100
MAX_SOURCE = 128 * 1024
MAX_TOTAL = 1024 * 1024


def safe_path(path):
    if not isinstance(path, str) or not path or "\\" in path or "\x00" in path:
        raise ValueError("invalid_source_path")
    parsed = PurePosixPath(path)
    if parsed.is_absolute() or ".." in parsed.parts or ".git" in parsed.parts or parsed.as_posix() != path or path == ".":
        raise ValueError("invalid_source_path")
    return path


def validate_sources(sources):
    if not isinstance(sources, list) or len(sources) > MAX_FILES:
        raise ValueError("source_file_limit")
    total = 0
    for source in sources:
        if not isinstance(source, dict) or "path" not in source or "content" not in source:
            raise ValueError("invalid_source_record")
        safe_path(source["path"])
        if not isinstance(source["content"], str):
            raise ValueError("source_must_be_text")
        size = len(source["content"].encode())
        total += size
        if size > MAX_SOURCE or total > MAX_TOTAL:
            raise ValueError("source_byte_limit")
    return sources


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, file_pointer, code, message, headers, new_url):
        raise ValueError("github_redirect_refused")


class GitHubSources:
    def __init__(self, repositories):
        self.repositories = set(repositories)
        self.opener = urllib.request.build_opener(NoRedirect)

    def get(self, endpoint):
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "arkham-creeper"}
        token = os.environ.get("CREEPER_GITHUB_TOKEN")
        if token:
            headers["Authorization"] = "Bearer " + token
        request = urllib.request.Request("https://api.github.com" + endpoint, headers=headers)
        with self.opener.open(request, timeout=20) as response:
            body = response.read(4 * 1024 * 1024 + 1)
        if len(body) > 4 * 1024 * 1024:
            raise ValueError("github_response_limit")
        result = json.loads(body)
        if not isinstance(result, dict):
            raise ValueError("invalid_github_response")
        return result

    def __call__(self, event, payload):
        repository = payload["repository"]["full_name"]
        if repository not in self.repositories or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
            raise ValueError("repository_not_allowed")
        prefix = "/repos/" + repository
        if event == "push":
            if payload.get("deleted"):
                return [], {"coverage": "branch_deleted", "repository": repository}
            before, after = payload["before"], payload["after"]
        else:
            if payload.get("action") not in {"opened", "synchronize", "reopened", "ready_for_review"}:
                return [], {"coverage": "event_ignored", "repository": repository}
            pull = payload["pull_request"]
            if pull["head"]["repo"]["full_name"] != repository:
                raise ValueError("fork_requires_explicit_review")
            before, after = pull["base"]["sha"], pull["head"]["sha"]
        if not all(isinstance(commit, str) and re.fullmatch(r"[0-9a-f]{40}", commit) for commit in (before, after)):
            raise ValueError("invalid_commit_sha")
        if before == "0" * 40:
            tree = self.get(prefix + "/git/trees/" + after + "?recursive=1")
            if not isinstance(tree, dict) or tree.get("truncated") is not False or not isinstance(tree.get("tree"), list):
                raise ValueError("incomplete_tree")
            files = []
            for entry in tree["tree"]:
                if not isinstance(entry, dict):
                    raise ValueError("invalid_tree_entry")
                path = safe_path(entry.get("path"))
                if entry.get("type") == "tree" and entry.get("mode") == "040000":
                    continue
                if entry.get("type") != "blob" or entry.get("mode") not in {"100644", "100755"}:
                    raise ValueError("unsupported_source_requires_review")
                files.append({"filename": path, "sha": entry.get("sha")})
        else:
            comparison = self.get(prefix + "/compare/" + before + "..." + after)
            if not isinstance(comparison, dict) or comparison.get("status") not in {"ahead", "identical"}:
                raise ValueError("non_linear_change_requires_review")
            changes = comparison.get("files")
            if not isinstance(changes, list):
                raise ValueError("incomplete_comparison")
            if len(changes) >= 300:
                raise ValueError("possibly_truncated_comparison")
            files = []
            for entry in changes:
                if not isinstance(entry, dict) or entry.get("status") not in {"added", "removed", "modified", "renamed", "copied", "changed", "unchanged"}:
                    raise ValueError("invalid_comparison_entry")
                safe_path(entry.get("filename"))
                if entry["status"] != "removed":
                    files.append(entry)
        if len(files) > MAX_FILES:
            raise ValueError("source_file_limit")
        sources = []
        seen = set()
        for entry in files:
            path = safe_path(entry["filename"])
            expected_sha = entry.get("sha")
            if path in seen or not isinstance(expected_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", expected_sha):
                raise ValueError("invalid_source_identity")
            seen.add(path)
            content = self.get(prefix + "/contents/" + urllib.parse.quote(path, safe="/") + "?ref=" + after)
            if not isinstance(content, dict) or content.get("type") != "file" or content.get("encoding") != "base64" or content.get("submodule_git_url") is not None:
                raise ValueError("unsupported_source_requires_review")
            if content.get("path") != path or content.get("sha") != expected_sha:
                raise ValueError("source_identity_mismatch")
            size = content.get("size")
            encoded = content.get("content")
            if type(size) is not int or size < 0 or size > MAX_SOURCE or not isinstance(encoded, str):
                raise ValueError("invalid_source_content")
            encoded = encoded.replace("\n", "")
            if len(encoded) > 4 * ((MAX_SOURCE + 2) // 3):
                raise ValueError("source_byte_limit")
            decoded = base64.b64decode(encoded, validate=True)
            actual_sha = hashlib.sha1(b"blob " + str(len(decoded)).encode() + b"\0" + decoded).hexdigest()
            if len(decoded) != size or actual_sha != expected_sha:
                raise ValueError("source_identity_mismatch")
            sources.append({"path": path, "content": decoded.decode("utf-8")})
            validate_sources(sources)
        return validate_sources(sources), {"coverage": "changed_text_files", "repository": repository, "before": before, "after": after}
