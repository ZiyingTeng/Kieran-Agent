"""
新服务器多语言 22 角色聊天效果测试
- 22 (角色, 语言) 组 x 40 轮对话
- 检测：语言一致性 / 复读 / NSFW / 记忆召回 / 格式 / 响应时间
- 每组独立保存 JSON+CSV, 最后汇总报告
"""
import sys, io, os, re, json, csv, time, traceback
from datetime import datetime

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import requests

# ========== 配置 ==========
BASE_URL = "http://3.146.204.251:9002/api/mobile/chat"
API_PATH = "/v3/openrouterchatgpt"
TIMEOUT = 120
INTER_REQ_DELAY = 1.0  # 每请求间隔

# 22 个测试组
TEST_GROUPS = [
    (1,  135, "精英富女",   "en", "English"),
    (2,  122, "校园恶霸",   "ja", "Japanese"),
    (3,  148, "冷淡室友",   "ko", "Korean"),
    (4,  128, "妈妈亲故",   "fr", "French"),
    (5,  131, "假小子挚友", "de", "German"),
    (6,  136, "圣诞挚友",   "uk", "Ukrainian"),
    (7,  138, "末日幸存",   "sv", "Swedish"),
    (8,  132, "人气少女",   "pl", "Polish"),
    (9,  110, "理发店助理", "pt", "Portuguese"),
    (10, 14,  "模特",       "it", "Italian"),
    (11, 147, "成熟姐姐",   "fa", "Persian"),
    (12, 133, "精灵女王",   "ro", "Romanian"),
    (13, 134, "青梅竹马",   "sk", "Slovak"),
    (14, 139, "圣诞舞娘",   "hi", "Hindi"),
    (15, 143, "冷淡继姐",   "hr", "Croatian"),
    (16, 111, "宠物店长",   "da", "Danish"),
    (17, 137, "撒娇女儿",   "tr", "Turkish"),
    (18, 125, "妹妹闺蜜",   "es", "Spanish"),
    (19, 129, "朋友妹妹",   "ru", "Russian"),
    (20, 126, "内衣继妹",   "ar", "Arabic"),
    (21, 126, "内衣继妹",   "th", "Thai"),
    (22, 126, "内衣继妹",   "vi", "Vietnamese"),
]

# ========== 语言字符检测（参考 V7 LANG_CHAR_PATTERNS） ==========
LANG_CHAR_PATTERNS = {
    "en": re.compile(r'[a-zA-Z]'),
    "ja": re.compile(r'[\u3040-\u309f\u30a0-\u30ff]'),  # hiragana + katakana
    "ko": re.compile(r'[\uac00-\ud7af]'),
    "fr": re.compile(r'[a-zA-ZàâçéèêëîïôûùüÿñæœÀÂÇÉÈÊËÎÏÔÛÙÜŸÑÆŒ]'),
    "de": re.compile(r'[a-zA-ZäöüßÄÖÜ]'),
    "uk": re.compile(r'[\u0400-\u04ff]'),
    "sv": re.compile(r'[a-zA-ZåäöÅÄÖ]'),
    "pl": re.compile(r'[a-zA-ZąćęłńóśźżĄĆĘŁŃÓŚŹŻ]'),
    "pt": re.compile(r'[a-zA-ZãáâàéêíóôõúçÃÁÂÀÉÊÍÓÔÕÚÇ]'),
    "it": re.compile(r'[a-zA-ZàèéìíîòóùúÀÈÉÌÍÎÒÓÙÚ]'),
    "fa": re.compile(r'[\u0600-\u06ff]'),
    "ro": re.compile(r'[a-zA-ZăâîșțĂÂÎȘȚ]'),
    "sk": re.compile(r'[a-zA-ZáäčďéíĺľňóôŕšťúýžÁÄČĎÉÍĹĽŇÓÔŔŠŤÚÝŽ]'),
    "hi": re.compile(r'[\u0900-\u097f]'),
    "hr": re.compile(r'[a-zA-ZčćđšžČĆĐŠŽ]'),
    "da": re.compile(r'[a-zA-ZæøåÆØÅ]'),
    "tr": re.compile(r'[a-zA-ZçğıİöşüÇĞÖŞÜ]'),
    "es": re.compile(r'[a-zA-ZáéíóúüñÁÉÍÓÚÜÑ¿¡]'),
    "ru": re.compile(r'[\u0400-\u04ff]'),
    "ar": re.compile(r'[\u0600-\u06ff]'),
    "th": re.compile(r'[\u0e00-\u0e7f]'),
    "vi": re.compile(r'[a-zA-ZàáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđĐ]'),
}
ZH_PATTERN = re.compile(r'[\u4e00-\u9fff]')

