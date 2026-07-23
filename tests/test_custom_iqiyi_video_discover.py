import importlib.util
import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
CORE_PATH = ROOT / "plugins.v2" / "customiqiyivideodiscover" / "core.py"
SPEC = importlib.util.spec_from_file_location("custom_iqiyi_video_core", CORE_PATH)
CORE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CORE)


def item(**values):
    result = {
        "albumId": 123,
        "name": "示例节目",
        "channelId": 2,
        "imageUrl": "http://pic1.iqiyipic.com/cover.jpg",
        "period": "2026-07-23",
        "videoCount": 24,
        "latestOrder": 12,
        "categories": ["悬疑", "内地"],
        "score": 8.6,
    }
    result.update(values)
    return result


def app_item(**values):
    result = {
        "album_id": 987,
        "channel_id": 4,
        "title": "示例动画单集标题",
        "display_name": "示例动画",
        "image_url_normal": "https://pic0.iqiyipic.com/example_318_424.webp",
        "page_url": "https://www.iqiyi.com/v_example.html",
        "description": "App频道简介",
        "desc": "每周四更新",
        "date": {"year": 2026, "month": 7, "day": 23},
        "dq_updatestatus": "更新至47集",
        "pay_mark": "PAY_MARK_FUN_VIP_MARK",
        "sns_score": "8.5",
        "hot_score": 3159,
        "isAd": False,
    }
    result.update(values)
    return result


