#!/usr/bin/env python3
"""K200 야간선물 가격 push — VM 내부 ws://127.0.0.1:8766 에서 받아 GitHub.

매 1분 cron → ngt_quote.json → UI fetch.
Tailscale Funnel /ngt 외부 노출 불필요 (사용자 환경에서 차단됨).
"""
import os
import sys
import json
import ssl
import asyncio
import base64
import urllib.request
import urllib.error
from datetime import datetime

import websockets

LOCAL_WS = "ws://127.0.0.1:8766"
CODE = "1A01609"

REPO = "goldpigbankgazua-dev/yeobtoni-stock-bot"
REPO_PATH = "modules/morning/data/ngt_quote.json"
BRANCH = "main"

SSL_CTX = ssl.create_default_context()


async def fetch_tick():
    """ws connect → subscribe → 첫 tick 받음 (last 캐시 즉시 또는 새 tick)."""
    async with websockets.connect(LOCAL_WS, ping_interval=None) as ws:
        # hello 메시지 먼저 (데몬이 즉시 보냄)
        try:
            await asyncio.wait_for(ws.recv(), timeout=3)
        except asyncio.TimeoutError:
            pass
        await ws.send(json.dumps({"action": "subscribe", "code": CODE}))
        # 최대 8초 동안 tick 대기
        deadline = asyncio.get_event_loop().time() + 8
        while asyncio.get_event_loop().time() < deadline:
            remaining = deadline - asyncio.get_event_loop().time()
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=remaining)
            except asyncio.TimeoutError:
                break
            try:
                data = json.loads(msg)
            except Exception:
                continue
            if data.get("type") == "tick" and data.get("code") == CODE:
                return data
        return None


def github_get_sha(pat):
    url = f"https://api.github.com/repos/{REPO}/contents/{REPO_PATH}?ref={BRANCH}"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {pat}",
        "Accept": "application/vnd.github+json",
    })
    try:
        with urllib.request.urlopen(req, timeout=20, context=SSL_CTX) as resp:
            return json.loads(resp.read())["sha"]
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def github_put(pat, content_str, sha=None):
    url = f"https://api.github.com/repos/{REPO}/contents/{REPO_PATH}"
    payload = {
        "message": f"data: ngt K200 ({datetime.now().strftime('%Y-%m-%d %H:%M')} KST)",
        "content": base64.b64encode(content_str.encode("utf-8")).decode(),
        "branch": BRANCH,
    }
    if sha:
        payload["sha"] = sha
    body = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=body, method="PUT", headers={
        "Authorization": f"Bearer {pat}",
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json",
    })
    with urllib.request.urlopen(req, timeout=30, context=SSL_CTX) as resp:
        return resp.status


def main():
    pat = os.environ.get("GITHUB_PAT", "").strip()
    if not pat:
        print("✗ GITHUB_PAT 없음", file=sys.stderr)
        sys.exit(1)

    try:
        tick = asyncio.run(fetch_tick())
    except Exception as e:
        print(f"✗ ws fetch 실패: {e}", file=sys.stderr)
        sys.exit(2)

    if not tick:
        print("✗ tick 못 받음 (장시간 외? 데몬 미동작?)", file=sys.stderr)
        sys.exit(3)

    price = tick.get("price")
    vrss = tick.get("vrss")
    vrss_sign = tick.get("vrss_sign")
    ctrt = tick.get("ctrt")

    # vrss_sign 4/5 = 하락 (KIS 표준 부호)
    if vrss_sign and str(vrss_sign) in ("4", "5") and isinstance(vrss, (int, float)) and vrss > 0:
        vrss = -vrss

    prev = (price - vrss) if (price is not None and vrss is not None) else None

    payload = {
        "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "code": CODE,
        "name": "K200 야간선물",
        "symbol": "K2I1!",
        "exchange": "KRX 야간",
        "price": price,
        "previous": prev,
        "change": vrss,
        "change_pct": ctrt,
        "state": "REGULAR",
        "time": tick.get("time"),
        "acml_vol": tick.get("acml_vol"),
        "source": "KIS WebSocket H0MFCNT0",
        "delayed": False,  # source 는 실시간, 1분 polling
    }
    content_str = json.dumps(payload, ensure_ascii=False, indent=2)
    sign = "+" if (vrss or 0) >= 0 else ""
    print(f"✓ K200: {price} ({sign}{vrss}, {sign}{ctrt}%)")

    try:
        sha = github_get_sha(pat)
        status = github_put(pat, content_str, sha=sha)
        print(f"[gh] PUT OK HTTP {status}")
    except Exception as e:
        print(f"[gh] PUT 실패: {e}", file=sys.stderr)
        sys.exit(4)


if __name__ == "__main__":
    main()
