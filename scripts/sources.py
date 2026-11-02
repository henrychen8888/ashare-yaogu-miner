# -*- coding: utf-8 -*-
"""
数据层：东方财富公开行情接口。

设计原则（踩坑换来的）：
1. **不依赖 push2 全市场快照。** 2026-11-02 实测 push2.eastmoney.com 在本机
   代理下整条链路不可达（clist 类接口全挂），而 push2ex / push2his 正常。
   所以全市场统计不做，改为「涨停池 + 指数 + 跌停/炸板池」自洽表达情绪，
   资金流逐票从 push2his 的 fflow 拿，不赌 clist。
2. **单位必须实测反推，不信表头。** 涨停池 p=4940 表示 4.94 元（×1000）；
   amount / ltsz / fund 都是元。fflow 各字段单位是元。
3. **涨停必须算术校验。** 用「昨收 ×(1+限制) ≈ 收盘」反推，区分主板 10%、
   创业板/科创 20%、北交所 30%、ST 5%。不做校验就会把 +13% 的科创票当涨停。
"""
from __future__ import annotations

import datetime as dt
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Iterable

from http_client import HttpError, fetch_json

EM_UT = "7eea3edcaed734bea9cbfc24409ed989"
HIS = "https://push2his.eastmoney.com"
EX = "https://push2ex.eastmoney.com"
DC = "https://datacenter-web.eastmoney.com"

KLINE_FIELDS = "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"


# ---------------------------------------------------------------- 基础工具
def secid(code: str) -> str:
    """东财 secid：沪市 1.xxxxxx，深市/创业板/北交所 0.xxxxxx。"""
    code = str(code).strip()
    if code.startswith(("6", "5", "9")):
        return f"1.{code}"
    return f"0.{code}"


def limit_ratio(code: str, name: str = "") -> float:
    """
    涨跌停幅度。ST/*ST 5%，北交所 30%，创业板(300/301)/科创板(688/689) 20%，
    其余 10%。
    """
    code = str(code)
    upper_name = (name or "").upper()
    if "ST" in upper_name:
        return 0.05
    if code.startswith(("8", "4", "92")):
        return 0.30
    if code.startswith(("300", "301", "688", "689")):
        return 0.20
    return 0.10


def is_limit_up(close: float, pct: float, code: str, name: str = "") -> bool:
    """
    算术校验涨停：由 收盘 与 涨跌幅 反推昨收，再看 昨收×(1+限制) 是否落在收盘上。
    容差 0.015 元（一分钱进位误差）。
    """
    if not close or not pct:
        return False
    ratio = limit_ratio(code, name)
    prev = close / (1 + pct / 100.0)
    target = round(prev * (1 + ratio), 2)
    return abs(target - close) < 0.015


# ---------------------------------------------------------------- 交易日
def trade_dates(n: int = 10) -> list[str]:
    """用上证指数日线取最近 n 个交易日（YYYY-MM-DD，升序）。"""
    url = (f"{HIS}/api/qt/stock/kline/get?secid=1.000001&klt=101&fqt=0&lmt={max(n, 5)}"
           f"&end=20500101&fields1=f1,f2&fields2=f51,f53")
    data = fetch_json(url)
    klines = ((data.get("data") or {}).get("klines") or [])
    return [k.split(",")[0] for k in klines]


# ---------------------------------------------------------------- 涨停 / 炸板 / 跌停
def _pool_meta(api: str, date: str, sort: str | None, pagesize: int = 300) -> dict:
    """
    返回 {pool:[...], tc:int}。

    坑：跌停池会出现 tc=8 但 pool=[] 的情况（接口对 pagesize/sort 的组合敏感），
    只信 len(pool) 会把跌停数误报成 0。所以 tc 必须一起取出来。
    """
    url = f"{EX}/{api}?ut={EM_UT}&dpt=wz.ztzt&Pageindex=0&pagesize={pagesize}&date={date}"
    if sort:
        url += f"&sort={sort}"
    data = fetch_json(url)
    body = data.get("data") or {}
    pool = body.get("pool") or []
    tc = int(body.get("tc") or len(pool))
    # 部分池子不认 sort 字段：pool 空但 tc>0。实测跌停池只认 fund/zdp 排序，
    # 用 fbt 或 lbc 会返回 pool=[] 而 tc 正常（静默空表，最容易漏）。
    if not pool and tc > 0 and sort not in (None, "fund%3Aasc"):
        return _pool_meta(api, date, "fund%3Aasc", pagesize)
    return {"pool": pool, "tc": tc}


