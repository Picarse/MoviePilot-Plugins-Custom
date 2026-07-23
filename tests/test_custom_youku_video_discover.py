import importlib.util
import json
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

    def test_extract_media_items_uses_all_modules_and_filters_noise(self):
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
                            "tags": [{
                                "uiType": 2,
                                "text": {"title": "剧情 · 喜剧"},
                            }],
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
        self.assertEqual([item["media_id"] for item in items], ["carousel", "show-1"])
        self.assertEqual(items[1]["tags"], ("剧情 · 喜剧",))
        self.assertEqual(items[1]["genres"], ("剧情", "喜剧"))

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

    def test_extract_mtop_items_and_apply_rich_filters(self):
        card = {
            "title": "分页电影",
            "img": "https://m.ykimg.com/feed.jpg",
            "action": {"type": "JUMP_TO_SHOW", "value": "feed-1"},
            "tags": [
                {"uiType": 12, "text": {"title": "VIP"}},
                {"uiType": 2, "text": {"title": "动作 · 冒险"}},
                {"uiType": 1, "text": {"title": "12集全"}},
            ],
        }
        payload = {
            "data": {
                "2019061000": {
                    "success": True,
                    "data": {"nodes": [{
                        "typeName": "KU_FLIX_FEED_BILLBOARD_COMPONENT",
                        "data": {"title": "电影热度榜"},
                        "nodes": [{"data": card}],
                    }]},
                }
            }
        }
        items = CORE.extract_mtop_items(payload, "2019061000")
        self.assertEqual([item["media_id"] for item in items], ["feed-1"])
        self.assertEqual(items[0]["section"], "ranking")
        self.assertEqual(items[0]["module_title"], "电影热度榜")
        self.assertEqual(
            CORE.filter_media_items(
                items,
                genre="冒险",
                access="vip",
                progress="complete",
                section="ranking",
            ),
            items,
        )
        self.assertEqual(CORE.filter_media_items(items, genre="爱情"), [])

    def test_extract_detail_metadata_normalizes_rich_fields(self):
        payload = {"data": {"2019030100": {
            "success": True,
            "data": {"nodes": [{"data": {
                "showId": "show-1",
                "showName": "悬案",
                "showReleaseTime": "2026-07-03 21:30:00",
                "introSubTitle": "中国大陆·2026·悬疑/罪案",
                "desc": "详情简介",
                "lastStage": 14,
            }}]},
        }}}
        detail = CORE.extract_detail_metadata(payload, mtype="tv")
        self.assertEqual(detail["media_id"], "show-1")
        self.assertEqual(detail["year"], "2026")
        self.assertEqual(detail["regions"], ("中国",))
        self.assertEqual(detail["genres"], ("悬疑", "罪案"))
        self.assertEqual(detail["release_date"], "2026-07-03")
        self.assertEqual(detail["description"], "详情简介")
        self.assertEqual(detail["total_episodes"], 14)
        self.assertIsNone(detail["update_date"])
        self.assertEqual(
            CORE.media_overview(detail), "共14集\n详情简介"
        )

        unknown_region = {"data": {"2019030100": {
            "success": True,
            "data": {"introSubTitle": "荷兰·2024·剧情"},
        }}}
        self.assertEqual(
            CORE.extract_detail_metadata(unknown_region)["regions"],
            ("其他",),
        )

    def test_detail_date_and_filter_sort_are_distinguished(self):
        payload = {"data": {"2019030100": {
            "success": True,
            "data": {"data": {
                "introSubTitle": "中国·2026·美食",
                "lastStage": 20260723,
            }},
        }}}
        detail = CORE.extract_detail_metadata(payload, mtype="documentary")
        self.assertEqual(detail["update_date"], "2026-07-23")
        self.assertIsNone(detail["total_episodes"])
        items = [
            {"media_id": "old", "year": "2025", "regions": ("中国",),
             "genres": ("美食",), "release_date": "2025-01-01", "tags": ()},
            {"media_id": "new", "year": "2026", "regions": ("中国",),
             "genres": ("美食",), "release_date": "2026-07-01", "tags": ()},
        ]
        filtered = CORE.filter_media_items(
            items, region="中国", year="2026", sort="release_desc"
        )
        self.assertEqual([item["media_id"] for item in filtered], ["new"])


