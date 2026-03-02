"""BB Squeeze Breakout Bot — FastAPI dashboard"""
import csv, json, os
from datetime import datetime, timedelta, timezone
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from config import TOKENS, STATE_FILE, LOG_FILE, SIGNAL_CHECK_UTC, POSITION_CHECK_M

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)


def _load_trades():
    if not os.path.exists(LOG_FILE): return []
    try:
        with open(LOG_FILE, newline="") as f: return list(csv.DictReader(f))
    except: return []


def _load_positions():
    if not os.path.exists(STATE_FILE): return {}
    try:
        with open(STATE_FILE) as f: return json.load(f)
    except: return {}


def _next_scan():
    now = datetime.now(timezone.utc)
    h, m = map(int, SIGNAL_CHECK_UTC.split(":"))
    t = now.replace(hour=h, minute=m, second=0, microsecond=0)
    if t <= now: t += timedelta(days=1)
    diff = t - now
    hrs, rem = divmod(int(diff.total_seconds()), 3600)
    return f"{hrs}h {rem//60}m"


def _equity_curve(trades):
    pts, running = [], 0.0
    for t in trades:
        try:
            pnl = float(t.get("pnl_usd", 0))
            if pnl == 0: continue
            running += pnl
            pts.append({"time": t["timestamp"][:10], "equity": round(running, 2)})
        except: pass
    return pts


