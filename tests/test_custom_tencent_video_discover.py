import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock


ROOT = Path(__file__).resolve().parents[1]
CORE_PATH = ROOT / "plugins.v2" / "customtencentvideodiscover" / "core.py"
SPEC = importlib.util.spec_from_file_location("custom_tencent_video_core", CORE_PATH)
CORE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CORE)


class CustomTencentVideoCoreTest(unittest.TestCase):
    def test_extract_item_datas_selects_richest_module_without_fixed_index(self):
        payload = {
            "data": {
                "module_list_datas": [
                    {"module_datas": [{"item_data_lists": {"item_datas": [
                        {"item_type": 11}, {"item_type": 11},
                        {"item_type": 11}, {"item_type": 11},
                    ]}}]},
                    {"module_datas": [{"item_data_lists": {"item_datas": [
                        {"item_type": 11}, {"item_type": 2}, {"item_type": 2},
                    ]}}]},
                ]
            }
        }
        items = CORE.extract_item_datas(payload)
        self.assertEqual(len(items), 3)
        self.assertEqual(sum(str(item["item_type"]) == "2" for item in items), 2)

    def test_extract_item_datas_handles_malformed_payload(self):
        for payload in (None, {}, {"data": None}, {"data": {"module_list_datas": {}}}):
            self.assertEqual(CORE.extract_item_datas(payload), [])

    def test_build_filter_groups_uses_all_label_and_deduplicates(self):
        items = [
            {"item_type": 11, "item_params": {
                "index_item_key": "iyear", "index_name": "", "option_name": "全部年份", "option_value": "-1",
            }},
            {"item_type": "11", "item_params": {
                "index_item_key": "iyear", "index_name": "年份", "option_name": "2026", "option_value": "2026",
            }},
            {"item_type": "11", "item_params": {
                "index_item_key": "iyear", "index_name": "年份", "option_name": "重复", "option_value": "2026",
            }},
        ]
        groups = CORE.build_filter_groups(items)
        self.assertEqual(groups, [{
            "key": "iyear",
            "label": "全部年份",
            "options": [{"value": "2026", "text": "2026"}],
        }])

    def test_media_items_filters_invalid_records_and_honors_count(self):
        items = [
            {"item_type": 11, "item_params": {}},
            {"item_type": 2, "item_params": {"title": "A", "cid": "1"}},
            {"item_type": 2, "item_params": {"title": "", "cid": "2"}},
            {"item_type": "2", "item_params": {"title": "B", "cid": 3}},
        ]
        self.assertEqual(
            [item["title"] for item in CORE.media_items(items, count=2)],
            ["A", "B"],
        )

    def test_normalize_poster_url_and_integer_clamping(self):
        self.assertEqual(
            CORE.normalize_poster_url({"new_pic_vt": "https://puui.qpic.cn/vcover_vt_pic/0/a/350"}),
            "https://puui.qpic.cn/vcover_vt_pic/0/a",
        )
        self.assertEqual(CORE.clamp_positive_int("0", 10, 100), 1)
        self.assertEqual(CORE.clamp_positive_int("999", 10, 100), 100)
        self.assertEqual(CORE.clamp_positive_int("bad", 10, 100), 10)