class CustomIqiyiVideoCoreTest(unittest.TestCase):
    def test_extract_items_validates_status_channel_and_deduplicates(self):
        payload = {"code": "A00000", "data": {"list": [
            item(), item(name="重复标题"), item(albumId=456, channelId=1),
        ]}}
        rows = CORE.extract_items(payload, "tv")
        self.assertEqual([row["media_id"] for row in rows], ["123"])
        self.assertEqual(
            rows[0]["poster"],
            "https://pic1.iqiyipic.com/cover_579_772.jpg",
        )
        self.assertEqual(rows[0]["year"], "2026")
        self.assertEqual(rows[0]["release_date"], "2026-07-23")
        self.assertEqual(rows[0]["categories"], ("悬疑", "内地"))
        self.assertEqual(rows[0]["score"], 8.6)
        self.assertEqual(CORE.extract_items({"code": "A00003"}, "tv"), [])
        self.assertEqual(
            CORE.high_resolution_poster(
                "https://pic1.iqiyipic.com/cover_260_360.jpg",
                ["260_360", "579_772"],
            ),
            "https://pic1.iqiyipic.com/cover_579_772.jpg",
        )

    def test_detail_parses_dict_categories_areas_and_actors(self):
        payload = {"code": "A00000", "data": item(
            description="详情简介",
            categories=[{"name": "罪案"}, {"name": "悬疑"}],
            areas=[{"name": "中国大陆"}],
            people={"main_charactor": [{"name": "演员甲"}, {"name": "演员乙"}]},
        )}
        detail = CORE.extract_detail(payload, "tv")
        self.assertEqual(detail["categories"], ("罪案", "悬疑"))
        self.assertEqual(detail["areas"], ("中国大陆",))
        self.assertEqual(detail["actors"], ("演员甲", "演员乙"))
        self.assertEqual(detail["description"], "详情简介")

    def test_category_intersection_and_overview_semantics(self):
        self.assertEqual(CORE.category_value("15", "32"), "15,32")
        self.assertEqual(CORE.category_value("15", "15"), "15")
        self.assertIsNone(CORE.category_value(None, None))
        row = CORE.normalize_item(item(description="剧情简介"), "2")
        self.assertEqual(
            CORE.media_overview(row, "tv"),
            "更新至12/共24集\n分类：悬疑 · 内地\n剧情简介",
        )
        documentary = CORE.normalize_item(item(channelId=3), "3")
        self.assertTrue(CORE.media_overview(documentary, "documentary").startswith(
            "更新日期：2026-07-23"
        ))
        anime = CORE.normalize_item(
            item(channelId=4, videoCount=0, latestOrder=1170), "4"
        )
        self.assertTrue(CORE.media_overview(anime, "anime").startswith("更新至1170集"))

    def test_merge_detail_keeps_catalog_fields_when_detail_is_empty(self):
        catalog = CORE.normalize_item(item(description="目录简介"), "2")
        merged = CORE.merge_detail(catalog, {"description": None, "areas": ()})
        self.assertEqual(merged["description"], "目录简介")
        self.assertEqual(merged["poster"], catalog["poster"])

    def test_extract_app_channel_sections_and_movie_ids(self):
        payload = {"code": 0, "items": [{"video": [
            {"title": "C位动画", "block_id": "hot", "data": [
                app_item(), app_item(title="重复单集标题"),
                app_item(album_id=654, channel_id=2),
            ]},
            {"title": "周四", "block_id": "jmd_Thur", "data": [
                app_item(album_id=321, display_name="周四动画", dq_updatestatus="12集全")
            ]},
            {"title": "热播榜", "block_id": "rank_list_1", "data": [
                app_item(album_id=456, display_name="榜单动画")
            ]},
        ]}]}
        rows = CORE.extract_app_items(payload, "anime", "all")
        self.assertEqual([row["media_id"] for row in rows], ["987", "321", "456"])
        self.assertEqual(rows[0]["title"], "示例动画")
        self.assertEqual(rows[0]["latest_episode"], 47)
        self.assertEqual(rows[0]["pay_mark"], 1)
        self.assertEqual(rows[0]["score"], 8.5)
        self.assertEqual(rows[0]["app_section"], "C位动画")
        schedule = CORE.extract_app_items(payload, "anime", "schedule")
        self.assertEqual([row["media_id"] for row in schedule], ["321"])
        self.assertEqual(schedule[0]["total_episodes"], 12)

        movie = CORE.normalize_app_item(
            app_item(album_id=None, film_id=777, channel_id=1, display_name="示例电影"),
            "1", "rank_list_1", "热播榜",
        )
        self.assertEqual(movie["media_id"], "777")
        self.assertEqual(movie["release_date"], "2026-07-23")
        self.assertEqual(CORE.extract_app_items({"code": 1}, "anime"), [])

    def test_clamp_and_verified_filter_tables(self):
        self.assertEqual(CORE.clamp_positive_int("0", 10, 48), 1)
        self.assertEqual(CORE.clamp_positive_int("99", 10, 48), 48)
        self.assertEqual(CORE.clamp_positive_int("bad", 10, 48), 10)
        self.assertIn(("32", "悬疑"), CORE.GENRE_OPTIONS["tv"])
        self.assertIn(("20323", "国内"), CORE.REGION_OPTIONS["documentary"])
        self.assertIn(
            ("27815", "院线"),
            CORE.EXTRA_FILTER_OPTIONS["movie"]["specification"][1],
        )
        self.assertIn(
            ("28468", "BBC"),
            CORE.EXTRA_FILTER_OPTIONS["documentary"]["producer"][1],
        )
        self.assertEqual(CORE.GENRE_OPTIONS["children"], ())
        self.assertEqual(CORE.REGION_OPTIONS["children"], ())


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
        SECURITY_IMAGE_DOMAINS=[], API_TOKEN="token"
    )
    event_module = types.ModuleType("app.core.event")
    event_module.Event = type("Event", (), {})
    event_module.eventmanager = types.SimpleNamespace(
        register=lambda _event: (lambda function: function)
    )
    log_module = types.ModuleType("app.log")
    log_module.logger = types.SimpleNamespace(warning=Mock())
    plugins_module = types.ModuleType("app.plugins")
    plugins_module._PluginBase = object
    types_module = types.ModuleType("app.schemas.types")
    types_module.ChainEventType = types.SimpleNamespace(DiscoverSource="discover")

    stubs = {
        "requests": requests_module,
        "app": app_module,
        "app.schemas": schemas_module,
        "app.core.cache": cache_module,
        "app.core.config": config_module,
        "app.core.event": event_module,
        "app.log": log_module,
        "app.plugins": plugins_module,
        "app.schemas.types": types_module,
    }
    module_name = "custom_iqiyi_video_plugin"
    spec = importlib.util.spec_from_file_location(
        module_name,
        ROOT / "plugins.v2" / "customiqiyivideodiscover" / "__init__.py",
        submodule_search_locations=[str(CORE_PATH.parent)],
    )
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, stubs):
        sys.modules[module_name] = module
        sys.modules[f"{module_name}.core"] = CORE
        spec.loader.exec_module(module)
    return module, requests_module


