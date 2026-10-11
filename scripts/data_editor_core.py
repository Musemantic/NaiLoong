"""Git diff and local data operations for the browser-based data editor."""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path, PurePosixPath
from urllib.parse import quote, unquote, urlsplit

try:
    from .data_editor import load_json, normalize_image_url
    from .validate_data import validate_data
except ImportError:
    from data_editor import load_json, normalize_image_url
    from validate_data import validate_data


IMAGE_TYPES = {
    ".gif": "animated",
    ".apng": "animated",
    ".png": "static",
    ".jpg": "static",
    ".jpeg": "static",
    ".webp": "static",
    ".bmp": "static",
}
ANIMATED_EXTENSIONS = {".gif", ".apng"}
SHA1 = re.compile(r"[0-9a-f]{40}\Z", re.IGNORECASE)
MAX_IMAGE_BYTES = 5 * 1024 * 1024


class EditorError(ValueError):
    pass


def git(repo: Path, *args: str, binary: bool = False):
    result = subprocess.run(
        ["git", *args], cwd=repo, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, check=False,
    )
    if result.returncode:
        message = result.stderr.decode("utf-8", "replace").strip()
        raise EditorError(message or "Git 命令执行失败")
    return result.stdout if binary else result.stdout.decode("utf-8", "replace").strip()


def repository_owner(remote: str) -> str:
    remote = remote.strip()
    match = re.search(r"(?:github\.com[:/])([^/]+)/NaiLoong(?:\.git)?/?$", remote, re.IGNORECASE)
    if not match:
        raise EditorError("origin 必须指向 GitHub 上的 NaiLoong Fork")
    return match.group(1)


def image_path_from_url(value: str, owner: str, root: Path) -> str | None:
    try:
        compact = normalize_image_url(value, root)
    except ValueError:
        return None
    if compact.startswith("assets/placeholders/"):
        return None
    parts = compact.split("/", 2)
    if len(parts) != 3 or parts[0].casefold() != owner.casefold() or not SHA1.fullmatch(parts[1]):
        return None
    return PurePosixPath(unquote(parts[2])).as_posix()


def media_category(root: Path, ref: str, path: str) -> str:
    extension = Path(path).suffix.lower()
    if extension not in IMAGE_TYPES:
        return "static"
    if extension in ANIMATED_EXTENSIONS:
        return "animated"
    try:
        header = git(root, "show", f"{ref}:{path}", binary=True)[:64 * 1024]
    except EditorError:
        return IMAGE_TYPES[extension]
    if extension == ".png" and b"acTL" in header:
        return "animated"
    if extension == ".webp" and len(header) >= 21 and header[:4] == b"RIFF" and header[8:12] == b"WEBP":
        if header[12:16] == b"VP8X" and header[20] & 0x02:
            return "animated"
    return IMAGE_TYPES[extension]


def _blob_size(root: Path, ref: str, path: str) -> int:
    try:
        return int(git(root, "cat-file", "-s", f"{ref}:{path}"))
    except (EditorError, ValueError):
        return 0


def project_metadata(root: Path) -> dict:
    data_dir = root / "data"
    manifest = load_json(data_dir / "manifest.json")
    roles = []
    for role in manifest:
        role_id = role["id"]
        tags_path = data_dir / role.get("tags", f"{role_id}/tags.json")
        tags = load_json(tags_path)
        categories = []
        examples = []
        for category in role.get("subcategories", []):
            category_path = data_dir / category["file"]
            entries = load_json(category_path)
            categories.append({
                "id": category["id"], "name": category["name"], "file": category["file"],
            })
            if isinstance(entries, list):
                examples.extend(
                    str(entry.get("title", "")) for entry in entries[:12]
                    if isinstance(entry, dict) and entry.get("title")
                )
        roles.append({
            "id": role_id,
            "name": role["name"],
            "icon": role.get("icon", ""),
            "image": f"{role_id}/{role_id}.png",
            "categories": categories,
            "tags": tags,
            "examples": examples[:12],
        })
    return {"roles": roles}