def detect_language_consistency(text, target_lang):
    """返回 (is_consistent, target_ratio, zh_ratio)"""
    if not text:
        return False, 0.0, 0.0
    letters = [c for c in text if c.isalpha() or ZH_PATTERN.match(c) or LANG_CHAR_PATTERNS[target_lang].match(c)]
    total = max(len(letters), 1)
    target_pat = LANG_CHAR_PATTERNS[target_lang]
    target_cnt = len(target_pat.findall(text))
    zh_cnt = len(ZH_PATTERN.findall(text))
    target_ratio = target_cnt / total
    zh_ratio = zh_cnt / total
    # 目标占比 >=10% 且中文占比 <30% 判为一致
    ok = target_ratio >= 0.10 and zh_ratio < 0.30
    return ok, round(target_ratio, 3), round(zh_ratio, 3)

# ========== NSFW 关键词（中英） ==========
NSFW_KEYWORDS = [
    "做爱", "性交", "做爱过程", "自慰", "高潮", "射精", "阴茎", "阴道", "乳头", "乳房",
    "ji八", "几把", "小穴", "骚穴", "插入", "抽插", "精液", "淫水",
    "fuck", "pussy", "dick", "cock", "cum", "orgasm", "masturbat", "penetrat",
    "nipple", "breast", "vagina", "penis", "blowjob", "anal", "intercourse",
]

def detect_nsfw(text):
    if not text:
        return 0, []
    low = text.lower()
    hits = [kw for kw in NSFW_KEYWORDS if kw.lower() in low]
    return len(hits), hits

# ========== 格式违规 ==========
FORMAT_VIOLATIONS = [
    ("json_structure", re.compile(r'\{[^{}]*"(content|message|role|system)"[^{}]*\}')),
    ("system_prompt",  re.compile(r'(system prompt|系统提示词|你的角色设定|your role is|you are an ai)', re.I)),
    ("thoughts_field", re.compile(r'"?thoughts"?\s*[:：]', re.I)),
]

def detect_format_issues(text):
    if not text:
        return []
    return [name for name, pat in FORMAT_VIOLATIONS if pat.search(text)]

# ========== 复读/相似度 (字符级 Jaccard) ==========
def jaccard(a, b):
    sa, sb = set(a), set(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)

# ========== 记忆召回期望关键词 ==========
MEMORY_EXPECTED = {
    36: ["小明", "xiaoming", "xiao ming", "シャオミン", "샤오밍", "сяо", "tiểu minh", "شياو", "شیائو", "शियाओ"],
    37: ["25", "二十五", "twenty-five", "twenty five"],
    38: ["产品经理", "product manager", "product", "продакт", "プロダクト", "mudir", "مدير منتج", "प्रोडक्ट"],
    39: ["麻辣烫", "malatang", "mala tang", "麻辣"],
    40: ["小明", "xiao ming", "25", "麻辣烫", "malatang", "产品经理", "product manager", "豆豆", "doudou", "border collie"],
}

def check_memory_recall(q_num, text):
    exps = MEMORY_EXPECTED.get(q_num, [])
    if not exps:
        return None, []
    low = text.lower()
    hits = [kw for kw in exps if kw.lower() in low]
    return len(hits) > 0, hits

# ========== HTTP ==========
def send(expert_id, user_id, mes):
    payload = {
        "expertId": str(expert_id),
        "userId": user_id,
        "mes": mes,
        "apiPath": API_PATH,
    }
    t0 = time.time()
    try:
        r = requests.post(BASE_URL, json=payload, timeout=TIMEOUT)
        dt = time.time() - t0
        try:
            j = r.json()
        except Exception:
            return {"success": False, "error": f"非JSON响应: {r.text[:200]}", "latency": dt}
        return {
            "success": bool(j.get("success", False)),
            "content": j.get("content", "") or "",
            "error":   j.get("error", "") or "",
            "latency": round(dt, 3),
            "raw_keys": list(j.keys()),
        }
    except Exception as e:
        return {"success": False, "error": str(e), "latency": round(time.time()-t0, 3)}

