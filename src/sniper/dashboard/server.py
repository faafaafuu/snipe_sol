from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from sniper.core.app import SniperBot
from sniper.core.models import utc_now
from sniper.storage.repository import Repository


def create_dashboard(repo: Repository, bot: SniperBot | None = None) -> FastAPI:
    app = FastAPI(title="Pump.fun Sniper Dashboard")

    @app.get("/", response_class=HTMLResponse)
    async def index() -> str:
        return """
        <!doctype html><html lang="en"><head><meta charset="utf-8">
        <meta name="viewport" content="width=device-width,initial-scale=1">
        <title>Pump Scanner</title>
        <style>
        :root{color-scheme:light;--bg:#f6f7f8;--panel:#fff;--line:#e5e7eb;--text:#15171a;--muted:#69707a;--green:#12833b;--red:#c92a2a;--amber:#a15c00}
        *{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:14px/1.4 Inter,Arial,sans-serif}
        main{max-width:1320px;margin:24px auto;padding:0 16px}header{display:flex;justify-content:space-between;gap:12px;align-items:end;margin-bottom:14px}
        h1{font-size:22px;margin:0}.meta{color:var(--muted);font-size:12px}.layout{display:grid;grid-template-columns:minmax(0,1.35fr) minmax(360px,.65fr);gap:14px}
        .panel{background:var(--panel);border:1px solid var(--line);border-radius:8px;overflow:hidden}.pad{padding:14px}
        .stats{display:flex;gap:8px;flex-wrap:wrap}.stat{background:#fff;border:1px solid var(--line);border-radius:8px;padding:8px 10px;min-width:110px}.stat b{display:block;font-size:15px}
        table{width:100%;border-collapse:separate;border-spacing:0;background:var(--panel);border:1px solid var(--line);border-radius:8px;overflow:hidden}
        th,td{padding:11px 12px;border-bottom:1px solid var(--line);text-align:left;white-space:nowrap}
        th{font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted);background:#fafafa}
        tbody tr{cursor:pointer;transition:background .12s ease}tbody tr:hover,tbody tr.selected{background:#f1f5f9}tbody tr.new{animation:flash .8s ease}.trade-table{margin-top:14px}
        td.name{font-weight:650;white-space:normal}td.mint{max-width:180px;overflow:hidden;text-overflow:ellipsis;color:var(--muted);font-size:12px}
        .up{color:var(--green);font-weight:650}.down{color:var(--red);font-weight:650}.empty{padding:28px;text-align:center;color:var(--muted)}
        .badge{display:inline-flex;align-items:center;gap:6px;border-radius:999px;padding:3px 8px;font-size:12px;border:1px solid var(--line);background:#fff}.ok{color:var(--green);border-color:#b7e4c7;background:#f0fff4}.fail{color:var(--red);border-color:#ffc9c9;background:#fff5f5}.wait{color:var(--amber);border-color:#ffe0a3;background:#fff9db}
        .detail h2{font-size:18px;margin:0 0 2px}.detail .mintline{font-size:12px;color:var(--muted);word-break:break-all}.score{display:flex;gap:8px;flex-wrap:wrap;margin:12px 0}.checks{display:grid;gap:8px;margin-top:10px}.check{display:grid;grid-template-columns:70px 1fr;gap:8px;align-items:start;border-top:1px solid var(--line);padding-top:8px}.check strong{font-size:13px}.check small{display:block;color:var(--muted)}.reasons{margin-top:12px}.reason{font-size:12px;color:#6b1f1f;background:#fff5f5;border:1px solid #ffd6d6;border-radius:6px;padding:7px;margin-top:6px}
        a.btn{display:inline-flex;align-items:center;justify-content:center;border:1px solid var(--line);border-radius:6px;padding:5px 8px;color:#111;text-decoration:none;background:#fff;font-size:12px;font-weight:650}a.btn:hover{background:#eef2f7}.accepted{margin-top:14px}.accepted-list{display:flex;gap:8px;overflow:auto;padding:10px}.accepted-card{min-width:210px;border:1px solid #b7e4c7;background:#f0fff4;border-radius:8px;padding:9px}.accepted-card strong{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.accepted-card .meta{margin:3px 0 8px}
        @keyframes flash{from{background:#ecfdf3}to{background:transparent}}
        @media(max-width:900px){.layout{grid-template-columns:1fr}.detail{order:-1}}@media(max-width:720px){main{margin:16px auto}th:nth-child(2),td:nth-child(2){display:none}th,td{padding:10px 8px}}
        </style></head><body>
        <main>
          <header><div><h1>Pump Scanner</h1><div class="meta">Paper mode · top 7 live candidates · obvious junk hidden</div></div><div id="count" class="meta">0 projects</div></header>
          <div id="stats" class="stats"></div>
          <section class="panel accepted"><div class="pad" style="padding-bottom:0"><strong>Accepted / Ready</strong><div class="meta">Open strongest candidates in GMGN</div></div><div id="accepted" class="accepted-list"><div class="meta">No accepted tokens yet.</div></div></section>
          <div class="layout" style="margin-top:14px">
            <section>
              <table>
                <thead><tr><th>Name</th><th>Mint</th><th>Price</th><th>Volume</th><th>Buyers</th><th>Age</th><th>Entry</th><th>Open</th></tr></thead>
                <tbody id="tokens"><tr><td class="empty" colspan="8">Waiting for tokens...</td></tr></tbody>
              </table>
            </section>
            <aside class="panel detail"><div id="detail" class="pad"><div class="empty">Select a token</div></div></aside>
          </div>
          <section class="trade-table">
            <table>
              <thead><tr><th>Time</th><th>Token</th><th>Side</th><th>Size</th><th>Price</th><th>PnL</th><th>Reason</th><th>Open</th></tr></thead>
              <tbody id="trades"><tr><td class="empty" colspan="8">No trades yet.</td></tr></tbody>
            </table>
          </section>
        </main>
        <script>
        const tbody=document.getElementById('tokens'), tradeBody=document.getElementById('trades'), count=document.getElementById('count');
        const detail=document.getElementById('detail'), stats=document.getElementById('stats'), accepted=document.getElementById('accepted');
        const seen=new Set(); const byMint=new Map(); let rows=[], selected=null;
        const esc=v=>String(v??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
        const price=v=>Number(v||0).toLocaleString(undefined,{maximumFractionDigits:6});
        const compact=n=>{n=Number(n||0);return Math.abs(n)>=1e6?(n/1e6).toFixed(1)+'M':Math.abs(n)>=1e3?(n/1e3).toFixed(1)+'K':n.toFixed(n<10?2:0)};
        const age=s=>{s=Math.max(0,Math.floor(s||0));return s<60?s+'s':Math.floor(s/60)+'m'};
        const badge=(cls,text)=>`<span class="badge ${cls}">${text}</span>`;
        const stateClass=s=>s==='ok'?'ok':s==='fail'?'fail':'wait';
        const gmgn=m=>`https://gmgn.ai/sol/token/${encodeURIComponent(m)}`;
        function row(t){
          const dir=Number(t.change_pct||0)>=0?'up':'down';
          const cls=t.mint===selected?' selected':'';
          return `<tr class="new${cls}" data-mint="${esc(t.mint)}"><td class="name">${esc(t.name||t.symbol||'Unknown')}</td><td class="mint">${esc(t.mint)}</td><td class="${dir}">${price(t.price)}</td><td>${compact(t.volume)}</td><td>${Number(t.buyers||0)}</td><td>${age(t.age_seconds)}</td><td>${badge(stateClass(t.entry_state),esc(t.entry_label))}</td><td><a class="btn" href="${gmgn(t.mint)}" target="_blank" rel="noopener" onclick="event.stopPropagation()">GMGN</a></td></tr>`;
        }
        function render(items){
          const fresh=[];
          for(const t of items.sort((a,b)=>new Date(a.seen_at)-new Date(b.seen_at))){
            if(!t.mint)continue; byMint.set(t.mint,t);
            if(!seen.has(t.mint)){seen.add(t.mint);rows.unshift(t);fresh.push(t)}
            else rows=rows.map(x=>x.mint===t.mint?t:x);
          }
          rows=rows.slice(0,7); for(const m of [...seen])if(!rows.find(x=>x.mint===m))seen.delete(m);
          if(rows.length){tbody.innerHTML=rows.map(row).join('')}
          count.textContent=rows.length+' projects';
          if(!selected&&rows[0])selected=rows[0].mint;
          if(selected)showDetail(byMint.get(selected)||rows.find(x=>x.mint===selected));
          setTimeout(()=>document.querySelectorAll('tr.new').forEach(x=>x.classList.remove('new')),900);
        }
        function showDetail(t){
          if(!t)return;
          detail.innerHTML=`<h2>${esc(t.name||t.symbol||'Unknown')}</h2><div class="mintline">${esc(t.mint)}</div>
          <div class="score">${badge(stateClass(t.entry_state),esc(t.entry_label))}${badge('wait',`${t.ok_count}/${t.total_checks} ok`)}${badge('fail',`${t.fail_count} fail`)}${badge('wait',`${t.wait_count} wait`)}<a class="btn" href="${gmgn(t.mint)}" target="_blank" rel="noopener">Open GMGN</a></div>
          <div class="stats"><div class="stat"><b>${price(t.price)}</b><span class="meta">price</span></div><div class="stat"><b>${compact(t.volume)}</b><span class="meta">volume</span></div><div class="stat"><b>${Number(t.buyers||0)}</b><span class="meta">buyers</span></div><div class="stat"><b>${age(t.age_seconds)}</b><span class="meta">age</span></div></div>
          <div class="checks">${t.checks.map(c=>`<div class="check"><div>${badge(stateClass(c.state),c.state)}</div><div><strong>${esc(c.label)}</strong><small>${esc(c.actual)} · target ${esc(c.target)}</small></div></div>`).join('')}</div>
          <div class="reasons">${(t.reasons||[]).slice(0,6).map(r=>`<div class="reason">${esc(r)}</div>`).join('')||'<div class="meta">No skip reason yet.</div>'}</div>`;
          document.querySelectorAll('tbody tr').forEach(x=>x.classList.toggle('selected',x.dataset.mint===t.mint));
        }
        function renderStats(s){
          if(!s)return; const p=s.performance||{};
          stats.innerHTML=`<div class="stat"><b>${Number(s.balance_sol||0).toFixed(3)} SOL</b><span class="meta">paper balance</span></div><div class="stat"><b>${p.signals||0}</b><span class="meta">signals</span></div><div class="stat"><b>${p.accepted_signals||0}</b><span class="meta">accepted</span></div><div class="stat"><b>${p.skipped_signals||0}</b><span class="meta">skipped</span></div><div class="stat"><b>${(s.positions||[]).length}</b><span class="meta">positions</span></div>`;
        }
        function renderAccepted(items){
          const list=items.filter(t=>t.entry_state==='ok'||t.accepted).slice(0,12);
          accepted.innerHTML=list.length?list.map(t=>`<div class="accepted-card"><strong>${esc(t.name||t.symbol||'Unknown')}</strong><div class="meta">${esc(t.mint)}</div><a class="btn" href="${gmgn(t.mint)}" target="_blank" rel="noopener">Open GMGN</a></div>`).join(''):'<div class="meta">No accepted tokens yet.</div>';
        }
        function renderTrades(items){
          tradeBody.innerHTML=items.length?items.slice(0,25).map(t=>`<tr><td>${esc(t.created_at)}</td><td class="mint">${esc(t.mint)}</td><td>${esc(t.side)}</td><td>${compact(t.size_sol)} SOL</td><td>${price(t.price_sol)}</td><td class="${Number(t.pnl_sol)>=0?'up':'down'}">${Number(t.pnl_sol||0).toFixed(5)}</td><td>${esc(t.reason)}</td><td><a class="btn" href="${gmgn(t.mint)}" target="_blank" rel="noopener">GMGN</a></td></tr>`).join(''):'<tr><td class="empty" colspan="8">No trades yet.</td></tr>';
        }
        tbody.addEventListener('click',e=>{const tr=e.target.closest('tr[data-mint]');if(!tr)return;selected=tr.dataset.mint;showDetail(byMint.get(selected));});
        let timer; async function poll(){
          clearTimeout(timer);
          try{
            const [tokens,status,trades]=await Promise.all([fetch('/api/tokens?limit=7',{cache:'no-store'}).then(r=>r.json()),fetch('/api/status',{cache:'no-store'}).then(r=>r.json()),fetch('/api/trades',{cache:'no-store'}).then(r=>r.json())]);
            render(tokens); renderStats(status); renderAccepted(tokens); renderTrades(trades);
          }catch(e){console.warn(e)}
          timer=setTimeout(poll,2000);
        } poll();
        </script></body></html>
        """

    @app.get("/api/status")
    async def status() -> dict:
        balance = await bot.broker.balance_sol() if bot else 0.0
        positions = []
        if bot:
            for p in bot.positions.values():
                item = asdict(p)
                item["take_profit_hits"] = list(p.take_profit_hits)
                positions.append(item)
        return {"balance_sol": balance, "positions": positions, "performance": repo.performance_snapshot()}

    @app.get("/api/trades")
    async def trades() -> list[dict]:
        return [
            {
                "created_at": str(t.created_at),
                "mint": t.mint,
                "side": t.side,
                "price_sol": t.price_sol,
                "size_sol": t.size_sol,
                "pnl_sol": t.pnl_sol,
                "reason": t.reason,
            }
            for t in repo.last_trades(50)
        ]

    @app.get("/api/signals")
    async def signals(limit: int = 100, skipped_only: bool = False) -> list[dict]:
        rows = repo.last_signals(min(max(limit, 1), 500), passed=False if skipped_only else None)
        return [
            {
                "created_at": str(s.created_at),
                "mint": s.mint,
                "score": s.score,
                "passed": s.passed,
                "mode": s.mode,
                "reasons": s.reasons,
            }
            for s in rows
        ]

    @app.get("/api/tokens")
    async def tokens(limit: int = 50) -> list[dict]:
        return _token_rows(repo, bot, min(limit, 7))

    @app.get("/api/accepted")
    async def accepted(limit: int = 20) -> list[dict]:
        all_tokens = _token_rows(repo, bot, 200)
        return [t for t in all_tokens if t["entry_state"] == "ok" or t.get("accepted")][:limit]

    return app


