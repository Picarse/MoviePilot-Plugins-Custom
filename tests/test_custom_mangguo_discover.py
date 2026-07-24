import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock


ROOT = Path(__file__).resolve().parents[1]
CORE_PATH = ROOT / "plugins.v2" / "custommangguodiscover" / "core.py"
SPEC = importlib.util.spec_from_file_location("custom_mangguo_core", CORE_PATH)
CORE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CORE)


class CustomMangGuoCoreTest(unittest.TestCase):
    def test_extract_filter_groups_filters_all_and_malformed_values(self):
        payload = {"data": {"listItems": [{
            "eName": "kind", "typeName": "类型", "items": [
                {"tagId": "a1", "tagName": "全部"},
                {"tagId": "3094", "tagName": "爱情"},
                {"tagId": "3094", "tagName": "重复"},
            ],
        }]}}
        self.assertEqual(CORE.extract_filter_groups(payload), [{
            "key": "kind", "label": "类型",
            "options": [{"value": "3094", "text": "爱情"}],
        }])
        self.assertEqual(CORE.extract_filter_groups(None), [])

    def test_extract_and_normalize_media(self):
        payload = {"data": {"hitDocs": [
            {"clipId": 1, "title": "节目", "img": "http://1img.hitv.com/a.jpg"},
            {"clipId": 1, "title": "重复"},
            {"clipId": 2, "title": ""},
        ]}}
        items = CORE.media_items(CORE.extract_hit_docs(payload), 10)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["clipId"], "1")
        self.assertEqual(items[0]["img"], "https://1img.hitv.com/a.jpg")

    def test_integer_clamping(self):
        self.assertEqual(CORE.clamp_positive_int("0", 80, 100), 1)
        self.assertEqual(CORE.clamp_positive_int("bad", 80, 100), 80)
        self.assertEqual(CORE.clamp_positive_int("999", 80, 100), 100)


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
        API_TOKEN="test-token", SECURITY_IMAGE_DOMAINS=[]
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
    log_module.logger = types.SimpleNamespace(warning=Mock())
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
        "custommangguodiscover",
        plugin_dir / "__init__.py",
        submodule_search_locations=[str(plugin_dir)],
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module, requests_module, event_module


class CustomMangGuoPluginTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module, cls.requests, cls.events = load_plugin_module()

    def setUp(self):
        self.plugin = self.module.CustomMangGuoDiscover()
        self.plugin._enabled = True
        self.plugin._filter_rows = []

    def test_identity_and_discover_source_are_independent(self):
        self.assertEqual(self.plugin.plugin_config_prefix, "custommangguodiscover_")
        event_data = types.SimpleNamespace(extra_sources=[])
        self.plugin.discover_source(self.events.Event(event_data))
        self.plugin.discover_source(self.events.Event(event_data))
        self.assertEqual(len(event_data.extra_sources), 1)
        source = event_data.extra_sources[0]
        self.assertEqual(source.mediaid_prefix, "custommangguo")
        self.assertIn("plugin/CustomMangGuoDiscover/", source.api_path)

    def test_endpoint_validates_and_converts_media(self):
        self.plugin._request = Mock(return_value=[{
            "clipId": "756916", "title": "野狗骨头", "year": "2026",
            "img": "https://3img.hitv.com/poster.jpg",
        }])
        results = self.plugin.mangguo_discover(
            mtype="电影", page="2", count="1", year="2026"
        )
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].type, "电影")
        self.assertEqual(results[0].mediaid_prefix, "custommangguo")
        self.plugin._request.assert_called_once_with(
            2, 1, "电影", year="2026"
        )
        self.assertEqual(self.plugin.mangguo_discover(mtype="无效"), [])

    def test_fetches_use_timeout_and_degrade_safely(self):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"data": {"hitDocs": []}}
        self.requests.get.return_value = response
        self.assertEqual(self.plugin._request(1, 10, "电视剧"), [])
        self.assertEqual(
            self.requests.get.call_args.kwargs["timeout"],
            self.module.REQUEST_TIMEOUT,
        )

    def test_disabled_plugin_returns_no_media(self):
        self.plugin._enabled = False
        self.assertEqual(self.plugin.mangguo_discover(), [])


if __name__ == "__main__":
    unittest.main()