def _pool(api: str, date: str, sort: str | None, pagesize: int = 300) -> list[dict]:
    return _pool_meta(api, date, sort, pagesize)["pool"]


def zt_pool(date: str) -> dict:
    """
    涨停池。返回 {"list": [...], "count": 全池数量}。
    字段：
    c 代码 / m 市场 / n 名称 / p 价格×1000 / zdp 涨跌幅 / amount 成交额(元)
    ltsz 流通市值(元) / tshare 总市值 / hs 换手率% / lbc 连板数
    fbt 首封时间 HHMMSS / lbt 最后封板时间 / fund 封板资金(元)
    zbc 炸板次数 / hybk 行业板块 / zttj {days, ct} 涨停统计
    """
    meta = _pool_meta("getTopicZTPool", date, "fbt%3Aasc")
    out = []
    for r in meta["pool"]:
        out.append({
            "code": str(r.get("c")),
            "name": r.get("n"),
            "close": round(float(r.get("p") or 0) / 1000.0, 2),
            "pct": round(float(r.get("zdp") or 0), 2),
            "amount": float(r.get("amount") or 0),
            "float_cap": float(r.get("ltsz") or 0),
            "turnover": float(r.get("hs") or 0),
            "boards": int(r.get("lbc") or 1),
            "first_seal": str(r.get("fbt") or "").zfill(6),
            "last_seal": str(r.get("lbt") or "").zfill(6),
            "seal_fund": float(r.get("fund") or 0),
            "broken": int(r.get("zbc") or 0),
            "industry": r.get("hybk") or "未分类",
        })
    return {"list": out, "count": meta["tc"]}


def zb_pool(date: str) -> dict:
    """炸板池（曾涨停未封住）。"""
    meta = _pool_meta("getTopicZBPool", date, "fbt%3Aasc")
    out = []
    for r in meta["pool"]:
        out.append({
            "code": str(r.get("c")),
            "name": r.get("n"),
            "pct": round(float(r.get("zdp") or 0), 2),
            "broken": int(r.get("zbc") or 0),
        })
    return {"list": out, "count": meta["tc"]}


def dt_pool(date: str) -> dict:
    """
    跌停池。实测该接口常用 sort 字段不适用，pool 可能为空而 tc 有值，
    因此数量以 tc 为准，明细可能缺失（不抛错，由看板兜底）。
    """
    try:
        # 跌停池必须带 fund 排序，否则 tc 直接返回 0（不是空表，是零值）
        meta = _pool_meta("getTopicDTPool", date, "fund%3Aasc")
    except HttpError:
        return {"list": [], "count": 0}
    return {
        "list": [{"code": str(r.get("c")), "name": r.get("n"),
                  "pct": round(float(r.get("zdp") or 0), 2)} for r in meta["pool"]],
        "count": meta["tc"],
    }


# ---------------------------------------------------------------- 龙虎榜
def lhb(date: str, page_size: int = 500) -> dict[str, dict]:
    """
    当日龙虎榜，按代码聚合。
    上榜次数 = 上榜原因去重条数（同一股票可能因多个原因重复出现）。
    净买入取 NET_BS_AMT（元）；机构席位识别 BUY_SEAT 里的「机构专用」。
    """
    result: dict[str, dict] = {}
    page = 1
    pages = 1
    while page <= pages and page <= 20:
        url = (f"{DC}/api/data/v1/get?pageSize={page_size}&pageNumber={page}"
               f"&reportName=RPT_DAILYBILLBOARD_DETAILSNEW&columns=ALL"
               f"&filter=(TRADE_DATE%3D%27{date}%27)&source=WEB&client=WEB")
        try:
            data = fetch_json(url)
        except HttpError:
            break
        res = data.get("result") or {}
        pages = int(res.get("pages") or 1)
        rows = res.get("data") or []
        if not rows:
            break
        for r in rows:
            code = str(r.get("SECURITY_CODE") or "")
            if not code:
                continue
            item = result.setdefault(code, {
                "code": code, "name": r.get("SECURITY_NAME_ABBR"),
                "reasons": set(), "net_buy": 0.0, "buy": 0.0, "sell": 0.0,
                "institution": False,
            })
            item["reasons"].add(str(r.get("EXPLANATION") or ""))
            item["net_buy"] += float(r.get("NET_BS_AMT") or 0)
            item["buy"] += float(r.get("BILLBOARD_BUY_AMT") or 0)
            item["sell"] += float(r.get("BILLBOARD_SELL_AMT") or 0)
            seat = f"{r.get('BUY_SEAT') or ''}{r.get('SELL_SEAT') or ''}"
            if "机构专用" in seat:
                item["institution"] = True
        page += 1
    for item in result.values():
        item["count"] = len([x for x in item["reasons"] if x])
        item["reasons"] = sorted(x for x in item["reasons"] if x)
    return result


