import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock


CORE_PATH = (
    Path(__file__).parents[1]
    / "plugins.v2"
    / "customsiterefresh"
    / "core.py"
)
SPEC = importlib.util.spec_from_file_location("customsiterefresh_core", CORE_PATH)
CORE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CORE)


def load_plugin_module():
    app = types.ModuleType("app")
    app.__path__ = []
    schemas = types.ModuleType("app.schemas")

    class Response:
        def __init__(self, success, message=None, data=None):
            self.success = success
            self.message = message
            self.data = data

    schemas.Response = Response
    app.schemas = schemas

    chain_site = types.ModuleType("app.chain.site")

    class SiteChain:
        update_cookie = Mock(return_value=(True, ""))

    chain_site.SiteChain = SiteChain

    core_config = types.ModuleType("app.core.config")
    core_config.settings = types.SimpleNamespace(
        API_TOKEN="test-token",
        PROXY={
            "http": "http://proxy.test:8080",
            "https": "http://proxy.test:8080",
        },
    )
    core_event = types.ModuleType("app.core.event")
    core_event.eventmanager = types.SimpleNamespace(
        register=lambda _event_type: lambda function: function
    )

    db_site_oper = types.ModuleType("app.db.site_oper")

    class SiteOper:
        sites = {}

        def get(self, site_id):
            return self.sites.get(site_id)

        def list(self):
            return list(self.sites.values())

    db_site_oper.SiteOper = SiteOper

    utils_http = types.ModuleType("app.utils.http")

    class RequestUtils:
        init_calls = []
        request_calls = []
        response = None
        error = None

        def __init__(self, **kwargs):
            self.init_calls.append(kwargs)

        def request(self, **kwargs):
            self.request_calls.append(kwargs)
            if self.error:
                raise self.error
            return self.response

    utils_http.RequestUtils = RequestUtils

    app_log = types.ModuleType("app.log")
    app_log.logger = types.SimpleNamespace(
        info=lambda *_args, **_kwargs: None,
        warning=lambda *_args, **_kwargs: None,
        error=lambda *_args, **_kwargs: None,
    )
    app_plugins = types.ModuleType("app.plugins")

    class PluginBase:
        def post_message(self, **_kwargs):
            pass

    app_plugins._PluginBase = PluginBase
    schema_types = types.ModuleType("app.schemas.types")
    schema_types.EventType = types.SimpleNamespace(PluginAction="plugin.action")
    schema_types.NotificationType = types.SimpleNamespace(SiteMessage="site")

    stubs = {
        "app": app,
        "app.schemas": schemas,
        "app.chain": types.ModuleType("app.chain"),
        "app.chain.site": chain_site,
        "app.core": types.ModuleType("app.core"),
        "app.core.config": core_config,
        "app.core.event": core_event,
        "app.db": types.ModuleType("app.db"),
        "app.db.site_oper": db_site_oper,
        "app.log": app_log,
        "app.plugins": app_plugins,
        "app.schemas.types": schema_types,
        "app.utils": types.ModuleType("app.utils"),
        "app.utils.http": utils_http,
    }
    sys.modules.update(stubs)

    package_dir = CORE_PATH.parent
    module_name = "customsiterefresh_under_test"
    spec = importlib.util.spec_from_file_location(
        module_name,
        package_dir / "__init__.py",
        submodule_search_locations=[str(package_dir)],
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module, SiteOper, SiteChain, RequestUtils


class CustomSiteRefreshCoreTest(unittest.TestCase):
    def test_normalize_host_accepts_domain_and_url(self):
        self.assertEqual(CORE.normalize_host("Example.COM"), "example.com")
        self.assertEqual(
            CORE.normalize_host("https://User:pass@Sub.Example.com:443/path"),
            "sub.example.com",
        )

    def test_parse_site_configs_skips_invalid_lines_without_exposing_values(self):
        configs, errors = CORE.parse_site_configs(
            "example.com|alice|secret|OTPSECRET\ninvalid-line\n|bob|password"
        )
        self.assertEqual(configs, [{
            "host": "example.com",
            "username": "alice",
            "password": "secret",
            "two_step_code": "OTPSECRET",
        }])
        self.assertEqual(errors, ["第 2 行格式错误", "第 3 行格式错误"])
        self.assertNotIn("secret", " ".join(errors))
        self.assertNotIn("password", " ".join(errors))

    def test_find_site_config_prefers_exact_then_longest_parent(self):
        configs, _ = CORE.parse_site_configs(
            "example.com|root|one\npt.example.com|sub|two"
        )
        self.assertEqual(
            CORE.find_site_config("https://pt.example.com/login", configs)["username"],
            "sub",
        )
        self.assertEqual(
            CORE.find_site_config("https://tracker.pt.example.com", configs)["username"],
            "sub",
        )

    def test_find_site_config_does_not_use_last_unmatched_account(self):
        configs, _ = CORE.parse_site_configs(
            "example.com|alice|one\nother.test|bob|two"
        )
        self.assertIsNone(CORE.find_site_config("https://unconfigured.test", configs))

    def test_find_site_config_rejects_substring_domain_collision(self):
        configs, _ = CORE.parse_site_configs("pt.com|alice|secret")
        self.assertIsNone(CORE.find_site_config("https://evilpt.com", configs))


class CustomSiteRefreshFlowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module, cls.site_oper, cls.site_chain, cls.request_utils = load_plugin_module()

    def setUp(self):
        self.module.CustomSiteRefresh._site_locks.clear()
        self.module.CustomSiteRefresh._last_attempts.clear()
        self.module.CustomSiteRefresh._test_results.clear()
        self.module.CustomSiteRefresh._connectivity_results.clear()
        self.site_chain.update_cookie.reset_mock()
        self.site_chain.update_cookie.return_value = (True, "")
        self.response = types.SimpleNamespace(status_code=204, close=Mock())
        self.request_utils.init_calls.clear()
        self.request_utils.request_calls.clear()
        self.request_utils.response = self.response
        self.request_utils.error = None
        self.site_oper.sites = {
            1: types.SimpleNamespace(
                id=1,
                name="ExamplePT",
                url="https://pt.example.com/login",
                proxy=False,
                timeout=15,
            )
        }
        self.plugin = self.module.CustomSiteRefresh()

    def test_unmatched_site_never_attempts_login(self):
        self.plugin.init_plugin({
            "enabled": True,
            "siteconf": "other.test|wrong-user|wrong-password",
        })
        state, message = self.plugin._refresh_site(1, "测试")
        self.assertFalse(state)
        self.assertIn("没有匹配", message)
        self.site_chain.update_cookie.assert_not_called()

    def test_matched_site_passes_credentials_to_moviepilot(self):
        self.plugin.init_plugin({
            "enabled": True,
            "siteconf": "example.com|alice|secret|OTPSECRET",
        })
        state, message = self.plugin._refresh_site(1, "测试")
        self.assertTrue(state)
        self.assertEqual(message, "更新成功")
        self.site_chain.update_cookie.assert_called_once()
        kwargs = self.site_chain.update_cookie.call_args.kwargs
        self.assertEqual(kwargs["username"], "alice")
        self.assertEqual(kwargs["password"], "secret")
        self.assertEqual(kwargs["two_step_code"], "OTPSECRET")

    def test_automatic_duplicate_is_suppressed_during_cooldown(self):
        self.plugin.init_plugin({
            "enabled": True,
            "siteconf": "example.com|alice|secret",
        })
        first_state, _ = self.plugin._refresh_site(1, "自动签到")
        second_state, second_message = self.plugin._refresh_site(1, "自动签到")
        self.assertTrue(first_state)
        self.assertFalse(second_state)
        self.assertIn("冷却期", second_message)
        self.site_chain.update_cookie.assert_called_once()

    def test_manual_api_requires_token_and_records_result(self):
        self.plugin.init_plugin({
            "enabled": False,
            "siteconf": "example.com|alice|secret",
        })
        denied = self.plugin.test_site({"site_id": 1}, "wrong-token")
        self.assertFalse(denied.success)
        self.site_chain.update_cookie.assert_not_called()

        allowed = self.plugin.test_site({"site_id": 1}, "test-token")
        self.assertTrue(allowed.success)
        self.assertIn(1, self.plugin._test_results)
        self.site_chain.update_cookie.assert_called_once()

    def test_connectivity_uses_anonymous_head_without_logging_in(self):
        self.plugin.init_plugin({
            "enabled": False,
            "siteconf": "example.com|alice|secret",
        })
        response = self.plugin.test_connectivity({"site_id": 1}, "test-token")
        self.assertTrue(response.success)
        self.assertIn("直连", response.message)
        self.assertIn("HTTP 204", response.message)
        self.assertEqual(self.request_utils.init_calls[0]["proxies"], None)
        self.assertEqual(self.request_utils.init_calls[0]["timeout"], 10)
        self.assertEqual(
            self.request_utils.init_calls[0]["headers"]["User-Agent"],
            "MoviePilot-Connectivity-Test/1.0",
        )
        self.assertEqual(self.request_utils.request_calls, [{
            "method": "head",
            "url": "https://pt.example.com/login",
            "allow_redirects": False,
            "stream": True,
            "raise_exception": True,
        }])
        self.response.close.assert_called_once()
        self.site_chain.update_cookie.assert_not_called()

    def test_connectivity_honors_site_proxy_and_accepts_http_error_status(self):
        self.site_oper.sites[1].proxy = True
        self.response.status_code = 403
        response = self.plugin.test_connectivity({"site_id": 1}, "test-token")
        self.assertTrue(response.success)
        self.assertIn("站点代理", response.message)
        self.assertIn("HTTP 403", response.message)
        self.assertEqual(self.request_utils.init_calls[0]["proxies"], {
            "http": "http://proxy.test:8080",
            "https": "http://proxy.test:8080",
        })

    def test_connectivity_api_rejects_invalid_token(self):
        response = self.plugin.test_connectivity({"site_id": 1}, "wrong-token")
        self.assertFalse(response.success)
        self.assertEqual(self.request_utils.request_calls, [])

    def test_connectivity_discloses_missing_global_proxy(self):
        self.site_oper.sites[1].proxy = True
        original_proxy = self.module.settings.PROXY
        self.module.settings.PROXY = None
        try:
            response = self.plugin.test_connectivity({"site_id": 1}, "test-token")
        finally:
            self.module.settings.PROXY = original_proxy
        self.assertTrue(response.success)
        self.assertIn("代理未配置，实际直连", response.message)
        self.assertIsNone(self.request_utils.init_calls[0]["proxies"])

    def test_connectivity_failure_reports_only_safe_error_type(self):
        self.request_utils.error = RuntimeError("proxy-user:proxy-password")
        response = self.plugin.test_connectivity({"site_id": 1}, "test-token")
        self.assertFalse(response.success)
        self.assertIn("RuntimeError", response.message)
        self.assertNotIn("proxy-password", response.message)
        self.site_chain.update_cookie.assert_not_called()


if __name__ == "__main__":
    unittest.main()
