# -*- coding: utf-8 -*-
"""生成 M0 手机预览原型 v5：支持系统暗色模式（含画布配色）。

用法：
    python preview_gen.py            # 无条件重新抓取并生成
    python preview_gen.py --if-new   # 只有中证出现更新的交易日才生成
退出码：0=已更新  2=已是最新  3=探测失败
"""
import json, math, os, re, sys, datetime, urllib.request
from verify_worker import stock, bond, stock_sh, ymd

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.dirname(HERE)          # 仓库根目录
PATH = os.path.join(OUT, "index.html")
os.makedirs(OUT, exist_ok=True)

CSI = "https://www.csindex.com.cn/csindex-home/perf/index-perf"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")


def probe_latest():
    """轻量探测：只取最近 12 天，返回最新交易日 YYYYMMDD。"""
    today = datetime.date.today()
    start = (today - datetime.timedelta(days=12)).strftime("%Y%m%d")
    end = today.strftime("%Y%m%d")
    req = urllib.request.Request(
        f"{CSI}?indexCode=H00300&startDate={start}&endDate={end}",
        headers={"User-Agent": UA, "Referer": "https://www.csindex.com.cn/",
                 "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=25) as r:
        j = json.loads(r.read())
    ds = [x["tradeDate"] for x in (j.get("data") or [])]
    return max(ds) if ds else None


def stored_date():
    """读现有页面里烤进去的日期。"""
    try:
        with open(PATH, encoding="utf-8") as f:
            m = re.search(r'"updated":"(\d{4}-\d{2}-\d{2})"', f.read())
        return m.group(1) if m else None
    except FileNotFoundError:
        return None


if "--if-new" in sys.argv:
    cur = stored_date()
    try:
        new = probe_latest()
    except Exception as e:
        print("probe-failed:", e)
        sys.exit(3)
    if not new:
        print("probe-failed: no trade date")
        sys.exit(3)
    if cur and new <= cur.replace("-", ""):
        print(f"already-current page={cur} latest={new}")
        sys.exit(2)
    print(f"new-data {new} (page had {cur})")

s, b, sh = stock(), bond(), stock_sh()
if not s or not b:
    sys.exit("数据抓取失败")
bm = {ymd(int(k)): v for k, v in b.items()}
dates = sorted(k for k in s if k in bm and s[k] is not None and bm[k] is not None)

# 上证指数按日期对齐，缺失的用前一个交易日收盘价填充
sh_map, last_sh = {}, None
for k in sorted(sh):
    if sh[k] is not None:
        last_sh = sh[k]
        sh_map[k] = last_sh
sh_aligned = []
_prev = None
for k in dates:
    if k in sh_map:
        _prev = sh_map[k]
    sh_aligned.append(_prev)
_first = next((v for v in sh_aligned if v is not None), None)
if _first is not None:
    sh_aligned = [v if v is not None else _first for v in sh_aligned]
print(f"[上证] 对齐后 {len(sh_aligned)} 个点，缺失 {sum(1 for v in sh_aligned if v is None)} 个")
R = [s[k] / bm[k] for k in dates]
n, W = len(R), 500

z = [None] * n
mu = sd = 0.0
ssum = qsum = 0.0
for i in range(n):
    ssum += R[i]; qsum += R[i] * R[i]
    if i >= W:
        ssum -= R[i - W]; qsum -= R[i - W] * R[i - W]
    if i >= W - 1:
        mu = ssum / W
        sd = math.sqrt(max(qsum / W - mu * mu, 1e-12))
        z[i] = (R[i] - mu) / sd

r_last = R[-1]
to_buy = (mu - 1.5 * sd) / r_last - 1
to_sell = (mu + 1.0 * sd) / r_last - 1
pct = sum(1 for k in range(n - W, n) if R[k] <= r_last) / W

EPOCH = datetime.date(1970, 1, 1)
def dnum(ds):
    return (datetime.date(int(ds[:4]), int(ds[4:6]), int(ds[6:])) - EPOCH).days

start = next(i for i in range(n) if z[i] is not None)
idx = list(range(start, n))
d0 = dnum(dates[start])

BUILD = datetime.datetime.now().strftime("%m-%d %H:%M")

payload = {
    "updated": dates[-1][:4] + "-" + dates[-1][4:6] + "-" + dates[-1][6:],
    "from": dates[start][:4] + "-" + dates[start][4:6],
    "d0": d0,
    "d": [dnum(dates[i]) - d0 for i in idx],
    "z": [round(z[i], 3) for i in idx],
    "r": [round(R[i], 3) for i in idx],
    "s": [round(s[dates[i]], 1) for i in idx],
    "u": [round(sh_aligned[i], 1) if sh_aligned[i] is not None else 0 for i in idx],
    "now": {
        "z": round(z[-1], 2),
        "toBuy": round(to_buy * 100, 1),
        "toSell": round(to_sell * 100, 1),
        "pct": round(pct * 100),
        "mu": round(mu, 6),
        "sd": round(sd, 6),
    },
    "buys": [[i - start, round(z[i], 2)] for i in idx
             if z[i] is not None and z[i] <= -1.5 and (i == start or (z[i - 1] or 0) > -1.5)],
}

HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="color-scheme" content="light dark">
<meta name="theme-color" content="#f5f4f1" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#111113" media="(prefers-color-scheme: dark)">
<title>股债比价</title>
<style>
:root{
  color-scheme:light dark;
  --outer:#e9e7e2; --bg:#f5f4f1; --nav-bg:rgba(245,244,241,.94);
  --panel:#ffffff; --ink:#1c1c1e; --ink2:#2c2c2e; --muted:#6b6b70;
  --faint:#74747c; --fainter:#8a8a92; --hair:#f2f0eb;
  --chip:#f2f0eb; --chip-on:#1c1c1e; --chip-on-fg:#ffffff;
  --buy-fg:#17764a; --sell-fg:#a83a2d;
  --buy-bg:#e0f1e7; --sell-bg:#fbe3de; --mid-bg:#eceae4;
  --zone-buy:#cfe8da; --zone-mid:#eeece6; --zone-sell:#f6d9d3;
  --warn-bg:#fbf0ee; --warn-fg:#a83a2d;
  --shadow:0 1px 2px rgba(0,0,0,.045);
  --chart-ink:#2b2135; --chart-axis:#7c7c84; --chart-grid:#eae7e0;
  --band-buy:rgba(23,118,74,.10); --band-sell:rgba(199,72,48,.10);
  --chart-alt:#9bb8d6;
  --chart-alt2:#dfb28a;
  --tap-bg:rgba(255,255,255,.86);
}
@media (prefers-color-scheme: dark){
  :root{
    --outer:#0b0b0c; --bg:#111113; --nav-bg:rgba(17,17,19,.94);
    --panel:#1b1b1e; --ink:#f2f1f5; --ink2:#dcdbe2; --muted:#a8a7ae;
    --faint:#9a99a2; --fainter:#85848d; --hair:#2a2a2f;
    --chip:#26262b; --chip-on:#f2f1f5; --chip-on-fg:#111113;
    --buy-fg:#4ecf92; --sell-fg:#ff8a78;
    --buy-bg:rgba(78,207,146,.16); --sell-bg:rgba(255,138,120,.16); --mid-bg:#2a2a2f;
    --zone-buy:#1d3a2b; --zone-mid:#2a2a2f; --zone-sell:#3b2320;
    --warn-bg:rgba(255,138,120,.12); --warn-fg:#ff9a8a;
    --shadow:none;
    --chart-ink:#eae8f0; --chart-axis:#9a99a2; --chart-grid:#2e2e34;
    --band-buy:rgba(78,207,146,.13); --band-sell:rgba(255,120,98,.13);
    --chart-alt:#6f9bc4;
    --chart-alt2:#d09a6a;
    --tap-bg:rgba(27,27,30,.86);
  }
}
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
html,body{margin:0;padding:0}
body{background:var(--outer);color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Noto Sans CJK SC","Microsoft YaHei",sans-serif;-webkit-font-smoothing:antialiased}
.app{max-width:440px;margin:0 auto;min-height:100vh;min-height:100dvh;background:var(--bg);position:relative;box-shadow:0 0 0 1px rgba(128,128,128,.14),0 18px 50px rgba(0,0,0,.10)}
@media(max-width:460px){body{background:var(--bg)}.app{box-shadow:none}}
@media(min-width:760px){.app{max-width:640px}}
.nav{position:sticky;top:0;z-index:20;background:var(--nav-bg);backdrop-filter:saturate(180%) blur(12px);padding:calc(env(safe-area-inset-top) + 12px) 18px 10px;display:flex;align-items:center;justify-content:space-between;gap:10px;border-bottom:1px solid var(--hair)}
.nav h1{font-size:16px;font-weight:600;margin:0;letter-spacing:.3px;color:var(--ink)}
.nav .meta{font-size:10.5px;color:var(--faint);margin-top:2px;letter-spacing:.2px}
.badge{font-size:9.5px;color:var(--faint);background:var(--chip);border-radius:5px;padding:2px 5px;margin-left:5px;vertical-align:2px;font-weight:500}
.aboutbtn{flex:0 0 auto;border:0;background:var(--chip);color:var(--ink2);font-size:11px;padding:6px 11px;border-radius:9px;font-family:inherit;font-weight:500;cursor:pointer}
.scroll{padding:0 18px 26px}

.hero{text-align:center;padding:22px 0 6px}
.zbig{font-size:76px;font-weight:700;line-height:.95;letter-spacing:-3px;font-variant-numeric:tabular-nums;color:var(--ink)}
.zlab{color:var(--faint);font-size:11.5px;margin-top:9px;letter-spacing:.3px}
.status{display:inline-block;margin-top:12px;padding:7px 17px;border-radius:22px;font-size:13px;font-weight:600}
.s-buy{background:var(--buy-bg);color:var(--buy-fg)}
.s-sell{background:var(--sell-bg);color:var(--sell-fg)}
.s-mid{background:var(--mid-bg);color:var(--muted)}

.gauge{margin:24px 0 2px}
.bar{position:relative;height:26px;border-radius:13px;overflow:hidden;display:flex;box-shadow:inset 0 0 0 1px rgba(128,128,128,.18)}
.zone.buy{background:var(--zone-buy);flex:0 0 18.18%}
.zone.mid{background:var(--zone-mid);flex:0 0 45.46%}
.zone.sell{background:var(--zone-sell);flex:0 0 36.36%}
.ptr{position:absolute;top:-6px;width:3px;height:38px;background:var(--ink);border-radius:2px;box-shadow:0 0 0 3px var(--bg);transition:left .8s cubic-bezier(.2,.8,.2,1)}
.ptr:after{content:"";position:absolute;top:-8px;left:-4px;width:11px;height:11px;background:var(--ink);border-radius:50%}
.ticks{position:relative;height:16px;margin-top:9px;font-size:10.5px}
.ticks span{position:absolute;transform:translateX(-50%)}

.cards{display:grid;grid-template-columns:repeat(3,1fr);gap:9px;margin:20px 0 0}
.card{background:var(--panel);border-radius:14px;padding:12px 6px 11px;text-align:center;box-shadow:var(--shadow)}
.card .k{font-size:10.5px;color:var(--faint);letter-spacing:.2px}
.card .v{font-size:19px;font-weight:650;margin-top:5px;font-variant-numeric:tabular-nums;letter-spacing:-.3px;color:var(--ink)}
.card .s{font-size:9.5px;color:var(--fainter);margin-top:4px}

.panel{background:var(--panel);border-radius:16px;padding:14px 14px 12px;margin-top:13px;box-shadow:var(--shadow)}
.panel h2{font-size:12.5px;font-weight:600;margin:0 0 10px;color:var(--ink2);letter-spacing:.2px;display:flex;align-items:baseline;gap:6px}
.panel h2 em{font-style:normal;font-weight:400;color:var(--fainter);font-size:10.5px}
.panel h2 #rchg{margin-left:auto;font-size:12px;font-weight:650;letter-spacing:0}
canvas{display:block;width:100%}
#cvz{touch-action:none;cursor:crosshair}
.cvwrap{position:relative}
.tap{position:absolute;left:50%;top:46%;transform:translate(-50%,-50%);white-space:nowrap;font-size:10.5px;color:var(--faint);background:var(--tap-bg);padding:5px 11px;border-radius:9px;pointer-events:none;opacity:1;transition:opacity .45s;box-shadow:0 1px 3px rgba(0,0,0,.07)}
.tap.hide{opacity:0}
.ranges{display:flex;gap:4px;margin:0 0 10px}
.ranges button{flex:1 1 0;min-width:0;border:0;background:var(--chip);color:var(--muted);font-size:10.5px;padding:5px 0;border-radius:8px;font-family:inherit;font-weight:500;cursor:pointer;line-height:1.5}
.ranges button.on{background:var(--chip-on);color:var(--chip-on-fg)}
.ranges2{display:none;margin-top:6px}
.ranges2.open{display:flex}
#morebtn{color:var(--muted)}
.cinfo{font-size:12.5px;color:var(--muted);height:19px;margin:0 0 8px;white-space:nowrap;overflow:hidden;font-variant-numeric:tabular-nums}
.cinfo b{color:var(--ink);font-weight:650}
.lg{display:flex;gap:8px;justify-content:center;margin-top:10px;flex-wrap:wrap}
.lgbtn{display:inline-flex;align-items:center;gap:6px;border:1px solid transparent;background:var(--chip);
  color:var(--ink2);font-size:11.5px;font-weight:500;padding:6px 11px;border-radius:9px;font-family:inherit;
  cursor:pointer;line-height:1.2;transition:background .18s,border-color .18s,color .18s}
.lgbtn i{width:14px;height:3px;border-radius:2px;display:inline-block;flex:0 0 auto}
.lgbtn .ls{background:var(--chart-alt)}
.lgbtn .lu{background:var(--chart-alt2)}
.lgbtn .yes,.lgbtn .no{font-size:11px;font-weight:700;line-height:1;margin-left:1px}
.lgbtn .yes{color:var(--buy-fg)}
.lgbtn .no{display:none;color:var(--fainter)}
.lgbtn:not(.on){background:transparent;border:1px dashed var(--fainter);color:var(--fainter)}
.lgbtn:not(.on) i{opacity:.35}
.lgbtn:not(.on) .yes{display:none}
.lgbtn:not(.on) .no{display:inline}
.lghint{text-align:center;font-size:10px;color:var(--fainter);margin-top:6px}

.fold{padding:0}
.foldhead{display:flex;align-items:center;justify-content:space-between;padding:14px;cursor:pointer}
.foldhead h2{margin:0}
.chev{color:var(--fainter);font-size:15px;line-height:1;transition:transform .25s}
.fold.open .chev{transform:rotate(90deg)}
.foldbody{display:none;padding:0 14px 12px}
.fold.open .foldbody{display:block}
.fold{scroll-margin-top:70px}

table{width:100%;border-collapse:collapse;font-size:13px}
th{text-align:left;color:var(--faint);font-weight:500;font-size:10.5px;padding:0 0 7px;letter-spacing:.2px}
td{padding:9px 0;border-top:1px solid var(--hair);font-variant-numeric:tabular-nums;color:var(--ink2)}
td:last-child,th:last-child{text-align:right}
.hl{color:var(--buy-fg);font-weight:600}
.dim{color:var(--faint)}
.list{margin:0;padding:0;list-style:none}
.list li{display:flex;align-items:center;justify-content:space-between;padding:10px 0;border-top:1px solid var(--hair);font-size:13px;color:var(--ink2)}
.list li:first-child{border-top:none;padding-top:0}
.dot{width:6px;height:6px;border-radius:50%;background:var(--buy-fg);display:inline-block;margin-right:7px;vertical-align:1px}
.prose{font-size:12.5px;line-height:1.8;color:var(--muted)}
.prose b{font-weight:600;color:var(--ink2)}
.prose code{background:var(--chip);border-radius:4px;padding:1px 5px;font-size:11.5px;font-family:ui-monospace,Menlo,Consolas,monospace;color:var(--ink2)}
.prose p{margin:0 0 9px}
.prose h3{font-size:10.5px;color:var(--faint);font-weight:600;letter-spacing:1.5px;margin:18px 0 9px;padding-top:13px;border-top:1px solid var(--hair)}
.prose h3:first-child{margin-top:0;padding-top:0;border-top:0}
ol.prin{margin:0;padding-left:18px;font-size:12.5px;line-height:1.8;color:var(--muted)}
ol.prin li{margin-bottom:11px;padding-left:2px}
ol.prin li:last-child{margin-bottom:0}
ol.prin b{color:var(--ink2);font-weight:600}
.warn{background:var(--warn-bg);color:var(--warn-fg);border-radius:10px;padding:9px 11px;font-size:11.5px;line-height:1.7}
.foot{text-align:center;color:var(--fainter);font-size:10.5px;padding:20px 0 0;line-height:1.8}
</style>
</head>
<body>
<div class="app">
<!-- build __BUILD__ -->
  <div class="nav">
    <div>
      <h1>股债比价</h1>
      <div class="meta" id="asof"></div>
    </div>
    <button class="aboutbtn" id="aboutbtn">说明</button>
  </div>

  <div class="scroll">
    <div class="hero">
      <div class="zbig" id="zval">—</div>
      <div class="zlab">z 值 · 500 日滚动窗口</div>
      <div><span class="status s-mid" id="status">—</span></div>
    </div>

    <div class="gauge">
      <div class="bar">
        <div class="zone buy"></div><div class="zone mid"></div><div class="zone sell"></div>
        <div class="ptr" id="ptr" style="left:50%"></div>
      </div>
      <div class="ticks">
        <span style="left:18.18%;color:var(--buy-fg)">−1.5 买</span>
        <span style="left:63.64%;color:var(--sell-fg)">+1.0 卖</span>
      </div>
    </div>

    <div class="cards">
      <div class="card"><div class="k">距买入线</div><div class="v" id="tobuy">—</div><div class="s" id="tobuys">—</div></div>
      <div class="card"><div class="k">距卖出线</div><div class="v" id="tosell">—</div><div class="s" id="tosells">—</div></div>
      <div class="card"><div class="k">历史分位</div><div class="v" id="pct">—</div><div class="s">近 500 日</div></div>
    </div>

    <div class="panel">
      <h2>z 值走势<em id="vrangelab">1年</em><em id="rchg"></em></h2>
      <div class="ranges" id="ranges">
        <button data-k="250" class="on">1年</button>
        <button data-k="500">2年</button>
        <button data-k="750">3年</button>
        <button data-k="1250">5年</button>
        <button data-k="2430">10年</button>
        <button id="morebtn">更多</button>
      </div>
      <div class="ranges ranges2" id="ranges2">
        <button data-k="21">1月</button>
        <button data-k="63">3月</button>
        <button data-k="126">6月</button>
        <button data-k="3650">15年</button>
        <button data-k="0">全部</button>
      </div>
      <div class="cinfo" id="cinfo">—</div>
      <div class="cvwrap">
        <canvas id="cvz" data-h="290"></canvas>
        <div class="tap" id="taphint">← 左右看日期　上下看数值 →</div>
      </div>
      <div class="lg" id="lg">
        <button class="lgbtn on" data-k="s" title="点击显示或隐藏"><i class="ls"></i>沪深300<b class="yes">✓</b><b class="no">+</b></button>
        <button class="lgbtn" data-k="u" title="点击显示或隐藏"><i class="lu"></i>上证指数<b class="yes">✓</b><b class="no">+</b></button>
      </div>
    </div>

    <div class="panel">
      <h2>触发之后怎么投</h2>
      <table>
        <tr><th>条件</th><th>投入</th><th>累计</th></tr>
        <tr><td>z 跌破 −1.5 当天</td><td>60%</td><td class="hl">60%</td></tr>
        <tr><td>相对触发日再跌 3%</td><td>13%</td><td class="hl">73%</td></tr>
        <tr><td>再跌 6%</td><td>13%</td><td class="hl">86%</td></tr>
        <tr><td>再跌 9%</td><td>13%</td><td class="hl">99%</td></tr>
        <tr><td>第 60 个交易日兜底</td><td>剩余</td><td class="hl">100%</td></tr>
      </table>
    </div>

    <div class="panel fold" id="foldBuy">
      <div class="foldhead"><h2>跌破 −1.5 的时点<em>最近 8 次</em></h2><span class="chev">›</span></div>
      <div class="foldbody"><ul class="list" id="buylist"></ul></div>
    </div>

    <div class="panel fold" id="foldAbout">
      <div class="foldhead"><h2>原理与口径<em>为什么是这个数</em></h2><span class="chev">›</span></div>
      <div class="foldbody">
        <div class="prose">
          <h3>原理</h3>
          <ol class="prin">
            <li><b>不预测涨跌，只测量贵贱</b>，赌均值回归。股票和债券是同一批钱的两个去处，钱在两者之间流动。恐慌时钱涌向债券 → 股票被抛售、债券被抢购 → 比价被压到极端。这个比值量的不是「股票跌了多少」，而是「市场对股票的厌恶到了什么程度」。</li>
            <li><b>指标</b>：比价 = 沪深300全收益（H00300）÷ 中债-新综合财富指数；z =（今日比价 − 过去 500 日均值）÷ 过去 500 日标准差。z = −1.5 大致意味着比过去两年 88% 的日子都便宜。</li>
            <li><b>为什么有效</b>：价格低本身就等于未来收益率高（恒等式，不是观点）。收益来自两块：① 估值回归；② 避开大跌——跌 50% 要涨 100% 才回本，少亏一次等于多赚很多次。</li>
            <li><b>为什么技术指标不行</b>：它们只用价格算价格，信息没有增加。本指标引入了第二个资产（债券），问的是「贵不贵」，不是「接下来涨不涨」。前者可测，后者不可知。</li>
            <li><b>死穴</b>：均值回归假设可能失效。利率趋势性下行会让股债比价中枢整体上移，「回到均值」可能回到一个已经不存在的过去。这是所有均值回归策略的共同风险。</li>
            <li><b>定位</b>：它不是预测机器，是把「低买高卖」从感觉换成刻度，并在你最想乱来的时候给你一个不许乱来的数字。</li>
          </ol>

          <h3>口径</h3>
          <p>跌破 <b>−1.5</b> 记买入区，涨过 <b>+1.0</b> 记卖出区，中间不动。z 只说明贵贱，不含预测。</p>
          <p>2007 年以来 4816 个交易日里，z 低于 −1.5 的占 <b>11.7%</b>，高于 +1.0 的占 <b>23.3%</b>。</p>
          <p>图上纵轴按当前区间自动缩放，不同区间的高低不能直接横比——看刻度值。</p>

          <h3>更新</h3>
          <p>正式版每次打开自动拉取，服务端缓存 10 分钟。中债指数收盘后发布，盘中看到的是上一交易日数值。</p>

          <h3>数据</h3>
          <p class="dim">中证指数官网 · 中国债券信息网。本页面为静态快照，覆盖 <span id="snapfrom"></span> 至今，截至 <span id="snap2"></span>。</p>
        </div>
        <div class="warn">仅为个人研究记录，不构成投资建议。历史规律不保证未来重现，据此操作风险自负。</div>
      </div>
    </div>

    <div class="foot">数据每日收盘后更新 · 仅供个人记录<br><span id="histfoot"></span></div>
  </div>
</div>

<script>
var D = __DATA__;
var N = D.z.length;
var PAD = {l:5, r:52, t:14, b:30};
var V = {a:0, b:1};
var hover = null, hoverY = null, drag = null, pinch = null, sxy = null, lastTap = null;
var showS = true, showU = false;

function pad2(v){ return v<10 ? '0'+v : ''+v; }
function dOf(i){ return new Date((D.d0 + D.d[i]) * 86400000); }
function ymdOf(i){ var d=dOf(i); return d.getUTCFullYear()+'-'+pad2(d.getUTCMonth()+1)+'-'+pad2(d.getUTCDate()); }
function mdOf(i){ var d=dOf(i); return (d.getUTCMonth()+1)+'/'+d.getUTCDate(); }
function ymOf(i){ var d=dOf(i); return (d.getUTCFullYear()%100)+'/'+pad2(d.getUTCMonth()+1); }
function fmtPct(v){ return (v>0?'+':'−') + Math.abs(v).toFixed(1) + '%'; }

/* 当日涨跌幅：比价相对前一交易日 */
function dayChg(i){
  if(i <= 0 || D.r[i-1] == null) return 0;
  return D.r[i] / D.r[i-1] - 1;
}
/* 手动缩放后，把高亮贴回最接近的那个档位（纯视觉，不动数据） */
var PRESETS = [];
var curPreset = 250;
function syncPreset(){
  if(!PRESETS.length) return;
  var span = V.b - V.a;
  var best = PRESETS[0], bestD = Infinity;
  for(var i=0;i<PRESETS.length;i++){
    var p = PRESETS[i];
    var ps = (p.k === 0) ? (N - 1) : p.k;
    var dd = Math.abs(Math.log((span + 1) / (ps + 1)));
    if(dd < bestD){ bestD = dd; best = p; }
  }
  if(curPreset === best.k) return;   /* 没跨档就不动 DOM，避免抖动 */
  curPreset = best.k;
  PRESETS.forEach(function(p){ p.btn.classList.toggle('on', p === best); });
  var el = document.getElementById('vrangelab');
  if(el) el.textContent = best.text;
  /* 命中的档位藏在「更多」里就自动展开，免得一个高亮的都没有 */
  if(best.btn && best.btn.parentNode && best.btn.parentNode.id === 'ranges2'){
    var r2 = document.getElementById('ranges2');
    var mb = document.getElementById('morebtn');
    if(r2 && !r2.classList.contains('open')){
      r2.classList.add('open');
      if(mb) mb.textContent = '收起';
    }
  }
}

/* 区间涨跌幅，写到标题右侧 */
function setRangeChg(v){
  var el = document.getElementById('rchg');
  if(!el) return;
  var s = (v>=0?'+':'−') + Math.abs(v*100).toFixed(1) + '%';
  if(el._last === s) return;
  el._last = s;
  el.textContent = s;
  el.style.color = v>=0 ? 'var(--sell-fg)' : 'var(--buy-fg)';
}

/* 画布配色从 CSS 变量取，暗色模式自动跟着变 */
var T = null;
function cssVar(name, fb){
  try{
    if(typeof getComputedStyle !== 'function' || !document.documentElement) return fb;
    var v = getComputedStyle(document.documentElement).getPropertyValue(name);
    return (v || '').trim() || fb;
  }catch(e){ return fb; }
}
function theme(){
  if(T) return T;
  T = {
    ink:    cssVar('--chart-ink', '#2b2135'),
    axis:   cssVar('--chart-axis', '#8f8f96'),
    grid:   cssVar('--chart-grid', '#eae7e0'),
    alt:    cssVar('--chart-alt', '#9bb8d6'),
    alt2:   cssVar('--chart-alt2', '#dfb28a'),
    buy:    cssVar('--band-buy', 'rgba(23,118,74,.10)'),
    sell:   cssVar('--band-sell', 'rgba(199,72,48,.10)'),
    buyFg:  cssVar('--buy-fg', '#17764a'),
    sellFg: cssVar('--sell-fg', '#a83a2d'),
    panel:  cssVar('--panel', '#ffffff')
  };
  return T;
}

/* 宽度用 getBoundingClientRect：缩放/DPR 变化时才是真实显示尺寸，不会画糊 */
function cssW(cv){
  var w = 0;
  try{ w = cv.getBoundingClientRect().width; }catch(e){}
  if(!w) w = cv.clientWidth || 0;
  if(!w && cv.parentNode) w = cv.parentNode.clientWidth - 28;
  return w;
}

/* 高度只认 data-h，绝不回读 canvas.height */
function canvasOf(cv){
  var dpr = window.devicePixelRatio || 1;
  var w = cssW(cv);
  var h = parseInt(cv.getAttribute('data-h') || '290', 10);
  if(w > 520) h = Math.round(h * 1.2);
  if(!(w > 40) || !(h > 40)) return null;
  cv.style.height = h + 'px';
  if(cv.width !== Math.round(w*dpr)) cv.width = Math.round(w*dpr);
  if(cv.height !== Math.round(h*dpr)) cv.height = Math.round(h*dpr);
  var ctx = cv.getContext('2d');
  ctx.setTransform(dpr,0,0,dpr,0,0);
  ctx.clearRect(0,0,w,h);
  return {ctx:ctx, w:w, h:h};
}
function curW(){
  var cv = document.getElementById('cvz');
  return cv ? cssW(cv) : 0;
}
function clampView(){
  var span = V.b - V.a;
  if(span >= N-1){ V.a = 0; V.b = N-1; return; }
  if(V.a < 0){ V.b -= V.a; V.a = 0; }
  if(V.b > N-1){ V.a -= (V.b - (N-1)); V.b = N-1; }
  if(V.a < 0) V.a = 0;
}
function idxAt(x, w){
  var pw = (w||curW()) - PAD.l - PAD.r;
  if(pw <= 0) return 0;
  var f = Math.max(0, Math.min(1, (x - PAD.l) / pw));
  return Math.max(0, Math.min(N-1, Math.round(V.a + f*(V.b-V.a))));
}
function anchorIdx(){
  if(hover != null && hover >= V.a && hover <= V.b) return hover;
  return Math.round(Math.min(N-1, Math.floor(V.b)));
}

function drawZ(){
  var cv = document.getElementById('cvz'); if(!cv) return;
  var o = canvasOf(cv); if(!o) return;
  var ctx=o.ctx, w=o.w, h=o.h, C=theme();
  if(N < 2) return;
  var pl=PAD.l, pt=PAD.t, pr=w-PAD.r, pb=h-PAD.b;
  var pw=pr-pl, ph=pb-pt;
  if(pw<=10 || ph<=10) return;

  /* 缩放/平移后十字线若已跑出视野，就清掉，免得顶部日期和图对不上 */
  if(hover != null && (hover < V.a - 0.5 || hover > V.b + 0.5)){ hover = null; hoverY = null; }

  var i0 = Math.max(0, Math.floor(V.a)), i1 = Math.min(N-1, Math.ceil(V.b));
  var lo=Infinity, hi=-Infinity;
  for(var i=i0;i<=i1;i++){ var v=D.z[i]; if(v<lo) lo=v; if(v>hi) hi=v; }
  if(!isFinite(lo)){ lo=-1.5; hi=1.0; }

  var padY = Math.max((hi-lo)*0.15, 0.10);
  var ymin = lo - padY, ymax = hi + padY;
  if(ymax - ymin < 0.45){ var mid=(ymax+ymin)/2; ymin=mid-0.225; ymax=mid+0.225; }

  function X(i){ return pl + (i - V.a)/(V.b - V.a)*pw; }
  function Y(v){ return pt + (ymax - v)/(ymax - ymin)*ph; }

  var sellIn = (1.0 > ymin && 1.0 < ymax);
  var buyIn  = (-1.5 > ymin && -1.5 < ymax);

  ctx.save();
  ctx.beginPath(); ctx.rect(pl,pt,pw,ph); ctx.clip();

  var ySell = Y(1.0), yBuy = Y(-1.5);
  if(sellIn){ ctx.fillStyle=C.sell; ctx.fillRect(pl, pt, pw, ySell-pt); }
  if(buyIn){ ctx.fillStyle=C.buy; ctx.fillRect(pl, yBuy, pw, pb-yBuy); }

  if(0 > ymin && 0 < ymax){
    ctx.strokeStyle=C.grid; ctx.lineWidth=1;
    var y0 = Math.round(Y(0)) + 0.5;
    ctx.beginPath(); ctx.moveTo(pl,y0); ctx.lineTo(pr,y0); ctx.stroke();
  }

  /* 叠加线：沪深300 / 上证指数，共用一根缩放刻度，只看形状 */
  var oLo=Infinity, oHi=-Infinity;
  for(var oi=i0;oi<=i1;oi++){
    var a1=D.s[oi], a2=D.u[oi];
    if(a1>0){ if(a1<oLo)oLo=a1; if(a1>oHi)oHi=a1; }
    if(a2>0){ if(a2<oLo)oLo=a2; if(a2>oHi)oHi=a2; }
  }
  if(oHi > oLo){
    var insO = ph * 0.06, spanO = oHi - oLo, ppdO = (i1 - i0) / pw;
    var drawOverlay = function(arr, color){
      ctx.strokeStyle=color; ctx.lineWidth=1.4; ctx.globalAlpha=0.95;
      ctx.lineJoin='round'; ctx.lineCap='round';
      ctx.beginPath();
      if(ppdO > 1.8){
        var colsO = Math.ceil(pw), startedO = false;
        for(var cO=0;cO<colsO;cO++){
          var iaO = i0 + Math.floor(cO/colsO*(i1-i0));
          var ibO = i0 + Math.floor((cO+1)/colsO*(i1-i0));
          if(ibO <= iaO) ibO = iaO+1;
          var lastO = 0;
          for(var qO=iaO;qO<ibO && qO<=i1;qO++){ if(arr[qO] > 0) lastO = arr[qO]; }
          if(!lastO) continue;
          var xO = pl + cO + 0.5;
          var yO = pt + insO + (oHi - lastO)/spanO*(ph - insO*2);
          if(!startedO){ ctx.moveTo(xO,yO); startedO = true; } else ctx.lineTo(xO,yO);
        }
      } else {
        var stO = false;
        for(var sO=i0;sO<=i1;sO++){
          var vO = arr[sO];
          if(!(vO > 0)) continue;
          var xO2 = X(sO);
          var yO2 = pt + insO + (oHi - vO)/spanO*(ph - insO*2);
          if(!stO){ ctx.moveTo(xO2,yO2); stO = true; } else ctx.lineTo(xO2,yO2);
        }
      }
      ctx.stroke();
      ctx.globalAlpha = 1;
    };
    if(showU) drawOverlay(D.u, C.alt2);
    if(showS) drawOverlay(D.s, C.alt);
  }

  var ppd = (i1 - i0) / pw;
  if(ppd > 1.8){
    var cols = Math.ceil(pw);
    var bmn = [], bmx = [], bls = [];
    for(var c=0;c<cols;c++){
      var ia = i0 + Math.floor(c/cols*(i1-i0));
      var ib = i0 + Math.floor((c+1)/cols*(i1-i0));
      if(ib <= ia) ib = ia+1;
      var mn=Infinity, mx=-Infinity, ls=null;
      for(var q=ia;q<ib && q<=i1;q++){ var vq=D.z[q]; if(vq<mn) mn=vq; if(vq>mx) mx=vq; ls=vq; }
      bmn.push(isFinite(mn)?mn:null); bmx.push(isFinite(mx)?mx:null); bls.push(ls);
    }
    /* 第一层：淡包络，表示这一段的高低范围 */
    ctx.beginPath();
    for(var c2=0;c2<cols;c2++){
      if(bmn[c2] === null) continue;
      var xc = pl + c2 + 0.5;
      ctx.moveTo(xc, Y(bmx[c2])); ctx.lineTo(xc, Y(bmn[c2]));
    }
    ctx.strokeStyle=C.ink; ctx.globalAlpha=0.18; ctx.lineWidth=1; ctx.stroke();
    /* 第二层：实线，每像素取该段最后一个值，形状一眼能看出来 */
    ctx.beginPath();
    var st2=false;
    for(var c3=0;c3<cols;c3++){
      if(bls[c3] === null) continue;
      var xc2 = pl + c3 + 0.5, yc2 = Y(bls[c3]);
      if(!st2){ ctx.moveTo(xc2,yc2); st2=true; } else ctx.lineTo(xc2,yc2);
    }
    ctx.globalAlpha = 1;
    ctx.strokeStyle=C.ink; ctx.lineWidth=1.7; ctx.lineJoin='round'; ctx.lineCap='round'; ctx.stroke();
  } else {
    ctx.beginPath();
    var started=false;
    for(var k=i0;k<=i1;k++){
      var x2=X(k), y2=Y(D.z[k]);
      if(!started){ ctx.moveTo(x2,y2); started=true; } else ctx.lineTo(x2,y2);
    }
    var lwMain = Math.max(1.6, Math.min(2.4, 2.4 - Math.max(0, ppd - 0.5) * 1.2));
    ctx.strokeStyle=C.ink; ctx.lineWidth=lwMain; ctx.lineJoin='round'; ctx.lineCap='round'; ctx.stroke();
  }

  ctx.font='9.5px -apple-system,sans-serif';
  ctx.textAlign='left'; ctx.textBaseline='middle';
  ctx.globalAlpha=0.75;
  if(sellIn && ySell - pt > 20){ ctx.fillStyle=C.sellFg; ctx.fillText('卖出区', pl+6, pt+10); }
  if(buyIn && pb - yBuy > 20){ ctx.fillStyle=C.buyFg; ctx.fillText('买入区', pl+6, pb-10); }
  ctx.globalAlpha=1;
  ctx.restore();

  var marks = [];
  if(sellIn) marks.push({v:1.0, s:'+1.0', c:C.sellFg});
  if(0 > ymin && 0 < ymax) marks.push({v:0, s:'0', c:C.axis});
  if(buyIn) marks.push({v:-1.5, s:'−1.5', c:C.buyFg});

  ctx.font='10.5px -apple-system,sans-serif';
  ctx.textAlign='left'; ctx.textBaseline='middle';
  var lastY=-999;
  marks.forEach(function(m){
    var y=Y(m.v);
    if(Math.abs(y-lastY) < 15) return;
    lastY=y; ctx.fillStyle=m.c; ctx.fillText(m.s, pr+6, y);
  });

  /* 区间涨跌幅 + 锚点先算出来，横轴标签要用 */
  var ia = Math.max(0, Math.floor(V.a)), ib2 = Math.min(N-1, Math.floor(V.b));
  setRangeChg(ib2 > ia ? D.r[ib2] / D.r[ia] - 1 : 0);
  syncPreset();

  var anc = anchorIdx(), ax = X(anc), ay = Y(D.z[anc]);

  var span = V.b - V.a, ticks = 4;
  ctx.textAlign='center'; ctx.textBaseline='top';
  ctx.font='10.5px -apple-system,sans-serif';
  for(var t2=0;t2<ticks;t2++){
    var f2=(t2+0.5)/ticks;
    var idx=Math.round(V.a + f2*span);
    if(idx<0||idx>=N) continue;
    var xt=X(idx);
    if(xt<pl+10||xt>pr-10) continue;
    ctx.fillStyle=C.axis;
    ctx.fillText(span<=70 ? mdOf(idx) : (span<=1000 ? ymOf(idx) : String(dOf(idx).getUTCFullYear())), xt, pb+8);
  }

  /* 横轴：只放日期 */
  var xlab = ymdOf(anc);
  ctx.font='11px -apple-system,sans-serif';
  var lw2 = Math.min(pw, Math.max(74, ctx.measureText(xlab).width + 18));
  var lx2 = Math.max(pl + lw2/2, Math.min(pr - lw2/2, ax));
  ctx.fillStyle = C.ink;
  ctx.fillRect(lx2 - lw2/2, pb+3, lw2, 19);
  ctx.fillStyle = C.panel;
  ctx.textAlign='center'; ctx.textBaseline='middle';
  ctx.fillText(xlab, lx2, pb+12.5);

  /* 十字光标的 y；没触摸时贴着数据点 */
  var cy = (hover != null && hoverY != null)
         ? Math.max(pt+1, Math.min(pb-1, hoverY)) : ay;

  if(hover != null){
    ctx.setLineDash([3,3]); ctx.strokeStyle=C.axis; ctx.lineWidth=1;
    ctx.beginPath(); ctx.moveTo(ax, Math.round(pt)+0.5); ctx.lineTo(ax, Math.round(pb)+0.5); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(pl, Math.round(cy)+0.5); ctx.lineTo(pr, Math.round(cy)+0.5); ctx.stroke();
    ctx.setLineDash([]);
  }

  /* 右侧：沪深300 点位（上）+ 涨跌幅（下） */
  var pillW = 48, pillH = 17, px0 = pr + 4;
  var lvl, pch;
  if(hover != null){
    var zv = ymin + (pb - cy)/ph * (ymax - ymin);
    var ratioAt = D.now.mu + zv * D.now.sd;
    lvl = D.s[N-1] * (ratioAt / D.r[N-1]);   /* 这条线对应的沪深300点位 */
    pch = (lvl / D.s[N-1] - 1) * 100;
  } else {
    lvl = D.s[anc];
    pch = anc > 0 ? (D.s[anc] / D.s[anc-1] - 1) * 100 : 0;
  }
  var baseY = hover != null ? cy - 10 : ay - 10;
  baseY = Math.max(pt+9, Math.min(pb-29, baseY));

  ctx.font='10.5px -apple-system,sans-serif';
  ctx.textAlign='center'; ctx.textBaseline='middle';

  ctx.fillStyle = C.ink;
  ctx.fillRect(px0, baseY-8, pillW, pillH);
  ctx.fillStyle = C.panel;
  ctx.fillText(fmt300(lvl), px0 + pillW/2, baseY);

  ctx.fillStyle = pch >= 0 ? C.sellFg : C.buyFg;
  ctx.fillRect(px0, baseY+20-8, pillW, pillH);
  ctx.fillStyle = C.panel;
  ctx.fillText((pch>=0?'+':'−') + Math.abs(pch).toFixed(2) + '%', px0 + pillW/2, baseY+20);

  /* 数据点圆点 */
  ctx.beginPath(); ctx.arc(ax,ay,4.5,0,7); ctx.fillStyle=C.ink; ctx.fill();
  ctx.beginPath(); ctx.arc(ax,ay,1.9,0,7); ctx.fillStyle=C.panel; ctx.fill();

  setInfo(hover == null ? anc : hover);
}

function setInfo(i){
  var el = document.getElementById('cinfo');
  if(i==null || i<0 || i>=N) return;
  var html = ymdOf(i)
    + ' &nbsp;z <b>' + (D.z[i]>=0?'+':'') + D.z[i].toFixed(2) + '</b>'
    + ' &nbsp;比价 <b>' + D.r[i].toFixed(2) + '</b>';
  if(el._last === html) return;
  el._last = html;
  el.innerHTML = html;
}

/* 300 点位写法：5956 -> 5,956 */
function fmt300(v){
  var n = Math.round(v);
  var s = String(n), out = '';
  for(var i=0;i<s.length;i++){
    if(i>0 && (s.length-i)%3===0) out += ',';
    out += s.charAt(i);
  }
  return out;
}

function applyRange(k){
  if(!k || k >= N-1){ V.a = 0; V.b = N-1; }
  else { V.b = N-1; V.a = Math.max(0, N-1-k); }
  hover = null; hoverY = null; drawZ();
}
function zoomAt(x, factor, w){
  var i = idxAt(x, w);
  var span = V.b - V.a;
  var ns = Math.max(15, Math.min(N-1, span*factor));
  var r0 = Math.max(0, Math.min(1, (x - PAD.l) / ((w||curW()) - PAD.l - PAD.r)));
  V.a = i - r0*ns; V.b = V.a + ns;
  clampView(); drawZ();
}

function bindChart(){
  var cv = document.getElementById('cvz'); if(!cv) return;
  var tapEl = document.getElementById('taphint');
  function hideTap(){ if(tapEl) tapEl.classList.add('hide'); }

  cv.addEventListener('mousemove', function(e){
    var r = cv.getBoundingClientRect(), x = e.clientX - r.left;
    if(drag){
      var pw = r.width - PAD.l - PAD.r, span = drag.b - drag.a;
      var shift = -(x - drag.x) / pw * span;
      V.a = drag.a + shift; V.b = drag.b + shift;
      clampView();
    }
    hover = idxAt(x, r.width); hoverY = e.clientY - r.top; setInfo(hover); drawZ(); hideTap();
  });
  cv.addEventListener('mouseleave', function(){
    if(drag) return;
    hover = null; hoverY = null; drawZ();
  });
  cv.addEventListener('mousedown', function(e){
    var r = cv.getBoundingClientRect();
    drag = {x: e.clientX - r.left, a: V.a, b: V.b};
    e.preventDefault();
  });
  window.addEventListener('mouseup', function(){ drag = null; });
  cv.addEventListener('wheel', function(e){
    e.preventDefault();
    var r = cv.getBoundingClientRect();
    zoomAt(e.clientX - r.left, e.deltaY > 0 ? 1.18 : 0.85, r.width);
    hideTap();
  }, {passive:false});
  cv.addEventListener('dblclick', function(){ applyRange(curPreset); });

  cv.addEventListener('touchstart', function(e){
    var r = cv.getBoundingClientRect(); hideTap();
    if(e.touches.length === 1){
      pinch = null;
      sxy = {x: e.touches[0].clientX, y: e.touches[0].clientY};
      hover = idxAt(e.touches[0].clientX - r.left, r.width);
      hoverY = e.touches[0].clientY - r.top;
      setInfo(hover); drawZ();
    } else if(e.touches.length === 2){
      sxy = null;
      var dx = e.touches[0].clientX - e.touches[1].clientX;
      var dy = e.touches[0].clientY - e.touches[1].clientY;
      var cx = (e.touches[0].clientX + e.touches[1].clientX)/2 - r.left;
      pinch = {d: Math.sqrt(dx*dx+dy*dy) || 1, i: idxAt(cx, r.width), span: V.b - V.a, w: r.width};
    }
  }, {passive:false});

  cv.addEventListener('touchmove', function(e){
    var r = cv.getBoundingClientRect();
    if(e.touches.length === 2 && pinch){
      e.preventDefault();
      var dx = e.touches[0].clientX - e.touches[1].clientX;
      var dy = e.touches[0].clientY - e.touches[1].clientY;
      var d = Math.sqrt(dx*dx+dy*dy) || 1;
      var cx = (e.touches[0].clientX + e.touches[1].clientX)/2 - r.left;
      var ns = Math.max(15, Math.min(N-1, pinch.span * (pinch.d/d)));
      var f = Math.max(0, Math.min(1, (cx - PAD.l) / (r.width - PAD.l - PAD.r)));
      V.a = pinch.i - f*ns; V.b = V.a + ns;
      clampView(); drawZ();
    } else if(e.touches.length === 1 && !pinch){
      var t = e.touches[0];
      e.preventDefault();
      hover = idxAt(t.clientX - r.left, r.width);
      hoverY = t.clientY - r.top;
      setInfo(hover); drawZ();
    }
  }, {passive:false});

  cv.addEventListener('touchend', function(e){
    if(e.touches.length < 2) pinch = null;
    if(e.touches.length === 0 && e.changedTouches && e.changedTouches.length === 1){
      var t = e.changedTouches[0], now = Date.now();
      if(lastTap && now - lastTap.t < 320
         && Math.abs(t.clientX - lastTap.x) < 24 && Math.abs(t.clientY - lastTap.y) < 24){
        lastTap = null; applyRange(curPreset);
      } else {
        lastTap = {t: now, x: t.clientX, y: t.clientY};
      }
    }
    sxy = null;
  });

  var moreBtn = document.getElementById('morebtn');
  var row2 = document.getElementById('ranges2');
  if(moreBtn && row2){
    moreBtn.addEventListener('click', function(){
      var open = !row2.classList.contains('open');
      row2.classList.toggle('open', open);
      moreBtn.textContent = open ? '收起' : '更多';
    });
  }
  PRESETS = Array.prototype.map.call(
    document.querySelectorAll('.ranges button[data-k]'),
    function(b){ return { k: parseInt(b.getAttribute('data-k'), 10) || 0, btn: b, text: b.textContent }; }
  );
  PRESETS.forEach(function(p){ if(p.k === curPreset) p.btn.classList.add('on'); });

  document.querySelectorAll('.ranges button[data-k]').forEach(function(btn){
    btn.addEventListener('click', function(){
      document.querySelectorAll('.ranges button[data-k]').forEach(function(b){ b.classList.remove('on'); });
      btn.classList.add('on');
      var lab = document.getElementById('vrangelab');
      if(lab) lab.textContent = btn.textContent;
      curPreset = parseInt(btn.getAttribute('data-k'), 10) || 0;

      applyRange(parseInt(btn.getAttribute('data-k'), 10) || 0);
    });
  });

  /* 图例开关：点一下显示/隐藏那条线 */
  document.querySelectorAll('.lgbtn').forEach(function(el){
    el.addEventListener('click', function(){
      var k = el.getAttribute('data-k');
      if(k === 's') showS = !showS; else showU = !showU;
      el.classList.toggle('on', k === 's' ? showS : showU);
      drawZ();
    });
  });
}

function initToday(){
  var now = D.now;
  document.getElementById('asof').textContent = '数据截至 ' + D.updated;
  var z = now.z, el = document.getElementById('zval');
  el.textContent = (z>=0?'+':'') + z.toFixed(2);
  el.style.color = z<=-1.5 ? 'var(--buy-fg)' : (z>=1.0 ? 'var(--sell-fg)' : 'var(--ink)');

  var st = document.getElementById('status');
  if(z<=-1.5){ st.textContent='买入区 · 建议分批买入'; st.className='status s-buy'; }
  else if(z>=1.0){ st.textContent='卖出区 · 建议分批卖出'; st.className='status s-sell'; }
  else { st.textContent='中间地带 · 建议不动'; st.className='status s-mid'; }

  var lo=-2.5, hi=3.0, pp=Math.max(2, Math.min(98, (z-lo)/(hi-lo)*100));
  setTimeout(function(){ document.getElementById('ptr').style.left = pp+'%'; }, 60);

  var tb=document.getElementById('tobuy'), ts=document.getElementById('tosell');
  tb.textContent = z<=-1.5 ? '已触发' : fmtPct(now.toBuy);
  ts.textContent = z>=1.0 ? '已触发' : fmtPct(now.toSell);
  tb.style.color = z<=-1.5 ? 'var(--buy-fg)' : 'var(--sell-fg)';
  ts.style.color = z>=1.0 ? 'var(--sell-fg)' : 'var(--buy-fg)';
  document.getElementById('tobuys').textContent = z<=-1.5 ? '已在买入区' : '还要跌这么多';
  document.getElementById('tosells').textContent = z>=1.0 ? '已在卖出区' : '还要涨这么多';

  var pc = document.getElementById('pct');
  pc.textContent = now.pct + '%';
  pc.style.color = now.pct<=30 ? 'var(--buy-fg)' : (now.pct>=70 ? 'var(--sell-fg)' : 'var(--ink)');

  document.getElementById('snap2').textContent = D.updated;
  document.getElementById('snapfrom').textContent = D.from;
}

function buildBuyList(){
  var items = D.buys.slice(-8).reverse();
  document.getElementById('buylist').innerHTML = items.map(function(b){
    return '<li><span><i class="dot"></i>' + ymdOf(b[0]) + '</span>'
         + '<span class="dim">z ' + b[1].toFixed(2) + '</span></li>';
  }).join('') || '<li class="dim">区间内未触发</li>';
  document.getElementById('histfoot').textContent = D.from + ' 年至今共触发 ' + D.buys.length + ' 次';
}

document.querySelectorAll('.fold .foldhead').forEach(function(h){
  h.addEventListener('click', function(){ h.parentNode.classList.toggle('open'); });
});
document.getElementById('aboutbtn').addEventListener('click', function(){
  var f = document.getElementById('foldAbout');
  f.classList.add('open');
  f.scrollIntoView({behavior:'smooth', block:'start'});
});

/* 系统深浅色切换时，画布要重画 */
if(window.matchMedia){
  var mq = window.matchMedia('(prefers-color-scheme: dark)');
  var onScheme = function(){ T = null; drawZ(); };
  if(mq.addEventListener) mq.addEventListener('change', onScheme);
  else if(mq.addListener) mq.addListener(onScheme);
}

window.addEventListener('resize', function(){ drawZ(); });
window.addEventListener('load', function(){ drawZ(); });
if(document.fonts && document.fonts.ready) document.fonts.ready.then(function(){ drawZ(); });
if(window.ResizeObserver){
  new ResizeObserver(function(){ drawZ(); }).observe(document.getElementById('cvz'));
}

initToday();
buildBuyList();
bindChart();
applyRange(250);
</script>
</body>
</html>
"""

html = HTML.replace("__DATA__", json.dumps(payload, separators=(",", ":"))).replace("__BUILD__", BUILD)
path = os.path.join(OUT, "index.html")
with open(path, "w", encoding="utf-8") as f:
    f.write(html)

print("written:", path)
print("kb:", round(len(html.encode("utf-8")) / 1024, 1))
print("points:", len(payload["z"]), "now:", payload["now"])