def _token_rows(repo: Repository, bot: SniperBot | None, limit: int) -> list[dict]:
    rows = repo.last_raw_events(300)
    latest_by_mint = {}
    for row in rows:
        latest_by_mint.setdefault(row.mint, row)
    signal_map = {s.mint: s for s in repo.last_signals(500)}
    tokens = [_event_to_token(row, bot, signal_map.get(row.mint)) for row in latest_by_mint.values()]
    visible = [t for t in tokens if not _is_obvious_junk(t)]
    visible.sort(key=lambda t: (t["accepted"], t["entry_state"] == "ok", t["ok_count"], t["volume"], t["buyers"], t["seen_at"]), reverse=True)
    return visible[:limit]


def _is_obvious_junk(token: dict) -> bool:
    if token["price"] <= 0 or token["liquidity"] <= 0 or token["market_cap"] <= 0:
        return True
    if token["age_seconds"] > 10 and token["volume"] <= 0:
        return True
    if token["age_seconds"] > 20 and token["buyers"] == 0:
        return True
    if token.get("wash", 0) >= 0.85 or token.get("bot_score", 0) >= 0.92:
        return True
    if token["age_seconds"] > 15 and token["ok_count"] <= 2 and token["entry_state"] != "ok":
        return True
    return False


def _event_to_token(row, bot: SniperBot | None = None, signal=None) -> dict:
    payload = json.loads(row.payload_json)
    live_metrics = bot.aggregator.metrics(row.mint, utc_now()) if bot and hasattr(bot, "aggregator") else None
    price = live_metrics.price_sol if live_metrics else _number(payload.get("price_sol", payload.get("priceSol", _pump_price(payload))))
    volume = live_metrics.volume_60s_sol if live_metrics else _number(payload.get("volume_60s_sol", payload.get("volume60sSol", payload.get("solAmount", 0))))
    buyers = live_metrics.unique_buyers_60s if live_metrics else int(_number(payload.get("unique_buyers_60s", payload.get("uniqueBuyers60s", 0))))
    change = live_metrics.price_change_30s_pct if live_metrics else _number(payload.get("price_change_30s_pct", payload.get("priceChange30sPct", 0)))
    liquidity = live_metrics.liquidity_sol if live_metrics else _number(payload.get("liquidity_sol", payload.get("liquiditySol", payload.get("vSolInBondingCurve", 0))))
    market_cap = live_metrics.market_cap_sol if live_metrics else _number(payload.get("market_cap_sol", payload.get("marketCapSol", payload.get("marketCap", 0))))
    velocity = live_metrics.buy_velocity if live_metrics else _number(payload.get("buy_velocity", payload.get("buyVelocity", 0)))
    slippage = live_metrics.estimated_slippage_pct if live_metrics else _number(payload.get("estimated_slippage_pct", payload.get("estimatedSlippagePct", 0)))
    wash = live_metrics.wash_trade_score if live_metrics else 0.0
    bot_score = live_metrics.bot_activity_score if live_metrics else 0.0
    created_at = _aware(_parse_dt(payload.get("created_at") or payload.get("createdAt")) or row.created_at)
    seen_at = _aware(row.created_at)
    age_seconds = max(0, (datetime.now(timezone.utc) - created_at).total_seconds())
    checks = _entry_checks(bot, age_seconds, liquidity, volume, buyers, velocity, change, market_cap, slippage, wash, bot_score)
    ok_count = sum(1 for c in checks if c["state"] == "ok")
    fail_count = sum(1 for c in checks if c["state"] == "fail")
    wait_count = sum(1 for c in checks if c["state"] == "wait")
    accepted = bool(signal and signal.passed)
    if accepted:
        entry_state, entry_label = "ok", "accepted"
    elif fail_count:
        entry_state, entry_label = "fail", "not ready"
    elif wait_count:
        entry_state, entry_label = "wait", "watching"
    else:
        entry_state, entry_label = "ok", "entry ready"
    return {
        "mint": row.mint,
        "name": payload.get("name") or payload.get("symbol") or "Unknown",
        "symbol": payload.get("symbol") or "",
        "price": price,
        "volume": volume,
        "buyers": buyers,
        "age_seconds": age_seconds,
        "change_pct": change,
        "liquidity": liquidity,
        "market_cap": market_cap,
        "buy_velocity": velocity,
        "wash": wash,
        "bot_score": bot_score,
        "entry_state": entry_state,
        "entry_label": entry_label,
        "accepted": accepted,
        "checks": checks,
        "ok_count": ok_count,
        "fail_count": fail_count,
        "wait_count": wait_count,
        "total_checks": len(checks),
        "reasons": signal.reasons.split("\n") if signal and signal.reasons else [],
        "seen_at": seen_at.isoformat(),
    }


