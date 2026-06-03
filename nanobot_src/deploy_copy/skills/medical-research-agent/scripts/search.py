#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
医学文献搜索工具 - 封装 Infox-Med API
支持关键词列表搜索，自动去重，返回结构化文献信息。

使用方式：
    python3 search.py --keywords "关键词1" "关键词2" --output "/tmp/results.json"
"""
import argparse
import json
import logging
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

URL = "https://api.infox-med.com/search/home/keywords"
HEADERS = {"Content-Type": "application/json", "X-Internal-Key": "infoxmed_internal_ai_data"}

# 默认搜索参数
DEFAULT_PAGE_SIZE = 10  # 每个关键词最多返回的文献数
DEFAULT_NEAR_MONTH = 120  # 搜索近 N 个月的文献（10年，覆盖演变趋势）
DEFAULT_CATEGORY = 3
MAX_SEARCH_WORKERS = 4


def search_api_retry(url: str, data: dict, headers: dict, retries: int = 1, delay: float = 0.1) -> dict:
    """带重试的 API 调用。"""
    for attempt in range(retries + 1):
        try:
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
            request = urllib.request.Request(url, data=body, headers=headers, method="POST")
            with urllib.request.urlopen(request, timeout=30) as response:
                result = json.loads(response.read().decode("utf-8"))
            msg = result.get("msg")
            if msg != "success":
                raise ValueError(f"API 返回非成功状态: msg={msg}")
            return result
        except urllib.error.HTTPError as e:
            if attempt < retries:
                time.sleep(delay)
                continue
            raise RuntimeError(f"HTTP {e.code}: {e.read().decode('utf-8', errors='replace')[:200]}") from e
        except Exception as e:
            if attempt < retries:
                time.sleep(delay)
                continue
            raise e


def _fetch_keyword(keyword: str) -> tuple[str, list[dict]]:
    """单个关键词的搜索，供线程池并行调用。"""
    data_body = {
        "keywords": keyword,
        "category": DEFAULT_CATEGORY,
        "pageNum": 1,
        "pageSize": DEFAULT_PAGE_SIZE,
        "nearMonth": DEFAULT_NEAR_MONTH,
    }

    try:
        query_response = search_api_retry(URL, data_body, HEADERS)
    except Exception as e:
        logger.warning(f"搜索关键词 '{keyword}' 失败: {e}")
        return keyword, []

    records = query_response.get("data", {}).get("records", [])
    if not isinstance(records, list):
        return keyword, []
    return keyword, records


def search(keywords: List[str]) -> List[Dict]:
    """
    搜索医学文献。

    :param keywords: 关键词列表，例如 ["肺癌", "免疫治疗"]。也支持传入空格分隔的字符串。
    :return: 去重后的文献列表，每条包含 id, title, pmid, abstract, url, publish_time, docIf
    """
    logger.info(f"SearchDocumentInfo: {keywords}")
    print(f"SearchDocument: {keywords}")

    # 支持字符串输入（空格分隔）
    if isinstance(keywords, str):
        kw_list = [k.strip() for k in keywords.split() if k.strip()]
    else:
        kw_list = [str(k).strip() for k in keywords if str(k).strip()]

    merged: Dict[str, dict] = {}

    workers = max(1, min(MAX_SEARCH_WORKERS, len(kw_list)))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(_fetch_keyword, keyword) for keyword in kw_list]
        for future in as_completed(futures):
            keyword, records = future.result()
            for hit in records:
                doc_id = hit.get("id", "")
                title = hit.get("docTitle", "")
                abstract = hit.get("docAbstract", "") or hit.get("docAbstractZh", "")
                doc_publish_time = hit.get("docPublishTime", "")
                publish_date = doc_publish_time[:7] if doc_publish_time else ""
                doc_if = hit.get("docIf", "")
                url = f"https://www.infox-med.com/#/articleDetails?id={doc_id}"

                if doc_id not in merged:
                    merged[doc_id] = {
                        "id": doc_id,
                        "title": title.title(),
                        "pmid": hit.get("pmid", ""),
                        "abstract": abstract,
                        "url": url,
                        "publish_time": publish_date,
                        "docIf": doc_if,
                        "_matched_keywords": [keyword],
                    }
                else:
                    # 记录被多个关键词命中的文献
                    existing = merged[doc_id]
                    matched = existing.get("_matched_keywords", [])
                    if keyword not in matched:
                        matched.append(keyword)
                    existing["_matched_keywords"] = matched

    return list(merged.values())


def _impact_factor(doc: dict) -> float:
    try:
        return float(doc.get("docIf") or 0)
    except (TypeError, ValueError):
        return 0.0


def format_summary(results: List[Dict], limit: int = 8) -> str:
    """Return a compact human-readable summary for agent context."""
    sorted_docs = sorted(results, key=_impact_factor, reverse=True)
    lines = [f"搜索摘要：共 {len(results)} 条去重结果，以下为按影响因子排序的前 {limit} 条。"]
    for index, doc in enumerate(sorted_docs[:limit], start=1):
        title = doc.get("title") or "Untitled"
        pmid = doc.get("pmid") or "N/A"
        publish_time = doc.get("publish_time") or "N/A"
        doc_if = doc.get("docIf") or "N/A"
        matched = ", ".join(doc.get("_matched_keywords") or [])
        lines.append(
            f"{index}. IF={doc_if} | {publish_time} | PMID={pmid} | {title} | keywords={matched}"
        )
    return "\n".join(lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Infox-Med 医学文献关键词搜索")
    parser.add_argument("--keywords", nargs="+", required=True,
                        help="搜索关键词列表，例如: --keywords \"肺癌\" \"免疫治疗\"")
    parser.add_argument("--output", type=str, default="",
                        help="输出结果保存的文件路径（可选，默认输出到终端）")
    parser.add_argument("--summary-limit", type=int, default=8,
                        help="保存完整 JSON 时，终端摘要最多展示的文献条数")
    args = parser.parse_args()

    print(f"开始搜索关键词: {args.keywords}")
    results = search(args.keywords)

    output_json = json.dumps(results, ensure_ascii=False, indent=2)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output_json)
        print(f"搜索完成，找到 {len(results)} 条结果，已保存到: {args.output}")
        print(format_summary(results, limit=args.summary_limit))
    else:
        print(f"\n===== 搜索完成，找到 {len(results)} 条结果 =====")
        print(output_json)
