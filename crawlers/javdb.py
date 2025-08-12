# javdb.py
import asyncio
import random
import re
import time
from typing import Dict, Any, Tuple

import httpx
from lxml import etree
from astrbot.api import logger


# --- 从原始文件中复制过来的所有 get_* 辅助函数 ---
# 这些函数的核心逻辑不需要改变，所以我们直接复用

def get_number(html, number):
    result = html.xpath('//a[@class="button is-white copy-to-clipboard"]/@data-clipboard-text')
    return result[0] if result else number


def get_title(html, org_language) -> Tuple[str, str]:
    title = html.xpath('string(//h2[@class="title is-4"]/strong[@class="current-title"])')
    originaltitle = html.xpath('string(//h2[@class="title is-4"]/span[@class="origin-title"])')
    if originaltitle:
        if org_language == "jp":
            title = originaltitle
    else:
        originaltitle = title

    # 清理标题中的多余部分
    number_val = get_number(html, "")
    title = title.replace(number_val, "").replace("中文字幕", "").replace("無碼", "").strip()
    originaltitle = originaltitle.replace(number_val, "").replace("中文字幕", "").replace("無碼", "").strip()

    return title, originaltitle


def get_actor(html) -> Tuple[str, str]:
    actor_result = html.xpath(
        '//div[@class="panel-block"]/strong[contains(text(), "演員:") or contains(text(), "Actor(s):")]/../span[@class="value"]/a/text()'
    )
    gender_result = html.xpath(
        '//div[@class="panel-block"]/strong[contains(text(), "演員:") or contains(text(), "Actor(s):")]/../span[@class="value"]/strong/@class'
    )
    actor_list = [actor for i, actor in enumerate(actor_result) if
                  i < len(gender_result) and gender_result[i] == "symbol female"]
    return ",".join(actor_list), ",".join(actor_result)


def get_studio(html):
    result = html.xpath('//strong[contains(text(),"片商:") or contains(text(),"Maker:")]/../span/a/text()')
    return result[0] if result else ""


def get_runtime(html):
    result = html.xpath('//strong[contains(text(),"時長") or contains(text(),"Duration:")]/../span/text()')
    return (result[0] if result else "").replace(" 分鍾", "").replace(" minute(s)", "")


def get_series(html):
    result = html.xpath('//strong[contains(text(),"系列:") or contains(text(),"Series:")]/../span/a/text()')
    return result[0] if result else ""


def get_release(html):
    result = html.xpath('//strong[contains(text(),"日期:") or contains(text(),"Released Date:")]/../span/text()')
    return result[0] if result else ""


def get_year(release_date):
    match = re.search(r"\d{4}", release_date)
    return match.group() if match else release_date


def get_tag(html):
    tags = html.xpath('//strong[contains(text(),"類別:") or contains(text(),"Tags:")]/../span/a/text()')
    return ", ".join(tags)

def get_score(html):
    result = str(html.xpath("//span[@class='score-stars']/../text()")).strip(" ['']")
    try:
        score = re.findall(r"(\d{1}\..+)分", result)
        score = score[0] if score else ""
    except Exception:
        score = ""
    return score

def get_cover(html):
    try:
        result = str(html.xpath("//img[@class='video-cover']/@src")[0]).strip(" ['']")
    except Exception:
        result = ""
    return result


def get_extrafanart(html):  # 获取封面链接
    extrafanart_list = html.xpath("//div[@class='tile-images preview-images']/a[@class='tile-item']/@href")
    return extrafanart_list

def get_real_url(html, number):
    res_list = html.xpath("//a[@class='box']")
    for each in res_list:
        href = each.xpath("@href")
        title = each.xpath("div[@class='video-title']/strong/text()")
        if href and title and number.upper() in title[0].upper():
            return href[0]
    # 如果精确匹配失败，尝试模糊匹配
    for each in res_list:
        href = each.xpath("@href")
        title = each.xpath("div[@class='video-title']/strong/text()")
        meta = each.xpath("div[@class='meta']/text()")
        full_text = (title[0] if title else "") + (meta[0] if meta else "")
        if href and number.upper().replace("-", "") in full_text.upper().replace("-", ""):
            return href[0]
    return None


# --- 主要改造的函数 ---
async def fetch_movie_data(
        number: str,
        client: httpx.AsyncClient,
        # cookie: str,
        base_url: str = "https://javdb.com",
) -> Dict[str, Any]:
    """
    一个独立的异步函数，用于从JavDB获取电影数据。

    :param number: 电影番号
    :param client: httpx.AsyncClient 实例
    :param cookie: 用于请求的 Cookie 字符串
    :param base_url: JavDB 的基础 URL
    :return: 包含电影信息的字典，或包含错误信息的字典
    """
    start_time = time.time()
    logger.info(f"开始查询 JavDB，番号: {number}")
    headers = {
        # "Cookie": cookie,
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"
    }

    try:
        # 1. 搜索页面获取详情页链接
        search_url = f"{base_url}/search?q={number.strip()}&f=all"
        logger.debug(f"访问搜索地址: {search_url}")

        response = await client.get(search_url, headers=headers, timeout=30.0)
        response.raise_for_status()

        html_search = response.text
        if "ray-id" in html_search or "Cloudflare" in html_search:
            raise Exception("被 Cloudflare 拦截，请检查Cookie或更换网络环境。")
        if "Due to copyright restrictions" in html_search:
            raise Exception("IP地区受版权限制，请使用非日本代理。")

        html = etree.fromstring(html_search, etree.HTMLParser())
        detail_path = get_real_url(html, number)
        if not detail_path:
            raise Exception("未在搜索结果中匹配到该番号。")

        detail_url = f"{base_url}{detail_path}?locale=zh"
        logger.debug(f"访问详情页: {detail_url}")

        # 2. 访问详情页获取数据
        response = await client.get(detail_url, headers=headers, timeout=30.0)
        response.raise_for_status()

        html_info = response.text
        if "/password_resets" in html_info or "此內容需要登入才能查看" in html_info:
            raise Exception("Cookie已失效或需要登录权限，请更新Cookie。")

        html_detail = etree.fromstring(html_info, etree.HTMLParser())

        # 3. 解析数据
        title, _ = get_title(html_detail, "zh")
        if not title:
            raise Exception("解析失败：未获取到标题。")

        release_date = get_release(html_detail)

        result_dic = {
            "number": get_number(html_detail, number),
            "title": title,
            "actor": get_actor(html_detail)[0],
            "release": release_date,
            "year": get_year(release_date),
            "runtime": get_runtime(html_detail),
            "studio": get_studio(html_detail),
            "series": get_series(html_detail),
            "tags": get_tag(html_detail),
            "thumb": get_cover(html_detail),
            "extrafanart": get_extrafanart(html_detail),
            "website": detail_url,
            "score": get_score(html_detail),
        }

        logger.info(f"数据获取成功！耗时 {time.time() - start_time:.2f}s")
        return result_dic

    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP请求错误: {e.response.status_code} - {e}")
        return {"error": f"请求失败，网站返回状态码: {e.response.status_code}"}
    except Exception as e:
        logger.error(f"处理番号 {number} 时发生错误: {e}")
        return {"error": str(e)}
