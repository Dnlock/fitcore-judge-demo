#!/usr/bin/env python3
"""ws-judge-core · 访客隔离冒烟（双访客独立 Session，服务器零访客绑定机制下的隔离验证）。

公网演示隔离架构：每访客独立 Session（前端本地生成会话）+ 服务端唯一测试 Token
（代理代持，浏览器零持有）。本冒烟验证：
  G1 访客A、访客B 各自建 Session，互不干扰（facts 各自独立）
  G2 同服务会话数据不串扰：A 的事实不出现于 B
  G3 前端静态资产不含 Token 字面量（服务端唯一 Token 不进入浏览器）
  G4 会话跨 Session 无法指定他人（sid 由服务端发放；不存在 sid 404）
  G5 多访客并发上传互不阻塞（顺序验证即可，Worker 串行处理）

用法:
  python3 e2e/isolation_smoke.py --proxy http://127.0.0.1:8956 --wav-dir fixtures/wav \
      --token-literal <本次运行使用的服务端测试Token值（用于零泄漏断言，不回显）>
退出码: 0 = 全部断言通过。
"""

import argparse
import json
import sys
import time
import urllib.request
import urllib.error
import uuid
from pathlib import Path

APP_KEY_HEADER = "X-Demo-App-Key"


def call(base, method, path, body=None, headers=None, raw=None, expect=None):
    data = json.dumps(body).encode() if body is not None else raw
    req = urllib.request.Request(base + path, method=method, data=data, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            payload = json.loads(r.read())
            if expect is not None:
                assert r.status == expect, f"{method} {path}: {r.status} != {expect}"
            return r.status, payload
    except urllib.error.HTTPError as e:
        rawb = e.read()
        try:
            payload = json.loads(rawb)
        except Exception:
            payload = {"raw": rawb.decode("utf-8", "replace")[:200]}
        if expect is not None:
            assert e.code == expect, f"{method} {path}: {e.code} != {expect}: {payload}"
        return e.code, payload


def upload(base, sid, uid, seq, wav_path):
    boundary = "----ws-jc-iso-" + uuid.uuid4().hex
    parts = []
    for name, value in (("utterance_id", uid), ("sequence", str(seq)),
                        ("audio_source", "client_complete_wav")):
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="c.wav"\r\n'
                 f'Content-Type: audio/wav\r\n\r\n'.encode())
    parts.append(wav_path.read_bytes())
    parts.append(f"\r\n--{boundary}--\r\n".encode())
    return call(base, "POST", f"/sessions/{sid}/audio-jobs", raw=b"".join(parts),
                headers={APP_KEY_HEADER: "fitcore-demo-app-v1",
                         "Content-Type": f"multipart/form-data; boundary={boundary}"})