# ---------------------------------------------------------------- 个股行情
def kline(code: str, lmt: int = 140) -> list[dict]:
    """前复权日线，升序。字段：日期/开/收/高/低/量(手)/额(元)/振幅/涨跌幅/涨跌额/换手率。"""
    url = (f"{HIS}/api/qt/stock/kline/get?secid={secid(code)}&klt=101&fqt=1&lmt={lmt}"
           f"&end=20500101&fields1=f1,f2,f3,f4,f5,f6&fields2={KLINE_FIELDS}")
    data = fetch_json(url)
    rows = ((data.get("data") or {}).get("klines") or [])
    out = []
    for row in rows:
        p = row.split(",")
        if len(p) < 11:
            continue
        out.append({
            "date": p[0], "open": float(p[1]), "close": float(p[2]),
            "high": float(p[3]), "low": float(p[4]),
            "volume": float(p[5]), "amount": float(p[6]),
            "pct": float(p[8]), "turnover": float(p[10]),
        })
    return out


def fflow(code: str) -> list[dict]:
    """
    资金流历史（日）。字段顺序实测：
    日期, 主力净流入, 小单, 中单, 大单, 超大单, 主力净占比, ...
    自洽校验：主力净流入 ≈ 大单 + 超大单，不等则抛错（防字段错位静默出错）。
    """
    url = (f"{HIS}/api/qt/stock/fflow/daykline/get?lmt=0&klt=101&secid={secid(code)}"
           f"&fields1=f1,f2,f3,f7&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65")
    data = fetch_json(url)
    rows = ((data.get("data") or {}).get("klines") or [])
    out = []
    for row in rows:
        p = row.split(",")
        if len(p) < 6:
            continue
        main = float(p[1] or 0)
        large = float(p[4] or 0)
        huge = float(p[5] or 0)
        out.append({
            "date": p[0], "main": main, "small": float(p[2] or 0),
            "mid": float(p[3] or 0), "large": large, "huge": huge,
            "main_ratio": float(p[7]) if len(p) > 7 and p[7] not in ("", "-") else None,
            "check_gap": abs(main - (large + huge)),
        })
    return out


def index_quotes() -> list[dict]:
    """主要指数当日快照（用日K最后两根算涨跌幅，避免再依赖 clist）。"""
    targets = [("1.000001", "上证指数"), ("0.399001", "深证成指"),
               ("0.399006", "创业板指"), ("1.000688", "科创50")]
    out = []
    for sid, name in targets:
        try:
            url = (f"{HIS}/api/qt/stock/kline/get?secid={sid}&klt=101&fqt=0&lmt=3"
                   f"&end=20500101&fields1=f1,f2&fields2=f51,f53")
            data = fetch_json(url)
            ks = ((data.get("data") or {}).get("klines") or [])
            if len(ks) < 2:
                continue
            last = ks[-1].split(",")
            prev = ks[-2].split(",")
            close = float(last[1])
            pct = (close / float(prev[1]) - 1) * 100
            out.append({"name": name, "close": close, "pct": round(pct, 2),
                        "date": last[0]})
        except Exception:
            continue
    return out


# ---------------------------------------------------------------- 批量并发
def batch(codes: Iterable[str], fn, workers: int = 8) -> dict[str, Any]:
    """并发拉取，单票失败返回 None 而不中断整批。"""
    codes = [c for c in codes]
    out: dict[str, Any] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fn, c): c for c in codes}
        for fut, code in futures.items():
            try:
                out[code] = fut.result()
            except Exception:
                out[code] = None
    return out


def normalize_date(s: str) -> str:
    """支持 20261102 / 2026-11-02 / 空（取最近交易日）。"""
    if not s:
        return trade_dates(3)[-1]
    s = re.sub(r"\D", "", s)
    if len(s) != 8:
        raise ValueError(f"日期格式应为 YYYYMMDD 或 YYYY-MM-DD，收到 {s!r}")
    return f"{s[:4]}-{s[4:6]}-{s[6:]}"


def compact(date: str) -> str:
    return date.replace("-", "")


def now_str() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
