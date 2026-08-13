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


# ---------------------------------------------------------------------------
# Scheduling
# ---------------------------------------------------------------------------

_scheduler = None


def send_all_digests() -> dict:
    """
    One weekly pass over everyone with a simulation worth reporting on.

    Sends to each user's OWN address, taken from the accounts that have
    simulations — never a blast to one list. A user with nothing to report is
    skipped rather than mailed, which is the whole point: an email that says
    "no change" teaches people to ignore the sender.
    """
    from db import get_conn
    try:
        conn = get_conn()
        rows = conn.execute(
            "SELECT DISTINCT user_id FROM simulations WHERE status = 'active' "
            "AND COALESCE(is_demo, 0) = 0").fetchall()
        conn.close()
    except Exception as e:
        return {"error": str(e)[:120]}

    sent, skipped, no_address = [], [], []
    for (uid,) in rows:
        try:
            d = build_digest(uid)
            if "skip" in d:
                skipped.append(uid[:8]); continue

            # HARD STOP. We do not store per-user email addresses — the address
            # only exists inside a request's JWT. Calling send_email without an
            # explicit recipient falls back to GMAIL_RECEIVER, which would post
            # every user's holdings to a single inbox. That is a privacy breach,
            # not a delivery bug, so the batch refuses rather than guessing.
            addr = _address_for(uid)
            if not addr:
                no_address.append(uid[:8]); continue

            from alerts import send_email
            r = send_email(d["subject"], d["html"], to_email=addr)
            if r and not r.get("error"):
                sent.append(uid[:8])
            else:
                no_address.append(uid[:8])
        except Exception:
            no_address.append(uid[:8])

    return {
        "sent": len(sent), "skipped_nothing_to_say": len(skipped),
        "skipped_no_address": len(no_address),
        "blocker": ("Digests can only go to users whose address we hold. Emails "
                    "live in the Supabase JWT, not in our database, so the batch "
                    "cannot address them. Store an opt-in address per user, or "
                    "drive digests from Supabase, before relying on this."
                    if no_address else None),
        "ran_at": datetime.now().isoformat(),
    }


def _address_for(user_id: str):
    """
    The address this user explicitly opted in with, or None. Only opted-in rows
    exist at all, so "no row" and "did not consent" are the same answer — which
    is why the batch can treat None as a hard stop rather than a lookup miss.
    """
    try:
        from user_prefs import address_for
        return address_for(user_id)
    except Exception:
        return None


def start_digest_scheduler(day_of_week: str = "sun", hour: int = 18):
    """Weekly, Sunday evening — before the week starts, not during it."""
    global _scheduler
    if _scheduler is not None:
        return {"status": "already_running"}
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        _scheduler = BackgroundScheduler(daemon=True)
        _scheduler.add_job(send_all_digests, "cron", day_of_week=day_of_week,
                           hour=hour, id="weekly_digest")
        _scheduler.start()
        return {"status": "started", "when": f"{day_of_week} {hour:02d}:00"}
    except Exception as e:
        return {"status": "failed", "error": str(e)[:120]}