def poll(base, sid, uid, timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        st, jr = call(base, "GET", f"/sessions/{sid}/audio-jobs/{uid}",
                      headers={APP_KEY_HEADER: "fitcore-demo-app-v1"}, expect=200)
        job = jr.get("job", {})
        if job.get("status") in ("done", "blocked"):
            return job
        time.sleep(0.1)
    raise AssertionError("poll timeout")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--proxy", default="http://127.0.0.1:8956")
    ap.add_argument("--wav-dir", default=str(Path(__file__).resolve().parents[1] / "fixtures" / "wav"))
    ap.add_argument("--token-literal", default="")
    args = ap.parse_args()
    base = args.proxy.rstrip("/") + "/realproxy/v1"
    wav = Path(args.wav_dir)
    checks, ok = [], True

    def check(name, cond, detail=""):
        nonlocal ok
        checks.append(name)
        print(f"[{'OK' if cond else 'FAIL'}] {name} {detail}")
        if not cond:
            ok = False

    # G1 双访客各自建 Session + 各自上传（60×8 与 下一组70 各一）
    st, sa = call(base, "POST", "/sessions", {}, {APP_KEY_HEADER: "fitcore-demo-app-v1",
                                                  "Content-Type": "application/json"}, expect=201)
    st, sb = call(base, "POST", "/sessions", {}, {APP_KEY_HEADER: "fitcore-demo-app-v1",
                                                  "Content-Type": "application/json"}, expect=201)
    sid_a, sid_b = sa["session_id"], sb["session_id"]
    check("G1a_two_sessions_created", sid_a != sid_b and sa["status"] == sb["status"] == "active",
          f"sidA={sid_a[:8]}… sidB={sid_b[:8]}…")

    st, _ = upload(base, sid_a, "UA-1", 0, wav / "real_E-0002.wav")   # 卧推60公斤8个
    job_a = poll(base, sid_a, "UA-1")
    st, _ = upload(base, sid_b, "UB-1", 0, wav / "real_E-0005.wav")   # 下一组想试70公斤
    job_b = poll(base, sid_b, "UB-1")
    check("G1b_both_jobs_done", job_a["status"] == job_b["status"] == "done",
          f"A={job_a.get('final_text')!r} B={job_b.get('final_text')!r}")

    # G2 facts 不串扰：A=卧推60×8（1 组）；B=下一组想试70（计划修改，正确语义=不落事实）
    st, fa = call(base, "GET", f"/sessions/{sid_a}/facts", headers={APP_KEY_HEADER: "fitcore-demo-app-v1"}, expect=200)
    st, fb = call(base, "GET", f"/sessions/{sid_b}/facts", headers={APP_KEY_HEADER: "fitcore-demo-app-v1"}, expect=200)
    check("G2a_facts_isolated", len(fa) == 1 and fa[0]["reps"] == 8 and fa[0]["weight_kg"] == 60.0,
          f"A facts={fa}")
    check("G2b_facts_isolated", len(fb) == 0,
          f"B facts={fb}（下一组想试70=计划修改，正确语义不落事实）")
    a_ids = {f["source_utterance_id"] for f in fa}
    b_ids = {f["source_utterance_id"] for f in fb}
    check("G2c_no_cross_contamination", a_ids.isdisjoint(b_ids),
          f"A src={a_ids} B src={b_ids}（两访客事实来源集合无交集）")

    # G3 静态资产零 Token 字面量
    page = urllib.request.urlopen(urllib.request.Request(args.proxy + "/"), timeout=15).read()
    js_files = ["js/app.js", "js/httpAdapter.js", "js/v1client.js"]
    leak_free = args.token_literal not in page.decode("utf-8", "replace")
    for js in js_files:
        body = urllib.request.urlopen(urllib.request.Request(args.proxy + "/" + js), timeout=15).read()
        leak_free = leak_free and (args.token_literal not in body.decode("utf-8", "replace"))
    check("G3_static_assets_token_free", leak_free,
          "index+3 JS 均不含服务端测试 Token 字面量（浏览器零持有）")

    # G4 访客不能访问他人 Session：前端无法从服务端获得他人 sid；
    # 但同 token 体系下任何持 App 密钥者可读已知 sid —— 演示隔离边界为
    # “每访客独立 Session + 服务器不发他人 sid + 无枚举端点”。验证：不存在 sid 404。
    st, e404, = call(base, "GET", "/sessions/no-such-session",
                     headers={APP_KEY_HEADER: "fitcore-demo-app-v1"}, expect=404)
    check("G4_no_session_enumeration", e404.get("detail") == "SESSION_NOT_FOUND",
          f"detail={e404.get('detail')}（无列表/枚举端点，sid 仅服务端发放）")

    # G5 并发两个上传（不同会话）各自完成，无串扰错误。
    # A、B 第二轮都传 "8"（BARE_NUMBER pending）；B 首轮"下一组70"在无活动
    # 训练时正确产生 MISSING_EXERCISE pending（上游语义），因此 B 共 2 个 pending。
    st, _ = upload(base, sid_a, "UA-2", 1, wav / "real_E-0003.wav")   # 8 → pending
    job_a2 = poll(base, sid_a, "UA-2")
    st, _ = upload(base, sid_b, "UB-2", 1, wav / "real_E-0006.wav")   # 8 → pending
    job_b2 = poll(base, sid_b, "UB-2")
    st, pa = call(base, "GET", f"/sessions/{sid_a}/pending", headers={APP_KEY_HEADER: "fitcore-demo-app-v1"}, expect=200)
    st, pb = call(base, "GET", f"/sessions/{sid_b}/pending", headers={APP_KEY_HEADER: "fitcore-demo-app-v1"}, expect=200)
    reasons_a = sorted({p["reason"] for p in pa})
    reasons_b = sorted({p["reason"] for p in pb})
    check("G5_pending_isolated", reasons_a == ["BARE_NUMBER"]
          and reasons_b == ["BARE_NUMBER", "MISSING_EXERCISE"]
          and pa[0]["utterance_id"].startswith("UA-") and all(
              p["utterance_id"].startswith("UB-") for p in pb),
          f"A pending={len(pa)} reason={reasons_a} | B pending={len(pb)} reason={reasons_b}"
          f"（各访客 pending 只含自己的 utterance_id，无串扰）")

    print(f"\nISOLATION_RESULT: {'ALL_OK' if ok else 'HAS_FAILURES'} {len(checks)} checks")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
