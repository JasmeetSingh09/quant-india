"""
audit_record.py — turn a production audit run into a permanent record.

Reads the raw per-domain JSON captured from /health/data-integrity and writes a
dated Markdown record. The point is that the record is generated FROM the
responses rather than typed from memory, so the numbers in it cannot drift from
the numbers the endpoint returned.

Every domain reports what it examined next to what it found. Where a domain
could not measure something, this prints UNMEASURED and the reason instead of
quietly omitting it -- an audit record with a gap in it is honest; one that
looks complete because the gap was left out is not.

Usage:
    python audit_record.py <dir-of-json> <output.md>
"""

import json
import os
import sys
from datetime import datetime, timezone

ORDER = ["prices", "continuity", "identity", "fundamentals_pit",
         "news", "missing_data"]


def load(d):
    out = {}
    for name in ORDER:
        p = os.path.join(d, f"{name}.json")
        if not os.path.exists(p):
            out[name] = {"status": "NOT RUN",
                         "reason": "no response captured for this domain"}
            continue
        try:
            with open(p, encoding="utf-8") as fh:
                out[name] = json.load(fh)
        except Exception as e:
            out[name] = {"status": "NOT RUN",
                         "reason": f"response unreadable: {type(e).__name__}: {e}"}
    return out


def fmt_examined(ex):
    if not ex:
        return "_nothing recorded_"
    if not isinstance(ex, dict):
        return f"`{ex}`"
    return ", ".join(f"**{k}** = {v:,}" if isinstance(v, int) else f"**{k}** = {v}"
                     for k, v in ex.items())


def main(src, dst):
    dom = load(src)
    snap = os.path.join(src, "snapshot.txt")
    when = "unknown"
    if os.path.exists(snap):
        when = open(snap, encoding="utf-8").read().strip()

    L = []
    A = L.append
    A("# Quant India — Production Data Integrity Audit")
    A("")
    A(f"- **Snapshot (UTC):** {when}")
    A(f"- **Record generated:** {datetime.now(timezone.utc).isoformat(timespec='seconds')}")
    A("- **Target:** production Postgres, via the read-only endpoint "
      "`/health/data-integrity` at https://quant-india.onrender.com")
    A("- **Mode:** read-only. No production row was created, altered, repaired, "
      "backfilled, normalised or deleted.")
    A("- **Model:** V1.4, frozen. No factor formula, weight, threshold, "
      "identity mapping or historical observation was changed.")
    A("")
    A("There is deliberately **no single data-health score**. A duplicate price "
      "row and an undated article are not the same unit; averaging them would "
      "invent a number that hides which half is broken.")
    A("")

    # ---------------------------------------------------------- status table
    A("## Status by domain")
    A("")
    A("| Domain | Status | Examined | Failed checks |")
    A("|---|---|---|---|")
    for name in ORDER:
        d = dom[name]
        f = d.get("findings") or []
        nfail = sum(1 for x in f if x.get("status") == "FAIL")
        ex = d.get("examined")
        exs = ""
        if isinstance(ex, dict):
            first = next(iter(ex.items()), None)
            if first:
                v = first[1]
                exs = f"{first[0]} = {v:,}" if isinstance(v, int) else f"{first[0]} = {v}"
        A(f"| `{name}` | **{d.get('status','?')}** | {exs or '—'} | "
          f"{nfail if f else '—'} |")
    A("")

    # ------------------------------------------------------------- per domain
    for name in ORDER:
        d = dom[name]
        A(f"## {name}")
        A("")
        A(f"**Status: {d.get('status','?')}**"
          + (f"  ·  {d.get('seconds')}s" if d.get("seconds") is not None else ""))
        A("")
        if d.get("reason"):
            A(f"> Not measured: {d['reason']}")
            A("")
        if d.get("examined"):
            A(f"Examined: {fmt_examined(d['examined'])}")
            A("")
        findings = d.get("findings") or []
        if findings:
            A("| Check | Result | Examined | Defects |")
            A("|---|---|---|---|")
            for f in findings:
                ex, bad = f.get("examined"), f.get("bad")
                exs = f"{ex:,}" if isinstance(ex, int) else "—"
                bads = f"{bad:,}" if isinstance(bad, int) else "—"
                A(f"| {f.get('check','?')} | **{f.get('status','?')}** | {exs} | {bads} |")
            A("")
            for f in findings:
                if f.get("detail"):
                    A(f"- _{f['check']}_ — {f['detail']}")
            A("")
            for f in findings:
                if f.get("offenders"):
                    A(f"**Offenders — {f['check']}:**")
                    A("")
                    for o in f["offenders"][:20]:
                        A(f"- `{o}`")
                    A("")

        for extra in ("fundamentals_history", "known_defect_sbin_state_bank",
                      "renames_observed", "worst_securities", "relevance_pct",
                      "calendar_gap_count", "gap_note", "note", "per_factor",
                      "distinct_titles", "titles_shared_by_more_than_one_security",
                      "cycle"):
            if extra in d and d[extra] not in (None, [], {}):
                A(f"**{extra}:**")
                A("")
                A("```json")
                A(json.dumps(d[extra], indent=1)[:4000])
                A("```")
                A("")

    with open(dst, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")
    print(f"written: {dst}  ({len(L)} lines)")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