def load_plugin_module():
    requests_module = types.ModuleType("requests")

    class RequestException(Exception):
        pass

    requests_module.RequestException = RequestException
    requests_module.get = Mock()
    requests_module.Session = Mock()

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
        self.requests.Session.reset_mock()
        self.requests.Session.side_effect = None
        self.plugin = self.module.CustomYoukuVideoDiscover()
        self.plugin._enabled = True
        self.plugin._request_details = Mock(return_value={})

    def test_plugin_identity_and_discover_source_are_independent(self):
        self.assertEqual(self.plugin.plugin_version, "1.3.0")
        package = json.loads((ROOT / "package.v2.json").read_text(encoding="utf-8"))
        self.assertEqual(
            self.plugin.plugin_version,
            package["CustomYoukuVideoDiscover"]["version"],
        )
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
        self.assertEqual(source.filter_params["mtype"], "tv")
        self.assertIn("genre", source.filter_params)
        self.assertIn("region", source.filter_params)
        self.assertIn("year", source.filter_params)
        self.assertIn("sort", source.filter_params)
        self.assertGreater(len(source.filter_ui), 3)
        self.plugin.discover_source(self.events.Event(event_data))
        self.assertEqual(len(event_data.extra_sources), 1)

    def test_endpoint_validates_channel_paginates_and_converts_media(self):
        self.plugin._request_channel = Mock(return_value={
            "items": [
                {
                    "title": f"节目{index}",
                    "year": "2026" if index == 1 else None,
                    "media_id": f"id-{index}",
                    "poster": f"https://m.ykimg.com/{index}.jpg",
                    "tags": (),
                    "genres": (),
                }
                for index in range(4)
            ],
            "session": {"subIndex": 7},
        })
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
        state = self.plugin._fetch_channel("tv")
        self.assertEqual(state["items"][0]["media_id"], "show-3")
        self.assertEqual(
            self.requests.get.call_args.kwargs["timeout"],
            self.module.REQUEST_TIMEOUT,
        )

    def test_endpoint_aggregates_prefetched_mtop_catalog(self):
        self.plugin._request_channel = Mock(return_value={
            "items": [{
                "title": "首屏",
                "year": None,
                "media_id": "base-1",
                "poster": "https://m.ykimg.com/base.jpg",
                "tags": (),
                "genres": (),
            }],
            "session": {"subIndex": 7},
            "more": True,
            "feed_page": 1,
            "page_num_max": 60,
        })
        self.plugin._request_feed_pages = Mock(return_value=[{
            "title": "分页",
            "year": None,
            "media_id": "feed-1",
            "poster": "https://m.ykimg.com/feed.jpg",
            "tags": ("VIP", "动作 · 冒险"),
            "genres": ("动作", "冒险"),
        }])
        results = self.plugin.youkuvideo_discover(
            mtype="movie", page=1, count=1, genre="冒险", access="vip"
        )
        self.assertEqual([result.media_id for result in results], ["feed-1"])
        self.assertEqual(self.plugin._request_feed_pages.call_args.args[1], 2)
        self.assertEqual(
            self.plugin._request_feed_pages.call_args.args[2],
            self.module.DEFAULT_PREFETCH_PAGES,
        )

    def test_deep_filters_use_bounded_detail_enrichment(self):
        self.plugin._detail_limit = 3
        self.plugin._request_catalog = Mock(return_value=[
            {
                "title": f"节目{index}", "year": None,
                "media_id": f"id-{index}",
                "poster": f"https://m.ykimg.com/{index}.jpg",
                "tags": (), "genres": (), "regions": (),
                "release_date": None, "description": None,
            }
            for index in range(5)
        ])
        self.plugin._request_details = Mock(return_value={
            "id-0": {"year": "2025", "regions": ("中国",),
                     "genres": ("剧情",), "release_date": "2025-01-01"},
            "id-1": {"year": "2026", "regions": ("中国",),
                     "genres": ("悬疑",), "release_date": "2026-01-01",
                     "description": "较早"},
            "id-2": {"year": "2026", "regions": ("中国",),
                     "genres": ("悬疑",), "release_date": "2026-07-01",
                     "description": "最新"},
        })
        results = self.plugin.youkuvideo_discover(
            mtype="tv", region="中国", year="2026", genre="悬疑",
            sort="release_desc", page=1, count=10,
        )
        self.assertEqual([result.media_id for result in results], ["id-2", "id-1"])
        self.assertEqual(results[0].overview, "最新")
        requested_ids = json.loads(
            self.plugin._request_details.call_args.args[1]
        )
        self.assertEqual(requested_ids, ["id-0", "id-1", "id-2"])

    def test_regular_detail_enrichment_is_also_bounded(self):
        self.plugin._detail_limit = 2
        items = [
            {"media_id": f"id-{index}", "genres": (), "regions": ()}
            for index in range(5)
        ]
        self.plugin._request_details = Mock(return_value={})

        enriched = self.plugin._enrich_items("tv", items)

        self.assertEqual(len(enriched), 5)
        requested_ids = json.loads(
            self.plugin._request_details.call_args.args[1]
        )
        self.assertEqual(requested_ids, ["id-0", "id-1"])

    def test_detail_request_body_uses_anonymous_web_component(self):
        outer = json.loads(
            self.plugin._detail_data("show-1")["data"]
        )
        params = json.loads(outer["params"])
        self.assertEqual(outer["ms_codes"], "2019030100")
        self.assertEqual(params["showId"], "show-1")
        self.assertEqual(params["biz"], "new_detail_web2")

    def test_fetch_detail_batch_bootstraps_and_signs_anonymous_request(self):
        class CookieJar(list):
            def get_dict(self):
                return {cookie.name: cookie.value for cookie in self}

            def update(self, _cookies):
                return None

        bootstrap_response = Mock()
        bootstrap_response.raise_for_status.return_value = None
        bootstrap_response.json.return_value = {"ret": ["FAIL_SYS_TOKEN_EMPTY"]}
        detail_response = Mock()
        detail_response.raise_for_status.return_value = None
        detail_response.json.return_value = {"data": {"2019030100": {
            "success": True,
            "data": {"showId": "show-1", "showName": "节目",
                     "introSubTitle": "中国·2026·剧情", "lastStage": 12},
        }}}
        bootstrap_client = Mock()
        bootstrap_client.cookies = CookieJar([
            types.SimpleNamespace(name="_m_h5_tk", value="token_expiry"),
            types.SimpleNamespace(name="_m_h5_tk_enc", value="encoded"),
        ])
        bootstrap_client.get.return_value = bootstrap_response
        worker_client = Mock()
        worker_client.cookies = CookieJar()
        worker_client.get.return_value = detail_response
        self.requests.Session.side_effect = [bootstrap_client, worker_client]

        details = self.plugin._fetch_detail_batch("tv", ("show-1",))

        self.assertEqual(details["show-1"]["year"], "2026")
        self.assertEqual(details["show-1"]["total_episodes"], 12)
        self.assertEqual(worker_client.get.call_count, 1)
        signed_params = worker_client.get.call_args.kwargs["params"]
        self.assertEqual(signed_params["api"], self.module.DETAIL_API)
        self.assertTrue(signed_params["sign"])

    def test_fetch_feed_bootstraps_token_and_retries_with_signature(self):
        first = Mock()
        first.raise_for_status.return_value = None
        first.json.return_value = {"ret": ["FAIL_SYS_TOKEN_EMPTY"]}
        second = Mock()
        second.raise_for_status.return_value = None
        second.json.return_value = {
            "data": {
                "2019061000": {
                    "success": True,
                    "data": {"nodes": [{"nodes": [{"data": {
                        "title": "签名分页",
                        "img": "https://m.ykimg.com/signed.jpg",
                        "action": {
                            "type": "JUMP_TO_SHOW",
                            "value": "signed-1",
                        },
                    }}]}]},
                }
            }
        }
        client = Mock()
        client.cookies = [types.SimpleNamespace(name="_m_h5_tk", value="token_expiry")]
        client.get.side_effect = [first, second]
        self.requests.Session.return_value = client
        results = self.plugin._fetch_feed("movie", 2, '{"subIndex":7}')
        self.assertEqual([item["media_id"] for item in results], ["signed-1"])
        self.assertEqual(client.get.call_count, 2)
        first_sign = client.get.call_args_list[0].kwargs["params"]["sign"]
        second_sign = client.get.call_args_list[1].kwargs["params"]["sign"]
        self.assertNotEqual(first_sign, second_sign)

    def test_fetch_feed_pages_carries_forward_server_session(self):
        bootstrap = Mock()
        bootstrap.raise_for_status.return_value = None
        bootstrap.json.return_value = {"ret": ["FAIL_SYS_TOKEN_EMPTY"]}

        def page_response(media_id, next_index, more):
            response = Mock()
            response.raise_for_status.return_value = None
            response.json.return_value = {
                "data": {
                    "2019061000": {
                        "success": True,
                        "data": {
                            "more": more,
                            "data": {"session": {"subIndex": next_index}},
                            "nodes": [{"nodes": [{"data": {
                                "title": media_id,
                                "img": "https://m.ykimg.com/feed.jpg",
                                "action": {
                                    "type": "JUMP_TO_SHOW",
                                    "value": media_id,
                                },
                            }}]}],
                        },
                    }
                }
            }
            return response

        client = Mock()
        client.cookies = [types.SimpleNamespace(name="_m_h5_tk", value="token_expiry")]
        client.get.side_effect = [
            bootstrap,
            page_response("page-2", 8, True),
            page_response("page-3", 9, False),
        ]
        self.requests.Session.return_value = client
        results = self.plugin._fetch_feed_pages(
            "movie", 2, 4, '{"subIndex":7}'
        )
        self.assertEqual(
            [item["media_id"] for item in results], ["page-2", "page-3"]
        )
        third_query = client.get.call_args_list[2].kwargs["params"]
        outer = __import__("json").loads(third_query["data"])
        inner = __import__("json").loads(outer["params"])
        self.assertEqual(__import__("json").loads(inner["session"])["subIndex"], 8)

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
