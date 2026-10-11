import json
import threading
import subprocess
import tempfile
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from scripts import data_editor_ai
from scripts.data_editor_core import MAX_IMAGE_BYTES, EditorError, apply_changes, repository_owner, scan_image_branch, with_baseline
from scripts.data_editor_ai import (
    DEFAULT_MODELS, _parse_response, _request, _run_ffmpeg,
    _schema, _upload_google_video, annotate,
)
from scripts.data_editor_server import create_handler
from scripts.validate_data import validate_data


class DataEditorCoreTests(unittest.TestCase):
    def test_repository_owner_accepts_github_remote_forms(self):
        self.assertEqual(repository_owner("https://github.com/Contributor/NaiLoong.git"), "Contributor")
        self.assertEqual(repository_owner("git@github.com:Contributor/NaiLoong.git"), "Contributor")
        with self.assertRaises(EditorError):
            repository_owner("https://example.com/user/NaiLoong.git")

    def test_scan_uses_image_ref_and_requires_meme_work_branch(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            calls = []

            def fake_git(_root, *args, binary=False):
                calls.append(args)
                if args[:2] == ("branch", "--show-current"):
                    return "meme/test"
                if args[:2] == ("rev-parse", "refs/heads/image"):
                    return "a" * 40
                if args[0] == "rev-parse":
                    return "b" * 40
                if args[0] == "config":
                    return "https://github.com/example-user/NaiLoong.git"
                if args[:2] == ("diff", "--name-status"):
                    return ""
                raise AssertionError(args)

            with patch("scripts.data_editor_core.git", side_effect=fake_git), patch(
                "scripts.data_editor_core.project_metadata", return_value={"roles": []}
            ):
                result = scan_image_branch(root, 3)
            self.assertEqual(result["head"], "a" * 40)
            self.assertEqual(result["base"], "b" * 40)
            self.assertTrue(any("refs/heads/image~3" in call for call in calls))

            with patch("scripts.data_editor_core.git", return_value="image"), self.assertRaisesRegex(
                EditorError, "meme/"
            ):
                scan_image_branch(root, 1)

    def test_scan_count_is_bounded(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(EditorError, "1 到 100"):
                scan_image_branch(Path(temporary), 101)

    def test_git_scan_rename_update_and_delete_review_flow(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)

            def run(*args):
                return subprocess.run(
                    ["git", *args], cwd=root, check=True,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                ).stdout.decode("utf-8", "replace").strip()

            run("init", "-b", "main")
            run("config", "user.name", "Test Contributor")
            run("config", "user.email", "test@example.invalid")
            run("remote", "add", "origin", "https://github.com/example-user/NaiLoong.git")
            data = root / "data" / "naiwa"
            data.mkdir(parents=True)
            manifest = [{"id": "naiwa", "name": "奶蛙", "subcategories": [
                {"id": "animated", "name": "动图", "file": "naiwa/animated.json"},
                {"id": "static", "name": "静态图", "file": "naiwa/static.json"},
            ]}]
            (root / "data" / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            (root / "data" / "tag-translations.json").write_text(
                json.dumps({"mood": {"en": "Mood", "zh": "心情"}}), encoding="utf-8"
            )
            tags = {"mood": {"0": "开心"}}
            (data / "tags.json").write_text(json.dumps(tags), encoding="utf-8")
            (data / "animated.json").write_text("[]\n", encoding="utf-8")
            (data / "static.json").write_text("[]\n", encoding="utf-8")
            run("add", "data")
            run("commit", "-m", "test: seed data")

            image_dir = root / "assets" / "memes"
            image_dir.mkdir(parents=True)
            (image_dir / "old.gif").write_bytes(b"GIF89a" + b"fake-gif-frame")
            (image_dir / "replace.gif").write_bytes(b"GIF89a" + b"old-frame")
            run("switch", "-c", "image")
            run("add", "assets/memes/old.gif", "assets/memes/replace.gif")
            run("commit", "-m", "test: upload image")
            upload_sha = run("rev-parse", "HEAD")
            run("mv", "assets/memes/old.gif", "assets/memes/new.gif")
            (image_dir / "replace.gif").write_bytes(b"GIF89a" + b"high-resolution-frame")
            (image_dir / "fresh.gif").write_bytes(b"GIF89a" + b"new-image")
            run("add", "assets/memes")
            run("commit", "-m", "test: rename and update images")
            (image_dir / "still.webp").write_bytes(b"RIFF" + b"fake-webp")
            run("add", "assets/memes/still.webp")
            run("commit", "-m", "test: add static image")

            run("switch", "main")
            entries = [
                {"title": "旧标题", "url": f"example-user/{upload_sha}/assets/memes/old.gif", "tags": [0]},
                {"title": "清晰度待更新", "url": f"example-user/{upload_sha}/assets/memes/replace.gif", "tags": [0]},
            ]
            (data / "animated.json").write_text(json.dumps(entries), encoding="utf-8")
            run("add", "data/naiwa/animated.json")
            run("commit", "-m", "test: add old entry")
            run("switch", "-c", "meme/test")

            one_commit_scan = scan_image_branch(root, 1)
            self.assertEqual(len(one_commit_scan["changes"]), 1)
            self.assertEqual(one_commit_scan["changes"][0]["category_hint"], "static")
            scan = with_baseline(root, scan_image_branch(root, 2))
            self.assertEqual(len(scan["changes"]), 4)
            rename = next(item for item in scan["changes"] if item["kind"] == "updated" and item["change_reason"] == "重命名")
            self.assertEqual(rename["old_record"]["entry"]["title"], "旧标题")
            self.assertIn("assets/memes/new.gif", rename["url"])
            replace = next(item for item in scan["changes"] if item["kind"] == "updated" and item["path"].endswith("replace.gif"))
            self.assertEqual(replace["change_reason"], "图片内容更新")
            additions = [item for item in scan["changes"] if item["kind"] == "added"]
            self.assertEqual({item["category_hint"] for item in additions}, {"animated", "static"})
            self.assertTrue(all(item.get("role_id") is None for item in additions))
            decisions = []
            for item in scan["changes"]:
                old_title = (item.get("entry") or {}).get("title", "")
                decisions.append({
                    "id": item["id"], "selected": True, "role_id": "naiwa",
                    "category_id": item["category_hint"],
                    "title": "新标题" if item is rename else old_title or item["path"], "tags": [0],
                })
            apply_changes(root, scan, decisions)
            animated = json.loads((data / "animated.json").read_text(encoding="utf-8"))
            static = json.loads((data / "static.json").read_text(encoding="utf-8"))
            self.assertEqual(len(animated), 3)
            self.assertEqual(len(static), 1)
            self.assertEqual(next(item for item in animated if item["title"] == "新标题")["tags"], [0])

            run("add", "data/naiwa/animated.json")
            run("commit", "-m", "test: apply rename data")
            run("switch", "image")
            run("rm", "assets/memes/new.gif")
            run("commit", "-m", "test: remove image")
            run("switch", "meme/test")
            delete_scan = with_baseline(root, scan_image_branch(root, 1))
            deleted = delete_scan["changes"][0]
            self.assertEqual(deleted["kind"], "deleted")
            self.assertIsNotNone(deleted["old_record"])
            self.assertEqual(run("show", f"{deleted['restore_ref']}:assets/memes/new.gif"), "GIF89a" + "fake-gif-frame")
            apply_changes(root, delete_scan, [{"id": deleted["id"], "selected": False, "remove_record": False}])
            self.assertEqual(len(json.loads((data / "animated.json").read_text(encoding="utf-8"))), 3)
            apply_changes(root, with_baseline(root, delete_scan), [
                {"id": deleted["id"], "selected": False, "remove_record": True}
            ])
            self.assertEqual(len(json.loads((data / "animated.json").read_text(encoding="utf-8"))), 2)

    def test_apply_updates_url_and_preserves_old_tags_transactionally(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            data = root / "data"
            (data / "naiwa").mkdir(parents=True)
            manifest = [{
                "id": "naiwa", "name": "奶蛙", "subcategories": [
                    {"id": "animated", "name": "动图", "file": "naiwa/animated.json"},
                    {"id": "static", "name": "静态图", "file": "naiwa/static.json"},
                ],
            }]
            (data / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            (data / "tag-translations.json").write_text("{}", encoding="utf-8")
            tags = {"mood": {"0": "平静", "1": "开心"}}
            (data / "naiwa" / "tags.json").write_text(json.dumps(tags), encoding="utf-8")
            old_url = "contributor/" + "a" * 40 + "/assets/memes/old.gif"
            entries = [{"title": "旧标题", "url": old_url, "tags": [1]}]
            category = data / "naiwa" / "animated.json"
            category.write_text(json.dumps(entries), encoding="utf-8")
            (data / "naiwa" / "static.json").write_text("[]", encoding="utf-8")
            (data / "tag-translations.json").write_text(json.dumps({"mood": {"en": "Mood", "zh": "心情"}}), encoding="utf-8")
            metadata = {
                "roles": [{
                    "id": "naiwa", "name": "奶蛙", "tags": tags,
                    "categories": [
                        {"id": "animated", "name": "动图", "file": "naiwa/animated.json"},
                        {"id": "static", "name": "静态图", "file": "naiwa/static.json"},
                    ],
                }]
            }
            scan = with_baseline(root, {
                "head": "b" * 40, "metadata": metadata,
                "changes": [{
                    "id": "0", "kind": "updated", "url": "contributor/" + "b" * 40 + "/assets/memes/new.gif",
                    "old_record": {"file": "naiwa/animated.json", "index": 0,
                                   "role_id": "naiwa", "entry": entries[0]},
                }],
            })
            decisions = [{"id": "0", "selected": True, "role_id": "naiwa",
                          "category_id": "animated", "title": "新标题", "tags": [None]}]
            result = apply_changes(root, scan, decisions)
            self.assertEqual(result["written_files"], ["naiwa/animated.json"])
            updated = json.loads(category.read_text(encoding="utf-8"))[0]
            self.assertEqual(updated["url"], "contributor/" + "b" * 40 + "/assets/memes/new.gif")
            self.assertEqual(updated["tags"], [None])

            large_scan = with_baseline(root, {
                "head": "d" * 40, "metadata": metadata,
                "changes": [{
                    "id": "large", "kind": "added", "path": "assets/memes/large.png",
                    "url": "contributor/" + "d" * 40 + "/large.png",
                    "size_bytes": MAX_IMAGE_BYTES + 1,
                }],
            })
            with self.assertRaisesRegex(EditorError, "超过 5 MB"):
                apply_changes(root, large_scan, [{
                    "id": "large", "selected": True, "role_id": "naiwa",
                    "category_id": "static", "title": "过大图片", "tags": [0],
                }])

            broken = with_baseline(root, {
                "head": "c" * 40, "metadata": metadata,
                "changes": [{"id": "1", "kind": "added", "url": "contributor/" + "b" * 40 + "/assets/memes/new.gif"}],
            })
            before = category.read_bytes()
            duplicate = json.loads(before.decode("utf-8"))
            duplicate.append({"title": "重复", "url": "contributor/" + "b" * 40 + "/assets/memes/new.gif", "tags": [0]})
            category.write_text(json.dumps(duplicate), encoding="utf-8")
            self.assertTrue(any("重复" in error for error in validate_data(root)))
            category.write_bytes(before)
            with self.assertRaisesRegex(EditorError, "数据校验失败"):
                apply_changes(root, broken, [{"id": "1", "selected": True, "role_id": "naiwa",
                                              "category_id": "animated", "title": "重复", "tags": [0]}])
            self.assertEqual(category.read_bytes(), before)


class DataEditorAITests(unittest.TestCase):
    def test_supported_provider_defaults_and_schema(self):
        self.assertEqual(set(DEFAULT_MODELS), {"openai", "anthropic", "google"})
        self.assertIn("items", _schema()["properties"])
        self.assertFalse(_schema()["additionalProperties"])

    def test_parse_json_and_reject_invalid_shapes(self):
        self.assertEqual(_parse_response('{"items": []}'), {"items": []})
        self.assertEqual(_parse_response("```json\n{\"items\": []}\n```"), {"items": []})
        with self.assertRaises(EditorError):
            _parse_response("not json")
        with self.assertRaises(EditorError):
            _parse_response("{}")

    def test_annotate_rejects_invalid_provider_and_settings_before_network(self):
        with self.assertRaises(EditorError):
            annotate(Path("."), {"changes": [], "metadata": {"roles": []}}, [], "invalid", "x", "m")
        with self.assertRaises(EditorError):
            annotate(Path("."), {"changes": [], "metadata": {"roles": []}}, [], "openai", "x", "m", batch_size=13)

    def test_provider_requests_use_native_vision_and_json_contracts(self):
        class Response:
            def __init__(self, payload, headers=None):
                self.payload = payload
                self.headers = headers or {}

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return json.dumps(self.payload).encode("utf-8")

        inputs = {
            "openai": {"output": [{"content": [{"type": "output_text", "text": '{"items":[]}'}]}]},
            "anthropic": {"content": [{"type": "text", "text": '{"items":[]}'}]},
            "google": {"candidates": [{"content": {"parts": [{"text": '{"items":[]}'}]}}]},
        }
        for provider in inputs:
            with self.subTest(provider=provider), patch.object(
                data_editor_ai, "urlopen", return_value=Response(inputs[provider])
            ) as open_request:
                result = _request(provider, "test-secret", "vision-model", "label each image", [],
                                  [("image/png", "sample.png", b"png")])
                self.assertEqual(_parse_response(result), {"items": []})
                request = open_request.call_args.args[0]
                body = json.loads(request.data.decode("utf-8"))
                if provider == "openai":
                    self.assertEqual(request.full_url, "https://api.openai.com/v1/responses")
                    self.assertIn("Bearer test-secret", request.get_header("Authorization"))
                    self.assertEqual(body["input"][0]["content"][1]["type"], "input_text")
                    self.assertEqual(body["text"]["format"]["type"], "json_schema")
                elif provider == "anthropic":
                    self.assertEqual(request.full_url, "https://api.anthropic.com/v1/messages")
                    self.assertEqual(request.get_header("X-api-key"), "test-secret")
                    self.assertEqual(body["messages"][0]["content"][1]["type"], "image")
                    self.assertEqual(body["output_config"]["format"]["type"], "json_schema")
                else:
                    self.assertNotIn("test-secret", request.full_url)
                    self.assertEqual(request.get_header("X-goog-api-key"), "test-secret")
                    self.assertEqual(body["contents"][0]["parts"][2]["inlineData"]["mimeType"], "image/png")
                    self.assertEqual(body["generationConfig"]["responseFormat"]["text"]["mimeType"], "APPLICATION_JSON")
                    self.assertEqual(body["generationConfig"]["responseFormat"]["text"]["schema"]["type"], "object")

    def test_gif_conversion_builds_mp4_and_contact_sheet_without_dependencies(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            source = directory / "sample.gif"
            source.write_bytes(b"gif")

            def run(command, **_kwargs):
                Path(command[-1]).write_bytes(b"mp4" if command[-1].endswith(".mp4") else b"jpeg-sheet")

            with patch.object(data_editor_ai.subprocess, "run", side_effect=run) as mocked:
                video, frames = _run_ffmpeg(source, directory)
            self.assertEqual(video, b"mp4")
            self.assertEqual(frames, [b"jpeg-sheet"])
            command = mocked.call_args_list[1].args[0]
            self.assertEqual(
                command[command.index("-vf") + 1],
                "fps=1,scale=256:-2,tile=4x2:padding=4:margin=4:color=white",
            )

    def test_gemini_video_upload_uses_files_resumable_headers_and_mime(self):
        class Response:
            def __init__(self, payload=b"", headers=None):
                self.payload = payload
                self.headers = headers or {}

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return self.payload

        responses = [
            Response(headers={"X-Goog-Upload-URL": "https://upload.example/session"}),
            Response(json.dumps({"file": {"name": "files/demo", "uri": "https://files.example/demo", "state": "ACTIVE"}}).encode()),
        ]
        with patch.object(data_editor_ai, "urlopen", side_effect=responses) as opened:
            part, name = _upload_google_video("secret", "clip.mp4", b"mp4-data")
        self.assertEqual(name, "files/demo")
        self.assertEqual(part["fileData"]["mimeType"], "video/mp4")
        init = opened.call_args_list[0].args[0]
        upload = opened.call_args_list[1].args[0]
        self.assertNotIn("secret", init.full_url)
        self.assertEqual(init.get_header("X-goog-api-key"), "secret")
        self.assertEqual(upload.get_header("X-goog-upload-command"), "upload, finalize")

    def test_annotate_batches_items_retries_failures_and_validates_suggestions(self):
        items = [{
            "id": str(index), "path": f"assets/memes/{index}.png", "kind": "added",
            "media_type": "static", "selected": True,
        } for index in range(3)]
        role = {
            "id": "naiwa", "name": "奶蛙", "tags": {"mood": {"0": "开心"}},
            "examples": ["奶蛙大笑"], "categories": [], "image": "naiwa/naiwa.png",
        }
        scan = {"head": "a" * 40, "changes": items, "metadata": {"roles": [role]}}
        calls = {"count": 0}

        def request(_provider, _key, _model, _prompt, _references, media):
            calls["count"] += 1
            if calls["count"] == 1:
                raise EditorError("temporary provider error")
            return json.dumps({"items": [{
                "path": path, "title": "模型建议", "role_id": "naiwa",
                "tags": [{"dimension": "mood", "value": 0}, {"dimension": "unknown", "value": 9}],
            } for _mime, path, _content in media]}, ensure_ascii=False)

        media = lambda _root, _scan, item, _provider: [("image/png", item["path"], b"png")]
        with patch("scripts.data_editor_ai._media_parts", side_effect=media), \
                patch("scripts.data_editor_ai._role_reference", return_value=None), \
                patch("scripts.data_editor_ai._request", side_effect=request), \
                patch("scripts.data_editor_ai.time.sleep") as sleep:
            result = annotate(
                Path("."), scan, ["0", "1", "2"], "openai", "local-key",
                "vision-model", batch_size=2, interval=0.5, retries=1,
            )
        self.assertEqual(calls["count"], 3)
        self.assertEqual(len(result["suggestions"]), 3)
        self.assertEqual(result["errors"], [])
        self.assertTrue(all(item["tags"] == [0] for item in result["suggestions"]))
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [1, 0.5])


class DataEditorServerTests(unittest.TestCase):
    def test_local_browser_service_serves_tool_and_rejects_cross_origin_posts(self):
        root = Path(__file__).resolve().parents[1]
        server = ThreadingHTTPServer(
            ("127.0.0.1", 0), create_handler(root, {}, threading.RLock())
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            self.assertEqual(server.server_address[0], "127.0.0.1")
            with urlopen(base + "/") as response:
                self.assertIn("差异编辑器", response.read().decode("utf-8"))
            with urlopen(base + "/api/project") as response:
                project = json.loads(response.read().decode("utf-8"))
            self.assertEqual({role["id"] for role in project["roles"]}, {"naiwa", "naidan"})
            with urlopen(base + "/assets/js/editor.js") as response:
                self.assertIn("确认并写入数据", response.read().decode("utf-8"))

            request = Request(
                base + "/api/apply", data=b"{}", method="POST",
                headers={"Content-Type": "application/json", "Origin": "https://attacker.example"},
            )
            with self.assertRaises(HTTPError) as denied:
                urlopen(request)
            self.assertEqual(denied.exception.code, 403)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)


if __name__ == "__main__":
    unittest.main()
