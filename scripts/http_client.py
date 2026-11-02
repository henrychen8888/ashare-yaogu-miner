# -*- coding: utf-8 -*-
"""
零依赖 HTTP 客户端（纯标准库 urllib）。

两条实测教训固化在这里：

1. **代理对不同域名的连通性是随机的。** 本机走本地代理，同一时刻
   push2his.eastmoney.com 通、push2.eastmoney.com 直接 RemoteDisconnected
   （2026-11-02 实测）。反过来也出现过。所以每个请求都做
   「信任环境代理 → 直连」双通道重试，而不是赌某一个域名一定通。

2. **备用域名不是简单的 host 替换。** 东财的 clist 接口有 push2 / 82.push2 /
   push2delay / push2ex 多个入口，但 clist 类接口在 push2 全挂时备用域名也挂
   （同一条链路）。真正的兜底是换数据面（例如用个股 fflow 逐票取资金流，
   而不是依赖全市场 clist 快照）。

编码：东财返回 UTF-8；腾讯行情返回 GBK，调用方需显式传 encoding="gbk"。
"""
from __future__ import annotations

import gzip
import json
import ssl
import urllib.error
import urllib.parse
import urllib.request
import zlib
from typing import Any

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

DEFAULT_HEADERS = {
    "User-Agent": UA,
    "Accept": "*/*",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Connection": "close",
}

_SSL_CTX = ssl.create_default_context()
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode = ssl.CERT_NONE


class HttpError(RuntimeError):
    """HTTP 层统一异常。"""


def _opener(trust_env: bool) -> urllib.request.OpenerDirector:
    handlers = [
        urllib.request.HTTPSHandler(context=_SSL_CTX),
        urllib.request.HTTPRedirectHandler(),
    ]
    if not trust_env:
        handlers.append(urllib.request.ProxyHandler({}))  # 空 = 完全绕开代理
    return urllib.request.build_opener(*handlers)


def _decode_body(raw: bytes, encoding: str, headers: dict) -> str:
    enc = (headers.get("Content-Encoding") or "").lower()
    if "gzip" in enc:
        try:
            raw = gzip.decompress(raw)
        except OSError:
            pass
    elif "deflate" in enc:
        try:
            raw = zlib.decompress(raw, -zlib.MAX_WBITS)
        except zlib.error:
            pass
    return raw.decode(encoding, errors="replace")


def fetch(url: str, *, params: dict | None = None, method: str = "GET",
          body: dict | None = None, headers: dict | None = None,
          timeout: int = 15, trust_env: bool = True,
          encoding: str = "utf-8") -> tuple[int, str]:
    """返回 (status, text)。网络层失败抛 HttpError。"""
    full = url
    if params:
        full = url + ("&" if "?" in url else "?") + urllib.parse.urlencode(
            params, doseq=True, safe=",:+")

    data = json.dumps(body).encode("utf-8") if body is not None else None
    hdrs = dict(DEFAULT_HEADERS)
    if data is not None:
        hdrs["Content-Type"] = "application/json"
    if headers:
        hdrs.update(headers)

    req = urllib.request.Request(full, data=data, headers=hdrs, method=method)
    try:
        with _opener(trust_env).open(req, timeout=timeout) as resp:
            return resp.status, _decode_body(resp.read(), encoding, dict(resp.headers))
    except urllib.error.HTTPError as e:
        try:
            text = _decode_body(e.read(), encoding, dict(e.headers))
        except Exception:
            text = ""
        return e.code, text
    except urllib.error.URLError as e:
        raise HttpError(f"URLError: {e.reason}") from e
    except ssl.SSLError as e:
        raise HttpError(f"SSLError: {e}") from e
    except Exception as e:
        raise HttpError(f"{type(e).__name__}: {e}") from e


def fetch_json(url: str, *, retries: int = 2, **kw) -> Any:
    """
    先 trust_env=True 再 False，任一通道成功即返回。
    这样做的代价是失败时多等一轮，收益是不用猜今天哪个域名被代理挡住。
    """
    last: Exception | None = None
    for trust in (True, False):
        for attempt in range(retries):
            try:
                status, text = fetch(url, trust_env=trust, **kw)
                if status != 200:
                    last = HttpError(f"HTTP {status}: {text[:160]}")
                    continue
                return json.loads(text)
            except (HttpError, json.JSONDecodeError) as e:
                last = e
    raise HttpError(f"{url.split('?')[0]} 双通道失败: {last}")
