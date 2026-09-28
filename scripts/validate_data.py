#!/usr/bin/env python3
"""Validate the repository's manifest and meme data using only the stdlib."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit


MARKDOWN_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
IMAGE_URL = re.compile(
    r"https://github\.com/([^/]+)/NaiLoong/blob/image/(.+)\Z", re.IGNORECASE
)
INVALID = object()


def _pairs_without_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _display_path(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def validate_data(root: Path | str) -> list[str]:
    root = Path(root).resolve()
    data_dir = root / "data"
    errors: list[str] = []

    if not data_dir.is_dir():
        return ["data/: directory not found"]

    json_files = sorted(data_dir.rglob("*.json"))
    if not json_files:
        return ["data/: no JSON files found"]

    loaded = {}
    for path in json_files:
        relative = _display_path(path, root)
        try:
            text = path.read_text(encoding="utf-8")
            value = json.loads(text, object_pairs_hook=_pairs_without_duplicates)
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
            errors.append(f"{relative}: invalid JSON: {exc}")
            continue

        loaded[path.resolve()] = value
        if MARKDOWN_IMAGE.search(text):
            errors.append(
                f'{relative}: found Markdown image syntax; store a plain URL in "url"'
            )

    manifest_path = (data_dir / "manifest.json").resolve()
    manifest = loaded.get(manifest_path, INVALID)
    if manifest is INVALID:
        if not manifest_path.is_file():
            errors.append("data/manifest.json: file not found")
        return errors
    if not isinstance(manifest, list) or not manifest:
        errors.append("data/manifest.json: expected a non-empty JSON array")
        return errors

    role_ids = set()
    referenced_entries = set()
    seen_urls = {}
    data_root = data_dir.resolve()

    def resolve_data_file(value, owner, field):
        if not isinstance(value, str) or not value.strip():
            errors.append(f"{owner}: {field} must be a non-empty path relative to data/")
            return None
        posix_path = PurePosixPath(value)
        if posix_path.is_absolute() or ".." in posix_path.parts or "\\" in value:
            errors.append(f"{owner}: {field} must stay inside data/: {value!r}")
            return None
        path = (data_dir / Path(*posix_path.parts)).resolve()
        try:
            path.relative_to(data_root)
        except ValueError:
            errors.append(f"{owner}: {field} must stay inside data/: {value!r}")
            return None
        if path.suffix.lower() != ".json":
            errors.append(f"{owner}: {field} must reference a .json file: {value!r}")
            return None
        return path

    for role_index, role in enumerate(manifest):
        owner = f"data/manifest.json role #{role_index}"
        if not isinstance(role, dict):
            errors.append(f"{owner}: expected an object")
            continue

        role_id = role.get("id")
        if not isinstance(role_id, str) or not role_id.strip():
            errors.append(f"{owner}: needs a non-empty string id")
            role_id = None
        elif not SLUG.fullmatch(role_id):
            errors.append(f"{owner}: id must use lowercase letters, digits, and single hyphens")
        elif role_id in role_ids:
            errors.append(f"{owner}: duplicate role id {role_id!r}")
        else:
            role_ids.add(role_id)

        if not isinstance(role.get("name"), str) or not role["name"].strip():
            errors.append(f"{owner}: needs a non-empty string name")

        categories = role.get("subcategories")
        if not isinstance(categories, list) or not categories:
            errors.append(f"{owner}: subcategories must be a non-empty array")
            continue

        category_ids = set()
        category_paths = []
        for category_index, category in enumerate(categories):
            category_owner = f"{owner} subcategory #{category_index}"
            if not isinstance(category, dict):
                errors.append(f"{category_owner}: expected an object")
                continue

            category_id = category.get("id")
            if not isinstance(category_id, str) or not category_id.strip():
                errors.append(f"{category_owner}: needs a non-empty string id")
            elif not SLUG.fullmatch(category_id):
                errors.append(
                    f"{category_owner}: id must use lowercase letters, digits, and single hyphens"
                )
            elif category_id in category_ids:
                errors.append(f"{category_owner}: duplicate category id {category_id!r}")
            else:
                category_ids.add(category_id)

            if not isinstance(category.get("name"), str) or not category["name"].strip():
                errors.append(f"{category_owner}: needs a non-empty string name")

            relative_file = category.get("file")
            entry_path = resolve_data_file(relative_file, category_owner, "file")
            if entry_path is None:
                continue
            category_paths.append(entry_path)
            if role_id and entry_path.parent.name != role_id:
                errors.append(
                    f"{category_owner}: file must be inside data/{role_id}/; "
                    f"found data/{entry_path.parent.name}/"
                )
            if entry_path.name == "manifest.json" or entry_path.name == "tags.json":
                errors.append(f"{category_owner}: file must be an entry array, not {entry_path.name}")
            if not entry_path.is_file():
                errors.append(f"{category_owner}: referenced file not found: {relative_file}")
                continue

            referenced_entries.add(entry_path)
            entries = loaded.get(entry_path, INVALID)
            if entries is INVALID:
                continue
            if not isinstance(entries, list):
                errors.append(f"{_display_path(entry_path, root)}: expected a JSON array")
                continue

            for entry_index, entry in enumerate(entries):
                entry_owner = f"{_display_path(entry_path, root)} entry #{entry_index}"
                if not isinstance(entry, dict):
                    errors.append(f"{entry_owner}: expected an object")
                    continue

                title = entry.get("title")
                if not isinstance(title, str) or not title.strip():
                    errors.append(f"{entry_owner}: title must be a non-empty string")

                normalized_url = _validate_url(entry.get("url"), entry_owner, root, errors)
                if normalized_url:
                    previous = seen_urls.get(normalized_url)
                    if previous:
                        errors.append(
                            f'{entry_owner}: duplicate image URL also used by {previous}: '
                            f'{entry.get("url")}'
                        )
                    else:
                        seen_urls[normalized_url] = entry_owner

        if role_id and category_paths:
            tags_value = role.get("tags")
            if tags_value is None:
                tags_path = category_paths[0].parent / "tags.json"
            else:
                tags_path = resolve_data_file(tags_value, owner, "tags")
            if tags_path is not None:
                if not tags_path.is_file():
                    errors.append(f"{owner}: tags file not found: {_display_path(tags_path, root)}")
                else:
                    tag_definitions = loaded.get(tags_path, INVALID)
                    if tag_definitions is INVALID:
                        continue
                    local_ids, labels = _validate_tag_definitions(
                        tag_definitions, _display_path(tags_path, root), errors
                    )
                    for category in categories:
                        if not isinstance(category, dict):
                            continue
                        entry_path = resolve_data_file(
                            category.get("file"), owner, "subcategory file"
                        )
                        if entry_path is None:
                            continue
                        entries = loaded.get(entry_path, INVALID)
                        if not isinstance(entries, list):
                            continue
                        for entry_index, entry in enumerate(entries):
                            if isinstance(entry, dict):
                                _validate_tags(
                                    entry.get("tags"),
                                    f"{_display_path(entry_path, root)} entry #{entry_index}",
                                    local_ids,
                                    labels,
                                    errors,
                                )

    for path in json_files:
        resolved = path.resolve()
        if path.name in {"manifest.json", "tags.json"}:
            continue
        if resolved not in referenced_entries:
            errors.append(f"{_display_path(path, root)}: entry file is not referenced by manifest")

    return errors


def _validate_url(value, owner, root, errors):
    if not isinstance(value, str) or not value.strip():
        errors.append(f'{owner}: "url" must be a non-empty string')
        return None

    value = value.strip()
    if MARKDOWN_IMAGE.search(value):
        errors.append(f'{owner}: "url" must be a plain URL, not Markdown image syntax')
        return None

    if value.startswith("assets/placeholders/"):
        local_path = PurePosixPath(value)
        if ".." in local_path.parts or "\\" in value:
            errors.append(f'{owner}: placeholder path must stay inside assets/placeholders/: {value!r}')
            return None
        target = (root / Path(*local_path.parts)).resolve()
        try:
            target.relative_to((root / "assets" / "placeholders").resolve())
        except ValueError:
            errors.append(f'{owner}: placeholder path must stay inside assets/placeholders/: {value!r}')
            return None
        if not target.is_file():
            errors.append(f'{owner}: placeholder file not found: {value}')
            return None
        return value

    match = IMAGE_URL.fullmatch(value)
    if not match:
        errors.append(
            f'{owner}: "url" must point to a GitHub fork file under '
            "NaiLoong/blob/image/<path>"
        )
        return None

    owner_name, file_path = match.groups()
    if any(character.isspace() for character in value):
        errors.append(f'{owner}: "url" must not contain whitespace')
        return None
    try:
        parsed = urlsplit(value)
        parsed.port
    except ValueError:
        errors.append(f'{owner}: "url" is not a valid GitHub image URL')
        return None
    if parsed.hostname != "github.com" or parsed.query or parsed.fragment:
        errors.append(f'{owner}: "url" must be a direct GitHub blob URL without query or fragment')
        return None
    parts = PurePosixPath(file_path)
    raw_parts = file_path.split("/")
    if (
        not file_path
        or parts.is_absolute()
        or any(part in {"", ".", ".."} for part in raw_parts)
        or "\\" in file_path
    ):
        errors.append(f'{owner}: image path must stay inside the fork image branch')
        return None
    if owner_name.lower() == "lin-alg":
        errors.append(f'{owner}: image URL must point to a fork, not the source repository')
        return None

    return f"https://github.com/{owner_name.lower()}/nailoong/blob/image/{parts.as_posix()}"


def _validate_tag_definitions(value, owner, errors):
    local_ids = {}
    labels = {}
    if not isinstance(value, dict):
        errors.append(f"{owner}: tag definitions must be a JSON object")
        return local_ids, labels

    for dimension, items in value.items():
        if not isinstance(dimension, str) or not dimension.strip():
            errors.append(f"{owner}: tag dimension names must be non-empty strings")
            continue
        if not isinstance(items, dict):
            errors.append(f"{owner}: dimension {dimension!r} must map local ids to labels")
            continue

        dimension_ids = set()
        dimension_labels = {}
        local_ids[dimension] = dimension_ids
        labels[dimension] = dimension_labels
        for local_id, label in sorted(items.items(), key=lambda pair: pair[0]):
            if not isinstance(local_id, str) or not re.fullmatch(r"0|[1-9][0-9]*", local_id):
                errors.append(f"{owner}: {dimension!r} has invalid local tag id {local_id!r}")
                continue
            if not isinstance(label, str) or not label.strip():
                errors.append(f"{owner}: {dimension!r} tag {local_id} needs a non-empty label")
                continue
            if label in dimension_labels.values():
                errors.append(f"{owner}: {dimension!r} has duplicate label {label!r}")
            local_number = int(local_id)
            dimension_ids.add(local_number)
            dimension_labels[local_number] = label
    return local_ids, labels


def _validate_tags(value, owner, local_ids, labels, errors):
    if isinstance(value, list):
        dimensions = list(local_ids)
        if len(value) != len(dimensions):
            errors.append(
                f"{owner}: tags array must have one value per tag dimension "
                f"({len(dimensions)} expected, {len(value)} found)"
            )
            return
        for dimension, tag in zip(dimensions, value):
            if tag is None:
                continue
            if isinstance(tag, bool) or not isinstance(tag, int) or tag not in local_ids[dimension]:
                errors.append(
                    f"{owner}: tags value for {dimension!r} must be a defined local id or null"
                )
                return
    elif isinstance(value, dict):
        for dimension, tag in value.items():
            if dimension not in local_ids:
                errors.append(f"{owner}: unknown tag dimension {dimension!r}")
                return
            if tag is None:
                continue
            if isinstance(tag, bool):
                errors.append(f"{owner}: tag value for {dimension!r} must be a local id or label")
                return
            if isinstance(tag, int):
                if tag not in local_ids[dimension]:
                    errors.append(f"{owner}: undefined local tag id {tag} in {dimension!r}")
                    return
            elif isinstance(tag, str) and tag in labels[dimension].values():
                continue
            else:
                errors.append(f"{owner}: unknown tag value {tag!r} in {dimension!r}")
                return
    else:
        errors.append(f"{owner}: tags must be a dimension-ordered array or dimension-to-value object")


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    errors = validate_data(root)
    if errors:
        for error in errors:
            print(f"::error::{error}", file=sys.stderr)
        return 1
    print("Data validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