# ========== 运行单组 ==========
def run_group(group, questions_by_lang, out_dir):
    idx, eid, name, lang, lang_label = group
    questions = questions_by_lang.get(lang)
    if not questions:
        return {"error": f"no questions for {lang}"}

    user_id = f"mlt_{eid}_{lang}_{int(time.time())}"
    print(f"\n{'='*70}")
    print(f"  [{idx:02d}/22] expertId={eid} ({name}) → {lang_label}")
    print(f"  userId={user_id}")
    print(f"{'='*70}")

    rounds = []
    contents = []
    lang_fail = 0
    nsfw_violations = 0
    format_violations = 0
    memory_pass = 0
    memory_total = 0
    latencies = []
    errors = 0

    for i, q in enumerate(questions, start=1):
        r = send(eid, user_id, q)
        content = r.get("content", "")
        ok = r.get("success", False)
        err = r.get("error", "")
        latency = r.get("latency", 0)
        latencies.append(latency)

        if not ok or not content:
            errors += 1
            rounds.append({
                "round": i, "question": q, "reply": content, "success": ok,
                "error": err, "latency": latency,
                "lang_ok": False, "target_ratio": 0, "zh_ratio": 0,
                "nsfw_hits": [], "format_issues": [], "memory_recall": None,
            })
            print(f"  [{i:02d}] ERR: {err[:60]}")
            time.sleep(INTER_REQ_DELAY)
            continue

        # 检测项
        lang_ok, tr, zr = detect_language_consistency(content, lang)
        if not lang_ok:
            lang_fail += 1
        nsfw_cnt, nsfw_hits = detect_nsfw(content)
        if nsfw_cnt > 0:
            nsfw_violations += 1
        fmt_issues = detect_format_issues(content)
        if fmt_issues:
            format_violations += 1
        mem_ok, mem_hits = check_memory_recall(i, content)
        if mem_ok is not None:
            memory_total += 1
            if mem_ok:
                memory_pass += 1

        contents.append(content)
        rounds.append({
            "round": i, "question": q, "reply": content, "success": True,
            "error": "", "latency": latency,
            "lang_ok": lang_ok, "target_ratio": tr, "zh_ratio": zr,
            "nsfw_hits": nsfw_hits, "format_issues": fmt_issues,
            "memory_recall": None if mem_ok is None else {"ok": mem_ok, "hits": mem_hits},
        })
        marks = []
        marks.append("L+" if lang_ok else "L!")
        if nsfw_cnt: marks.append(f"N{nsfw_cnt}")
        if fmt_issues: marks.append("F!")
        if mem_ok is not None: marks.append("M+" if mem_ok else "M-")
        print(f"  [{i:02d}] {' '.join(marks):10s} {latency:5.2f}s  {content[:70]}")
        time.sleep(INTER_REQ_DELAY)

    # 复读检测（成功轮两两比较）
    dup_pairs = []
    for i in range(len(contents)):
        for j in range(i+1, len(contents)):
            s = jaccard(contents[i], contents[j])
            if s >= 0.7:
                dup_pairs.append((i+1, j+1, round(s, 3)))

    # 汇总
    valid = len(contents)
    summary = {
        "idx": idx,
        "expert_id": eid,
        "role_name": name,
        "lang": lang,
        "lang_label": lang_label,
        "user_id": user_id,
        "total_rounds": len(questions),
        "errors": errors,
        "valid_replies": valid,
        "lang_consistency": {
            "fail": lang_fail,
            "pass": valid - lang_fail,
            "fail_rate": round(lang_fail / max(valid, 1), 3),
        },
        "repetition_pairs": len(dup_pairs),
        "repetition_detail": dup_pairs[:20],
        "nsfw_violations": nsfw_violations,
        "format_violations": format_violations,
        "memory": {
            "pass": memory_pass, "total": memory_total,
            "rate": round(memory_pass / max(memory_total, 1), 3),
        },
        "latency": {
            "avg": round(sum(latencies)/max(len(latencies),1), 3),
            "min": round(min(latencies) if latencies else 0, 3),
            "max": round(max(latencies) if latencies else 0, 3),
        },
    }

    # 保存单组 JSON + CSV
    base = f"{out_dir}/group_{idx:02d}_{eid}_{lang}"
    with open(base + ".json", "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "rounds": rounds}, f, ensure_ascii=False, indent=2)
    with open(base + ".csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["round", "question", "reply", "success", "lang_ok", "target_ratio", "zh_ratio",
                    "nsfw_hits", "format_issues", "memory_recall", "latency", "error"])
        for r in rounds:
            w.writerow([
                r["round"], r["question"], r["reply"], r["success"], r["lang_ok"],
                r["target_ratio"], r["zh_ratio"],
                "|".join(r["nsfw_hits"]) if r["nsfw_hits"] else "",
                "|".join(r["format_issues"]) if r["format_issues"] else "",
                json.dumps(r["memory_recall"], ensure_ascii=False) if r["memory_recall"] else "",
                r["latency"], r["error"],
            ])

    print(f"\n  组内汇总: 错误 {errors} | 语言失败 {lang_fail}/{valid} | 复读对 {len(dup_pairs)}"
          f" | NSFW {nsfw_violations} | 格式违规 {format_violations} | 记忆 {memory_pass}/{memory_total}"
          f" | 平均 {summary['latency']['avg']}s")
    return summary

