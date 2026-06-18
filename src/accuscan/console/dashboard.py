"""Console dashboard.

Renders the live ranking, best/second/avoid, suggested growth, alerts and paper
summary to the terminal. Uses `rich` if installed for a nicer table; otherwise
falls back to plain ANSI text so it always works.
"""

from __future__ import annotations

import asyncio

try:
    from rich.console import Console
    from rich.live import Live
    from rich.table import Table
    _HAS_RICH = True
except ImportError:
    _HAS_RICH = False

_RESET = "\033[0m"
_DIM = "\033[2m"
_C = {"READY": "\033[32m", "WATCH": "\033[33m", "HIGH_RISK": "\033[31m"}


def _plain(snap: dict) -> str:
    lines = []
    mode = snap.get("mode", "?")
    lines.append(f"AccuScan [{mode}/{snap.get('risk_profile','?')}]  "
                 f"best={snap.get('best_market')}  second={snap.get('second_best')}  "
                 f"avoid={','.join(snap.get('avoid_list', [])[:5])}")
    lines.append(f"{'SYMBOL':8} {'MQS':>6} {'STATUS':10} {'STAB':>6} {'JUMP':>6} "
                 f"{'DET':>5} {'DQ':>5} {'GR':>4} {'CONF':>5} {'HEALTH':12}")
    for r in snap.get("ranking", []):
        col = _C.get(r["status"], "")
        lines.append(
            f"{col}{r['symbol']:8} {r['mqs']:6.1f} {r['status']:10} {r['stability']:6.1f} "
            f"{r['jump_risk']:6.1f} {r.get('deterioration',0):5.0f} {r['data_quality']:5.0f} "
            f"{int(r['suggested_growth_rate']*100):3}% {r['confidence']*100:5.0f} "
            f"{(r.get('health') or '-'):12}{_RESET}"
        )
    if snap.get("paper"):
        p = snap["paper"]
        lines.append(f"{_DIM}paper: bal={p['balance']} net={p['net_pnl']} "
                     f"trades={p['trades']} wr={p['win_rate']*100:.0f}% dd={p['max_drawdown']}{_RESET}")
    alerts = snap.get("alerts", [])[-5:]
    for a in alerts:
        lines.append(f"  ! [{a['level']}] {a['symbol']} {a['reason']}: {a.get('message','')}")
    return "\n".join(lines)


def _rich_table(snap: dict) -> "Table":
    t = Table(title=f"AccuScan [{snap.get('mode')}/{snap.get('risk_profile')}]  "
                    f"best={snap.get('best_market')} second={snap.get('second_best')} "
                    f"avoid={','.join(snap.get('avoid_list', [])[:5])}")
    for col in ("Symbol", "MQS", "Status", "Stab", "Jump", "Deter", "DataQ", "Growth", "Conf", "Health"):
        t.add_column(col, justify="right" if col != "Symbol" else "left")
    style = {"READY": "green", "WATCH": "yellow", "HIGH_RISK": "red"}
    for r in snap.get("ranking", []):
        t.add_row(
            r["symbol"], f"{r['mqs']:.1f}",
            f"[{style.get(r['status'],'white')}]{r['status']}[/]",
            f"{r['stability']:.1f}", f"{r['jump_risk']:.1f}",
            f"{r.get('deterioration',0):.0f}", f"{r['data_quality']:.0f}",
            f"{int(r['suggested_growth_rate']*100)}%", f"{r['confidence']*100:.0f}",
            str(r.get("health") or "-"),
        )
    return t


async def run_console(app, refresh: float = 1.0, stop: asyncio.Event | None = None) -> None:
    if _HAS_RICH:
        console = Console()
        with Live(_rich_table(app.snapshot()), console=console, refresh_per_second=4) as live:
            while not (stop and stop.is_set()):
                live.update(_rich_table(app.snapshot()))
                await asyncio.sleep(refresh)
    else:
        while not (stop and stop.is_set()):
            print("\033[2J\033[H", end="")  # clear screen
            print(_plain(app.snapshot()))
            await asyncio.sleep(refresh)


def render_once(snap: dict) -> str:
    """Render a single snapshot to a string (used by tests / one-shot output)."""
    return _plain(snap)
