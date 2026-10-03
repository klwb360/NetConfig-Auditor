# SPDX-License-Identifier: GPL-3.0-only
"""Execute audited upstream method excerpts in isolation; no dependencies/network.

The parser stand-in implements only regex find_objects, not all CiscoConfParse.
These reproduce the documented control-flow/type defects, not a full upstream run.
"""
import json
from pathlib import Path
import re
from types import SimpleNamespace
import unittest


DATA = json.loads((Path(__file__).parent / "upstream_methods.json").read_text())


class ParserStandIn:
    def __init__(self, text):
        self.lines = text.splitlines()

    def find_objects(self, pattern):
        return [line for line in self.lines if re.search(pattern, line)]


def method(name, namespace=None):
    values = dict(namespace or {})
    exec(compile(DATA["methods"][name]["source"], "audited_upstream_excerpt", "exec"), values)
    return values[name]


class UpstreamReproductions(unittest.TestCase):
    def test_http_disable_is_misclassified(self):
        plug = SimpleNamespace(parse_cisco_ios_config_file=lambda _: ParserStandIn("no ip http server"))
        self.assertIs(method("_has_http")(plug, "unused"), True)
        print("CONFIRMED U-01: no ip http server -> _has_http=True")

    def test_ssh_retries_raises_typeerror(self):
        plug = SimpleNamespace(_get_cisco_ios_ssh_retries=lambda _: "3")
        with self.assertRaises(TypeError):
            method("get_cisco_ios_ssh_reties")(plug, "unused")
        print("CONFIRMED U-02: parsed SSH retry string '3' compared to int 5 -> TypeError")

    def test_secure_vty_hides_insecure_vty(self):
        parser = ParserStandIn("line vty 0 4\n transport input ssh\n!\nline vty 5 15\n transport input telnet")
        result = method("get_cisco_ios_telnet", {"parse_cisco_ios_config_file": lambda _: parser})("unused")
        self.assertFalse(result)
        print("CONFIRMED U-03: SSH-only VTY + Telnet VTY -> get_cisco_ios_telnet=False")


if __name__ == "__main__":
    print("Audited upstream commit:", DATA["commit"])
    unittest.main(verbosity=2)
