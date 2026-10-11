"""Optional local AI helpers for the browser data editor (stdlib only)."""

from __future__ import annotations

import base64
import json
import math
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

try:
    from .data_editor_core import EditorError, git
except ImportError:
    from data_editor_core import EditorError, git


DEFAULT_MODELS = {
    "openai": "gpt-6-astra",
    "anthropic": "claude-sonnet-5-5",
    "google": "gemini-2.5-flash",
}
MAX_REQUEST_BYTES = 14 * 1024 * 1024
MAX_MEDIA_BYTES = 5 * 1024 * 1024
MAX_FRAME_CANDIDATES = 160
MAX_UPLOAD_FRAMES = 12
FRAME_SIGNATURE_BYTES = 32 * 32 * 3


def _find_ffmpeg() -> str:
    executable = shutil.which("ffmpeg")
    if executable:
        return executable
    if sys.platform == "win32":
        # Existing terminals keep their old environment after PATH is edited.
        # Read the saved paths without replacing the process environment.
        import winreg

        paths = []
        for hive, key in (
            (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
            (winreg.HKEY_CURRENT_USER, r"Environment"),
        ):
            try:
                with winreg.OpenKey(hive, key) as handle:
                    value, _kind = winreg.QueryValueEx(handle, "Path")
                if isinstance(value, str):
                    paths.append(winreg.ExpandEnvironmentStrings(value))
            except OSError:
                continue
        if paths:
            executable = shutil.which("ffmpeg", path=";".join(paths))
            if executable:
                return executable
    raise EditorError(
        "未找到 ffmpeg。动画识别和 BMP 转换需要安装 ffmpeg，并将包含 ffmpeg 可执行文件的 bin 目录加入 PATH。"
        "如果刚修改 PATH，请关闭旧终端，打开新终端后重新启动编辑器；从 IDE 启动时也需重启 IDE。"
    )


def _b64(content: bytes) -> str:
    return base64.b64encode(content).decode("ascii")


def _distinct_frame_indices(signatures: list[bytes], limit: int = MAX_UPLOAD_FRAMES) -> list[int]:
    """Drop near-identical scenes, including frames from repeated animation loops.

    Compare small RGB images, not compressed JPEG bytes. A low average error
    and few substantially changed channels tolerate compression noise while
    retaining local changes such as a mouth opening or a caption changing.
    """
    unique = []
    for index, signature in enumerate(signatures):
        if len(signature) != FRAME_SIGNATURE_BYTES:
            raise EditorError("视频抽帧返回了不完整的画面。")
        duplicate = False
        for previous in unique:
            differences = [abs(left - right) for left, right in zip(signature, signatures[previous])]
            if sum(differences) / len(differences) <= 4 and sum(value > 20 for value in differences) / len(differences) <= .01:
                duplicate = True
                break
        if not duplicate:
            unique.append(index)
    if len(unique) <= limit:
        return unique
    # Keep first/last distinct scenes and cover the entire clip, never just its
    # first few seconds. The original timestamps accompany the uploaded frames.
    return [unique[round(index * (len(unique) - 1) / (limit - 1))] for index in range(limit)]


def _run_ffmpeg(source: Path, directory: Path, extract_frames: bool = True) -> tuple[bytes, list[tuple[float, bytes]]]:
    ffmpeg = _find_ffmpeg()
    mp4 = directory / "clip.mp4"
    try:
        subprocess.run(
            [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(source),
             "-vf", "scale='min(768,iw)':'min(768,ih)':force_original_aspect_ratio=decrease:force_divisible_by=2,setsar=1",
             "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(mp4)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, timeout=90,
        )
        if not extract_frames:
            return mp4.read_bytes(), []
        metadata = subprocess.run(
            [ffmpeg, "-hide_banner", "-i", str(mp4)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, timeout=15,
        )
        duration_match = re.search(rb"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", metadata.stderr)
        if not duration_match:
            raise EditorError("无法读取视频时长，请检查 ffmpeg 转换结果。")
        hours, minutes, seconds = (float(value) for value in duration_match.groups())
        duration = hours * 3600 + minutes * 60 + seconds
        if not math.isfinite(duration) or duration <= 0:
            raise EditorError("视频时长无效，无法抽帧。")
        fps = min(8, MAX_FRAME_CANDIDATES / duration)
        decoded = subprocess.run(
            [ffmpeg, "-hide_banner", "-loglevel", "error", "-i", str(mp4),
             "-vf", f"fps={fps:.8f}:round=up,scale=32:32", "-frames:v", str(MAX_FRAME_CANDIDATES),
             "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, timeout=90,
        )
        raw = decoded.stdout
        if not raw or len(raw) % FRAME_SIGNATURE_BYTES:
            raise EditorError("无法从视频抽取完整画面。")
        signatures = [raw[offset:offset + FRAME_SIGNATURE_BYTES] for offset in range(0, len(raw), FRAME_SIGNATURE_BYTES)]
        selected = _distinct_frame_indices(signatures)
        # Extract only the chosen frames at readable resolution in one pass.
        selection = "+".join(f"eq(n\\,{index})" for index in selected)
        subprocess.run(
            [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(mp4),
             "-vf", f"fps={fps:.8f}:round=up,select='{selection}'",
             "-vsync", "vfr", "-q:v", "3", "-frames:v", str(len(selected)), str(directory / "frame-%03d.jpg")],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, timeout=90,
        )
        frames = [(index / fps, (directory / f"frame-{ordinal:03d}.jpg").read_bytes())
                  for ordinal, index in enumerate(selected, 1)]
    except FileNotFoundError as exc:
        raise EditorError("动画识别需要安装 ffmpeg，并确保 ffmpeg 在 PATH 中。") from exc
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        detail = getattr(exc, "stderr", b"")
        if isinstance(detail, bytes):
            detail = detail.decode("utf-8", "replace").strip()
        raise EditorError("动画转换或抽帧失败：" + (detail or "ffmpeg 执行失败")) from exc
    return mp4.read_bytes(), frames


def _media_parts(root: Path, scan: dict, item: dict, provider: str) -> list[tuple[str, str, bytes]]:
    path = item["path"]
    content = git(root, "show", f"{scan['head']}:{path}", binary=True)
    if not content:
        raise EditorError(f"无法从 image 分支读取图片：{path}")
    if len(content) > MAX_MEDIA_BYTES:
        raise EditorError(f"{path} 超过 5 MB，无法发送给视觉模型。")
    extension = Path(path).suffix.lower()
    if item.get("media_type") == "animated" or extension in {".mp4", ".webm", ".mov"}:
        with tempfile.TemporaryDirectory(prefix="nailoong-ai-") as temporary:
            directory = Path(temporary)
            source = directory / ("source" + extension)
            source.write_bytes(content)
            mp4, frames = _run_ffmpeg(source, directory, extract_frames=provider != "google")
        if provider == "google":
            return [("video/mp4", path, mp4)]
        if not frames:
            raise EditorError(f"无法从动画中抽取画面：{path}")
        return [("image/jpeg", f"{path} · {timestamp:.2f}s", frame) for timestamp, frame in frames]
    mime = {
        ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }.get(extension)
    if extension == ".bmp":
        ffmpeg = _find_ffmpeg()
        with tempfile.TemporaryDirectory(prefix="nailoong-ai-still-") as temporary:
            directory = Path(temporary)
            source = directory / "source.bmp"
            target = directory / "still.jpg"
            source.write_bytes(content)
            try:
                subprocess.run(
                    [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(source),
                     "-frames:v", "1", str(target)],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, timeout=60,
                )
            except FileNotFoundError as exc:
                raise EditorError("BMP 图片的 AI 识别需要 ffmpeg，并确保 ffmpeg 在 PATH 中。") from exc
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
                raise EditorError("BMP 图片转换失败，请另存为 PNG 或 JPG 后重试。") from exc
            return [("image/jpeg", path, target.read_bytes())]
    if mime is None:
        raise EditorError(f"暂不支持 AI 识别此文件类型：{path}")
    return [(mime, path, content)]


def _role_reference(root: Path, role: dict) -> tuple[str, str, bytes] | None:
    relative = role.get("image", "")
    path = (root / "data" / relative).resolve()
    try:
        path.relative_to((root / "data").resolve())
    except ValueError:
        return None
    if not path.is_file() or path.stat().st_size > MAX_MEDIA_BYTES:
        return None
    return "image/png", f"角色参考图 {role['name']}", path.read_bytes()


def _prompt(scan: dict, batch: list[dict]) -> str:
    roles = []
    for role in scan["metadata"]["roles"]:
        dimensions = []
        for name, values in role["tags"].items():
            dimensions.append({"dimension": name, "values": [
                {"id": int(local_id), "label": label}
                for local_id, label in values.items()
            ]})
        roles.append({
            "role_id": role["id"], "name": role["name"],
            "tags": dimensions, "existing_title_examples": role["examples"],
            "reference_image_label": f"角色参考图 {role['name']}（如果本次请求包含）",
        })
    items = [{"path": item["path"], "media_type": item["media_type"]} for item in batch]
    return (
        "你是奶-hub表情包数据整理助手。请根据每个图片或视频帧，为每个文件生成简短中文标题，选择最合适的角色，"
        "并按该角色 tags 中已有的本地序号打标签。角色参考 PNG 只用于辨认形象，不是投稿条目。"
        "不要创造新角色、标签维度或标签值；无法判断的标签值填写 null，拿不准角色时 role_id 填 null。"
        "每个输入的文件路径必须原样返回。只返回符合 JSON Schema 的对象。\n\n"
        "角色、标签、已有标题示例和角色参考图标签：\n"
        + json.dumps(roles, ensure_ascii=False)
        + "\n本批待识别文件（图片旁会标出路径；动画按供应商支持情况提供 MP4 或其抽帧）：\n"
        + json.dumps(items, ensure_ascii=False)
        + '\n输出 items 数组。每项形如 {"path":"原路径","title":"中文标题","role_id":"角色ID或null",'
        '"tags":[{"dimension":"维度ID","value":本地整数序号或null}]}。'
    )


def _schema() -> dict:
    tag = {
        "type": "object",
        "properties": {
            "dimension": {"type": "string"},
            "value": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
        },
        "required": ["dimension", "value"],
        "additionalProperties": False,
    }
    item = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "title": {"type": "string"},
            "role_id": {"anyOf": [{"type": "string"}, {"type": "null"}]},
            "tags": {"type": "array", "items": tag},
        },
        "required": ["path", "title", "role_id", "tags"],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {"items": {"type": "array", "items": item}},
        "required": ["items"],
        "additionalProperties": False,
    }


def _request(provider: str, api_key: str, model: str, prompt: str,
             references: list[tuple[str, str, bytes]], media: list[tuple[str, str, bytes]]) -> str:
    blocks = references + media
    if sum(len(item[2]) for item in blocks) > MAX_REQUEST_BYTES:
        raise EditorError("本批图片原始总大小超过 14 MB，请减小批量数量或压缩图片。")
    schema = _schema()
    if provider == "openai":
        content = [{"type": "input_text", "text": prompt}]
        for mime, label, data in blocks:
            content.extend([
                {"type": "input_text", "text": label},
                {"type": "input_image", "image_url": f"data:{mime};base64,{_b64(data)}", "detail": "low"},
            ])
        body = {"model": model, "input": [{"role": "user", "content": content}],
                "text": {"format": {"type": "json_schema", "name": "meme_entries", "strict": True, "schema": schema}}}
        url = "https://api.openai.com/v1/responses"
        headers = {"Authorization": f"Bearer {api_key}"}
    elif provider == "anthropic":
        content = []
        for mime, label, data in blocks:
            content.extend([
                {"type": "text", "text": label},
                {"type": "image", "source": {"type": "base64", "media_type": mime, "data": _b64(data)}},
            ])
        content.append({"type": "text", "text": prompt})
        body = {"model": model, "max_tokens": 4096,
                "messages": [{"role": "user", "content": content}],
                "output_config": {"format": {"type": "json_schema", "schema": schema}}}
        url = "https://api.anthropic.com/v1/messages"
        headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01"}
    elif provider == "google":
        parts = [{"text": prompt}]
        uploaded = []
        for mime, label, data in blocks:
            parts.append({"text": label})
            if mime == "video/mp4":
                try:
                    file_part, file_name = _upload_google_video(api_key, label, data)
                except EditorError:
                    for name in uploaded:
                        _delete_google_file(api_key, name)
                    raise
                parts.append(file_part)
                uploaded.append(file_name)
            else:
                parts.append({"inlineData": {"mimeType": mime, "data": _b64(data)}})
        body = {"contents": [{"role": "user", "parts": parts}],
                "generationConfig": {"responseMimeType": "application/json", "responseJsonSchema": schema}}
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{quote(model, safe='')}:generateContent"
        headers = {"x-goog-api-key": api_key}
    else:
        raise EditorError("请选择 OpenAI、Anthropic 或 Google。")

    raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
    request = Request(url, data=raw, headers={"Content-Type": "application/json", **headers}, method="POST")
    try:
        with urlopen(request, timeout=120) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:1000]
        raise EditorError(f"AI 服务返回 HTTP {exc.code}: {detail}") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise EditorError(f"无法连接 AI 服务：{exc}") from exc
    finally:
        if provider == "google":
            for name in locals().get("uploaded", []):
                _delete_google_file(api_key, name)
    if provider == "openai":
        texts = [content["text"] for output in payload.get("output", [])
                 for content in output.get("content", []) if content.get("type") == "output_text"]
        text = "\n".join(texts)
    elif provider == "anthropic":
        text = "\n".join(block.get("text", "") for block in payload.get("content", []) if block.get("type") == "text")
    else:
        text = "\n".join(part.get("text", "") for candidate in payload.get("candidates", [])[:1]
                         for part in candidate.get("content", {}).get("parts", []) if not part.get("thought"))
    if not text:
        raise EditorError("AI 服务没有返回可读取的 JSON 文本。")
    return text


def _upload_google_video(api_key: str, label: str, content: bytes) -> tuple[dict, str]:
    start_url = "https://generativelanguage.googleapis.com/upload/v1beta/files"
    start = Request(
        start_url,
        data=json.dumps({"file": {"display_name": label[:120]}}).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "X-Goog-Upload-Protocol": "resumable",
            "X-Goog-Upload-Command": "start",
            "X-Goog-Upload-Header-Content-Length": str(len(content)),
            "X-Goog-Upload-Header-Content-Type": "video/mp4",
            "x-goog-api-key": api_key,
        },
        method="POST",
    )
    try:
        with urlopen(start, timeout=60) as response:
            upload_url = response.headers.get("X-Goog-Upload-URL")
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise EditorError("Gemini 视频上传初始化失败。检查 API key 和 Files API 权限。") from exc
    if not upload_url:
        raise EditorError("Gemini 视频上传没有返回上传地址。")
    upload = Request(
        upload_url,
        data=content,
        headers={
            "Content-Length": str(len(content)), "X-Goog-Upload-Offset": "0",
            "X-Goog-Upload-Command": "upload, finalize", "Content-Type": "video/mp4",
        },
        method="POST",
    )
    try:
        with urlopen(upload, timeout=120) as response:
            result = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise EditorError("Gemini 视频上传失败。") from exc
    file = result.get("file", result)
    name = file.get("name", "")
    uri = file.get("uri") or file.get("fileUri")
    if not name or not uri:
        raise EditorError("Gemini 视频上传响应缺少文件引用。")
    state = file.get("state", "ACTIVE")
    for _ in range(30):
        if state == "ACTIVE":
            break
        if state == "FAILED":
            _delete_google_file(api_key, name)
            raise EditorError("Gemini 无法处理上传的视频文件。")
        time.sleep(1)
        status_url = "https://generativelanguage.googleapis.com/v1beta/" + quote(name, safe="/")
        try:
            status_request = Request(status_url, headers={"x-goog-api-key": api_key})
            with urlopen(status_request, timeout=30) as response:
                status = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            _delete_google_file(api_key, name)
            raise EditorError("Gemini 视频状态读取失败。") from exc
        file = status.get("file", status)
        state = file.get("state", "")
        uri = file.get("uri") or file.get("fileUri") or uri
    if state != "ACTIVE":
        _delete_google_file(api_key, name)
        raise EditorError("Gemini 视频处理超时，请稍后重试或减小批量。")
    return {"fileData": {"mimeType": "video/mp4", "fileUri": uri}}, name


