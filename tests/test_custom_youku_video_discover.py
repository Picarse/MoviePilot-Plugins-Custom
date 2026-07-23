import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock


ROOT = Path(__file__).resolve().parents[1]
CORE_PATH = ROOT / "plugins.v2" / "customyoukuvideodiscover" / "core.py"
SPEC = importlib.util.spec_from_file_location("custom_youku_video_core", CORE_PATH)
CORE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CORE)


def initial_data_html(payload: str) -> str:
    return f"<html><script>window.__INITIAL_DATA__ ={payload};</script></html>"


class CustomYoukuVideoCoreTest(unittest.TestCase):
    def test_parse_initial_data_accepts_youku_undefined_values(self):
        html = initial_data_html(
            '{"pageMap":{"nodeKey":"WEBMOVIE","optional":undefined},'
            '"moduleList":[],"values":[1,undefined]}'
        )
        payload = CORE.parse_initial_data(html)
        self.assertEqual(payload["pageMap"]["nodeKey"], "WEBMOVIE")
        self.assertIsNone(payload["pageMap"]["optional"])
        self.assertEqual(payload["values"], [1, None])

    def test_parse_initial_data_rejects_missing_or_malformed_payload(self):
        for value in (None, "", "<html></html>", initial_data_html("{")):
            self.assertEqual(CORE.parse_initial_data(value), {})

    def test_extract_media_items_prefers_feed_and_filters_noise(self):
        payload = {
            "moduleList": [
                {"typeName": "KU_FLIX_LUNBO_V2", "components": [{"itemList": [
                    {"title": "轮播节目", "action_value": "carousel"},
                ]}]},
                {"typeName": "FEED_DRAWER_PAGINATION", "components": [
                    {"typeName": "KU_FLIX_FEED_V_SCROLL_COMPONENT", "itemList": [
                        {
                            "title": "示例电影",
                            "action_type": "JUMP_TO_SHOW",
                            "action_value": "show-1",
                            "img": "http://m.ykimg.com/poster.jpg",
                        },
                        {
                            "title": "重复节目",
                            "action_type": "JUMP_TO_SHOW",
                            "action_value": "show-1",
                            "img": "https://m.ykimg.com/duplicate.jpg",
                        },
                        {
                            "title": "广告",
                            "action_value": "ad-1",
                            "isYkAd": True,
                        },
                    ]},
                    {"typeName": "KU_FLIX_SHORT_VIDEO_COMPONENT", "itemList": [
                        {"title": "短视频", "action_value": "clip-1"},
                    ]},
                ]},
            ]
        }
        items = CORE.extract_media_items(payload)
        self.assertEqual(items, [{
            "title": "示例电影",
            "year": None,
            "media_id": "show-1",
            "poster": "https://m.ykimg.com/poster.jpg",
        }])

    def test_extract_media_items_falls_back_to_all_modules(self):
        payload = {"moduleList": [{"components": [{"itemList": [{
            "title": "节目",
            "action": {"value": "show-2"},
            "hImg": "//ykimg.alicdn.com/cover.jpg",
            "year": "2026",
        }]}]}]}
        self.assertEqual(CORE.extract_media_items(payload)[0]["year"], "2026")
        self.assertEqual(
            CORE.extract_media_items(payload)[0]["poster"],
            "https://ykimg.alicdn.com/cover.jpg",
        )

    def test_paging_and_integer_clamping(self):
        items = [{"media_id": str(index)} for index in range(25)]
        self.assertEqual(
            [item["media_id"] for item in CORE.page_items(items, 2, 10)],
            [str(index) for index in range(10, 20)],
        )
        self.assertEqual(CORE.clamp_positive_int("0", 10, 100), 1)
        self.assertEqual(CORE.clamp_positive_int("999", 10, 100), 100)
        self.assertEqual(CORE.clamp_positive_int("bad", 10, 100), 10)


def load_plugin_module():
    requests_module = types.ModuleType("requests")

    class RequestException(Exception):
        pass

    requests_module.RequestException = RequestException
    requests_module.get = Mock()

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
        "customyoukuvideodiscover",
        plugin_dir / "__init__.py",
        submodule_search_locations=[str(plugin_dir)],
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module, requests_module, event_module, config_module


class CustomYoukuVideoPluginTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module, cls.requests, cls.events, cls.config = load_plugin_module()

    def setUp(self):
        self.plugin = self.module.CustomYoukuVideoDiscover()
        self.plugin._enabled = True

    def test_plugin_identity_and_discover_source_are_independent(self):
        self.assertEqual(self.plugin.plugin_version, "1.0.0")
        self.assertEqual(
            self.plugin.plugin_config_prefix,
            "customyoukuvideodiscover_",
        )
        self.assertEqual(self.plugin.get_api()[0]["path"], "/youkuvideo_discover")
        event_data = types.SimpleNamespace(extra_sources=[])
        self.plugin.discover_source(self.events.Event(event_data))
        source = event_data.extra_sources[0]
        self.assertEqual(source.mediaid_prefix, "customyoukuvideo")
        self.assertIn("plugin/CustomYoukuVideoDiscover/", source.api_path)
        self.plugin.discover_source(self.events.Event(event_data))
        self.assertEqual(len(event_data.extra_sources), 1)

    def test_endpoint_validates_channel_paginates_and_converts_media(self):
        self.plugin._request = Mock(return_value=[
            {
                "title": f"节目{index}",
                "year": "2026" if index == 1 else None,
                "media_id": f"id-{index}",
                "poster": f"https://m.ykimg.com/{index}.jpg",
            }
            for index in range(4)
        ])
        results = self.plugin.youkuvideo_discover(
            mtype="movie", page="2", count="2"
        )
        self.assertEqual([result.media_id for result in results], ["id-2", "id-3"])
        self.assertTrue(all(result.type == "电影" for result in results))
        self.assertTrue(all(result.mediaid_prefix == "customyoukuvideo" for result in results))
        self.assertEqual(self.plugin.youkuvideo_discover(mtype="invalid"), [])

    def test_disabled_plugin_does_not_register_or_return_media(self):
        self.plugin._enabled = False
        event_data = types.SimpleNamespace(extra_sources=[])
        self.plugin.discover_source(self.events.Event(event_data))
        self.assertEqual(event_data.extra_sources, [])
        self.assertEqual(self.plugin.youkuvideo_discover(), [])

    def test_fetch_channel_sets_timeout_and_parses_response(self):
        response = Mock()
        response.raise_for_status.return_value = None
        response.text = initial_data_html(
            '{"moduleList":[{"components":[{"itemList":[{'
            '"title":"测试剧集","action_value":"show-3",'
            '"img":"https://m.ykimg.com/3.jpg"}]}]}]}'
        )
        self.requests.get.reset_mock()
        self.requests.get.return_value = response
        results = self.plugin._fetch_channel("tv")
        self.assertEqual(results[0]["media_id"], "show-3")
        self.assertEqual(
            self.requests.get.call_args.kwargs["timeout"],
            self.module.REQUEST_TIMEOUT,
        )

    def test_init_registers_youku_image_domains(self):
        self.config.settings.SECURITY_IMAGE_DOMAINS.clear()
        self.plugin.init_plugin({"enabled": True})
        self.assertTrue(self.plugin.get_state())
        self.assertIn(
            "liangcang-material.alicdn.com",
            self.config.settings.SECURITY_IMAGE_DOMAINS,
        )


if __name__ == "__main__":
    unittest.main()