# ========== 主入口 ==========
def main():
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = f"test_multilang_{stamp}"
    os.makedirs(out_dir, exist_ok=True)
    print(f"输出目录: {out_dir}")

    with open("questions_multilang.json", encoding="utf-8") as f:
        qdata = json.load(f)

    t_start = time.time()
    summaries = []
    for g in TEST_GROUPS:
        try:
            s = run_group(g, qdata, out_dir)
            summaries.append(s)
        except KeyboardInterrupt:
            print("\n[!] 用户中断")
            break
        except Exception:
            traceback.print_exc()
            summaries.append({"idx": g[0], "expert_id": g[1], "error": traceback.format_exc()[:500]})

    total_dt = time.time() - t_start

    # 汇总 JSON
    all_summary = {
        "start": stamp,
        "duration_sec": round(total_dt, 1),
        "groups": summaries,
    }
    with open(f"{out_dir}/_all_summary.json", "w", encoding="utf-8") as f:
        json.dump(all_summary, f, ensure_ascii=False, indent=2)

    # 文本报告
    lines = []
    lines.append(f"新服务器多语言聊天测试综合报告")
    lines.append(f"时间: {stamp}  耗时: {total_dt:.0f}s")
    lines.append(f"接口: POST {BASE_URL}  apiPath={API_PATH}")
    lines.append(f"测试组: {len(TEST_GROUPS)}  每组40轮")
    lines.append("=" * 80)
    lines.append(f"{'#':<3} {'eid':<5} {'角色':<12} {'语言':<12} "
                 f"{'错':<4} {'语言失败':<10} {'复读':<6} {'NSFW':<6} {'格式':<6} {'记忆':<8} {'延迟avg':<8}")
    lines.append("-" * 80)
    tot_lang_fail = tot_dup = tot_nsfw = tot_fmt = tot_mem_p = tot_mem_t = tot_err = 0
    for s in summaries:
        if "error" in s and "role_name" not in s:
            lines.append(f"{s.get('idx','?'):<3} {s.get('expert_id','?'):<5} <执行异常>")
            continue
        lines.append(
            f"{s['idx']:<3} {s['expert_id']:<5} {s['role_name']:<12} {s['lang_label']:<12} "
            f"{s['errors']:<4} "
            f"{s['lang_consistency']['fail']}/{s['valid_replies']:<6} "
            f"{s['repetition_pairs']:<6} "
            f"{s['nsfw_violations']:<6} "
            f"{s['format_violations']:<6} "
            f"{s['memory']['pass']}/{s['memory']['total']:<6} "
            f"{s['latency']['avg']:<8}"
        )
        tot_err += s['errors']
        tot_lang_fail += s['lang_consistency']['fail']
        tot_dup += s['repetition_pairs']
        tot_nsfw += s['nsfw_violations']
        tot_fmt += s['format_violations']
        tot_mem_p += s['memory']['pass']
        tot_mem_t += s['memory']['total']
    lines.append("-" * 80)
    lines.append(f"总计: 错误 {tot_err} | 语言失败 {tot_lang_fail} | 复读对 {tot_dup}"
                 f" | NSFW {tot_nsfw} | 格式违规 {tot_fmt} | 记忆 {tot_mem_p}/{tot_mem_t}")
    lines.append("")
    lines.append("说明:")
    lines.append("  - 语言失败: 回复中目标语言字符<10% 或中文字符>=30%")
    lines.append("  - 复读对: 同组内两轮回复 Jaccard 相似度 >= 0.7")
    lines.append("  - NSFW:   命中涉黄关键词的轮次数")
    lines.append("  - 格式:   JSON 结构泄露 / 系统提示词泄露 / thoughts 字段")
    lines.append("  - 记忆:   第 36-40 轮记忆召回测试通过数 / 总数")

    report_txt = "\n".join(lines)
    report_path = f"{out_dir}/综合测试报告_新服务器_{stamp}.txt"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_txt)
    print("\n" + "=" * 80)
    print(report_txt)
    print("\n输出目录:", out_dir)
    print("综合报告:", report_path)

if __name__ == "__main__":
    main()
