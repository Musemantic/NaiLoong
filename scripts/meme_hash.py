#!/usr/bin/env python3
"""GitHub Actions automation for meme image hashes and issue claim statuses."""

from __future__ import annotations

import base64
import copy
import datetime
import hashlib
import html
import http.client
import json
import os
import re
import sys
import time
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import Request, urlopen

try:
    from .validate_data import _pairs_without_duplicates, _validate_url
except ImportError:
    from validate_data import _pairs_without_duplicates, _validate_url


ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = os.environ.get("GITHUB_REPOSITORY", "lin-alg/NaiLoong")
API_ROOT = "https://api.github.com"
STATE_PATH = ".cache/meme-hash/state.json"
ISSUE_NUMBER = 1
MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_COMMENT_IMAGES = 5
MAX_DOWNLOAD_RETRIES = 4
DOWNLOAD_RETRY_BASE_SECONDS = 1
HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")
CLAIM_PATTERN = re.compile(r"\bMEME-CLAIM-[0-9a-f]{24}\b")
COMMENT_LINK_PATTERN = re.compile(
    r"https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)/issues/([0-9]+)#issuecomment-([0-9]+)",
    re.IGNORECASE,
)
MARKDOWN_IMAGE_PATTERN = re.compile(
    r"!\[[^\]]*\]\(\s*(?:<([^>]+)>|(https?://[^\s)>]+))[^)]*\)",
    re.IGNORECASE,
)
HTML_IMAGE_PATTERN = re.compile(r"<img\b[^>]*\bsrc=[\"']([^\"']+)[\"']", re.IGNORECASE)
HTML_IMAGE_TAG_PATTERN = re.compile(
    r"<img\b(?:[^>\"']|\"[^\"]*\"|'[^']*')*>", re.IGNORECASE
)
IMAGE_LINK_PATTERN = re.compile(
    MARKDOWN_IMAGE_PATTERN.pattern + "|"
    r"<img\b(?=[^>]*\bsrc=[\"']([^\"']+)[\"'])(?:[^>\"']|\"[^\"]*\"|'[^']*')*>",
    re.IGNORECASE,
)
STATUS_START = "<!-- nai-meme-hash-status:start -->"
STATUS_END = "<!-- nai-meme-hash-status:end -->"
STATUS_BLOCK_PATTERN = re.compile(
    re.escape(STATUS_START) + r".*?" + re.escape(STATUS_END) + r"\r?\n?", re.DOTALL
)
ATTACHMENT_HOSTS = {
    "github.com",
    "user-images.githubusercontent.com",
    "private-user-images.githubusercontent.com",
}
IMAGE_SIGNATURES = (
    b"\x89PNG\r\n\x1a\n",
    b"\xff\xd8\xff",
    b"GIF87a",
    b"GIF89a",
    b"BM",
    b"II*\x00",
    b"MM\x00*",
    b"RIFF",
    b"\x00\x00\x01\x00",
)


class BotError(RuntimeError):
    pass


class ImageTooLargeError(BotError):
    pass


class GitHubAPIError(BotError):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def empty_state():
    return {
        "version": 1,
        "ingested": [],
        "reserved": {},
        "comments": {},
        "pull_requests": {},
    }


def normalize_state(value):
    state = value if isinstance(value, dict) else empty_state()
    state.setdefault("version", 1)
    state.setdefault("ingested", [])
    state.setdefault("reserved", {})
    state.setdefault("comments", {})
    state.setdefault("pull_requests", {})
    if not isinstance(state["ingested"], list):
        state["ingested"] = []
    if not isinstance(state["reserved"], dict):
        state["reserved"] = {}
    if not isinstance(state["comments"], dict):
        state["comments"] = {}
    if not isinstance(state["pull_requests"], dict):
        state["pull_requests"] = {}
    return state


def parse_hash_file(text: str) -> set[str]:
    hashes = set()
    for line_number, line in enumerate(text.splitlines(), 1):
        value = line.strip().lower()
        if not value:
            continue
        if not HASH_PATTERN.fullmatch(value):
            raise BotError(f"hash.txt line {line_number} is not a SHA-256 digest")
        hashes.add(value)
    return hashes


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def find_duplicates(hashes, known_hashes):
    seen = set(known_hashes)
    duplicates = []
    for index, digest in enumerate(hashes, 1):
        if digest in seen:
            duplicates.append((index, digest))
        else:
            seen.add(digest)
    return duplicates


def parse_issue_image_urls(body: str) -> list[str]:
    body = html.unescape(body or "")
    return [next(group for group in match.groups() if group) for match in IMAGE_LINK_PATTERN.finditer(body)]


class _ArchivedImageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.url = None

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "img":
            self.url = dict(attrs).get("src")


def archive_comment_images(body: str) -> str:
    body = MARKDOWN_IMAGE_PATTERN.sub(lambda match: match.group(0)[1:], body)
    body = re.sub(r"(?<!\\)!\[((?:\\.|[^\]\\])*)\]", r"[\1]", body)

    def html_link(match):
        parser = _ArchivedImageParser()
        parser.feed(match.group(0))
        if not parser.url:
            return html.escape(match.group(0))
        url = parser.url.replace("<", "%3C").replace(">", "%3E")
        return f"[原图](<{url}>)"

    return HTML_IMAGE_TAG_PATTERN.sub(html_link, body)


def is_supported_image(data: bytes, content_type: str) -> bool:
    if data.startswith(b"RIFF"):
        return data[8:12] == b"WEBP"
    if any(data.startswith(signature) for signature in IMAGE_SIGNATURES if signature != b"RIFF"):
        return True
    if content_type.split(";", 1)[0].strip().lower() == "image/svg+xml":
        return b"<svg" in data[:8192].lower()
    return False


def validate_image_payload(data: bytes, content_type: str) -> None:
    if len(data) > MAX_IMAGE_BYTES:
        raise ImageTooLargeError("Image exceeds the 5 MB limit")
    if not is_supported_image(data, content_type):
        raise BotError("The attached file is not a supported image")


def added_canonical_urls(base_urls, head_urls):
    """Return URL occurrences added by a PR, preserving duplicate occurrences."""
    base_counts = Counter(base_urls)
    seen_counts = Counter()
    additions = []
    for url in head_urls:
        seen_counts[url] += 1
        if seen_counts[url] > base_counts[url]:
            additions.append(url)
    return additions


def github_image_url(url: str) -> str | None:
    errors = []
    canonical = _validate_url(url, "image URL", ROOT, errors)
    if errors:
        raise BotError(errors[0])
    if canonical.startswith("assets/placeholders/"):
        return None

    path_clean = urlsplit(canonical).path.lstrip("/")
    parts = path_clean.split("/")
    default_repo = REPOSITORY.split("/")[-1]

    # 适配: <Github用户名>/<40位commit>/assets/memes/xxx.gif
    if (
        len(parts) >= 3
        and len(parts[1]) == 40
        and all(c in "0123456789abcdefABCDEF" for c in parts[1])
    ):
        owner = parts[0]
        commit = parts[1]
        repo = default_repo
        file_path = "/".join(parts[2:])
        return f"https://raw.githubusercontent.com/{owner}/{repo}/{commit}/{file_path}"

    # 适配完整 GitHub 链接: owner/repo/raw(或blob)/commit/path
    if len(parts) >= 5 and parts[2] in {"raw", "blob"}:
        owner, repo = parts[0], parts[1]
        commit = parts[3]
        file_path = "/".join(parts[4:])
        return f"https://raw.githubusercontent.com/{owner}/{repo}/{commit}/{file_path}"

    # 适配标准的 raw 链接: owner/repo/commit/path
    if len(parts) >= 4:
        owner, repo, commit = parts[0], parts[1], parts[2]
        file_path = "/".join(parts[3:])
        return f"https://raw.githubusercontent.com/{owner}/{repo}/{commit}/{file_path}"

    raise BotError(f"无法解析图片 URL 格式: {canonical}")


