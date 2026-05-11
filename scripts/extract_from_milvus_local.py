#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
本地运行版：从正式服 Milvus 提取对话数据，保存为 JSONL 文件。

依赖：只需安装 pymilvus
    pip install pymilvus

用法：
    python extract_from_milvus_local.py
    python extract_from_milvus_local.py --cutoff "2026-04-10T00:00:00"

输出：
    当前目录下生成 milvus_export.jsonl，每行一条记录。
"""

import argparse
import json
import time
from datetime import datetime, timezone

# ============= 配置 =============
MILVUS_HOST = "3.146.204.251"
MILVUS_PORT = "19530"
MILVUS_DB   = "girlfriend_db"
COLLECTION  = "vectors"

BATCH_SIZE  = 2000
OUTPUT_FILE = "milvus_export.jsonl"

TARGET_FIELDS = ["user_id", "character_id", "message_id", "text", "timestamp"]


def parse_ts(ts_str: str) -> datetime | None:
    if not ts_str:
        return None
    try:
        ts = float(ts_str)
        if ts > 1e12:
            return datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    except (ValueError, TypeError):
        pass
    try:
        return datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
    except Exception:
        return None


def ts_from_message_id(mid: str) -> datetime | None:
    """从 message_id 末尾提取时间戳（格式：uid_cid_ai_timestamp）"""
    if not mid:
        return None
    parts = mid.rsplit("_", 1)
    if len(parts) == 2:
        return parse_ts(parts[-1])
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--cutoff",
        default=None,
        help="只提取该时间之前的数据（ISO 格式，如 2026-04-10T00:00:00）",
    )
    args = parser.parse_args()

    cutoff = None
    if args.cutoff:
        cutoff = parse_ts(args.cutoff)
        print(f"截止时间: {cutoff.isoformat()}")

    from pymilvus import connections, db, Collection

    print(f"连接 Milvus: {MILVUS_HOST}:{MILVUS_PORT} ...")
    connections.connect(alias="default", host=MILVUS_HOST, port=MILVUS_PORT)
    db.using_database(MILVUS_DB)

    col = Collection(COLLECTION)
    col.load()
    total = col.num_entities
    print(f"Milvus 共 {total} 条记录，开始提取...")

    fetched = 0
    written = 0
    skipped = 0
    t0 = time.time()

    iterator = col.query_iterator(
        batch_size=BATCH_SIZE,
        limit=-1,
        expr="",
        output_fields=TARGET_FIELDS,
    )

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        while True:
            results = iterator.next()
            if not results:
                break

            fetched += len(results)

            for item in results:
                mid = item.get("message_id", "")
                ts  = ts_from_message_id(mid) or parse_ts(item.get("timestamp", ""))

                if cutoff and ts and ts > cutoff:
                    skipped += 1
                    continue

                uid     = item.get("user_id", "").strip()
                cid     = item.get("character_id", "").strip()
                content = (item.get("text") or "").strip()

                if not uid or not cid or not content:
                    skipped += 1
                    continue

                # 判断角色
                m = mid.lower()
                if "_human_" in m or m.endswith("_human"):
                    role = "user"
                elif "_ai_" in m or m.endswith("_ai"):
                    role = "assistant"
                else:
                    skipped += 1
                    continue

                row = {
                    "user_id"   : uid,
                    "expert_id" : cid,
                    "role"      : role,
                    "content"   : content,
                    "timestamp" : ts.isoformat() if ts else None,
                }
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
                written += 1

            elapsed = time.time() - t0
            print(
                f"  已读 {fetched}/{total} | 写入 {written} | 跳过 {skipped} | 耗时 {elapsed:.0f}s",
                end="\r",
            )

    iterator.close()
    connections.disconnect("default")

    print(f"\n完成！写入 {written} 条 → {OUTPUT_FILE}")
    print(f"总耗时: {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
