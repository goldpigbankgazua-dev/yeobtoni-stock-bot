#!/usr/bin/env python3
"""K200 야간선물 실시간 데몬 — TR_ID H0MFCNT0.

기존 kis_realtime.py (일반 주식 H0UNCNT0, 포트 8765) 와 독립.
- 포트: 8766
- TR_ID: H0MFCNT0 (KRX 야간선물 실시간 체결)
- 활성 종목: 1A01609 (2026-09 K200 야간선물 — 매 분기 갱신 필요)

env:
  KIS_APP_KEY / KIS_APP_SECRET — KIS Open API 키
"""
import os
import sys
import json
import ssl
import asyncio
import logging
import urllib.request
from datetime import datetime

import websockets

# ============================================================
# 설정
# ============================================================
LOCAL_WS_HOST = "127.0.0.1"
LOCAL_WS_PORT = 8766

KIS_WS_URL = "ws://ops.koreainvestment.com:21000"
KIS_APPROVAL_URL = "https://openapi.koreainvestment.com:9443/oauth2/Approval"

TR_TRADE = "H0MFCNT0"  # KRX 야간선물 실시간 체결

# K200 야간선물 활성 월물 — 매 분기 만기일 (3/6/9/12월 둘째주 목요일)
# fo_cme_code.mst 파일에서 자동 추출 가능 (TODO: 자동화)
DEFAULT_CODES = ["1A01609"]  # 2026-09 활성

LOG_FILE = os.path.expanduser("~/kis_ngt_realtime.log")

# ============================================================
# H0MFCNT0 payload 필드 (KIS sample 의 columns 순서)
# ============================================================
TRADE_FIELDS = [
    "futs_shrn_iscd",     # 0: 선물 단축 종목코드
    "bsop_hour",          # 1: 영업 시간
    "futs_prdy_vrss",     # 2: 선물 전일 대비
    "prdy_vrss_sign",     # 3: 전일 대비 부호
    "futs_prdy_ctrt",     # 4: 선물 전일 대비율
    "futs_prpr",          # 5: 선물 현재가 ← 가격
    "futs_oprc",          # 6: 선물 시가
    "futs_hgpr",          # 7: 선물 최고가
    "futs_lwpr",          # 8: 선물 최저가
    "last_cnqn",          # 9: 최종 거래량
    "acml_vol",           # 10: 누적 거래량
    "acml_tr_pbmn",       # 11: 누적 거래 대금
    "hts_thpr",           # 12: HTS 이론가
    "mrkt_basis",         # 13: 시장 베이시스
    "dprt",               # 14: 괴리율
    "nmsc_fctn_stpl_prc", # 15: 근월물 약정가
    "fmsc_fctn_stpl_prc", # 16: 원월물 약정가
    "spead_prc",          # 17: 스프레드1
    "hts_otst_stpl_qty",  # 18: HTS 미결제 약정 수량
    "otst_stpl_qty_icdc", # 19: 미결제 약정 수량 증감
    "oprc_hour",          # 20: 시가 시간
    "oprc_vrss_prpr_sign",# 21
    "oprc_vrss_nmix_prpr",# 22
    "hgpr_hour",          # 23
    "hgpr_vrss_prpr_sign",# 24
    "hgpr_vrss_nmix_prpr",# 25
    "lwpr_hour",          # 26
    "lwpr_vrss_prpr_sign",# 27
    "lwpr_vrss_nmix_prpr",# 28
    "shnu_rate",          # 29: 매수2 비율
    "cttr",               # 30: 체결강도
    "esdg",               # 31: 괴리도
    "otst_stpl_rgbf_qty_icdc",  # 32
    "thpr_basis",         # 33: 이론 베이시스
    "futs_askp1",         # 34: 선물 매도호가1
    "futs_bidp1",         # 35: 선물 매수호가1
    "askp_rsqn1",         # 36
    "bidp_rsqn1",         # 37
    "seln_cntg_csnu",     # 38: 매도 체결 건수
    "shnu_cntg_csnu",     # 39: 매수 체결 건수
    "ntby_cntg_csnu",     # 40: 순매수 체결 건수
    "seln_cntg_smtn",     # 41: 총 매도 수량
    "shnu_cntg_smtn",     # 42: 총 매수 수량
    "total_askp_rsqn",    # 43: 총 매도호가 잔량
    "total_bidp_rsqn",    # 44: 총 매수호가 잔량
    "prdy_vol_vrss_acml_vol_rate",  # 45: 전일 거래량 대비 등락율
    "dynm_mxpr",          # 46: 실시간 상한가
    "dynm_llam",          # 47: 실시간 하한가
    "dynm_prc_limt_yn",   # 48: 실시간 가격제한 구분
]


