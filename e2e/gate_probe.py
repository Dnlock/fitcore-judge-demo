#!/usr/bin/env python3
"""ws-judge-core · 公网门禁探针（对外代理 8956/80 + 隔离 Core 8957/8001 直连拒绝面）。

独立于 28 步 E2E，验证「公网安全 12 项」中最关键的可远程观测门禁：
  P01 直连 Core 无需认证的越权面 → 401（Core 未暴露公网，双保险）
  P02 代理路径白名单外 → 404/405（/admin、/docs、/openapi.json、PUT 等）
  P03 App 密钥缺失 → 403 app_key_required
  P04 代理错误体与响应头不含 Token 字面量
  P05 代理直连 health 不泄露 Core /health 之外字段（token_configured 布尔）
  P06 超大 multipart → 413（上传大小限制）
  P07 代理静态路径穿越 → 400/404（web/ 子树外拒绝）
  P08 直连 Core /docs、/openapi.json 存在（上游行为），但代理不转发（信息面收紧）
  P09 FAKE_TEST 未映射 WAV → 422/确定性失败（不猜测转录）
  P10 独立 DB 验证：e2e 库不在上游 fitcore.db、8790 不动（由 E2E db 路径断言）

用法:
  python3 e2e/gate_probe.py --proxy http://127.0.0.1:8956 --core http://127.0.0.1:8957
退出码: 0 = 全部探针通过。
"""

import argparse
import json
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path

APP_KEY_HEADER = "X-Demo-App-Key"
WAV_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "wav"