class CustomIqiyiVideoPluginTest(unittest.TestCase):
    def test_request_uses_only_verified_server_parameters(self):
        module, requests_module = load_plugin_module()
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"code": "A00000", "data": {"list": [item()]}}
        requests_module.get.return_value = response
        rows = module.CustomIqiyiVideoDiscover._fetch_page(
            "tv", 2, 20, "4", "2026", "0", "15", "32"
        )
        self.assertEqual(len(rows), 1)
        params = requests_module.get.call_args.kwargs["params"]
        self.assertEqual(params["mode"], "4")
        self.assertEqual(params["market_release_date_level"], "2026")
        self.assertEqual(params["is_purchase"], "0")
        self.assertEqual(params["three_category_id"], "15,32")
        self.assertNotIn("order", params)
        self.assertNotIn("area", params)
        self.assertNotIn("genre", params)

        response.json.return_value = {
            "code": "A00000", "data": {"list": [item(channelId=1)]}
        }
        module.CustomIqiyiVideoDiscover._fetch_page(
            "movie", 1, 10, "11", None, None, "1", "8", "27815"
        )
        self.assertEqual(
            requests_module.get.call_args.kwargs["params"]["three_category_id"],
            "1,8,27815",
        )

        response.json.return_value = {"code": "A00003", "data": {}}
        self.assertIsNone(module.CustomIqiyiVideoDiscover._fetch_page(
            "tv", 1, 10, None, None, None, None, None
        ))

    def test_details_are_bounded_and_failure_preserves_catalog(self):
        module, _requests_module = load_plugin_module()
        plugin = module.CustomIqiyiVideoDiscover()
        plugin._detail_limit = 2
        rows = [CORE.normalize_item(item(albumId=index), "2") for index in range(1, 5)]
        plugin._request_detail = Mock(side_effect=[
            {"media_id": "1", "description": "详情一"}, None
        ])
        enriched = plugin._enrich_items("tv", rows)
        self.assertEqual(plugin._request_detail.call_count, 2)
        self.assertEqual(len(enriched), 4)
        self.assertEqual(enriched[0]["description"], "详情一")
        self.assertEqual(enriched[1]["title"], "示例节目")
        self.assertEqual(enriched[2]["media_id"], "3")

    def test_app_channel_request_and_local_pagination(self):
        module, requests_module = load_plugin_module()
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"code": 0, "items": [{"video": [{
            "title": "热播榜", "block_id": "rank_list_1",
            "data": [app_item(album_id=index) for index in range(1, 16)],
        }]}]}
        requests_module.get.return_value = response
        payload = module.CustomIqiyiVideoDiscover._fetch_app_payload("anime")
        self.assertEqual(payload["code"], 0)
        self.assertEqual(
            requests_module.get.call_args.args[0],
            "https://mesh.if.iqiyi.com/portal/lw/v7/channel/cartoon",
        )

        plugin = module.CustomIqiyiVideoDiscover()
        plugin._enabled = True
        plugin._request_app_payload = Mock(return_value=payload)
        plugin._request_detail = Mock()
        rows = plugin.iqiyivideo_discover(
            mtype="anime", catalog="app", section="rank_list_1", page=2, count=10
        )
        self.assertEqual([row.media_id for row in rows], [str(index) for index in range(11, 16)])
        plugin._request_detail.assert_not_called()

    def test_manifest_version_matches_plugin(self):
        module, _requests_module = load_plugin_module()
        manifest = json.loads((ROOT / "package.v2.json").read_text())
        self.assertEqual(
            manifest["CustomIqiyiVideoDiscover"]["version"],
            module.CustomIqiyiVideoDiscover.plugin_version,
        )


if __name__ == "__main__":
    unittest.main()