def parse_ngt_payload(payload, count):
    """KIS H0MFCNT0 payload (^ 구분) → list[dict].

    count: 한 패킷에 포함된 체결 건수
    """
    cells = payload.split("^")
    n = len(TRADE_FIELDS)
    out = []
    for i in range(count):
        slice_ = cells[i * n: (i + 1) * n]
        if len(slice_) < n:
            break
        row = dict(zip(TRADE_FIELDS, slice_))
        out.append({
            "type": "tick",
            "code": row.get("futs_shrn_iscd"),
            "tr_id": TR_TRADE,
            "price": _to_f(row.get("futs_prpr")),
            "vrss": _to_f(row.get("futs_prdy_vrss")),
            "vrss_sign": row.get("prdy_vrss_sign"),
            "ctrt": _to_f(row.get("futs_prdy_ctrt")),
            "open": _to_f(row.get("futs_oprc")),
            "high": _to_f(row.get("futs_hgpr")),
            "low": _to_f(row.get("futs_lwpr")),
            "last_vol": _to_i(row.get("last_cnqn")),
            "acml_vol": _to_i(row.get("acml_vol")),
            "askp1": _to_f(row.get("futs_askp1")),
            "bidp1": _to_f(row.get("futs_bidp1")),
            "time": row.get("bsop_hour"),
            "raw_first_row": row if i == 0 else None,  # 디버그용
        })
    return out