def _entry_checks(
    bot: SniperBot | None,
    age: float,
    liquidity: float,
    volume: float,
    buyers: int,
    velocity: float,
    momentum: float,
    market_cap: float,
    slippage: float,
    wash: float,
    bot_score: float,
) -> list[dict]:
    cfg = bot.cfg.active_filter if bot else None
    if not cfg:
        return []
    return [
        _check("Age window", age, f"{cfg.min_age_seconds}s..{cfg.max_age_seconds}s", cfg.min_age_seconds <= age <= cfg.max_age_seconds, f"{age:.0f}s"),
        _check("Liquidity", liquidity, f">= {cfg.min_liquidity_sol:g} SOL", liquidity >= cfg.min_liquidity_sol, f"{liquidity:.2f} SOL"),
        _check("60s volume", volume, f">= {cfg.min_volume_60s_sol:g} SOL", volume >= cfg.min_volume_60s_sol, f"{volume:.2f} SOL"),
        _check("Unique buyers", buyers, f">= {cfg.min_unique_buyers_60s}", buyers >= cfg.min_unique_buyers_60s, str(buyers), wait=buyers == 0),
        _check("Buy velocity", velocity, f">= {cfg.min_buy_velocity:g}/s", velocity >= cfg.min_buy_velocity, f"{velocity:.2f}/s", wait=velocity == 0),
        _check("Momentum", momentum, f">= {cfg.min_momentum_30s_pct:.1%}", momentum >= cfg.min_momentum_30s_pct, f"{momentum:.1%}", wait=momentum == 0),
        _check("Market cap", market_cap, f"<= {cfg.max_initial_market_cap_sol:g} SOL", market_cap <= cfg.max_initial_market_cap_sol, f"{market_cap:.2f} SOL", wait=market_cap == 0),
        _check("Slippage", slippage, f"<= {cfg.max_slippage_pct:.1%}", slippage <= cfg.max_slippage_pct, f"{slippage:.1%}", wait=slippage == 0),
        {"label": "Holder concentration", "state": "wait", "actual": "using safe default until holder API is connected", "target": f"top10 <= {cfg.max_top10_holder_pct:.0%}"},
        _check(
            "Bot / wash activity",
            max(wash, bot_score),
            f"wash <= {cfg.max_wash_trade_score:g}, bot <= {cfg.max_bot_activity_score:g}",
            wash <= cfg.max_wash_trade_score and bot_score <= cfg.max_bot_activity_score,
            f"wash {wash:.2f}, bot {bot_score:.2f}",
            wait=wash == 0 and bot_score == 0,
        ),
    ]


def _check(label: str, raw, target: str, passed: bool, actual: str, wait: bool = False) -> dict:
    return {"label": label, "state": "wait" if wait else "ok" if passed else "fail", "actual": actual, "target": target}


def _number(value) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _pump_price(payload: dict) -> float:
    sol = _number(payload.get("vSolInBondingCurve"))
    tokens = _number(payload.get("vTokensInBondingCurve"))
    return sol / tokens if sol > 0 and tokens > 0 else 0.0


def _parse_dt(value) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