def _entries_for_paths(root: Path, owner: str, paths: set[str]) -> dict[str, dict]:
    found = {}
    metadata = project_metadata(root)
    for role in metadata["roles"]:
        for category in role["categories"]:
            file_path = root / "data" / category["file"]
            entries = load_json(file_path)
            if not isinstance(entries, list):
                continue
            for index, entry in enumerate(entries):
                if not isinstance(entry, dict):
                    continue
                image_path = image_path_from_url(str(entry.get("url", "")), owner, root)
                if image_path in paths:
                    record = {
                        "role_id": role["id"], "category_id": category["id"],
                        "file": category["file"], "index": index,
                        "entry": entry,
                    }
                    found.setdefault(image_path, []).append(record)
    return found


def scan_image_branch(root: Path, commit_count: int = 1) -> dict:
    """Summarize a committed image-branch range without modifying the worktree."""
    if isinstance(commit_count, bool) or not isinstance(commit_count, int) or not 1 <= commit_count <= 100:
        raise EditorError("扫描 commit 数量必须在 1 到 100 之间")
    root = root.resolve()
    branch = git(root, "branch", "--show-current")
    if not branch.startswith("meme/"):
        raise EditorError("请先切换到 meme/... 投稿工作分支；编辑器会从本地 image 分支读取图片提交。")
    try:
        head = git(root, "rev-parse", "refs/heads/image")
    except EditorError as exc:
        raise EditorError("未找到本地 image 分支。先运行 git fetch origin image，再创建本地跟踪分支。") from exc
    if not SHA1.fullmatch(head):
        raise EditorError("当前仓库不是使用 40 位 SHA 的 GitHub SHA-1 仓库")
    try:
        base = git(root, "rev-parse", f"refs/heads/image~{commit_count}")
    except EditorError as exc:
        raise EditorError(f"本地 image 分支不足 {commit_count} 个可扫描的提交。") from exc
    remote = git(root, "config", "--get", "remote.origin.url")
    owner = repository_owner(remote)
    diff = git(root, "diff", "--name-status", "-M20%", "-z", base, head, "--")
    fields = diff.split("\0") if diff else []
    statuses = []
    index = 0
    while index < len(fields):
        status = fields[index]
        index += 1
        if status.startswith("R") and index + 1 < len(fields):
            statuses.append(("renamed", fields[index], fields[index + 1]))
            index += 2
        elif status[:1] in {"A", "M", "D"} and index < len(fields):
            statuses.append(({"A": "added", "M": "modified", "D": "deleted"}[status[0]], None, fields[index]))
            index += 1

    media_statuses = []
    for kind, old_path, path in statuses:
        effective = path if kind != "deleted" else path
        if Path(effective).suffix.lower() in IMAGE_TYPES:
            media_statuses.append((kind, old_path, path))
    all_paths = {path for _, old_path, path in media_statuses}
    all_paths.update(old_path for _, old_path, _ in media_statuses if old_path)
    matches = _entries_for_paths(root, owner, all_paths)

    categories_by_role = {
        role["id"]: {item["id"]: item for item in role["categories"]}
        for role in project_metadata(root)["roles"]
    }
    changes = []
    for ordinal, (status, old_path, path) in enumerate(media_statuses):
        record_path = old_path if status == "renamed" else path
        matching_records = matches.get(record_path, [])
        record = matching_records[0] if len(matching_records) == 1 else None
        extension = Path(path).suffix.lower()
        category_id = media_category(root, head, path)
        item = {
            "id": str(ordinal), "kind": "added", "path": path,
            "old_path": old_path, "extension": extension,
            "media_type": category_id,
            "category_hint": category_id,
            "url": f"{owner.lower()}/{head.lower()}/{quote(PurePosixPath(path).as_posix(), safe='/-._~')}",
            "preview": f"/api/image?ref={head}&path={quote(PurePosixPath(path).as_posix(), safe='/-._~')}",
            "old_preview": (
                f"/api/image?ref={_record_commit(record['entry'].get('url', ''), root)}"
                f"&path={quote(PurePosixPath(record_path).as_posix(), safe='/-._~')}"
                if record else ""
            ),
            "old_record": record,
            "ambiguous_records": len(matching_records) > 1,
            "size_bytes": _blob_size(root, head, path),
        }
        if status == "deleted":
            item["restore_ref"] = _deleted_file_parent(root, path, base)
            item["size_bytes"] = _blob_size(root, item["restore_ref"], path) if item["restore_ref"] else 0
            item["old_preview"] = (
                f"/api/image?ref={item['restore_ref']}&path={quote(PurePosixPath(path).as_posix(), safe='/-._~')}"
                if item["restore_ref"] else ""
            )
            item.update({"kind": "deleted", "url": "", "preview": ""})
        elif record:
            role_categories = categories_by_role[record["role_id"]]
            target_category = category_id if category_id in role_categories else record["category_id"]
            if target_category not in role_categories:
                target_category = next(iter(role_categories))
            item.update({
                "kind": "updated", "role_id": record["role_id"],
                "category_id": target_category,
                "entry": record["entry"],
                "record_file": record["file"],
                "record_index": record["index"],
                "change_reason": "重命名" if status == "renamed" else "图片内容更新",
            })
        else:
            item["change_reason"] = "新图片"
        changes.append(item)

    return {
        "head": head,
        "base": base,
        "owner": owner,
        "branch": "image",
        "work_branch": branch,
        "commit_count": commit_count,
        "changes": changes,
        "metadata": project_metadata(root),
    }