def _to_f(v):
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _to_i(v):
    try:
        return int(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


# ============================================================
# KIS approval_key
# ============================================================
def get_approval_key(app_key, app_secret):
    """WebSocket approval_key 발급 — body 키이름은 secretkey (not appsecret)."""
    body = json.dumps({
        "grant_type": "client_credentials",
        "appkey": app_key,
        "secretkey": app_secret,
    }).encode()
    req = urllib.request.Request(
        KIS_APPROVAL_URL,
        data=body,
        headers={"content-type": "application/json"},
    )
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
        return json.loads(resp.read())["approval_key"]


# ============================================================
# Bridge — KIS WebSocket ↔ local clients
# ============================================================
class NgtBridge:
    def __init__(self, approval_key):
        self.approval_key = approval_key
        self.kis_ws = None
        self.subs = {}      # code → set[client_ws]
        self.last = {}      # code → 마지막 tick
        self.clients = set()

    async def ensure_kis_ws(self):
        if self.kis_ws is not None:
            return
        logging.info(f"KIS WS 연결: {KIS_WS_URL}")
        self.kis_ws = await websockets.connect(
            KIS_WS_URL, ping_interval=None, max_size=2 ** 22)
        asyncio.create_task(self._read_kis())

    async def _send_kis_subscribe(self, code, action="subscribe"):
        await self.ensure_kis_ws()
        tr_type = "1" if action == "subscribe" else "2"
        msg = {
            "header": {
                "approval_key": self.approval_key,
                "custtype": "P",
                "tr_type": tr_type,
                "content-type": "utf-8",
            },
            "body": {"input": {"tr_id": TR_TRADE, "tr_key": code}},
        }
        await self.kis_ws.send(json.dumps(msg))
        logging.info(f"KIS {action} {TR_TRADE} {code}")

    async def _read_kis(self):
        try:
            async for raw in self.kis_ws:
                await self._handle_kis_msg(raw)
        except Exception as e:
            logging.warning(f"KIS WS 종료: {e}")
            self.kis_ws = None
            # 재연결 + 재구독
            await asyncio.sleep(2)
            try:
                await self.ensure_kis_ws()
                for code in list(self.subs.keys()):
                    await self._send_kis_subscribe(code, "subscribe")
            except Exception as e2:
                logging.error(f"재연결 실패: {e2}")

    async def _handle_kis_msg(self, raw):
        if not isinstance(raw, str):
            try:
                raw = raw.decode("utf-8", errors="replace")
            except Exception:
                return
        # JSON (구독 응답/에러)
        if raw.startswith("{"):
            try:
                d = json.loads(raw)
                body = d.get("body", {})
                rt_cd = body.get("rt_cd")
                if rt_cd and rt_cd != "0":
                    logging.warning(f"KIS 응답: {body.get('msg1', raw[:200])}")
                else:
                    logging.info(f"KIS 응답 ok: {body.get('msg1', '')}")
            except Exception:
                logging.info(f"KIS msg: {raw[:200]}")
            return
        # 실시간 데이터: 0|H0MFCNT0|001|payload
        try:
            header, _, payload = raw.partition("|")
            tr_id, _, rest = payload.partition("|")
            count_s, _, body = rest.partition("|")
            count = int(count_s)
        except Exception:
            return
        if tr_id != TR_TRADE:
            return
        ticks = parse_ngt_payload(body, count)
        for t in ticks:
            code = t.get("code")
            if not code:
                continue
            self.last[code] = t
            await self._broadcast(code, t)

    async def _broadcast(self, code, ev):
        clients = self.subs.get(code, set())
        if not clients:
            return
        data = json.dumps(ev, ensure_ascii=False)
        dead = []
        for ws in clients:
            try:
                await ws.send(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            clients.discard(ws)

    # ---- local WS server ----
    async def serve_client(self, ws):
        self.clients.add(ws)
        try:
            await ws.send(json.dumps({
                "type": "hello",
                "approval_ok": bool(self.approval_key),
                "tr_id": TR_TRADE,
                "default_codes": DEFAULT_CODES,
            }))
        except Exception:
            return
        try:
            async for raw in ws:
                try:
                    msg = json.loads(raw)
                except Exception:
                    continue
                action = msg.get("action")
                codes = msg.get("codes") or (
                    [msg.get("code")] if msg.get("code") else [])
                codes = [c for c in codes if c]
                if action == "subscribe":
                    for code in codes:
                        s = self.subs.setdefault(code, set())
                        new = (len(s) == 0)
                        s.add(ws)
                        if new:
                            await self._send_kis_subscribe(code, "subscribe")
                        elif code in self.last:
                            await ws.send(json.dumps(self.last[code]))
                elif action == "unsubscribe":
                    for code in codes:
                        s = self.subs.get(code)
                        if not s:
                            continue
                        s.discard(ws)
                        if not s:
                            await self._send_kis_subscribe(code, "unsubscribe")
                            del self.subs[code]
        except Exception as e:
            logging.info(f"client 종료: {e}")
        finally:
            self.clients.discard(ws)
            empty = []
            for code, s in self.subs.items():
                s.discard(ws)
                if not s:
                    empty.append(code)
            for code in empty:
                try:
                    await self._send_kis_subscribe(code, "unsubscribe")
                except Exception:
                    pass
                del self.subs[code]


def load_env(path):
    env = {}
    if not os.path.exists(path):
        return env
    with open(path) as f:
        for l in f:
            l = l.strip()
            if not l or l.startswith("#") or "=" not in l:
                continue
            k, v = l.split("=", 1)
            env[k] = v
    return env


async def main_async():
    env_paths = ["/home/ec2-user/morning/.env",
                 "/home/ec2-user/market/.env",
                 "/home/ec2-user/kis-ngt/.env"]
    env = {}
    for p in env_paths:
        env.update(load_env(p))
    app_key = env.get("KIS_APP_KEY") or os.environ.get("KIS_APP_KEY", "")
    app_secret = env.get("KIS_APP_SECRET") or os.environ.get("KIS_APP_SECRET", "")
    if not app_key or not app_secret:
        logging.error("KIS_APP_KEY / KIS_APP_SECRET 없음")
        sys.exit(2)

    # approval_key
    try:
        approval = await asyncio.to_thread(get_approval_key, app_key, app_secret)
        logging.info(f"approval_key OK: {approval[:20]}...")
    except Exception as e:
        logging.error(f"approval_key 실패: {e}")
        sys.exit(3)

    bridge = NgtBridge(approval)

    async def handler(ws):
        await bridge.serve_client(ws)

    logging.info(f"로컬 WS 시작: ws://{LOCAL_WS_HOST}:{LOCAL_WS_PORT}")
    async with websockets.serve(handler, LOCAL_WS_HOST, LOCAL_WS_PORT):
        # 시작 시 DEFAULT_CODES 자동 구독 (대시보드에 즉시 표시되도록)
        for code in DEFAULT_CODES:
            self_ = bridge
            self_.subs.setdefault(code, set())
            await self_._send_kis_subscribe(code, "subscribe")
        await asyncio.Future()


def main():
    # systemd 가 StandardOutput=append: 로 로그 파일에 직접 저장하므로
    # Python 은 stdout 만 — FileHandler 두면 권한 충돌.
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        stream=sys.stdout,
    )
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        logging.info("종료")


if __name__ == "__main__":
    main()
