import base64
import importlib.util
import pathlib
import sys
import types
import unittest
from unittest.mock import patch


def _load_headers_module():
    # Load headers.py in isolation against lightweight stubs. The stubbed
    # sys.modules entries are restored afterwards so this does NOT permanently
    # pollute the interpreter for other test modules (notably the real
    # app.platform.config.snapshot, which other suites import).
    logger_stub = types.SimpleNamespace(debug=lambda *args, **kwargs: None)
    stubs = {
        "app.platform.logging.logger": types.SimpleNamespace(logger=logger_stub),
        "app.platform.config.snapshot": types.SimpleNamespace(get_config=lambda: None),
        "app.control.proxy.models": types.SimpleNamespace(ProxyLease=object),
        "app.dataplane.proxy.adapters.profile": types.SimpleNamespace(
            ProxyProfile=object,
            resolve_proxy_profile=lambda lease: None,
        ),
    }
    parents = [
        "app", "app.platform", "app.platform.logging", "app.platform.config",
        "app.control", "app.control.proxy", "app.dataplane",
        "app.dataplane.proxy", "app.dataplane.proxy.adapters",
    ]

    saved: dict[str, object] = {}
    added: list[str] = []
    for name in list(stubs) + parents:
        if name in sys.modules:
            saved[name] = sys.modules[name]
        else:
            added.append(name)

    try:
        for name in parents:
            sys.modules.setdefault(name, types.ModuleType(name))
        for name, stub in stubs.items():
            sys.modules[name] = stub

        file_path = pathlib.Path(__file__).resolve().parents[1] / "app/dataplane/proxy/adapters/headers.py"
        spec = importlib.util.spec_from_file_location("test_headers_module", file_path)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        return module
    finally:
        # Restore originals; drop any entries we introduced.
        for name in added:
            sys.modules.pop(name, None)
        for name, original in saved.items():
            sys.modules[name] = original


headers = _load_headers_module()


class _DummyConfig:
    def get_bool(self, key, default=False):
        if key == "features.dynamic_statsig":
            return True
        return default


class StatsigIdTests(unittest.TestCase):
    def test_dynamic_statsig_uses_x1_prefix(self):
        with patch.object(headers, "get_config", return_value=_DummyConfig()):
            with patch.object(headers.random, "choice", return_value=True):
                value = headers._statsig_id()

        decoded = base64.b64decode(value).decode()
        self.assertTrue(decoded.startswith("x1:TypeError:"))


if __name__ == "__main__":
    unittest.main()