def apply_changes(root: Path, scan: dict, decisions: list[dict]) -> dict:
    """Apply selected scan decisions transactionally and validate full data."""
    root = root.resolve()
    if scan.get("work_branch"):
        if git(root, "branch", "--show-current") != scan["work_branch"]:
            raise EditorError("当前工作分支已经变化，请切回扫描时的投稿分支并重新扫描。")
        if git(root, "rev-parse", "refs/heads/image") != scan["head"]:
            raise EditorError("本地 image 分支在扫描后发生了变化，请重新扫描。")
    metadata = scan["metadata"]
    role_map = {role["id"]: role for role in metadata["roles"]}
    changes_by_id = {item["id"]: item for item in scan["changes"]}
    category_files = {
        category["file"]
        for role in metadata["roles"] for category in role["categories"]
    }
    data_dir = root / "data"
    current_baseline = {
        path.relative_to(data_dir).as_posix(): path.read_bytes()
        for path in data_dir.rglob("*.json") if path.is_file()
    }
    expected = scan["baseline"]
    if current_baseline != expected:
        raise EditorError("数据文件在扫描后发生了变化。请重新扫描，避免覆盖其他修改。")
    current_bytes = {name: current_baseline[name] for name in category_files}

    working = {name: json.loads(content.decode("utf-8")) for name, content in current_bytes.items()}
    changed_files = set()
    for decision in decisions:
        item = changes_by_id.get(str(decision.get("id")))
        if not item:
            continue
        if item["kind"] == "deleted":
            if decision.get("remove_record") and item.get("old_record"):
                record = item["old_record"]
                entries = working[record["file"]]
                old_url = record["entry"].get("url")
                index = next((index for index, entry in enumerate(entries)
                              if isinstance(entry, dict) and entry.get("url") == old_url), None)
                if index is not None:
                    entries.pop(index)
                    changed_files.add(record["file"])
            continue
        if not decision.get("selected", True):
            continue
        if item.get("size_bytes", 0) > MAX_IMAGE_BYTES:
            raise EditorError(f"{item['path']} 超过 5 MB 图片上限，请压缩后再扫描。")

        role_id = str(decision.get("role_id", ""))
        category_id = str(decision.get("category_id", ""))
        role = role_map.get(role_id)
        category = next(
            (value for value in role["categories"] if value["id"] == category_id), None
        ) if role else None
        title = str(decision.get("title", "")).strip()
        if not role or not category or not title:
            raise EditorError("每条待写入记录都需要选择角色、分类并填写标题。")
        tags = decision.get("tags")
        if not isinstance(tags, list):
            raise EditorError("标签值格式无效，请重新选择标签。")
        dimensions = list(role["tags"])
        if len(tags) != len(dimensions):
            raise EditorError(f"角色 {role_id} 的标签数量已变化，请重新扫描。")
        for value, dimension in zip(tags, dimensions):
            if value is not None and (isinstance(value, bool) or not isinstance(value, int)
                                      or str(value) not in role["tags"][dimension]):
                raise EditorError(f"标签 {dimension} 的序号无效。")

        destination = category["file"]
        updated = {
            "title": title,
            "url": item["url"],
            "tags": tags,
        }
        if item["kind"] == "updated":
            old_record = item["old_record"]
            source_entries = working[old_record["file"]]
            old_url = old_record["entry"].get("url")
            source_index = next((index for index, entry in enumerate(source_entries)
                                 if isinstance(entry, dict) and entry.get("url") == old_url), None)
            if source_index is None:
                raise EditorError("要更新的原条目已不存在，请重新扫描。")
            old_entry = source_entries[source_index]
            updated = {**old_entry, **updated}
            if destination == old_record["file"] and role_id == old_record["role_id"]:
                source_entries[source_index] = updated
                changed_files.add(destination)
            else:
                source_entries.pop(source_index)
                working[destination].append(updated)
                changed_files.update((old_record["file"], destination))
        else:
            working[destination].append(updated)
            changed_files.add(destination)

    backups = {name: current_bytes[name] for name in changed_files}
    temporary_files = []
    try:
        for name in changed_files:
            target = root / "data" / name
            content = (json.dumps(working[name], ensure_ascii=False, indent=2) + "\n").encode("utf-8")
            with tempfile.NamedTemporaryFile(dir=target.parent, prefix=target.name + ".", suffix=".tmp", delete=False) as handle:
                handle.write(content)
                temporary_files.append(Path(handle.name))
        for name, temporary in zip(changed_files, temporary_files):
            os.replace(temporary, root / "data" / name)
        errors = validate_data(root)
        if errors:
            raise EditorError("数据校验失败：\n" + "\n".join(errors[:15]))
    except Exception:
        for name, content in backups.items():
            (root / "data" / name).write_bytes(content)
        raise
    finally:
        for temporary in temporary_files:
            if temporary.exists():
                temporary.unlink()
    return {"written_files": sorted(changed_files), "entry_count": sum(
        len(working[name]) for name in changed_files
    )}


def with_baseline(root: Path, scan: dict) -> dict:
    data_dir = root / "data"
    scan["baseline"] = {
        path.relative_to(data_dir).as_posix(): path.read_bytes()
        for path in data_dir.rglob("*.json") if path.is_file()
    }
    return scan


def _record_commit(value: str, root: Path) -> str:
    try:
        canonical = normalize_image_url(value, root)
    except ValueError:
        return ""
    if canonical.startswith("assets/placeholders/"):
        return ""
    parts = urlsplit(canonical).path.strip("/").split("/")
    if len(parts) < 5 or not SHA1.fullmatch(parts[3]):
        return ""
    return parts[3]


def _deleted_file_parent(root: Path, path: str, base: str) -> str:
    try:
        deletion_commit = git(root, "log", "-1", "--format=%H", "refs/heads/image", "--", path)
        if deletion_commit:
            parent = git(root, "rev-parse", f"{deletion_commit}^")
            git(root, "cat-file", "-e", f"{parent}:{path}")
            return parent
        git(root, "cat-file", "-e", f"{base}:{path}")
        return base
    except EditorError:
        return ""
