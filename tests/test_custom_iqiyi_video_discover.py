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
    def test_app_poster_uses_verified_high_resolution_portrait(self):
        item = app_item(
            image_url_normal=(
                "https://pic0.iqiyipic.com/image/example_m4_320_180.webp"
            ),
            image_cover="http://pic0.iqiyipic.com/image/example_m4.webp",
        )
        poster = CORE.high_resolution_app_poster(item)
        self.assertEqual(
            poster,
            "https://pic0.iqiyipic.com/image/example_m4_579_772.webp",
        )
        normalized = CORE.normalize_app_item(item, "4", "hot", "C位动画")
        self.assertEqual(normalized["poster"], poster)
        self.assertNotIn("320_180", normalized["poster"])
        self.assertEqual(
            CORE.high_resolution_app_poster({
                "image_url_normal": "https://example.com/poster_318_424.webp"
            }),
            "https://example.com/poster_318_424.webp",
        )

    def test_media_overview_does_not_expose_internal_app_section(self):
        item = CORE.normalize_app_item(app_item(), "4", "banner", "焦点图")
        overview = CORE.media_overview(item, "anime")
        self.assertNotIn("App频道：焦点图", overview)
        self.assertNotIn("App频道：", overview)
        self.assertIn("更新至47集", overview)

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

    def test_app_tv_card_metadata_and_screenshot_style_filters(self):
        rows = [CORE.normalize_app_item(app_item(
            channel_id=2,
            tag="内地;悬疑;文学改编;自制",
            cornerMark="exclusive",
            pay_mark="NONE_MARK",
            starring=[{"name": "张凌赫"}],
            theaters=[{"title": "迷雾剧场"}],
            awards=[{"title": "白玉兰奖"}],
            tag3lines=[{"text": "豆瓣高分"}, {"text": "近1月转免"}],
        ), "2", "waterfall", "猜你喜欢")]
        row = rows[0]
        self.assertEqual(row["categories"], ("内地", "悬疑", "文学改编", "自制"))
        self.assertTrue(row["exclusive"])
        self.assertTrue(row["produced"])
        self.assertEqual(row["theaters"], ("迷雾剧场",))
        self.assertEqual(row["awards"], ("白玉兰奖",))
        self.assertEqual(row["actors"], ("张凌赫",))
        self.assertEqual(row["card_labels"], ("豆瓣高分", "近1月转免"))
        filtered = CORE.filter_app_tv_items(
            rows, region="内地", genre="悬疑", access="recent_free",
            hall="honor", specification="exclusive", theater="迷雾剧场",
            award="白玉兰奖", actor="张凌赫", recommendation="douban_high",
        )
        self.assertEqual([item["media_id"] for item in filtered], ["987"])
        self.assertEqual(CORE.filter_app_tv_items(rows, region="美国"), [])

        merged = CORE.merge_app_item(
            rows[0],
            CORE.normalize_app_item(app_item(
                channel_id=2, tag="内地;悬疑",
                tag3lines=[{"text": "最高热度破万"}, {"text": "金鹰奖"}],
            ), "2", "waterfall", "猜你喜欢"),
        )
        self.assertIn("最高热度破万", merged["card_labels"])
        self.assertEqual(
            len(CORE.filter_app_tv_items([merged], recommendation="heat_10000")), 1
        )

        popular = CORE.merge_app_item(
            rows[0],
            CORE.normalize_app_item(
                app_item(channel_id=2), "2", "rank_list_1", "热播榜"
            ),
        )
        self.assertEqual(
            len(CORE.filter_app_tv_items([popular], hall="popular")), 1
        )

    def test_app_tv_year_and_sort_filters(self):
        rows = [
            CORE.normalize_app_item(app_item(
                album_id=1, channel_id=2, display_name="待播剧",
                dq_updatestatus="即将上线", hot_score=20,
                date={"year": 2027, "month": 1, "day": 1},
            ), "2", "online", "网剧热播"),
            CORE.normalize_app_item(app_item(
                album_id=2, channel_id=2, display_name="高分剧",
                sns_score="9.6", hot_score=10,
                date={"year": 2026, "month": 2, "day": 1},
            ), "2", "online", "网剧热播"),
        ]
        self.assertEqual(
            [item["media_id"] for item in CORE.filter_app_tv_items(
                rows, year="upcoming"
            )], ["1"],
        )
        self.assertEqual(
            [item["media_id"] for item in CORE.filter_app_tv_items(
                rows, mode="score"
            )], ["2", "1"],
        )

    def test_clamp_and_app_channel_tables(self):
        self.assertEqual(CORE.clamp_positive_int("0", 10, 48), 1)
        self.assertEqual(CORE.clamp_positive_int("99", 10, 48), 48)
        self.assertEqual(CORE.clamp_positive_int("bad", 10, 48), 10)
        self.assertEqual(
            list(CORE.APP_CHANNEL_PATHS),
            ["tv", "movie", "variety", "anime", "children"],
        )
        self.assertNotIn("documentary", CORE.CHANNEL_PARAMS)


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
        self.assertIsNone(requests_module.get.call_args.kwargs["params"])
        module.CustomIqiyiVideoDiscover._fetch_app_payload("tv", 2)
        self.assertEqual(requests_module.get.call_args.kwargs["params"], {"page": 2})

        plugin = module.CustomIqiyiVideoDiscover()
        plugin._enabled = True
        plugin._request_app_payload = Mock(return_value=payload)
        rows = plugin.iqiyivideo_discover(
            mtype="anime", section="rank_list_1", page=2, count=10
        )
        self.assertEqual([row.media_id for row in rows], [str(index) for index in range(11, 16)])
        self.assertEqual(plugin.iqiyivideo_discover(mtype="documentary"), [])

    def test_app_only_filter_ui_matches_requested_dimensions(self):
        module, _requests_module = load_plugin_module()
        plugin = module.CustomIqiyiVideoDiscover()
        rows = plugin.iqiyivideo_filter_ui()
        labels = [row["content"][0]["content"][0]["text"] for row in rows]
        self.assertNotIn("来源", labels)
        kind_values = [
            chip["props"]["value"] for chip in rows[0]["content"][1]["content"]
        ]
        self.assertEqual(kind_values, ["tv", "movie", "variety", "anime", "children"])
        app_tv_rows = {
            row["content"][0]["content"][0]["text"]: row
            for row in rows
            if row.get("props", {}).get("show") == "{{mtype == 'tv'}}"
        }
        self.assertTrue({
            "类型", "地区", "时间", "资费", "殿堂", "规格",
            "奖项", "剧场", "演员", "推荐", "排序",
        }.issubset(app_tv_rows))
        theater_text = [
            chip["text"] for chip in app_tv_rows["剧场"]["content"][1]["content"]
        ]
        self.assertIn("迷雾剧场", theater_text)
        self.assertIn("小逗剧场", theater_text)
        self.assertNotIn("短剧场", theater_text)
        actor_text = [
            chip["text"] for chip in app_tv_rows["演员"]["content"][1]["content"]
        ]
        self.assertIn("张凌赫", actor_text)
        self.assertIn("杨志刚", actor_text)
        self.assertNotIn("栏目", app_tv_rows)

    def test_manifest_version_matches_plugin(self):
        module, _requests_module = load_plugin_module()
        manifest = json.loads((ROOT / "package.v2.json").read_text())
        self.assertEqual(
            manifest["CustomIqiyiVideoDiscover"]["version"],
            module.CustomIqiyiVideoDiscover.plugin_version,
        )


if __name__ == "__main__":
    unittest.main()