def load_plugin_module():
    requests_module = types.ModuleType("requests")

    class RequestException(Exception):
        pass

    requests_module.RequestException = RequestException
    requests_module.post = Mock()

    app_module = types.ModuleType("app")
    schemas_module = types.ModuleType("app.schemas")

    class DataObject:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    schemas_module.MediaInfo = DataObject
    schemas_module.DiscoverMediaSource = DataObject
    schemas_module.DiscoverSourceEventData = DataObject
    app_module.schemas = schemas_module

    cache_module = types.ModuleType("app.core.cache")
    cache_module.cached = lambda **_kwargs: (lambda function: function)

    config_module = types.ModuleType("app.core.config")
    config_module.settings = types.SimpleNamespace(
        API_TOKEN="test-token",
        SECURITY_IMAGE_DOMAINS=[],
    )

    event_module = types.ModuleType("app.core.event")

    class Event:
        def __init__(self, event_data=None):
            self.event_data = event_data

    class EventManager:
        @staticmethod
        def register(_event_type):
            return lambda function: function

    event_module.Event = Event
    event_module.eventmanager = EventManager()

    log_module = types.ModuleType("app.log")
    log_module.logger = types.SimpleNamespace(warning=Mock(), info=Mock(), debug=Mock())

    plugins_module = types.ModuleType("app.plugins")
    plugins_module._PluginBase = object

    types_module = types.ModuleType("app.schemas.types")
    types_module.ChainEventType = types.SimpleNamespace(DiscoverSource="DiscoverSource")

    core_package = types.ModuleType("app.core")
    core_package.__path__ = []
    schemas_module.__path__ = []
    sys.modules.update({
        "requests": requests_module,
        "app": app_module,
        "app.schemas": schemas_module,
        "app.core": core_package,
        "app.core.cache": cache_module,
        "app.core.config": config_module,
        "app.core.event": event_module,
        "app.log": log_module,
        "app.plugins": plugins_module,
        "app.schemas.types": types_module,
    })

    plugin_dir = CORE_PATH.parent
    spec = importlib.util.spec_from_file_location(
        "customtencentvideodiscover",
        plugin_dir / "__init__.py",
        submodule_search_locations=[str(plugin_dir)],
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module, requests_module, event_module


class CustomTencentVideoPluginTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module, cls.requests, cls.events = load_plugin_module()

    def setUp(self):
        self.plugin = self.module.CustomTencentVideoDiscover()
        self.plugin._enabled = True
        self.plugin._filter_rows = []

    def test_plugin_identity_is_independent_from_upstream(self):
        self.assertEqual(self.plugin.plugin_version, "1.0.0")
        self.assertEqual(
            self.plugin.plugin_config_prefix,
            "customtencentvideodiscover_",
        )
        api = self.plugin.get_api()[0]
        self.assertEqual(api["path"], "/tencentvideo_discover")

    def test_discover_source_uses_custom_api_and_media_prefix(self):
        event_data = types.SimpleNamespace(extra_sources=[])
        self.plugin.discover_source(self.events.Event(event_data))
        self.assertEqual(len(event_data.extra_sources), 1)
        source = event_data.extra_sources[0]
        self.assertEqual(source.mediaid_prefix, "customtencentvideo")
        self.assertIn("plugin/CustomTencentVideoDiscover/", source.api_path)
        self.assertIn("apikey=test-token", source.api_path)
        self.plugin.discover_source(self.events.Event(event_data))
        self.assertEqual(len(event_data.extra_sources), 1)

    def test_disabled_plugin_does_not_register_or_return_media(self):
        self.plugin._enabled = False
        event_data = types.SimpleNamespace(extra_sources=[])
        self.plugin.discover_source(self.events.Event(event_data))
        self.assertEqual(event_data.extra_sources, [])
        self.assertEqual(self.plugin.tencentvideo_discover(), [])

    def test_endpoint_validates_channel_and_converts_media(self):
        self.plugin._request = Mock(return_value=[
            {"item_type": 2, "item_params": {
                "title": "示例电影", "year": "2026", "cid": "cid-1",
                "new_pic_vt": "https://puui.qpic.cn/poster/350",
            }},
            {"item_type": 2, "item_params": {
                "title": "第二部", "year": "2025", "cid": "cid-2",
            }},
        ])
        results = self.plugin.tencentvideo_discover(
            mtype="movie", page="2", count="1", iyear="2026"
        )
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].type, "电影")
        self.assertEqual(results[0].mediaid_prefix, "customtencentvideo")
        self.assertEqual(results[0].media_id, "cid-1")
        self.assertEqual(results[0].poster_path, "https://puui.qpic.cn/poster")
        self.plugin._request.assert_called_once_with(2, "movie", iyear="2026")
        self.assertEqual(self.plugin.tencentvideo_discover(mtype="invalid"), [])

    def test_fetch_page_sets_bounded_timeout(self):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"data": {"module_list_datas": []}}
        self.requests.post.reset_mock()
        self.requests.post.return_value = response
        self.assertEqual(self.plugin._fetch_page("100113"), [])
        self.assertEqual(
            self.requests.post.call_args.kwargs["timeout"],
            self.module.REQUEST_TIMEOUT,
        )


if __name__ == "__main__":
    unittest.main()
