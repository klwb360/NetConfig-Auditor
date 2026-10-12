import codecs
from contextlib import redirect_stderr, redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest


class ConfigDecodingTests(unittest.TestCase):
    def decode(self, data, encoding="auto"):
        from netaudit.config_io import decode_config_bytes
        return decode_config_bytes(data, encoding)

    def test_utf8_preserves_original_lines(self):
        text = "hostname LAB\r\n! 中文说明\r\n\tip http server\r\n"
        self.assertEqual(self.decode(text.encode()), (text, "utf-8"))

    def test_bom_encodings_are_identified_and_removed(self):
        text = "hostname LAB\r\n! 中文说明\n"
        for bom, codec, detected in ((codecs.BOM_UTF8, "utf-8", "utf-8-sig"),
                                     (codecs.BOM_UTF16_LE, "utf-16-le", "utf-16-le"),
                                     (codecs.BOM_UTF16_BE, "utf-16-be", "utf-16-be")):
            with self.subTest(codec=codec):
                self.assertEqual(self.decode(bom + text.encode(codec)), (text, detected))

    def test_auto_uses_strict_gb18030_after_utf8(self):
        text = "sysname 实验设备\n# 注释𠀀\n"
        self.assertEqual(self.decode(text.encode("gb18030")), (text, "gb18030"))

    def test_manual_encodings_and_utf16_bom(self):
        text = "sysname 实验设备\n"
        for codec in ("utf-8", "gb18030", "gbk", "utf-16"):
            with self.subTest(codec=codec):
                decoded, used = self.decode(text.encode(codec), codec)
                self.assertEqual(decoded, text)
                self.assertIn(used, (codec, "utf-16-le", "utf-16-be"))
        self.assertEqual(self.decode(codecs.BOM_UTF8 + text.encode(), "utf-8"),
                         (text, "utf-8-sig"))

    def test_invalid_bytes_are_never_replaced_or_ignored(self):
        for data, codec in ((b"hostname LAB\n\xff", "auto"),
                            (b"hostname LAB\n\xc0\xaf", "utf-8"),
                            (b"hostname LAB\n\x81", "gbk"),
                            (b"hostname LAB", "utf-16"),
                            (codecs.BOM_UTF16_LE + b"h", "auto")):
            with self.subTest(codec=codec, data=data):
                with self.assertRaises(ValueError):
                    self.decode(data, codec)

    def test_explicit_encoding_must_match_present_bom(self):
        for data, codec in ((codecs.BOM_UTF8 + b"hostname LAB", "gbk"),
                            (codecs.BOM_UTF16_LE + "hostname LAB".encode("utf-16-le"), "gb18030")):
            with self.subTest(codec=codec):
                with self.assertRaises(ValueError):
                    self.decode(data, codec)

    def test_rejects_controls_binary_empty_and_unknown_encoding(self):
        for data in (b"", b" \r\n\t", b"hostname LAB\x00", b"hostname LAB\x1b[0m",
                     "hostname LAB\u0085secret".encode(), b"PK\x03\x04archive", b"%PDF-1.7\n",
                     codecs.BOM_UTF32_LE + "hostname LAB".encode("utf-32-le")):
            with self.subTest(data=data):
                with self.assertRaises(ValueError):
                    self.decode(data)
        with self.assertRaises(ValueError):
            self.decode(b"hostname LAB", "latin-1")

    def test_size_limit_applies_to_bytes_and_decoded_text(self):
        from netaudit.config_io import MAX_CONFIG_BYTES
        with self.assertRaisesRegex(ValueError, "2 MiB"):
            self.decode(b"x" * (MAX_CONFIG_BYTES + 1))
        with self.assertRaisesRegex(ValueError, "2 MiB"):
            self.decode(("中" * (MAX_CONFIG_BYTES // 3 + 1)).encode("gbk"))


class EncodedCLITests(unittest.TestCase):
    def test_single_audit_encoding_and_source_hash(self):
        from netaudit.cli import main
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "设备.cfg"
            report = Path(directory) / "report.json"
            data = "hostname LAB\n! 中文说明\nip http server\n".encode("gbk")
            source.write_bytes(data)
            with redirect_stderr(io.StringIO()), redirect_stdout(io.StringIO()):
                code = main(["audit", str(source), "--encoding", "gbk", "--format", "json", "--out", str(report)])
            self.assertEqual(code, 0)
            result = json.loads(report.read_text(encoding="utf-8"))
            self.assertEqual(result["source"], {"path": "设备.cfg", "sha256": hashlib.sha256(data).hexdigest(), "encoding": "gbk"})
            self.assertEqual(next(f for f in result["findings"] if f["rule_id"] == "MGMT-HTTP")["evidence"][0]["line"], 3)

    def test_simulation_and_plan_remain_utf8_only(self):
        from netaudit.cli import main
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "设备.cfg"
            source.write_bytes("hostname LAB\n! 中文说明\n".encode("gbk"))
            for command in (["simulate", str(source)], ["plan", str(source), "--goal", "创建 VLAN 20"]):
                with self.subTest(command=command), redirect_stderr(io.StringIO()), redirect_stdout(io.StringIO()):
                    self.assertEqual(main(command), 2)


if __name__ == "__main__":
    unittest.main()