def _delete_google_file(api_key: str, name: str) -> None:
    request = Request(
        f"https://generativelanguage.googleapis.com/v1beta/{quote(name, safe='/')}",
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key}, method="DELETE",
    )
    try:
        with urlopen(request, timeout=20):
            pass
    except (HTTPError, URLError, TimeoutError, OSError):
        pass


def _parse_response(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.partition("\n")[2].rsplit("```", 1)[0].strip()
    try:
        result = json.loads(text)
    except json.JSONDecodeError as exc:
        raise EditorError(f"AI 返回内容不是有效 JSON：{exc}") from exc
    if not isinstance(result, dict) or not isinstance(result.get("items"), list):
        raise EditorError("AI 返回 JSON 缺少 items 数组。")
    return result


def annotate(root: Path, scan: dict, item_ids: list[str], provider: str, api_key: str,
             model: str, batch_size: int = 4, interval: float = 1.0, retries: int = 2) -> dict:
    if provider not in DEFAULT_MODELS:
        raise EditorError("请选择 OpenAI、Anthropic 或 Google。")
    if not api_key.strip() or not model.strip():
        raise EditorError("API 密钥和模型名称不能为空。")
    api_key = api_key.strip()
    if not 1 <= batch_size <= 12 or not 0 <= interval <= 60 or not 0 <= retries <= 5:
        raise EditorError("批量数量、请求间隔或重试次数超出范围。")
    selected = {str(value) for value in item_ids}
    items = [item for item in scan["changes"] if item["id"] in selected and item["kind"] != "deleted"]
    if not items:
        raise EditorError("请至少选择一条新增或更新的图片。")
    roles = scan["metadata"]["roles"]
    references = [image for role in roles if (image := _role_reference(root, role)) is not None]
    results = []
    errors = []
    batches = [items[index:index + batch_size] for index in range(0, len(items), batch_size)]
    for batch_index, batch in enumerate(batches):
        try:
            media = [part for item in batch for part in _media_parts(root, scan, item, provider)]
            prompt = _prompt(scan, batch)
            for attempt in range(retries + 1):
                try:
                    response = _request(provider, api_key.strip(), model.strip(), prompt, references, media)
                    parsed = _parse_response(response)
                    break
                except (EditorError, ValueError) as exc:
                    if attempt >= retries:
                        raise exc
                    time.sleep(min(2 ** attempt, 8))
            expected_paths = {item["path"] for item in batch}
            received_paths = set()
            for suggestion in parsed["items"]:
                if not isinstance(suggestion, dict) or not isinstance(suggestion.get("path"), str):
                    continue
                if suggestion["path"] not in expected_paths or suggestion["path"] in received_paths:
                    continue
                received_paths.add(suggestion["path"])
                role_id = suggestion.get("role_id")
                role = next((value for value in roles if value["id"] == role_id), None)
                if role is None:
                    suggestion["role_id"] = None
                    suggestion["tags"] = []
                else:
                    tag_values = suggestion.get("tags", [])
                    by_dimension = {}
                    if isinstance(tag_values, list):
                        by_dimension = {value.get("dimension"): value.get("value")
                                        for value in tag_values if isinstance(value, dict) and isinstance(value.get("dimension"), str)}
                    elif isinstance(tag_values, dict):
                        by_dimension = tag_values
                    suggestion["tags"] = [
                        value if type(value) is int and str(value) in role["tags"][dimension] else None
                        for dimension in role["tags"] for value in [by_dimension.get(dimension)]
                    ]
                suggestion["title"] = suggestion.get("title", "").strip() if isinstance(suggestion.get("title"), str) else ""
                results.append(suggestion)
            missing = sorted(expected_paths - received_paths)
            if missing:
                errors.append({"paths": missing, "error": "AI 未返回这些文件的建议，可手工填写或重新标注。"})
        except (EditorError, ValueError) as exc:
            errors.append({"paths": [item["path"] for item in batch], "error": str(exc).replace(api_key, "[已隐藏]")})
        if batch_index + 1 < len(batches) and interval:
            time.sleep(interval)
    return {"suggestions": results, "errors": errors}
