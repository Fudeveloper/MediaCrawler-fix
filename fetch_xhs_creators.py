# -*- coding: utf-8 -*-
"""Fetch Xiaohongshu creator fans for a prepared user_id list (standalone)."""
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from playwright.async_api import async_playwright

import config
from media_platform.xhs.core import XiaoHongShuCrawler
from media_platform.xhs.login import XiaoHongShuLogin
from store import xhs as xhs_store
from tools import utils
from var import crawler_type_var


async def run(targets_path: Path, sleep_sec: float = 8.0, limit: int | None = None) -> None:
    targets = json.loads(targets_path.read_text(encoding="utf-8"))
    if limit:
        targets = targets[:limit]

    crawler_type_var.set("creator")
    config.CRAWLER_TYPE = "creator"

    crawler = XiaoHongShuCrawler()
    ok, fail = 0, 0

    async with async_playwright() as playwright:
        if config.ENABLE_CDP_MODE:
            crawler.browser_context = await crawler.launch_browser_with_cdp(
                playwright, None, crawler.user_agent, headless=config.CDP_HEADLESS
            )
        else:
            chromium = playwright.chromium
            crawler.browser_context = await crawler.launch_browser(
                chromium, None, crawler.user_agent, headless=config.HEADLESS
            )
            await crawler.browser_context.add_init_script(path="libs/stealth.min.js")

        crawler.context_page = await crawler.browser_context.new_page()
        await crawler.context_page.goto(crawler.index_url)
        crawler.xhs_client = await crawler.create_xhs_client(None)

        if not await crawler.xhs_client.pong():
            login_obj = XiaoHongShuLogin(
                login_type=config.LOGIN_TYPE,
                login_phone="",
                browser_context=crawler.browser_context,
                context_page=crawler.context_page,
                cookie_str=config.COOKIES,
            )
            await login_obj.begin()
            await crawler.xhs_client.update_cookies(
                browser_context=crawler.browser_context,
                urls=crawler.cookie_urls,
            )

        for idx, t in enumerate(targets, 1):
            uid = t.get("user_id")
            token = t.get("xsec_token") or ""
            source = t.get("xsec_source") or "pc_search"
            utils.logger.info(f"[fetch_creators] ({idx}/{len(targets)}) user_id={uid}")
            try:
                info = await crawler.xhs_client.get_creator_info(
                    user_id=uid, xsec_token=token, xsec_source=source
                )
                if not info:
                    utils.logger.warning(f"[fetch_creators] empty info for {uid}")
                    fail += 1
                else:
                    await xhs_store.save_creator(uid, creator=info)
                    # quick fans peek
                    fans = None
                    for i in info.get("interactions") or []:
                        if i.get("type") == "fans":
                            fans = i.get("count")
                    utils.logger.info(f"[fetch_creators] saved {uid} fans={fans}")
                    ok += 1
            except Exception as ex:
                utils.logger.error(f"[fetch_creators] failed {uid}: {ex}")
                fail += 1
            await asyncio.sleep(sleep_sec)

        # cleanup browser if manager exists
        if getattr(crawler, "cdp_manager", None):
            try:
                await crawler.cdp_manager.cleanup()
            except Exception:
                pass

    print(f"DONE ok={ok} fail={fail} total={len(targets)}")


if __name__ == "__main__":
    targets = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("creator_targets.json")
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else None
    sleep_sec = float(sys.argv[3]) if len(sys.argv) > 3 else 8.0
    asyncio.run(run(targets, sleep_sec=sleep_sec, limit=limit))