class GitHub:
    def __init__(self):
        self.token = os.environ.get("GITHUB_TOKEN")
        if not self.token:
            raise BotError("GITHUB_TOKEN is required")
        self.repository = os.environ.get("GITHUB_REPOSITORY", REPOSITORY)

    def request(self, method: str, path: str, payload=None, accept=None):
        url = API_ROOT + path
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        request = Request(
            url,
            data=body,
            method=method,
            headers={
                "Accept": accept or "application/vnd.github+json",
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
                "User-Agent": "NaiLoong-meme-hash-bot",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        try:
            with urlopen(request, timeout=30) as response:
                data = response.read()
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise GitHubAPIError(exc.code, f"GitHub API {method} {path}: {detail}") from exc
        except URLError as exc:
            raise BotError(f"GitHub API request failed: {exc}") from exc
        if not data:
            return {}
        try:
            return json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BotError(f"GitHub API returned invalid JSON for {path}") from exc

    def get_optional(self, path: str):
        try:
            return self.request("GET", path)
        except GitHubAPIError as exc:
            if exc.status == 404:
                return None
            raise

    def read_contents(self, path: str, ref: str):
        quoted_path = quote(path, safe="/")
        query = urlencode({"ref": ref})
        item = self.get_optional(f"/repos/{self.repository}/contents/{quoted_path}?{query}")
        if item is None:
            return None, None
        if item.get("encoding") != "base64":
            raise BotError(f"GitHub Contents API did not return base64 content for {path}")
        text = base64.b64decode(item.get("content", "")).decode("utf-8")
        return text, item.get("sha")

    def read_content_item(self, path: str, ref: str):
        quoted_path = quote(path, safe="/")
        query = urlencode({"ref": ref})
        return self.get_optional(f"/repos/{self.repository}/contents/{quoted_path}?{query}")

    def write_contents(self, path: str, branch: str, text: str, message: str, sha=None):
        payload = {
            "message": message,
            "content": base64.b64encode(text.encode("utf-8")).decode("ascii"),
            "branch": branch,
        }
        if sha:
            payload["sha"] = sha
        quoted_path = quote(path, safe="/")
        return self.request("PUT", f"/repos/{self.repository}/contents/{quoted_path}", payload)

    def write_binary_contents(self, path: str, branch: str, content: bytes, message: str, sha=None):
        payload = {
            "message": message,
            "content": base64.b64encode(content).decode("ascii"),
            "branch": branch,
        }
        if sha:
            payload["sha"] = sha
        quoted_path = quote(path, safe="/")
        return self.request("PUT", f"/repos/{self.repository}/contents/{quoted_path}", payload)

    def get_ref(self, ref: str):
        return self.get_optional(f"/repos/{self.repository}/git/ref/{quote(ref, safe='/')}")

    def create_ref(self, ref: str, sha: str):
        return self.request(
            "POST",
            f"/repos/{self.repository}/git/refs",
            {"ref": f"refs/{ref}", "sha": sha},
        )

    def load_state(self):
        state_path = ROOT / STATE_PATH
        if not state_path.is_file():
            return empty_state(), None
        try:
            return normalize_state(json.loads(state_path.read_text(encoding="utf-8"))), None
        except (OSError, json.JSONDecodeError) as exc:
            raise BotError(f"{STATE_PATH} is invalid JSON") from exc

    def mutate_state(self, mutator):
        current, _ = self.load_state()
        updated = copy.deepcopy(current)
        outcome = mutator(updated)
        if updated != current:
            state_path = ROOT / STATE_PATH
            state_path.parent.mkdir(parents=True, exist_ok=True)
            state_path.write_text(
                json.dumps(updated, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                encoding="utf-8",
            )
        return outcome

    def list_meme_caches(self):
        caches = []
        page = 1
        while True:
            result = self.request(
                "GET",
                f"/repos/{self.repository}/actions/caches?per_page=100&page={page}",
            )
            items = result.get("actions_caches", [])
            caches.extend(items)
            if len(items) < 100:
                return caches
            page += 1

    def delete_cache(self, cache_id):
        self.request("DELETE", f"/repos/{self.repository}/actions/caches/{cache_id}")

    def cleanup_meme_caches(self, current_key):
        prefix = os.environ.get("MEME_HASH_CACHE_PREFIX", "meme-hash-state-")
        for item in self.list_meme_caches():
            key = item.get("key", "")
            if not key.startswith(prefix) or key == current_key:
                continue
            try:
                self.delete_cache(item["id"])
            except GitHubAPIError as exc:
                print(f"::warning::Could not delete old hash cache {item.get('id')}: {exc}")

    def main_hashes(self):
        text, _ = self.read_contents("hash.txt", "main")
        return parse_hash_file(text or "")

    def get_issue_comments(self, issue_number):
        return self.paginated(f"/repos/{self.repository}/issues/{issue_number}/comments")

    def get_pr_files(self, number, expected_head_sha=None):
        endpoint = f"/repos/{self.repository}/pulls/{number}"

        def check_head():
            if expected_head_sha:
                current = self.request("GET", endpoint)
                if (current.get("head") or {}).get("sha") != expected_head_sha:
                    raise BotError(f"PR #{number} changed while checking; retry the latest PR event")

        check_head()
        files = self.paginated(endpoint + "/files")
        check_head()
        return files

    def paginated(self, path):
        records = []
        page = 1
        while True:
            separator = "&" if "?" in path else "?"
            items = self.request("GET", f"{path}{separator}per_page=100&page={page}")
            if not items:
                return records
            records.extend(items)
            if len(items) < 100:
                return records
            page += 1

    def pr_file_json(self, repository, path, ref, allow_missing=False):
        encoded_path = quote(path, safe="/")
        query = urlencode({"ref": ref})
        endpoint = f"/repos/{repository}/contents/{encoded_path}?{query}"
        try:
            item = self.request("GET", endpoint)
        except GitHubAPIError as exc:
            if exc.status == 404 and allow_missing:
                return []
            raise
        if item.get("encoding") != "base64":
            raise BotError(f"Could not read PR file as base64: {path}")
        try:
            parsed = json.loads(
                base64.b64decode(item.get("content", "")),
                object_pairs_hook=_pairs_without_duplicates,
            )
        except (ValueError, json.JSONDecodeError) as exc:
            raise BotError(f"PR file is invalid JSON: {path}") from exc
        if not isinstance(parsed, list) or any(not isinstance(entry, dict) for entry in parsed):
            raise BotError(f"PR file must contain an array of meme objects: {path}")
        return parsed

    def read_blob_json(self, blob_sha):
        if not blob_sha:
            return []
        item = self.request("GET", f"/repos/{self.repository}/git/blobs/{blob_sha}")
        if item.get("encoding") != "base64":
            raise BotError(f"Could not read PR file blob as base64: {blob_sha}")
        try:
            parsed = json.loads(base64.b64decode(item.get("content", "")))
        except (ValueError, json.JSONDecodeError) as exc:
            raise BotError(f"PR file blob is invalid JSON: {blob_sha}") from exc
        if not isinstance(parsed, list):
            return []
        return [entry for entry in parsed if isinstance(entry, dict)]

    def issue_comment(self, issue_number, body):
        return self.request(
            "POST",
            f"/repos/{self.repository}/issues/{issue_number}/comments",
            {"body": body},
        )

    def edit_issue_comment(self, comment_id, body):
        return self.request(
            "PATCH",
            f"/repos/{self.repository}/issues/comments/{comment_id}",
            {"body": body},
        )

    def get_issue_comment(self, comment_id):
        return self.request(
            "GET",
            f"/repos/{self.repository}/issues/comments/{comment_id}",
            accept="application/vnd.github.full+json",
        )

    def find_marked_comment(self, issue_number, marker):
        for comment in self.get_issue_comments(issue_number):
            if marker in (comment.get("body") or ""):
                return comment
        return None

    def upsert_marked_comment(self, issue_number, marker, body, comment_id=None):
        full_body = f"{marker}\n{body}"
        if comment_id:
            try:
                return self.edit_issue_comment(comment_id, full_body)
            except GitHubAPIError as exc:
                if exc.status != 404:
                    raise
        existing = self.find_marked_comment(issue_number, marker)
        if existing:
            return self.edit_issue_comment(existing["id"], full_body)
        return self.issue_comment(issue_number, full_body)

    def minimize_comment(self, node_id, classifier="SPAM"):
        query = (
            "mutation($id: ID!) { minimizeComment(input: {subjectId: $id, "
            f"classifier: {classifier}" + "}) { minimizedComment { isMinimized } } }"
        )
        try:
            response = self.request("POST", "/graphql", {"query": query, "variables": {"id": node_id}})
            if response.get("errors"):
                print(f"::warning::Could not minimize issue comment: {response['errors']}")
        except GitHubAPIError as exc:
            print(f"::warning::Could not minimize issue comment: {exc}")

    def pr_status_comment(self, number, body, comment_id=None):
        marker = f"<!-- nai-meme-hash-pr:{number} -->"
        return self.upsert_marked_comment(number, marker, body, comment_id)


def fetch_image_bytes(url: str, attachment=False) -> bytes:
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower()
    if attachment:
        if host not in ATTACHMENT_HOSTS:
            raise BotError(f"Unsupported issue image host: {host or '(missing)'}")
        if host == "github.com" and not parsed.path.startswith("/user-attachments/assets/"):
            raise BotError("Issue images must be uploaded as GitHub comment attachments")
    elif host != "raw.githubusercontent.com":
        raise BotError("Fork images must be fetched from raw.githubusercontent.com")

    headers = {"User-Agent": "NaiLoong-meme-hash-bot", "Accept": "image/*"}
    request = Request(url, headers=headers)
    max_attempts = MAX_DOWNLOAD_RETRIES + 1
    for attempt in range(1, max_attempts + 1):
        try:
            with urlopen(request, timeout=25) as response:
                final = urlsplit(response.geturl())
                final_host = (final.hostname or "").lower()
                allowed = ATTACHMENT_HOSTS if attachment else {
                    "raw.githubusercontent.com", "objects.githubusercontent.com"
                }
                if final.scheme != "https" or final_host not in allowed:
                    raise BotError("GitHub image request redirected to an unsupported host")
                content_length = response.headers.get("Content-Length")
                if content_length and int(content_length) > MAX_IMAGE_BYTES:
                    raise ImageTooLargeError("Image exceeds the 5 MB limit")
                data = response.read(MAX_IMAGE_BYTES + 1)
                content_type = response.headers.get("Content-Type", "")
            validate_image_payload(data, content_type)
            return data
        except (ImageTooLargeError, BotError):
            raise
        except (HTTPError, URLError, TimeoutError, OSError, http.client.HTTPException) as exc:
            retryable = not isinstance(exc, HTTPError) or exc.code in {408, 425, 429} or exc.code >= 500
            if not retryable or attempt == max_attempts:
                raise BotError(f"Could not download image from {url}: {exc}") from exc
            print(
                f"::warning::Image download from {host} failed (attempt {attempt}/"
                f"{max_attempts}); retrying ({attempt}/{MAX_DOWNLOAD_RETRIES}): {exc}"
            )
            time.sleep(DOWNLOAD_RETRY_BASE_SECONDS * (2 ** (attempt - 1)))
    raise BotError(f"Could not download image from {url}")


def hash_attachment_urls(urls):
    hashes = []
    for url in urls:
        data = fetch_image_bytes(url, attachment=True)
        hashes.append(sha256_bytes(data))
    return hashes


def hash_fork_urls(urls):
    hashes = []
    for url in urls:
        raw_url = github_image_url(url)
        if raw_url is None:
            continue
        data = fetch_image_bytes(raw_url)
        hashes.append(sha256_bytes(data))
    return hashes


def canonical_urls_from_entries(entries, source="PR image URL"):
    urls = []
    for index, entry in enumerate(entries):
        value = entry.get("url")
        errors = []
        canonical = _validate_url(value, f"{source} entry #{index}", ROOT, errors)
        if errors:
            raise BotError(errors[0])
        if canonical.startswith("assets/placeholders/"):
            continue
        urls.append(canonical)
    return urls


def category_data_files(github: GitHub, repository, ref):
    """Discover meme arrays from the manifest at a fixed repository commit."""
    manifest = github.pr_file_json(repository, "data/manifest.json", ref)
    return manifest_category_files(manifest, ref)


def manifest_category_files(manifest, ref):
    if not manifest:
        raise BotError(f"data/manifest.json at {ref}: expected a non-empty role array")
    result = set()
    for role in manifest:
        categories = role.get("subcategories")
        if not isinstance(categories, list) or not categories:
            raise BotError(f"data/manifest.json at {ref}: expected non-empty subcategories")
        for category in categories:
            relative = category.get("file") if isinstance(category, dict) else None
            if not isinstance(relative, str) or not relative.strip():
                raise BotError(f"data/manifest.json at {ref}: category file must be a non-empty string")
            path = PurePosixPath(relative)
            if path.is_absolute() or ".." in path.parts or "\\" in relative or path.suffix != ".json":
                raise BotError(f"data/manifest.json at {ref}: invalid category file {relative!r}")
            result.add(PurePosixPath("data", path).as_posix())
    return result


def pr_data_changes(github: GitHub, pull_request):
    number = pull_request["number"]
    base = pull_request["base"]
    head = pull_request["head"]
    head_repo = (head.get("repo") or {}).get("full_name")
    if not head_repo:
        raise BotError("The PR head repository is unavailable")
    head_sha = head.get("sha")
    if not head_sha:
        raise BotError("The PR head commit SHA is unavailable")
    files = github.get_pr_files(number, expected_head_sha=head_sha)
    changes = {"files": files, "urls": [], "removed_urls": [], "categories": [], "head_sha": head_sha}
    if not any(item.get("filename", "").startswith("data/") and
               item.get("filename", "").endswith(".json") for item in files):
        return changes
    base_manifest = github.pr_file_json(REPOSITORY, "data/manifest.json", base["sha"])
    head_manifest = github.pr_file_json(head_repo, "data/manifest.json", head_sha)
    changes.update(base_manifest=base_manifest, head_manifest=head_manifest)
    base_categories = manifest_category_files(base_manifest, base["sha"])
    head_categories = manifest_category_files(head_manifest, head_sha)
    old_urls, new_urls = [], []
    for item in files:
        filename = item.get("filename", "")
        base_filename = item.get("previous_filename", filename)
        if base_filename not in base_categories and filename not in head_categories:
            continue
        base_entries = []
        head_entries = []
        if base_filename in base_categories and item.get("status") != "added":
            base_entries = github.pr_file_json(REPOSITORY, base_filename, base["sha"])
        if filename in head_categories and item.get("status") != "removed":
            head_entries = github.pr_file_json(head_repo, filename, head_sha)
        old_urls.extend(canonical_urls_from_entries(base_entries, base_filename))
        new_urls.extend(canonical_urls_from_entries(head_entries, filename))
        changes["categories"].append((base_filename, filename, base_entries, head_entries))
    # Compare across files so moving an entry between categories is not a new image.
    changes["urls"] = added_canonical_urls(old_urls, new_urls)
    changes["removed_urls"] = added_canonical_urls(new_urls, old_urls)
    return changes


def new_data_urls(github: GitHub, pull_request):
    return pr_data_changes(github, pull_request)["urls"]


def hash_text(github: GitHub):
    text, _ = github.read_contents("hash.txt", "main")
    return parse_hash_file(text or "")


def issue_comment_url(comment_id):
    return f"https://github.com/{REPOSITORY}/issues/{ISSUE_NUMBER}#issuecomment-{comment_id}"


def issue_status_body(status, hashes=None, claim_code=None, pr_number=None, comment_id=None, note=None):
    if status == "unprocessed":
        if comment_id:
            reference = (
                f"认领链接：[直接复制此评论的链接]({issue_comment_url(comment_id)})\n"
                "贡献者请在 PR 描述中粘贴此链接；一个 PR 可以认领多条评论，"
                "并需包含每条评论中的全部图片。"
            )
            if claim_code:
                reference += f"\n兼容旧格式：旧认领口令 `{claim_code}` 仍然有效。"
            text = f"[ ⚪ 未处理 ]\n\n{reference}"
            return f"{text}\n\n{note}" if note else text
        text = (
            "[ ⚪ 未处理 ]\n\n"
            + (
                f"旧认领口令：`{claim_code}`\n"
                "处理者也可以直接粘贴这条评论的 GitHub 链接；"
                "一个 PR 需包含该评论中的全部图片。"
                if claim_code
                else "处理者请粘贴这条评论的 GitHub 链接到 PR 描述；一个 PR 需包含该评论中的全部图片。"
            )
        )
        return f"{text}\n\n{note}" if note else text
    if status == "processing":
        text = f"[ 🟡 处理中 ]\n\n已由 [PR #{pr_number}](https://github.com/{REPOSITORY}/pull/{pr_number}) 认领。"
        return f"{text}\n\n{note}" if note else text
    if status == "ingested":
        link = f"\n\n已由 [PR #{pr_number}](https://github.com/{REPOSITORY}/pull/{pr_number}) 合并入库。" if pr_number else ""
        text = f"[ 🟢 已入库 ]{link}"
        return f"{text}\n\n{note}" if note else text
    if status == "oversize":
        return "[ 🔴 图片过大 ]\n\n单张图片严格不能超过 5 MB；请压缩图片后编辑这条评论。"
    duplicate_text = ", ".join(f"第 {index} 张（SHA256 `{digest[:12]}…`）" for index, digest in hashes or [])
    return (
        "[ 🔴 重复图片 ]\n"
        f"发现重复图片：{duplicate_text}。没有图片被占位。请编辑这条评论，移除重复图片后重新提交。"
    )


def strip_status_block(body: str) -> str:
    return STATUS_BLOCK_PATTERN.sub("", body or "", count=1).lstrip("\r\n")


def comment_status(body: str) -> str | None:
    match = STATUS_BLOCK_PATTERN.match(body or "")
    if not match:
        return None
    block = match.group(0)
    for status, label in (
        ("ingested", "[ 🟢 已入库 ]"),
        ("processing", "[ 🟡 处理中 ]"),
        ("unprocessed", "[ ⚪ 未处理 ]"),
        ("oversize", "[ 🔴 图片过大 ]"),
    ):
        if label in block:
            return status
    return "duplicate" if "[ 🔴 重复图片 ]" in block else None


def issue_comment_reply(github: GitHub, comment_id, state, status, hashes=None):
    record = state.get("comments", {}).get(str(comment_id), {})
    try:
        current = github.get_issue_comment(comment_id)
    except GitHubAPIError as exc:
        if exc.status == 404:
            return None
        raise
    original_body = strip_status_block(current.get("body", ""))
    if status == "ingested":
        original_body = archive_comment_images(original_body)
    status_text = issue_status_body(
        status,
        hashes,
        record.get("claim_code"),
        record.get("pr_number"),
        comment_id,
        record.get("note"),
    )
    body = f"{STATUS_START}\n{status_text}\n{STATUS_END}\n\n{original_body}"
    try:
        updated = github.edit_issue_comment(comment_id, body) if body != current.get("body") else current
    except GitHubAPIError as exc:
        if exc.status == 404:
            return None
        raise
    if status == "ingested" and current.get("node_id"):
        github.minimize_comment(current["node_id"], classifier="RESOLVED")
    return updated


def release_comment_reservations(state, comment_id):
    for digest, reservation in list(state["reserved"].items()):
        if reservation.get("comment_id") == str(comment_id):
            state["reserved"].pop(digest)


def release_pr_reservations(state, number, hashes=None):
    for digest, reservation in list(state["reserved"].items()):
        if str(reservation.get("pr_number")) != str(number):
            continue
        if hashes is not None and digest not in hashes:
            continue
        if reservation.get("comment_id"):
            if str(reservation["comment_id"]) in state["comments"]:
                reservation["pr_number"] = None
            else:
                state["reserved"].pop(digest)
        else:
            state["reserved"].pop(digest)


def reset_issue_comment_after_pr(state, comment_id):
    comment_key = str(comment_id)
    record = state["comments"].get(comment_key)
    if not record:
        return
    if record.get("deleted"):
        release_comment_reservations(state, comment_key)
        if any(item["phase"] == "processing" for item in record.get("takeovers", [])):
            record.update(hashes=[], pr_number=None, comment_update_pending=True)
            refresh_transferred_comment(record)
        else:
            state["comments"].pop(comment_key, None)
        return
    record["status"] = "unprocessed"
    record["pr_number"] = None
    if record.get("returned_hashes"):
        record["hashes"] = sorted(set(record.get("hashes", [])) | set(record.pop("returned_hashes")))
    if record.get("takeovers"):
        record["comment_update_pending"] = True
        refresh_transferred_comment(record)


def handle_deleted_issue_comment(github: GitHub, comment_id):
    comment_id = str(comment_id)

    def update(state):
        record = state["comments"].get(comment_id)
        if record and (record.get("pr_number") or any(
            item["phase"] == "processing" for item in record.get("takeovers", [])
        )):
            # Keep the reservation while the already-open PR is under review.
            record["deleted"] = True
            for digest, reservation in list(state["reserved"].items()):
                if reservation.get("comment_id") == comment_id and not reservation.get("pr_number"):
                    state["reserved"].pop(digest)
            if not record.get("pr_number"):
                record["hashes"] = []
            return
        release_comment_reservations(state, comment_id)
        state["comments"].pop(comment_id, None)

    github.mutate_state(update)


def handle_issue_comment(github: GitHub, event):
    issue = event.get("issue") or {}
    comment = event.get("comment") or {}
    if issue.get("number") != ISSUE_NUMBER or issue.get("pull_request"):
        return
    if (comment.get("user") or {}).get("type") == "Bot":
        return
    if event.get("action") == "edited" and (event.get("sender") or {}).get("type") == "Bot":
        return
    if event.get("action") == "deleted":
        if comment.get("id") is None:
            raise BotError("Deleted issue comment event is missing the comment ID")
        handle_deleted_issue_comment(github, comment["id"])
        return

    sync_comment_takeovers(github)
    full_comment = github.get_issue_comment(comment["id"])
    comment_body = full_comment.get("body", comment.get("body", ""))
    html_body = full_comment.get("body_html") or ""
    urls = parse_issue_image_urls(html_body or comment_body)
    initial_state, _ = github.load_state()
    previous = initial_state["comments"].get(str(comment["id"]), {})
    if previous.get("status") == "transferred":
        sync_comment_takeovers(github)
        return
    if previous.get("status") == "ingested":
        issue_comment_reply(github, comment["id"], initial_state, "ingested")
        return
    if previous.get("status") == "processing":
        print(f"Issue comment {comment['id']} is already claimed or ingested; leaving its status unchanged.")
        return
    if not urls:
        if previous:
            comment_id = str(comment["id"])

            def release_empty_comment(state):
                old = state["comments"].get(comment_id)
                if not old or old.get("status") == "processing":
                    return
                release_comment_reservations(state, comment_id)
                if old.get("takeovers"):
                    old["hashes"] = []
                    old["remaining_images"] = []
                    old["comment_update_pending"] = True
                    refresh_transferred_comment(old)
                else:
                    state["comments"].pop(comment_id, None)

            github.mutate_state(release_empty_comment)
            if previous.get("takeovers"):
                sync_comment_takeovers(github)
            else:
                github.edit_issue_comment(comment["id"], strip_status_block(comment_body))
        return
    try:
        if len(urls) > MAX_COMMENT_IMAGES:
            raise BotError(f"A comment may contain at most {MAX_COMMENT_IMAGES} images")
        hashes = hash_attachment_urls(urls)
    except ImageTooLargeError as exc:
        comment_id = str(comment["id"])

        def release_oversize_comment(state):
            existing = state["comments"].get(comment_id)
            if existing:
                release_comment_reservations(state, comment_id)
                existing["hashes"] = []
                existing["claim_code"] = None
                existing["status"] = "oversize"
                existing["pr_number"] = None

        github.mutate_state(release_oversize_comment)
        issue_comment_reply(
            github,
            comment["id"],
            _current_state(github),
            "oversize",
        )
        print(f"::warning::{exc}")
        return
    except BotError as exc:
        current = github.get_issue_comment(comment["id"])
        original_body = strip_status_block(current.get("body", ""))
        github.edit_issue_comment(
            comment["id"],
            f"{STATUS_START}\n[ ⚪ 未处理 ]\n机器人暂时无法处理图片：{exc}。请检查图片后编辑评论重试。\n{STATUS_END}\n\n{original_body}",
        )
        print(f"::warning::{exc}")
        return

    comment_id = str(comment["id"])
    result = {}

    def update(state):
        result.clear()
        known_main = hash_text(github)
        existing = state["comments"].get(comment_id, {})
        if existing.get("pr_number"):
            result["status"] = "processing"
            return

        known = known_main | set(state["ingested"])
        known.update(
            digest
            for digest, reservation in state["reserved"].items()
            if reservation.get("comment_id") != comment_id
        )
        duplicates = find_duplicates(hashes, known)
        release_comment_reservations(state, comment_id)

        if duplicates:
            state["comments"][comment_id] = {
                **existing,
                "hashes": [],
                "claim_code": None,
                "status": "duplicate",
            }
            result.update(status="duplicate", duplicates=duplicates)
            return

        # New comments use their stable GitHub comment URL. Keep a previously
        # issued code only so old PRs can continue to be checked.
        code = existing.get("claim_code")
        state["comments"][comment_id] = {
            **existing,
            "hashes": sorted(set(hashes)),
            "claim_code": code,
            "status": "unprocessed",
            "pr_number": None,
        }
        matches = list(IMAGE_LINK_PATTERN.finditer(comment_body))
        if len(matches) == len(hashes):
            state["comments"][comment_id]["remaining_images"] = [
                {"hash": digest, "markdown": matches[index].group(0)}
                for index, digest in enumerate(hashes)
            ]
        for digest in set(hashes):
            state["reserved"][digest] = {
                "kind": "issue_comment",
                "comment_id": comment_id,
                "claim_code": code,
                "pr_number": None,
            }
        result.update(status="unprocessed", duplicates=[])

    github.mutate_state(update)
    if result.get("status") == "processing":
        return
    status = result["status"]
    issue_comment_reply(github, comment["id"], _current_state(github), status, result.get("duplicates"))
    if status == "duplicate" and len(urls) == 1 and comment.get("node_id"):
        github.issue_comment(
            ISSUE_NUMBER,
            "这条评论中的图片与已入库或已认领的图片重复，机器人已折叠原评论。"
            "请移除重复图片后编辑评论或重新投稿。",
        )
        github.minimize_comment(comment["node_id"])


def _current_state(github):
    state, _ = github.load_state()
    return state


def find_claim_comment(state, claim_code):
    matches = [
        (comment_id, record)
        for comment_id, record in state["comments"].items()
        if record.get("claim_code") == claim_code
    ]
    if len(matches) != 1:
        return None, None
    return matches[0]


def parse_claim_comment_links(body):
    links = []
    repository = REPOSITORY.lower()
    for match in COMMENT_LINK_PATTERN.finditer(body or ""):
        owner, repo, issue_number, comment_id = match.groups()
        if f"{owner}/{repo}".lower() != repository or issue_number != str(ISSUE_NUMBER):
            raise BotError(
                "PR description contains an issue comment link from the wrong repository or issue"
            )
        links.append((comment_id, match.group(0)))
    return links


def pull_request_comment_ids(record):
    ids = record.get("issue_comment_ids")
    if isinstance(ids, list):
        return [str(comment_id) for comment_id in ids if comment_id is not None]
    old_id = record.get("issue_comment_id")
    return [str(old_id)] if old_id is not None else []


def pr_duplicate_errors(hashes, state, main_hashes, number, allowed_comment_ids=None,
                        replacement_hashes=None):
    known = set(main_hashes) | set(state["ingested"])
    replacements = Counter(replacement_hashes or [])
    result = []
    seen = set()
    for index, digest in enumerate(hashes, 1):
        if digest in seen:
            result.append((index, digest, "repeated in this PR"))
        else:
            seen.add(digest)
        if digest in known:
            if replacements[digest]:
                replacements[digest] -= 1
            else:
                result.append((index, digest, "already ingested"))

    pr_key = str(number)
    if allowed_comment_ids is None:
        allowed_comment_ids = set()
    elif isinstance(allowed_comment_ids, str):
        allowed_comment_ids = {allowed_comment_ids}
    else:
        allowed_comment_ids = {str(comment_id) for comment_id in allowed_comment_ids}
    for index, digest in enumerate(hashes, 1):
        reservation = state["reserved"].get(digest)
        if not reservation:
            continue
        if str(reservation.get("pr_number")) == pr_key:
            continue
        if reservation.get("pr_number") is not None:
            result.append((index, digest, "reserved by another PR"))
            continue
        if str(reservation.get("comment_id")) in allowed_comment_ids:
            continue
        if reservation.get("comment_id"):
            continue  # An unclaimed comment yields to a complete PR submission.
        result.append((index, digest, "reserved by another submission"))
    return result


def prepare_comment_takeovers(github, hashes, allowed_comment_ids):
    """Read and verify comment contents before any reservation is transferred."""
    state = _current_state(github)
    conflicts = {}
    for digest in set(hashes):
        reservation = state["reserved"].get(digest, {})
        comment_id = reservation.get("comment_id")
        if (comment_id and str(comment_id) not in allowed_comment_ids and
                reservation.get("pr_number") is None):
            conflicts.setdefault(str(comment_id), set()).add(digest)
    transfers = {}
    for comment_id, conflict_hashes in conflicts.items():
        try:
            comment = github.get_issue_comment(comment_id)
        except GitHubAPIError as exc:
            if exc.status != 404:
                raise
            transfers[comment_id] = {
                "deleted": True, "remaining_images": [],
                "images": [{"hash": digest, "markdown": ""} for digest in sorted(conflict_hashes)],
            }
            continue
        body = comment.get("body", "")
        urls = parse_issue_image_urls(body)
        download_urls = parse_issue_image_urls(comment.get("body_html") or body)
        if len(urls) != len(download_urls):
            raise BotError("Issue comment image rendering changed; retry after editing the comment")
        image_hashes = hash_attachment_urls(download_urls)
        if not conflict_hashes.issubset(image_hashes):
            raise BotError("Issue comment images changed since reservation; recheck the comment first")
        indexes = [index for index, digest in enumerate(image_hashes) if digest in conflict_hashes]
        matches = list(IMAGE_LINK_PATTERN.finditer(body))
        transfers[comment_id] = {
            "images": [
                {"hash": image_hashes[index], "markdown": matches[index].group(0)}
                for index in indexes
            ],
            "remaining_images": [
                {"hash": digest, "markdown": matches[index].group(0)}
                for index, digest in enumerate(image_hashes) if index not in indexes
            ],
        }
    return transfers


def refresh_transferred_comment(record):
    active = [item for item in record.get("takeovers", []) if item["phase"] == "processing"]
    if record.get("pr_number"):
        record["status"] = "processing"
    elif record.get("hashes"):
        record["status"] = "unprocessed"
    elif active:
        record["status"] = "transferred"
    else:
        record["status"] = "ingested"
    references = sorted({item["pr_number"] for item in active})
    record["note"] = (
        "重复图片已由 " + "、".join(f"PR #{number}" for number in references) + " 优先处理。"
        if references else None
    )


def settle_comment_takeovers(state, number, merged=False, keep_hashes=None):
    for comment_id, record in list(state["comments"].items()):
        for transfer in list(record.get("takeovers", [])):
            if transfer["pr_number"] != number or transfer["phase"] != "processing":
                continue
            released = [image for image in transfer["images"]
                        if keep_hashes is None or image["hash"] not in keep_hashes]
            if not released:
                continue
            if len(released) != len(transfer["images"]):
                transfer["images"] = [image for image in transfer["images"] if image not in released]
                transfer = {"pr_number": number, "images": released}
                record["takeovers"].append(transfer)
            transfer.update(phase="ingested" if merged else "released", pending=True)
            if merged:
                for image in released:
                    state["ingested"] = sorted(set(state["ingested"]) | {image["hash"]})
                    reservation = state["reserved"].get(image["hash"])
                    if reservation and reservation.get("comment_id") == comment_id:
                        state["reserved"].pop(image["hash"], None)
            if not merged and not record.get("deleted"):
                for image in released:
                    digest = image["hash"]
                    if digest in state["reserved"] or digest in state["ingested"]:
                        continue
                    state["reserved"][digest] = {
                        "kind": "issue_comment", "comment_id": comment_id,
                        "pr_number": None, "claim_code": record.get("claim_code"),
                    }
                    # Do not change another PR's exact claim while restoring an
                    # earlier takeover from the same multi-image comment.
                    key = "returned_hashes" if record.get("pr_number") else "hashes"
                    record[key] = sorted(set(record.get(key, [])) | {digest})
                    if image not in record.setdefault("remaining_images", []):
                        record["remaining_images"].append(image)
            refresh_transferred_comment(record)
        if record.get("takeovers"):
            refresh_transferred_comment(record)


def sync_comment_takeovers(github, number=None):
    """Retry comment edits after their intended state has reached the cache."""
    for comment_id, record in _current_state(github)["comments"].items():
        transfers = [item for item in record.get("takeovers", [])
                     if item.get("pending") and (number is None or item["pr_number"] == number)]
        if not transfers and not record.get("links_to_archive") and not record.get("comment_update_pending"):
            continue
        try:
            current = github.get_issue_comment(comment_id)
        except GitHubAPIError as exc:
            if exc.status != 404:
                raise
            current = None
        if current:
            body = strip_status_block(current.get("body", ""))
            for transfer in transfers:
                for image in transfer["images"]:
                    syntax = image["markdown"]
                    if transfer["phase"] == "processing":
                        body = body.replace(syntax, "", 1)
                    elif transfer["phase"] == "released":
                        if syntax not in body:
                            body = body.rstrip() + "\n\n" + syntax
                    else:
                        body = body.replace(syntax, "", 1)
                        link = archive_comment_images(syntax)
                        if link not in body:
                            body = body.rstrip() + "\n\n" + link
            for syntax in record.get("links_to_archive", []):
                body = body.replace(syntax, archive_comment_images(syntax), 1)
            active = [item for item in record.get("takeovers", []) if item["phase"] == "processing"]
            pr_number = record.get("pr_number") or (active[0]["pr_number"] if active else number)
            status = "processing" if record["status"] == "transferred" else record["status"]
            text = issue_status_body(status, claim_code=record.get("claim_code"),
                                     pr_number=pr_number, comment_id=comment_id, note=record.get("note"))
            updated = f"{STATUS_START}\n{text}\n{STATUS_END}\n\n{body}"
            if updated != current.get("body"):
                github.edit_issue_comment(comment_id, updated)
            if status == "ingested" and current.get("node_id"):
                github.minimize_comment(current["node_id"], classifier="RESOLVED")

        def finish(state):
            saved = state["comments"].get(comment_id)
            if not saved:
                return
            for item in saved.get("takeovers", []):
                if number is None or item["pr_number"] == number:
                    item["pending"] = False
            saved["takeovers"] = [item for item in saved.get("takeovers", [])
                                  if item["phase"] != "released" or item.get("pending")]
            saved.pop("links_to_archive", None)
            saved.pop("comment_update_pending", None)
            if saved.get("deleted") and not saved.get("pr_number") and not any(
                item["phase"] == "processing" for item in saved["takeovers"]
            ):
                state["comments"].pop(comment_id, None)

        github.mutate_state(finish)


def duplicate_pr_message(duplicates):
    detail = "; ".join(
        f"image {index} `{digest[:12]}…` ({reason})"
        for index, digest, reason in duplicates
    )
    return (
        f"Duplicate or reserved images found: {detail}. No new hashes were reserved. "
        "Remove or replace the repeated image, then update this PR."
    )


def summary_label(value):
    text = re.sub(r"\s+", " ", str(value))[:80]
    return re.sub(r"([\\`*_\[\]<>|])", r"\\\1", text)


def entry_changes(changes):
    old = [(path, entry) for path, _, entries, _ in changes.get("categories", []) for entry in entries]
    new = [(path, entry) for _, path, _, entries in changes.get("categories", []) for entry in entries]
    pairs = []

    def canonical(record):
        errors = []
        value = _validate_url(record[1].get("url"), "summary image URL", ROOT, errors)
        return value or str(record[1].get("url", ""))

    # Stable URL is the entry identity; insertion and sorting must not create
    # false edits. Unique titles also pair source URL replacements.
    for key in (canonical, lambda record: str(record[1].get("title", ""))):
        old_map, new_map = {}, {}
        for record in old:
            old_map.setdefault(key(record), []).append(record)
        for record in new:
            new_map.setdefault(key(record), []).append(record)
        matched_old, matched_new = set(), set()
        for value in sorted(old_map.keys() & new_map.keys()):
            old_matches, new_matches = old_map[value], new_map[value]
            if len(old_matches) != 1 or len(new_matches) != 1:
                continue
            before, after = old_matches[0], new_matches[0]
            matched_old.add(id(before))
            matched_new.add(id(after))
            pairs.append((before, after))
        old = [record for record in old if id(record) not in matched_old]
        new = [record for record in new if id(record) not in matched_new]
    return old, new, pairs


def pr_change_summary(changes):
    lines = ["### 本次 PR 变更摘要", ""]
    old_roles = {role["id"]: role for role in changes.get("base_manifest", [])
                 if isinstance(role.get("id"), str)}
    new_roles = {role["id"]: role for role in changes.get("head_manifest", [])
                 if isinstance(role.get("id"), str)}
    for label, ids, manifest in (
            ("新增角色", new_roles.keys() - old_roles.keys(), new_roles),
            ("删除角色", old_roles.keys() - new_roles.keys(), old_roles),
            ("修改角色", {key for key in old_roles.keys() & new_roles.keys()
                          if {k: v for k, v in old_roles[key].items() if k != "subcategories"}
                          != {k: v for k, v in new_roles[key].items() if k != "subcategories"}}, new_roles)):
        if ids:
            names = [summary_label(manifest[key].get("name", key)) for key in sorted(ids)]
            lines.append(f"- {label}：{len(ids)} 个（{'、'.join(names[:10])}{'等' if len(ids) > 10 else ''}）")

    def categories(roles):
        return {(role_id, category.get("id")): category for role_id, role in roles.items()
                for category in role.get("subcategories", []) if isinstance(category.get("id"), str)}

    old_categories, new_categories = categories(old_roles), categories(new_roles)
    for label, count in (
            ("新增分类", len(new_categories.keys() - old_categories.keys())),
            ("删除分类", len(old_categories.keys() - new_categories.keys())),
            ("修改分类", sum(old_categories[key] != new_categories[key]
                             for key in old_categories.keys() & new_categories.keys()))):
        if count:
            lines.append(f"- {label}：{count} 个")

    removed, added, pairs = entry_changes(changes)
    modified = [(before, after) for before, after in pairs if before[1] != after[1]]
    for label, count in (("新增条目", len(added)), ("删除条目", len(removed)),
                         ("修改条目", len(modified)),
                         ("条目标签修改", sum(a[1].get("tags") != b[1].get("tags") for a, b in modified)),
                         ("条目标题修改", sum(a[1].get("title") != b[1].get("title") for a, b in modified)),
                         ("图片来源 URL 修改", sum(a[1].get("url") != b[1].get("url") for a, b in modified)),
                         ("条目分类或文件迁移", sum(a[0] != b[0] for a, b in pairs))):
        if count:
            lines.append(f"- {label}：{count} 条")

    tag_paths = {"data/tag-translations.json"}
    voice_paths = set()
    for role in list(old_roles.values()) + list(new_roles.values()):
        tag_path = role.get("tags", f"{role['id']}/tags.json")
        if isinstance(tag_path, str):
            tag_paths.add("data/" + tag_path)
        if isinstance(role.get("voice"), str):
            voice_paths.add("data/" + role["voice"])
    files = changes.get("files", [])
    for label, paths in (("标签定义或翻译文件", tag_paths), ("角色语音文件", voice_paths),
                         ("桌宠配置", {"data/pet.json"})):
        affected = [item for item in files if item.get("filename") in paths
                    or item.get("previous_filename") in paths]
        if affected:
            lines.append(f"- {label}变更：{len(affected)} 个")
    described_paths = tag_paths | voice_paths | {"data/manifest.json", "data/pet.json"}
    described_paths.update(path for old_path, new_path, _, _ in changes.get("categories", [])
                           for path in (old_path, new_path))
    extra_data = [item for item in files if item.get("filename", "").startswith("data/")
                  and item.get("filename") not in described_paths
                  and item.get("previous_filename") not in described_paths]
    if extra_data:
        lines.append(f"- 其他数据或配置文件变更：{len(extra_data)} 个")
    other_files = [item for item in files if not item.get("filename", "").startswith("data/")]
    if other_files:
        lines.append(f"- 项目代码、文档或其他文件变更：{len(other_files)} 个")
    if len(lines) == 2:
        lines.append("- 没有新增、删除或修改表情条目、角色及分类。")
    head_sha = changes.get("head_sha")
    if head_sha:
        lines.extend(["", f"检查版本：`{head_sha}`。数据格式及标签有效性以 Data Linter 为准。"])
    return "\n".join(lines)


def pr_check_message(summary, passed=True, detail=None):
    heading = "[ ✅ Image hash check passed ]" if passed else "[ ❌ Image hash check failed ]"
    body = f"{heading}\n\n{summary}"
    if detail:
        body += f"\n\n{detail}"
    return body


def process_pull_request(github: GitHub, pull_request):
    number = int(pull_request["number"])
    if (pull_request.get("base") or {}).get("ref") != "main":
        print(f"PR #{number} does not target main; hash check is skipped.")
        return
    summary = "### 本次 PR 变更摘要\n\n数据读取失败，暂时无法生成摘要。"
    try:
        changes = pr_data_changes(github, pull_request)
        summary = pr_change_summary(changes)
        _process_pull_request(github, pull_request, changes, summary)
    except BotError as exc:
        if isinstance(exc, ImageTooLargeError):
            comment_ids = release_pull_request_state(github, number)
            for comment_id in comment_ids:
                issue_comment_reply(github, comment_id, _current_state(github), "unprocessed")
        github.pr_status_comment(number, pr_check_message(summary, passed=False, detail=str(exc)))
        raise


def _process_pull_request(github, pull_request, changes, summary):
    number = int(pull_request["number"])
    sync_comment_takeovers(github)
    urls = changes["urls"]
    pr_body = pull_request.get("body") or ""
    claim_matches = CLAIM_PATTERN.findall(pr_body)
    claim_links = parse_claim_comment_links(pr_body)
    unique_claim_matches = list(dict.fromkeys(claim_matches))
    unique_claim_links = list(dict.fromkeys(claim_links))
    if len(unique_claim_matches) > 1:
        raise BotError("PR description contains more than one legacy claim code")
    if not urls and not unique_claim_matches and not unique_claim_links:
        state, _ = github.load_state()
        if str(number) not in state["pull_requests"]:
            print(f"PR #{number} does not add meme image URLs; hash check has nothing to reserve.")
            sync_comment_takeovers(github, number)
            github.pr_status_comment(number, pr_check_message(summary))
            return
    hashes = hash_fork_urls(urls)
    known = hash_text(github) | set(_current_state(github)["ingested"])
    replacement_hashes = []
    if known.intersection(hashes):
        # Removed references provide a one-for-one allowance for the same
        # content at a new URL, even when title/tags/order changed as well.
        replacement_hashes = hash_fork_urls(changes.get("removed_urls", []))
    claim_code = unique_claim_matches[0] if unique_claim_matches else None
    result = {}

    def update(state):
        result.clear()
        main_hashes = hash_text(github)
        pr_key = str(number)
        previous = state["pull_requests"].get(pr_key, {})
        previous_comment_ids = pull_request_comment_ids(previous)

        def release_previous():
            if previous_comment_ids:
                result["released_comment_ids"] = previous_comment_ids
            release_pr_reservations(state, number)
            settle_comment_takeovers(state, number)
            for previous_comment_id in previous_comment_ids:
                old_comment = state["comments"].get(str(previous_comment_id))
                if old_comment and old_comment.get("pr_number") == number:
                    reset_issue_comment_after_pr(state, previous_comment_id)
            state["pull_requests"].pop(pr_key, None)

        if previous_comment_ids and not (claim_code or unique_claim_links):
            release_previous()
            result.update(ok=False, reason="Keep at least one issue comment link in the PR description.")
            return

        issue_comment_ids = [comment_id for comment_id, _ in unique_claim_links]
        if claim_code:
            legacy_comment_id, _ = find_claim_comment(state, claim_code)
            if not legacy_comment_id:
                release_previous()
                result.update(ok=False, reason="The legacy issue claim code is unknown or expired.")
                return
            issue_comment_ids.append(str(legacy_comment_id))
        issue_comment_ids = list(dict.fromkeys(issue_comment_ids))
        issue_records = []
        for issue_comment_id in issue_comment_ids:
            issue_record = state["comments"].get(str(issue_comment_id))
            if issue_record is None:
                release_previous()
                result.update(ok=False, reason="One of the issue comment links or claim codes is unknown or expired.")
                return
            if issue_record.get("status") == "ingested":
                release_previous()
                result.update(ok=False, reason="One of the issue submissions is already merged.")
                return
            if issue_record.get("status") == "transferred" and not issue_record.get("hashes"):
                release_previous()
                result.update(ok=False, reason="All images in one of the issue comments are already being processed by PRs.")
                return
            if issue_record.get("pr_number") not in (None, number):
                release_previous()
                result.update(ok=False, reason="One of the issue submissions is already claimed by another PR.")
                return
            issue_records.append(issue_record)

        expected_hashes = set()
        for issue_record in issue_records:
            expected_hashes.update(issue_record.get("hashes", []))
        if issue_records and set(hashes) != expected_hashes:
            release_previous()
            result.update(
                ok=False,
                reason="The PR image hashes must exactly match all images in the claimed issue comments.",
            )
            return

        allowed_comment_ids = set(issue_comment_ids)
        duplicates = pr_duplicate_errors(
            hashes, state, main_hashes, number, allowed_comment_ids, replacement_hashes
        )
        if duplicates:
            release_previous()
            result.update(ok=False, duplicates=duplicates)
            return

        transfers = prepare_comment_takeovers(github, hashes, allowed_comment_ids)
        for comment_id, transfer in transfers.items():
            transfer.update(pr_number=number, phase="processing", pending=True)
            record = state["comments"].get(str(comment_id))
            if not record:
                raise BotError(f"Issue comment {comment_id} disappeared while reserving the PR")
            removed = {image["hash"] for image in transfer["images"]}
            record["hashes"] = [digest for digest in record.get("hashes", []) if digest not in removed]
            if record.get("returned_hashes"):
                record["returned_hashes"] = [digest for digest in record["returned_hashes"] if digest not in removed]
            record["remaining_images"] = transfer.pop("remaining_images")
            if transfer.get("deleted"):
                record.update(deleted=True, hashes=[])
                release_comment_reservations(state, comment_id)
            record.setdefault("takeovers", []).append(transfer)
            for digest in removed:
                reservation = state["reserved"].get(digest)
                if reservation and reservation.get("comment_id") == str(comment_id):
                    state["reserved"].pop(digest)
            refresh_transferred_comment(record)

        current_hashes = set(hashes) - set(main_hashes) - set(state["ingested"])
        release_pr_reservations(state, number, set(state["reserved"]) - current_hashes)
        settle_comment_takeovers(state, number, keep_hashes=current_hashes)
        current_comment_ids = set(issue_comment_ids)
        for previous_comment_id in previous_comment_ids:
            if previous_comment_id in current_comment_ids:
                continue
            old_comment = state["comments"].get(previous_comment_id)
            if old_comment and old_comment.get("pr_number") == number:
                reset_issue_comment_after_pr(state, previous_comment_id)

        for digest in current_hashes:
            reservation = state["reserved"].get(digest)
            if reservation and str(reservation.get("comment_id")) in allowed_comment_ids:
                reservation["pr_number"] = number
            else:
                state["reserved"][digest] = {
                    "kind": "pull_request",
                    "pr_number": number,
                    "claim_code": claim_code,
                    "comment_id": None,
                }

        if not current_hashes and not issue_comment_ids:
            state["pull_requests"].pop(pr_key, None)
            result.update(ok=True, issue_comment_ids=[])
            return

        state["pull_requests"][pr_key] = {
            "hashes": sorted(current_hashes),
            "issue_comment_ids": issue_comment_ids,
            "claim_links": [link for _, link in unique_claim_links],
            "claim_codes": [claim_code] if claim_code else [],
            # Keep the old fields readable for cache entries created before multi-claim support.
            "issue_comment_id": issue_comment_ids[0] if len(issue_comment_ids) == 1 else None,
            "claim_code": claim_code,
        }
        for issue_comment_id in issue_comment_ids:
            issue_record = state["comments"][str(issue_comment_id)]
            issue_record["status"] = "processing"
            issue_record["pr_number"] = number
        result.update(ok=True, issue_comment_ids=issue_comment_ids, takeover_comments=transfers)

    github.mutate_state(update)
    if not result.get("ok"):
        detail = result.get("reason") or duplicate_pr_message(result.get("duplicates", []))
        sync_comment_takeovers(github, number)
        for released_comment_id in result.get("released_comment_ids", []):
            issue_state = _current_state(github)
            issue_comment_reply(
                github,
                released_comment_id,
                issue_state,
                "unprocessed",
            )
        raise BotError(detail)

    for issue_comment_id in result.get("issue_comment_ids", []):
        issue_state = _current_state(github)
        issue_comment_reply(
            github,
            issue_comment_id,
            issue_state,
            "processing",
        )
    sync_comment_takeovers(github, number)
    github.pr_status_comment(
        number,
        pr_check_message(
            summary,
            passed=True,
            detail=(f"已接管评论中的 {sum(len(item['images']) for item in result.get('takeover_comments', {}).values())} 张图片。"
                    if result.get("takeover_comments") else None),
        ),
    )
    print(f"Image hash check passed for PR #{number} ({len(set(hashes))} new image(s)).")


def close_pull_request(github: GitHub, pull_request):
    number = int(pull_request["number"])
    merged = bool(pull_request.get("merged"))
    result = {}

    def update(state):
        result.clear()
        pr_key = str(number)
        record = state["pull_requests"].get(pr_key)
        if not record:
            result["found"] = False
            if merged:
                result["comment_ids"] = []
                for comment_id, comment in state["comments"].items():
                    if comment.get("status") == "ingested" and comment.get("pr_number") == number:
                        result["comment_ids"].append(comment_id)
            return

        comment_ids = pull_request_comment_ids(record)
        hashes = set(record.get("hashes", []))
        for digest in hashes:
            reservation = state["reserved"].get(digest)
            if not reservation or str(reservation.get("pr_number")) != pr_key:
                continue
            if merged:
                state["ingested"] = sorted(set(state["ingested"]) | {digest})
                state["reserved"].pop(digest, None)
        if not merged:
            release_pr_reservations(state, number)

        settle_comment_takeovers(state, number, merged=merged)

        for comment_id in comment_ids:
            if str(comment_id) not in state["comments"]:
                continue
            issue_record = state["comments"][str(comment_id)]
            if merged:
                if issue_record.get("deleted"):
                    issue_record.update(hashes=[], pr_number=None, comment_update_pending=True)
                    if issue_record.get("takeovers"):
                        refresh_transferred_comment(issue_record)
                    else:
                        state["comments"].pop(str(comment_id), None)
                elif issue_record.get("takeovers") or issue_record.get("returned_hashes"):
                    issue_record["links_to_archive"] = [
                        image["markdown"] for image in issue_record.get("remaining_images", [])
                        if image["hash"] in hashes
                    ]
                    issue_record["hashes"] = sorted(set(issue_record.pop("returned_hashes", [])))
                    issue_record["pr_number"] = None
                    issue_record["comment_update_pending"] = True
                    refresh_transferred_comment(issue_record)
                else:
                    issue_record["status"] = "ingested"
                    issue_record["pr_number"] = number
            else:
                reset_issue_comment_after_pr(state, comment_id)
        state["pull_requests"].pop(pr_key, None)
        result.update(found=True, comment_ids=comment_ids, hashes=sorted(hashes))

    github.mutate_state(update)
    status = "ingested" if merged else "unprocessed"
    for comment_id in result.get("comment_ids", []):
        issue_state = _current_state(github)
        record = issue_state["comments"].get(str(comment_id), {})
        if not record.get("takeovers") and not record.get("comment_update_pending"):
            issue_comment_reply(github, comment_id, issue_state, status)
    sync_comment_takeovers(github, number)
    if result.get("found"):
        if merged:
            print(f"Moved {len(result['hashes'])} image hash(es) to the ingested cache for PR #{number}.")
        else:
            print(f"Released unmerged image reservations for PR #{number}.")


def release_pull_request_state(github: GitHub, number: int):
    result = {}

    def update(state):
        record = state["pull_requests"].pop(str(number), None)
        if not record:
            return
        result["comment_ids"] = pull_request_comment_ids(record)
        release_pr_reservations(state, number)
        settle_comment_takeovers(state, number)
        for comment_id in result.get("comment_ids", []):
            comment = state["comments"].get(str(comment_id))
            if comment:
                reset_issue_comment_after_pr(state, comment_id)

    github.mutate_state(update)
    sync_comment_takeovers(github, number)
    return result.get("comment_ids", [])


def archive_ingested_hashes(github: GitHub):
    sync_comment_takeovers(github)
    state, _ = github.load_state()
    batch = set(state["ingested"])
    if not batch:
        print("No newly ingested hashes to archive.")
        return

    for attempt in range(12):
        current_text, sha = github.read_contents("hash.txt", "main")
        current_text = current_text or ""
        current = parse_hash_file(current_text)
        additions = sorted(batch - current)
        if additions:
            prefix = current_text.rstrip("\r\n")
            new_text = (prefix + "\n" if prefix else "") + "\n".join(additions) + "\n"
            try:
                github.write_contents(
                    "hash.txt",
                    "main",
                    new_text,
                    "chore: archive meme hashes ("
                    f"{datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).date().isoformat()})",
                    sha,
                )
                print(f"Archived {len(additions)} image hash(es) in one main-branch commit.")
                break
            except GitHubAPIError as exc:
                if exc.status != 409 or attempt == 11:
                    raise
                time.sleep(min(0.25 * (attempt + 1), 2))
        else:
            print("All ingested hashes are already present in hash.txt.")
            break
    else:
        raise BotError("Could not archive hashes after repeated main-branch conflicts")

    def clear_archived(state):
        remaining = set(state["ingested"]) - batch
        if remaining == set(state["ingested"]):
            return None
        state["ingested"] = sorted(remaining)
        for comment in state["comments"].values():
            if comment.get("status") == "ingested":
                comment.pop("hashes", None)
        return True

    github.mutate_state(clear_archived)


def handle_event(github: GitHub, event_name: str, event):
    if event_name == "issue_comment":
        handle_issue_comment(github, event)
        return
    if event_name == "pull_request_target":
        pull_request = event.get("pull_request") or {}
        action = event.get("action")
        if action == "closed":
            close_pull_request(github, pull_request)
        elif action in {"opened", "reopened", "synchronize", "edited", "ready_for_review"}:
            process_pull_request(github, pull_request)
        return
    if event_name in {"schedule", "workflow_dispatch"}:
        archive_ingested_hashes(github)
        return
    raise BotError(f"Unsupported event: {event_name}")


def main(argv=None):
    argv = argv or sys.argv[1:]
    if len(argv) != 1:
        print("Usage: python scripts/meme_hash.py <event|init-cache|cleanup-cache>", file=sys.stderr)
        return 2
    if argv[0] == "init-cache":
        state_path = ROOT / STATE_PATH
        state_path.parent.mkdir(parents=True, exist_ok=True)
        if not state_path.is_file():
            state_path.write_text(
                json.dumps(empty_state(), ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                encoding="utf-8",
            )
        return 0
    if argv[0] == "cleanup-cache":
        GitHub().cleanup_meme_caches(os.environ.get("MEME_HASH_CACHE_KEY", ""))
        return 0
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if not event_path:
        print("GITHUB_EVENT_PATH is required", file=sys.stderr)
        return 2
    try:
        with open(event_path, "r", encoding="utf-8") as event_file:
            event = json.load(event_file)
        handle_event(GitHub(), argv[0], event)
        return 0
    except BotError as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
