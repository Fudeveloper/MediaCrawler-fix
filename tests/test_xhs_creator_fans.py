# -*- coding: utf-8 -*-
"""Xiaohongshu creator HTML parse and fan-count persistence."""

import json

import pytest

from media_platform.xhs.extractor import XiaoHongShuExtractor


def _page(state: str) -> str:
    return f"<html><script>window.__INITIAL_STATE__={state}</script></html>"


def test_extract_creator_info_neutralizes_js_tokens():
    state = (
        '{"user":{"loggedIn":undefined,"score":NaN,"userPageData":'
        '{"basicInfo":{"nickname":"n"},"interactions":[{"type":"fans","count":20}]}},"bag":new Set([]),'
        '"seen":new Map([])}'
    )
    info = XiaoHongShuExtractor().extract_creator_info_from_html(_page(state))
    assert info["basicInfo"]["nickname"] == "n"
    assert info["interactions"][0]["count"] == 20


def test_extract_creator_info_user_page_data_fallback():
    state = '{"user":{"user_page_data":{"basicInfo":{"nickname":"alt"}}}}'
    info = XiaoHongShuExtractor().extract_creator_info_from_html(_page(state))
    assert info["basicInfo"]["nickname"] == "alt"


def test_extract_creator_info_missing_state_returns_none():
    assert XiaoHongShuExtractor().extract_creator_info_from_html("<html></html>") is None


def test_extract_creator_info_replaces_none_token():
    state = '{"user":{"userPageData":{"basicInfo":{"nickname":None}}}}'
    info = XiaoHongShuExtractor().extract_creator_info_from_html(_page(state))
    assert info["basicInfo"]["nickname"] is None


def test_extract_creator_info_raises_on_leftover_non_json():
    with pytest.raises(json.JSONDecodeError):
        XiaoHongShuExtractor().extract_creator_info_from_html(_page("{not-json}"))


@pytest.mark.asyncio
async def test_save_creator_maps_fans(monkeypatch):
    captured = {}

    class Store:
        async def store_creator(self, item):
            captured["item"] = item

    monkeypatch.setattr("store.xhs.XhsStoreFactory.create_store", lambda: Store())

    from store.xhs import save_creator

    await save_creator(
        "u1",
        {
            "basicInfo": {
                "nickname": "n",
                "gender": 1,
                "images": "a",
                "desc": "d",
                "ipLocation": "上海",
            },
            "interactions": [
                {"type": "follows", "count": 1},
                {"type": "fans", "count": 20},
                {"type": "interaction", "count": 3},
            ],
            "tags": [{"tagType": "info", "name": "tag"}],
        },
    )

    item = captured["item"]
    assert item["user_id"] == "u1"
    assert item["fans"] == 20
    assert item["follows"] == 1
    assert item["interaction"] == 3
    assert item["gender"] == "Female"
    assert json.loads(item["tag_list"]) == {"info": "tag"}


@pytest.mark.asyncio
async def test_save_creator_skips_empty(monkeypatch):
    called = {"n": 0}

    class Store:
        async def store_creator(self, item):
            called["n"] += 1

    monkeypatch.setattr("store.xhs.XhsStoreFactory.create_store", lambda: Store())
    from store.xhs import save_creator

    await save_creator("u1", {})
    assert called["n"] == 0


@pytest.mark.asyncio
async def test_file_stores_write_creators(monkeypatch):
    calls = []

    class Writer:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        async def write_to_csv(self, item_type, item):
            calls.append(("csv", item_type, item))

        async def write_single_item_to_json(self, item_type, item):
            calls.append(("json", item_type, item))

        async def write_to_jsonl(self, item_type, item):
            calls.append(("jsonl", item_type, item))

    monkeypatch.setattr("store.xhs._store_impl.AsyncFileWriter", Writer)
    from store.xhs._store_impl import (
        XhsCsvStoreImplement,
        XhsDbStoreImplement,
        XhsJsonStoreImplement,
        XhsJsonlStoreImplement,
    )

    item = {"user_id": "u1", "fans": 20}
    await XhsCsvStoreImplement().store_creator(item)
    await XhsJsonStoreImplement().store_creator(item)
    await XhsJsonlStoreImplement().store_creator(item)
    await XhsDbStoreImplement().store_creator(item)

    assert [c[0] for c in calls] == ["csv", "json", "jsonl", "jsonl"]
    assert all(c[1] == "creators" and c[2]["fans"] == 20 for c in calls)


@pytest.mark.asyncio
async def test_mongo_store_creator_upserts():
    saved = {}

    class Mongo:
        async def save_or_update(self, collection_suffix, query, data):
            saved["args"] = (collection_suffix, query, data)

    from store.xhs._store_impl import XhsMongoStoreImplement

    store = XhsMongoStoreImplement.__new__(XhsMongoStoreImplement)
    store.mongo_store = Mongo()
    await store.store_creator({"user_id": "u1", "fans": 7})
    assert saved["args"][0] == "creators"
    assert saved["args"][1] == {"user_id": "u1"}
    assert saved["args"][2]["fans"] == 7

    saved.clear()
    await store.store_creator({"fans": 1})
    assert saved == {}


@pytest.mark.asyncio
async def test_save_creator_from_note_dedupes(monkeypatch):
    import config
    from media_platform.xhs.core import XiaoHongShuCrawler

    monkeypatch.setattr(config, "ENABLE_GET_CREATOR_INFO", True)
    monkeypatch.setattr(config, "CRAWLER_MAX_SLEEP_SEC", 0)

    saved = []

    async def fake_save(user_id, creator):
        saved.append(user_id)

    monkeypatch.setattr("media_platform.xhs.core.xhs_store.save_creator", fake_save)

    crawler = XiaoHongShuCrawler.__new__(XiaoHongShuCrawler)
    crawler._saved_creator_ids = set()

    class Client:
        def __init__(self):
            self.calls = 0

        async def get_creator_info(self, user_id, xsec_token, xsec_source):
            self.calls += 1
            return {"basicInfo": {"nickname": user_id}}

    crawler.xhs_client = Client()
    note = {"user": {"user_id": "u1", "xsec_token": "t"}, "xsec_source": "pc_search"}
    await crawler.save_creator_from_note(note)
    await crawler.save_creator_from_note(note)
    assert crawler.xhs_client.calls == 1
    assert saved == ["u1"]


@pytest.mark.asyncio
async def test_save_creator_from_note_respects_flag(monkeypatch):
    import config
    from media_platform.xhs.core import XiaoHongShuCrawler

    monkeypatch.setattr(config, "ENABLE_GET_CREATOR_INFO", False)
    crawler = XiaoHongShuCrawler.__new__(XiaoHongShuCrawler)
    crawler._saved_creator_ids = set()
    crawler.xhs_client = None
    await crawler.save_creator_from_note({"user": {"user_id": "u1"}})