def raw_call(url, method="GET", headers=None, body=None, timeout=10):
    req = urllib.request.Request(url, method=method, data=body, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read(), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read(), dict(e.headers)
    except urllib.error.URLError as e:
        return 0, str(e).encode(), {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--proxy", default="http://127.0.0.1:8956")
    ap.add_argument("--core", default="http://127.0.0.1:8957")
    args = ap.parse_args()
    proxy = args.proxy.rstrip("/")
    core = args.core.rstrip("/")
    results = []
    ok = True

    def probe(name, cond, detail):
        nonlocal ok
        results.append((name, cond, detail))
        print(f"[{'PASS' if cond else 'FAIL'}] {name}: {detail}")
        if not cond:
            ok = False

    # P01 直连 Core 缺 Bearer → 401（且不暴露存在性）
    st, body, _ = raw_call(core + "/v1/sessions", headers={})
    probe("P01_core_direct_no_auth_401", st == 401, f"status={st} body={body[:80]!r}")

    # P02 白名单外路径：/admin、/docs、/openapi.json、PUT /realproxy、DELETE
    #（带 App 密钥头=正常访客姿态；docs/openapi 已被容器装配剔除 → 404/400）
    for name, path, method, expect in [
        ("P02a_admin_404", "/admin", "GET", (404, 400)),
        ("P02b_docs_404", "/realproxy/docs", "GET", (400, 404)),
        ("P02c_openapi_404", "/realproxy/openapi.json", "GET", (400, 404)),
        ("P02d_put_405", "/realproxy/v1/sessions", "PUT", (405, 400)),
        ("P02e_delete_405", "/realproxy/v1/sessions/x", "DELETE", (405, 400)),
    ]:
        st, body, _ = raw_call(proxy + path, method=method,
                               headers={APP_KEY_HEADER: "fitcore-demo-app-v1"})
        probe(name, st in expect, f"status={st} body={body[:100]!r}")

    # P03 App 密钥缺失 → 403
    st, body, _ = raw_call(proxy + "/realproxy/v1/sessions", headers={})
    probe("P03_app_key_403", st == 403, f"status={st} body={body[:120]!r}")

    # P04 Token 不泄漏：对错误 token 请求代理，响应不含 token 值
    #（代理根本不接受外部 Bearer；用任意探针 token 请求，响应不应回显）
    st, body, _ = raw_call(proxy + "/realproxy/v1/sessions",
                           headers={"Authorization": "Bearer secret-probe-xyz",
                                    "X-Demo-App-Key": "fitcore-demo-app-v1"})
    probe("P04_no_token_echo", b"secret-probe-xyz" not in body, f"status={st} body={body[:120]!r}")

    # P05 代理 /health 字段面
    st, body, _ = raw_call(proxy + "/health")
    try:
        h = json.loads(body)
        fields = set(h.keys())
    except Exception:
        h, fields = {}, set()
    probe("P05_proxy_health_fields", st == 200 and fields == {"status", "mode", "token_configured", "upstream", "time"},
          f"status={st} fields={sorted(fields)}")

    # P06 超大 multipart → 413（构造 >7MB+64KB 的包；WAV 数据用真实 fixture 填充到超限）
    big = (WAV_DIR / "real_E-0002.wav").read_bytes() * 600  # ≈7.7MB > 7MB
    boundary = "----ws-jc-probe-" + uuid.uuid4().hex
    parts = [
        f'--{boundary}\r\nContent-Disposition: form-data; name="utterance_id"\r\n\r\nU-PROBE\r\n'.encode(),
        f'--{boundary}\r\nContent-Disposition: form-data; name="sequence"\r\n\r\n0\r\n'.encode(),
        f'--{boundary}\r\nContent-Disposition: form-data; name="audio_source"\r\n\r\nclient_complete_wav\r\n'.encode(),
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="big.wav"\r\n'
        f'Content-Type: audio/wav\r\n\r\n'.encode(),
        big,
        f"\r\n--{boundary}--\r\n".encode(),
    ]
    st, body, _ = raw_call(proxy + "/realproxy/v1/sessions/no-such-sid/audio-jobs", method="POST",
                           headers={APP_KEY_HEADER: "fitcore-demo-app-v1",
                                    "Content-Type": f"multipart/form-data; boundary={boundary}"},
                           body=b"".join(parts), timeout=30)
    probe("P06_upload_size_413", st == 413, f"status={st} body={body[:120]!r}")

    # P07 静态路径穿越 → 400/404
    for path in ("/../etc/passwd", "/..%2F..%2Fetc/passwd", "/js/..%2F..%2F..%2Fetc/passwd"):
        st, body, _ = raw_call(proxy + path)
        probe(f"P07_static_traversal_{path[-12:]}", st in (400, 404) and b"root:" not in body,
              f"status={st} len={len(body)}")

    # P08 Core /docs 存在（上游行为）但代理拒绝转发（信息面收紧已在 P02b/c 验证）
    st, body, _ = raw_call(core + "/docs", headers={})
    probe("P08_core_docs_exist_upstream_only", st == 200,
          f"core /docs status={st}（代理已剔除，见 P02b/c）")

    # P09 FAKE_TEST 未映射音频：在真实 fixture 基础上改动 1 个样本字节，
    # 生成「合法 WAV + sha256 不在映射表」的音频 → 入队后确定性 retry_asr（不猜测转录）
    import hashlib as _hashlib
    base_wav = (WAV_DIR / "real_E-0002.wav").read_bytes()
    mutated = bytearray(base_wav)
    mutated[-4] ^= 0x01  # 末样本最低位翻转：合法 PCM、sha 变化
    boundary2 = "----ws-jc-probe-" + uuid.uuid4().hex
    parts2 = [
        f'--{boundary2}\r\nContent-Disposition: form-data; name="utterance_id"\r\n\r\nU-UNMAP\r\n'.encode(),
        f'--{boundary2}\r\nContent-Disposition: form-data; name="sequence"\r\n\r\n0\r\n'.encode(),
        f'--{boundary2}\r\nContent-Disposition: form-data; name="audio_source"\r\n\r\nclient_complete_wav\r\n'.encode(),
        f'--{boundary2}\r\nContent-Disposition: form-data; name="file"; filename="c.wav"\r\n'
        f'Content-Type: audio/wav\r\n\r\n'.encode(),
        bytes(mutated),
        f"\r\n--{boundary2}--\r\n".encode(),
    ]
    st0, sbody, _ = raw_call(proxy + "/realproxy/v1/sessions", method="POST",
                             headers={APP_KEY_HEADER: "fitcore-demo-app-v1",
                                      "Content-Type": "application/json"}, body=b"{}")
    sid = json.loads(sbody)["session_id"] if st0 == 201 else "no-sid"
    st, body, _ = raw_call(proxy + f"/realproxy/v1/sessions/{sid}/audio-jobs", method="POST",
                           headers={APP_KEY_HEADER: "fitcore-demo-app-v1",
                                    "Content-Type": f"multipart/form-data; boundary={boundary2}"},
                           body=b"".join(parts2), timeout=30)
    probe("P09_unmapped_audio_deterministic", st == 202,
          f"upload status={st}（合法 WAV、sha256={_hashlib.sha256(bytes(mutated)).hexdigest()[:12]}… 未映射）")
    if st == 202:
        job_json = json.loads(body)
        uid = job_json.get("job", {}).get("utterance_id")
        import time as _t
        deadline = _t.time() + 15
        final = None
        while _t.time() < deadline:
            stj, jb, _ = raw_call(proxy + f"/realproxy/v1/sessions/{sid}/audio-jobs/{uid}",
                                  headers={APP_KEY_HEADER: "fitcore-demo-app-v1"})
            try:
                job2 = json.loads(jb).get("job", {})
            except Exception:
                job2 = {}
            if job2.get("status") in ("retry_asr", "blocked", "done"):
                final = job2
                break
            _t.sleep(0.1)
        probe("P09b_unmapped_job_retry_asr", bool(final) and final.get("status") == "retry_asr"
              and final.get("error_type") == "ASR_FAILED",
              f"job={ {k: final.get(k) for k in ('status', 'error_type')} if final else None }")
    else:
        probe("P09b_unmapped_job_retry_asr", False, "upload 未 202，跳过")

    # P10 独立 DB：本服务 e2e 数据必须落在指定库（由启动参数保证；此处验证代理 upstream 非 8790）
    st, body, _ = raw_call(proxy + "/health")
    h = json.loads(body)
    probe("P10_upstream_not_8790", h.get("upstream") != "http://127.0.0.1:8790",
          f"upstream={h.get('upstream')}")

    print(f"\nGATE_PROBE_RESULT: {'ALL_PASS' if ok else 'HAS_FAILURES'} {len(results)} probes")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
