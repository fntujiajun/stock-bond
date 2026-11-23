# -*- coding: utf-8 -*-
"""本地复刻 Worker 的数据链路，验证两个公开接口是否可用，并算出验收数字。"""
import json, math, urllib.request, urllib.error, datetime, sys

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
CSI = "https://www.csindex.com.cn/csindex-home/perf/index-perf"
CB = ("https://yield.chinabond.com.cn/cbweb-mn/indices/singleIndexQuery"
      "?indexid=8a8b2ca0332abed20134ea76d8885831&qxlxt=00&ltcslx=&zslxt=CFZS&lx=1&locale=")


def call(url, method="GET", data=None, extra=None, timeout=60):
    h = {"User-Agent": UA}
    if extra:
        h.update(extra)
    req = urllib.request.Request(url, method=method, data=data, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception as e:
        return None, str(e).encode()


def stock():
    u = f"{CSI}?indexCode=H00300&startDate=20041231&endDate=20261231"
    st, body = call(u, extra={"Referer": "https://www.csindex.com.cn/",
                              "Accept": "application/json"})
    print(f"[csindex] http={st} bytes={len(body)}")
    if st != 200:
        print("  body:", body[:300])
        return {}
    j = json.loads(body)
    arr = j.get("data") or []
    print(f"[csindex] rows={len(arr)} first={arr[0]['tradeDate']} last={arr[-1]['tradeDate']}")
    return {x["tradeDate"]: x["close"] for x in arr}


def bond():
    variants = [
        ("POST/no-body", "POST", None, {"Content-Type": "application/x-www-form-urlencoded"}),
        ("POST/form-body", "POST",
         b"indexid=8a8b2ca0332abed20134ea76d8885831&qxlxt=00&ltcslx=&zslxt=CFZS&lx=1&locale=",
         {"Content-Type": "application/x-www-form-urlencoded"}),
        ("GET", "GET", None, None),
    ]
    for name, m, d, h in variants:
        st, body = call(CB, method=m, data=d, extra=h)
        head = body[:120].decode("utf-8", "replace").replace("\n", " ")
        print(f"[chinabond] {name} http={st} bytes={len(body)} head={head!r}")
        if st == 200:
            try:
                j = json.loads(body)
            except Exception as e:
                print("   not-json:", e)
                continue
            keys = list(j.keys())[:6] if isinstance(j, dict) else "list"
            print("   keys:", keys)
            obj = j.get("CFZS_00") if isinstance(j, dict) else None
            if isinstance(obj, dict):
                ks = sorted(obj.keys(), key=lambda x: int(x))
                print(f"   CFZS_00 points={len(obj)} first={ks[0]} last={ks[-1]}")
                return obj
    return {}


def ymd(ts_ms):
    d = datetime.datetime.utcfromtimestamp((ts_ms + 8 * 3600 * 1000) / 1000)
    return d.strftime("%Y%m%d")


def compute(s, b):
    dates = sorted(k for k in s if k in b and s[k] is not None and b[k] is not None)
    print(f"[merge] common dates={len(dates)} {dates[0]}..{dates[-1]}")
    R = [s[k] / b[k] for k in dates]
    W, n = 500, len(R)
    z = mean = sd = None
    ssum = qsum = 0.0
    for i in range(n):
        ssum += R[i]; qsum += R[i] * R[i]
        if i >= W:
            ssum -= R[i - W]; qsum -= R[i - W] * R[i - W]
        if i >= W - 1:
            mu = ssum / W
            v = max(qsum / W - mu * mu, 1e-12)
            sdv = math.sqrt(v)
            z = (R[i] - mu) / sdv
            mean, sd = mu, sdv
    r = R[-1]
    tb, ts = mean - 1.5 * sd, mean + 1.0 * sd
    cnt = sum(1 for k in range(n - W, n) if R[k] <= r)
    pct = cnt / min(W, n)
    print("\n==== 当前读数 ====")
    print(f"日期      {dates[-1]}")
    print(f"比价      {r:.6f}   (股 {s[dates[-1]]} / 债 {b[dates[-1]]})")
    print(f"均值/标准差 {mean:.6f} / {sd:.6f}")
    print(f"z 值      {z:+.2f}")
    print(f"距买入线   {(tb / r - 1) * 100:+.1f}%")
    print(f"距卖出线   {(ts / r - 1) * 100:+.1f}%")
    print(f"历史分位   {pct * 100:.0f}%")
    lo, hi = -2.5, 3.0
    print(f"仪表盘位置 {(z - lo) / (hi - lo) * 100:.0f}%")
    return z


if __name__ == "__main__":
    s = stock()
    b = bond()
    if s and b:
        bm = {ymd(int(k)): v for k, v in b.items()}
        compute(s, bm)
    else:
        print("\n!! 数据不全，无法计算：stock=%d bond=%d" % (len(s), len(b)))