@app.get("/api/status")
def api_status():
    trades = _load_trades()
    pos    = _load_positions()
    total_pnl = sum(float(t.get("pnl_usd", 0)) for t in trades)
    wins   = [t for t in trades if float(t.get("pnl_usd", 0)) > 0 and t.get("event") != "OPEN"]
    losses = [t for t in trades if float(t.get("pnl_usd", 0)) < 0]
    win_rate = round(len(wins) / (len(wins) + len(losses)) * 100, 1) if (wins or losses) else 0
    try:
        from hl_client import get_account_equity
        equity = get_account_equity()
    except: equity = None
    return {
        "status": "running",
        "tokens": TOKENS,
        "open_positions": len(pos),
        "total_trades": len([t for t in trades if t.get("event") == "OPEN"]),
        "total_pnl_usd": round(total_pnl, 2),
        "win_rate": win_rate,
        "account_equity": equity,
        "next_scan_in": _next_scan(),
        "scan_time_utc": SIGNAL_CHECK_UTC,
        "monitor_every_m": POSITION_CHECK_M,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/positions")
def api_positions():
    pos = _load_positions()
    result = []
    for coin, p in pos.items():
        result.append({
            "coin":        coin,
            "side":        p.get("side", "long"),
            "size":        p.get("size", 0),
            "entry_price": p.get("entry_price", 0),
            "sl_price":    p.get("sl_price", 0),
            "trail_stop":  p.get("trail_stop", 0),
            "trail_high":  p.get("trail_high", 0),
            "trail_low":   p.get("trail_low", 0),
            "notional_usd": p.get("notional_usd", 0),
            "opened_at":   p.get("opened_at", ""),
        })
    return result


@app.get("/api/trades")
def api_trades():
    return _load_trades()


@app.get("/api/equity")
def api_equity():
    return _equity_curve(_load_trades())


@app.get("/", response_class=HTMLResponse)
def dashboard():
    return HTMLResponse(DASHBOARD_HTML)


DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>BB Squeeze Bot</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0a0c10;color:#e2e8f0;font-family:-apple-system,'SF Pro Display',sans-serif;min-height:100vh}
.header{background:#0f1218;border-bottom:1px solid #1e2535;padding:14px 28px;display:flex;align-items:center;justify-content:space-between}
.header h1{font-size:16px;font-weight:700;color:#f1f5f9}
.header p{font-size:11px;color:#64748b;margin-top:2px}
.badge{display:flex;align-items:center;gap:6px;border-radius:16px;padding:5px 12px;font-size:12px;font-weight:600;background:#0d1a2e;border:1px solid #1e3a5f;color:#60a5fa}
.dot{width:7px;height:7px;border-radius:50%;background:#60a5fa;animation:pulse 2s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}
.refresh{font-size:11px;color:#475569}
.container{max-width:1200px;margin:0 auto;padding:24px 28px}
.scan-bar{display:flex;gap:24px;background:#0d1018;border:1px solid #1a2030;border-radius:10px;padding:12px 18px;margin-bottom:22px;font-size:12px}
.scan-item{display:flex;flex-direction:column;gap:2px}
.scan-label{font-size:10px;color:#64748b;text-transform:uppercase;letter-spacing:.05em}
.scan-value{font-weight:600;color:#e2e8f0}
.scan-div{width:1px;height:28px;background:#1e2535}
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:22px}
.stat{background:#0f1218;border:1px solid #1e2535;border-radius:12px;padding:18px 20px;position:relative;overflow:hidden}
.stat::before{content:'';position:absolute;top:0;left:0;right:0;height:2px;background:var(--a)}
.stat-label{font-size:11px;color:#64748b;font-weight:500;text-transform:uppercase;letter-spacing:.05em}
.stat-value{font-size:24px;font-weight:700;margin-top:6px}
.stat-sub{font-size:11px;color:#64748b;margin-top:3px}
.positive{color:#4ade80}.negative{color:#f87171}.neutral{color:#94a3b8}
.panel{background:#0f1218;border:1px solid #1e2535;border-radius:12px;padding:20px;margin-bottom:16px}
.panel-header{display:flex;align-items:center;justify-content:space-between;margin-bottom:16px}
.panel-title{font-size:13px;font-weight:600;color:#f1f5f9}
.chart-wrap{height:180px;position:relative}
table{width:100%;border-collapse:collapse}
th{font-size:10px;color:#64748b;font-weight:600;text-transform:uppercase;letter-spacing:.05em;padding:0 10px 8px 0;text-align:left;border-bottom:1px solid #1e2535}
td{padding:9px 10px 9px 0;font-size:12px;color:#e2e8f0;border-bottom:1px solid #141a24}
tr:last-child td{border-bottom:none}
.side-long{color:#4ade80;background:#0f2918;border:1px solid #166534;border-radius:3px;padding:1px 6px;font-size:10px;font-weight:600}
.side-short{color:#f87171;background:#2d0f0f;border:1px solid #7f1d1d;border-radius:3px;padding:1px 6px;font-size:10px;font-weight:600}
.ev-OPEN{background:#1e3a5f;color:#60a5fa}.ev-TRAIL_STOP{background:#1f1a0a;color:#fbbf24}
.ev-SL{background:#2d0f0f;color:#f87171}.ev-EXTERNAL_CLOSE{background:#2d2a0f;color:#facc15}
.empty{text-align:center;padding:24px;color:#475569;font-size:12px}
.footer{text-align:center;padding:18px;color:#334155;font-size:11px}
</style></head><body>
<div class="header">
  <div><h1>🔵 BB Squeeze Breakout Bot</h1>
  <p>BB(20,2) Squeeze + EMA200 + Volume · Daily · 3× Leverage · 5% Trail · 5% SL</p></div>
  <div style="display:flex;align-items:center;gap:14px">
    <div class="badge"><div class="dot"></div>Squeeze Bot</div>
    <span class="refresh" id="last-refresh">Loading…</span>
  </div>
</div>
<div class="container">
  <div class="scan-bar">
    <div class="scan-item"><span class="scan-label">Status</span><span class="scan-value" id="status">–</span></div>
    <div class="scan-div"></div>
    <div class="scan-item"><span class="scan-label">Next Scan</span><span class="scan-value" id="next-scan">–</span></div>
    <div class="scan-div"></div>
    <div class="scan-item"><span class="scan-label">Scan Time UTC</span><span class="scan-value" id="scan-time">–</span></div>
    <div class="scan-div"></div>
    <div class="scan-item"><span class="scan-label">Tokens</span><span class="scan-value" id="tokens">–</span></div>
    <div class="scan-div"></div>
    <div class="scan-item"><span class="scan-label">Monitor Interval</span><span class="scan-value" id="monitor">–</span></div>
  </div>
  <div class="stats">
    <div class="stat" style="--a:linear-gradient(90deg,#3b82f6,#06b6d4)">
      <div class="stat-label">Account Equity</div><div class="stat-value" id="equity">–</div>
      <div class="stat-sub">Hyperliquid</div></div>
    <div class="stat" style="--a:linear-gradient(90deg,#10b981,#059669)">
      <div class="stat-label">Total P&L</div><div class="stat-value" id="total-pnl">–</div>
      <div class="stat-sub" id="trade-count">0 trades</div></div>
    <div class="stat" style="--a:linear-gradient(90deg,#6366f1,#8b5cf6)">
      <div class="stat-label">Win Rate</div><div class="stat-value" id="win-rate">–</div>
      <div class="stat-sub">closed trades</div></div>
    <div class="stat" style="--a:linear-gradient(90deg,#f59e0b,#ef4444)">
      <div class="stat-label">Open Positions</div><div class="stat-value" id="open-pos">–</div>
      <div class="stat-sub">max 1</div></div>
  </div>
  <div class="panel">
    <div class="panel-header"><div class="panel-title">Equity Curve (cumulative P&L)</div></div>
    <div class="chart-wrap"><canvas id="eq-chart"></canvas></div>
  </div>
  <div class="panel">
    <div class="panel-header"><div class="panel-title">Open Positions</div><div id="pos-count" style="font-size:11px;color:#64748b">–</div></div>
    <div id="positions"><div class="empty">No open positions</div></div>
  </div>
  <div class="panel">
    <div class="panel-header"><div class="panel-title">Trade History</div></div>
    <div id="trades"><div class="empty">No trades yet</div></div>
  </div>
</div>
<div class="footer">BB Squeeze Breakout Bot · Hyperliquid Perpetuals · Auto-refreshes every 30s</div>
<script>
const fmt = (n,d=2) => n==null?'–':parseFloat(n).toFixed(d);
const fmtUSD = n => { if(n==null)return'–'; const v=parseFloat(n); return (v>=0?'+':'')+'$'+Math.abs(v).toFixed(2); };
const cc = n => parseFloat(n)>0?'positive':parseFloat(n)<0?'negative':'neutral';
let chart = null;

async function safe(url) {
  try { return await (await fetch(url, {signal:AbortSignal.timeout(8000)})).json(); } catch { return null; }
}

async function refresh() {
  const [status, pos, trades, equity] = await Promise.all([
    safe('/api/status'), safe('/api/positions'), safe('/api/trades'), safe('/api/equity')
  ]);
  if (status) {
    document.getElementById('status').textContent = '🟢 Running';
    document.getElementById('next-scan').textContent = status.next_scan_in;
    document.getElementById('scan-time').textContent = status.scan_time_utc + ' UTC';
    document.getElementById('tokens').textContent = (status.tokens||[]).join(' · ');
    document.getElementById('monitor').textContent = 'every ' + status.monitor_every_m + 'm';
    document.getElementById('equity').textContent = status.account_equity != null ? '$'+fmt(status.account_equity) : '–';
    const p = document.getElementById('total-pnl');
    p.textContent = fmtUSD(status.total_pnl_usd); p.className = 'stat-value '+cc(status.total_pnl_usd);
    document.getElementById('win-rate').textContent = status.win_rate + '%';
    document.getElementById('open-pos').textContent = status.open_positions + '/1';
    document.getElementById('trade-count').textContent = status.total_trades + ' trades';
  } else {
    document.getElementById('status').textContent = '🔴 Offline';
  }

  // Equity chart
  if (equity && equity.length) {
    const labels = equity.map(p=>p.time), data = equity.map(p=>p.equity);
    if (chart) { chart.data.labels=labels; chart.data.datasets[0].data=data; chart.update(); }
    else {
      chart = new Chart(document.getElementById('eq-chart').getContext('2d'), {
        type:'line', data:{labels, datasets:[{data, borderColor:'#60a5fa', backgroundColor:'rgba(96,165,250,0.08)',
          borderWidth:2, fill:true, tension:0.4, pointRadius:data.length>20?0:3}]},
        options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false},
          tooltip:{backgroundColor:'#1e2535',bodyColor:'#f1f5f9',callbacks:{label:c=>' P&L: $'+c.parsed.y.toFixed(2)}}},
          scales:{x:{grid:{color:'#141a24'},ticks:{color:'#64748b',font:{size:10},maxTicksLimit:8}},
            y:{grid:{color:'#141a24'},ticks:{color:'#64748b',font:{size:10},callback:v=>'$'+v.toFixed(0)}}}}
      });
    }
  }

  // Positions
  const pw = document.getElementById('positions');
  document.getElementById('pos-count').textContent = (pos||[]).length + ' active';
  if (!pos || !pos.length) { pw.innerHTML='<div class="empty">No open positions</div>'; }
  else {
    pw.innerHTML = `<table><thead><tr><th>Coin</th><th>Side</th><th>Size</th><th>Entry</th><th>SL</th><th>Trail Stop</th><th>Trail High/Low</th></tr></thead><tbody>
    ${pos.map(p=>`<tr>
      <td><strong>${p.coin}</strong></td>
      <td><span class="side-${p.side}">${p.side.toUpperCase()}</span></td>
      <td>${fmt(p.size,4)}</td><td>$${fmt(p.entry_price)}</td>
      <td class="negative">$${fmt(p.sl_price)}</td>
      <td class="positive">$${fmt(p.trail_stop)}</td>
      <td>${p.side==='long'?'High: $'+fmt(p.trail_high):'Low: $'+fmt(p.trail_low)}</td>
    </tr>`).join('')}
    </tbody></table>`;
  }

  // Trades
  const tw = document.getElementById('trades');
  if (!trades || !trades.length) { tw.innerHTML='<div class="empty">No trades yet — bot scans daily at 00:15 UTC</div>'; }
  else {
    const sorted = [...trades].sort((a,b)=>new Date(b.timestamp||0)-new Date(a.timestamp||0)).slice(0,50);
    tw.innerHTML = `<table><thead><tr><th>Time</th><th>Coin</th><th>Event</th><th>Side</th><th>Size</th><th>Price</th><th>P&L</th><th>Equity</th></tr></thead><tbody>
    ${sorted.map(t=>{const pnl=parseFloat(t.pnl_usd||0); return`<tr>
      <td style="color:#64748b;font-size:11px">${(t.timestamp||'').slice(0,16).replace('T',' ')}</td>
      <td><strong>${t.coin}</strong></td>
      <td><span class="ev-${t.event||''}" style="border-radius:3px;padding:1px 6px;font-size:10px;font-weight:600">${t.event}</span></td>
      <td>${t.side?`<span class="side-${t.side}">${t.side.toUpperCase()}</span>`:'–'}</td>
      <td>${fmt(t.size,4)}</td>
      <td>${t.price&&t.price!='0.0'?'$'+fmt(t.price):'–'}</td>
      <td class="${cc(pnl)}">${pnl?fmtUSD(pnl):'–'}</td>
      <td>${t.account_equity&&t.account_equity!='0'?'$'+fmt(t.account_equity):'–'}</td>
    </tr>`;}).join('')}
    </tbody></table>`;
  }
  document.getElementById('last-refresh').textContent = 'Updated '+new Date().toLocaleTimeString();
}
refresh();
setInterval(refresh, 30000);
</script></body></html>"""
