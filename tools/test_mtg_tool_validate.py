#!/usr/bin/env python3
"""mtg_tool validate 数量门禁测试（check_card 打 mock，不访问网络）。"""

import sys
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mtg_tool  # noqa: E402


def _limited_deck_text(n_main):
    lines = ["1 Card %d" % i for i in range(n_main)]
    lines += ["Sideboard"] + ["1 Cut %d" % i for i in range(20)]
    return "\n".join(lines) + "\n"


class TestValidateLimitedGate(unittest.TestCase):
    def _run(self, text, *extra):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "deck.txt"
            path.write_text(text, encoding="utf-8")
            parser = mtg_tool.build_parser()
            args = parser.parse_args(["validate", str(path), "--format", "standard"] + list(extra))
            ok_rec = {"english": "", "ok": True, "notes": [], "type_line": "Creature",
                      "color_identity": ["R"], "legal": True, "platform_ok": True}
            with mock.patch.object(mtg_tool, "check_card", return_value=ok_rec), \
                    mock.patch("sys.stderr", new=StringIO()):
                return mtg_tool.cmd_validate(args)

    def test_limited_accepts_41_with_cuts_beyond_15(self):
        self.assertEqual(self._run(_limited_deck_text(41), "--limited"), 0)

    def test_limited_accepts_40(self):
        self.assertEqual(self._run(_limited_deck_text(40), "--limited"), 0)

    def test_limited_rejects_39(self):
        self.assertEqual(self._run(_limited_deck_text(39), "--limited"), 4)

    def test_constructed_gate_unchanged(self):
        # 41 张在构筑口径下仍违规；备牌 >15 仍违规（限制赛口径下不违规）
        self.assertEqual(self._run(_limited_deck_text(41)), 4)
        self.assertEqual(self._run(_limited_deck_text(60)), 4)  # sb 20 > 15
        self.assertEqual(self._run(_limited_deck_text(60), "--limited"), 4)  # 60 非 40/41

    def test_constructed_60_plus_sb15_passes(self):
        self.assertEqual(self._run(_limited_deck_text(60).replace(
            "Sideboard\n" + "\n".join("1 Cut %d" % i for i in range(20)),
            "Sideboard\n" + "\n".join("1 Cut %d" % i for i in range(15)))), 0)


if __name__ == "__main__":
    unittest.main()
