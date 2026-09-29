import unittest

from scripts.meme_hash import (
    added_canonical_urls,
    find_duplicates,
    normalize_state,
    parse_issue_image_urls,
    parse_hash_file,
    strip_status_block,
    validate_image_payload,
)


class MemeHashTests(unittest.TestCase):
    def test_parse_hash_file_accepts_blank_lines_and_rejects_bad_values(self):
        self.assertEqual(parse_hash_file("\n" + "a" * 64 + "\n"), {"a" * 64})
        with self.assertRaisesRegex(Exception, "line 1"):
            parse_hash_file("not-a-hash\n")

    def test_parse_issue_images_from_markdown_and_html(self):
        body = (
            "![one](https://github.com/user-attachments/assets/one)\n"
            '<img src="https://github.com/user-attachments/assets/two">\n'
            "![not-image](https://example.com/image.png)"
        )
        self.assertEqual(
            parse_issue_image_urls(body),
            [
                "https://github.com/user-attachments/assets/one",
                "https://github.com/user-attachments/assets/two",
                "https://example.com/image.png",
            ],
        )

    def test_parse_issue_images_preserves_markdown_then_html_order(self):
        body = '<img src="https://github.com/user-attachments/assets/two"> ![one](https://github.com/user-attachments/assets/one)'
        self.assertEqual(
            parse_issue_image_urls(body),
            [
                "https://github.com/user-attachments/assets/two",
                "https://github.com/user-attachments/assets/one",
            ],
        )

    def test_parse_issue_body_html_keeps_signed_private_image_url(self):
        signed = (
            "https://private-user-images.githubusercontent.com/1/2.png"
            "?jwt=eyJhbGciOiJIUzI1NiJ9&amp;expires=123"
        )
        self.assertEqual(parse_issue_image_urls(f'<p><img src="{signed}"></p>'), [
            signed.replace("&amp;", "&"),
        ])

    def test_find_duplicates_includes_known_and_repeated_hashes(self):
        digest_a = "a" * 64
        digest_b = "b" * 64
        self.assertEqual(
            find_duplicates([digest_a, digest_b, digest_b], {digest_a}),
            [(1, digest_a), (3, digest_b)],
        )

    def test_added_canonical_urls_only_returns_new_occurrences(self):
        old = ["a", "b", "b"]
        new = ["a", "b", "b", "c", "c"]
        self.assertEqual(added_canonical_urls(old, new), ["c", "c"])

    def test_added_canonical_urls_handles_empty_base(self):
        self.assertEqual(added_canonical_urls([], ["a", "b"]), ["a", "b"])

    def test_state_normalization_adds_cache_sections(self):
        state = normalize_state({"ingested": ["a" * 64]})
        self.assertEqual(state["ingested"], ["a" * 64])
        self.assertEqual(state["reserved"], {})
        self.assertEqual(state["comments"], {})
        self.assertEqual(state["pull_requests"], {})

    def test_status_block_replacement_preserves_comment_body(self):
        body = (
            "<!-- nai-meme-hash-status:start -->\n"
            "[ ⚪ 未处理 ]\n认领口令：MEME-CLAIM-abc\n"
            "<!-- nai-meme-hash-status:end -->\n\n"
            "投稿者的说明和图片链接"
        )
        self.assertEqual(strip_status_block(body), "投稿者的说明和图片链接")

    def test_image_payload_has_strict_five_mb_limit(self):
        with self.assertRaisesRegex(Exception, "5 MB"):
            validate_image_payload(b"x" * (5 * 1024 * 1024 + 1), "image/png")


if __name__ == "__main__":
    unittest.main()
