"""
weekly_digest.py — the reason to come back next week.

Everything else in this app is pull: the user has to remember it exists. A
paper portfolio is exactly the kind of thing people start and then never look
at again, which makes the six-week pilot measure forgetfulness rather than the
product.

The digest is deliberately NOT a promotion. It reports what happened to the
portfolio the user already built, names the holding that drove it, and states
one thing worth checking. If there is nothing to say, it does not send —
a weekly email that says "no change" trains people to ignore the sender.
"""

from datetime import datetime, timedelta

MIN_DAYS = 5          # nothing meaningful to report before a week of trading


def _fmt_pct(v):
    return f"{'+' if (v or 0) >= 0 else ''}{v:.2f}%"


def build_digest(user_id: str = "public") -> dict:
    """
    Compose one user's digest. Returns {"skip": reason} when there is nothing
    worth sending, which the caller must honour.
    """
    from simulator import list_simulations, get_simulation_pnl

    sims = list_simulations(user_id=user_id) or []
    active = []
    for s in sims:
        name = s.get("name")
        try:
            days = (datetime.now() - datetime.fromisoformat(s["started_at"])).days
        except Exception:
            days = 0
        if days < MIN_DAYS:
            continue
        p = get_simulation_pnl(name, user_id=user_id)
        if not p or "error" in p or not p.get("positions"):
            continue
        active.append({"name": name, "days": days, "pnl": p})

    if not active:
        return {"skip": "no simulation old enough to report on"}

    blocks = []
    for a in active:
        p = a["pnl"]
        pos = sorted(p["positions"], key=lambda x: -(x.get("pnl_pct") or 0))
        best, worst = pos[0], pos[-1]
        total = p.get("total_pnl_pct") or 0

        # The one thing worth checking: whichever holding moved the portfolio
        # most, in whichever direction. Naming it is what makes this useful
        # rather than a number the user shrugs at.
        driver = max(pos, key=lambda x: abs((x.get("pnl_pct") or 0) *
                                            (x.get("allocation_pct") or 0)))
        blocks.append(f"""
        <div style="border:1px solid #1f2937;border-radius:10px;padding:16px;margin:12px 0">
          <div style="font-weight:600;color:#e5e7eb">{a['name']}</div>
          <div style="font-size:26px;font-weight:700;font-family:monospace;
                      color:{'#4ade80' if total >= 0 else '#f87171'};margin:6px 0">
            {_fmt_pct(total)}
          </div>
          <div style="color:#9ca3af;font-size:13px">after {a['days']} days</div>
          <div style="color:#9ca3af;font-size:13px;margin-top:10px">
            Best: <b style="color:#4ade80">{best['ticker'].replace('.NS','')}</b>
            {_fmt_pct(best.get('pnl_pct') or 0)} &nbsp;·&nbsp;
            Worst: <b style="color:#f87171">{worst['ticker'].replace('.NS','')}</b>
            {_fmt_pct(worst.get('pnl_pct') or 0)}
          </div>
          <div style="color:#6b7280;font-size:12px;margin-top:10px;
                      border-left:2px solid #374151;padding-left:10px">
            Most of that move came from
            <b>{driver['ticker'].replace('.NS','')}</b> — it is
            {driver.get('allocation_pct', 0):.0f}% of the portfolio and moved
            {_fmt_pct(driver.get('pnl_pct') or 0)}. Worth asking whether that is
            a position size you meant to take.
          </div>
        </div>""")

    html = f"""
    <div style="background:#030712;color:#e5e7eb;font-family:system-ui,sans-serif;
                padding:24px;max-width:600px">
      <h2 style="margin:0 0 4px">Your week on Quant India</h2>
      <p style="color:#9ca3af;font-size:13px;margin:0 0 16px">
        What happened to the portfolios you are paper-trading.
      </p>
      {''.join(blocks)}
      <p style="color:#6b7280;font-size:12px;margin-top:20px">
        Paper trading only — no real money moved. Open the simulator to change a
        weight and see what it would have done differently.
      </p>
    </div>"""

    return {
        "subject": f"Your week on Quant India — {active[0]['name']} "
                   f"{_fmt_pct(active[0]['pnl'].get('total_pnl_pct') or 0)}",
        "html": html,
        "n_portfolios": len(active),
    }


def send_digest(user_id: str = "public", to_email: str = None) -> dict:
    """Send one user's digest, or skip when there is nothing worth saying."""
    d = build_digest(user_id)
    if "skip" in d:
        return {"sent": False, **d}
    from alerts import send_email
    r = send_email(d["subject"], d["html"], to_email=to_email)
    return {"sent": bool(r and not r.get("error")), "n_portfolios": d["n_portfolios"],
            "result": r}
