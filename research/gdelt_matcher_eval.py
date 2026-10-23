"""
gdelt_matcher_eval.py — the M-4 company-matcher evaluation (docs/PREREG_GDELT_MATCHER_EVALUATION_DRAFT_2026-10-15.md).

Subcommands
  categories                  assign every company to A/B/C/D by the frozen rules (section 5)
  sample  --dev | --final     draw the three samples (section 4):
                                P  600 matched headlines
                                Cs 400 not matched, with a strong (distinctive) candidate term
                                Cw 200 not matched, with only an ordinary candidate word
                                R 1000 headlines with no candidate term
                              --dev    reads ONLY already-seen days (1, 11, 21) to test this tool
                              --final  reads the evaluation days (5, 15, 25); refuses unless the
                                       prereg commit is given and the matcher and name list hashes match
  packet                      blind labelling packet: P, C and R shuffled together, with no sample,
                              category or matcher decision shown
  score                       metrics from adjudicated labels (precision, stratum-weighted recall,
                              false matches per 10,000, coverage proxy, Cohen's kappa)

The matcher is research/gdelt_strict.py at 00bb4e0, imported, never restated. Read-only on the archive.
"""
import collections
import csv
import glob
import gzip
import hashlib
import html
import json
import os
import random
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gdelt_strict as G  # noqa: E402

GDELT = os.path.join(os.path.expanduser("~"), "quant_data", "gdelt")
NAMES = os.path.join(os.path.expanduser("~"), "quant_data", "gdelt_names.json")
MATCHER_COMMIT = "00bb4e0"
NAMES_SHA16 = "a3c5cb00f700bb73"
SEED = 20261016
DEV_DAYS, FINAL_DAYS, RESERVE_DAYS = {1, 11, 21}, {5, 15, 25}, {2, 12, 22}
TITLES_FROM = "20190922"
N_P, N_R = 600, 1000
# C is split (owner, 2026-10-23) so the labelling effort goes where misses are likely:
#   Cs (strong): the headline contains a distinctive identifier of a listed company
#   Cw (weak):   only an ordinary word from a company's name
N_CS, N_CW = 400, 200
GROUP_TOKENS = {"adani", "aditya", "bajaj", "birla", "godrej", "hero", "hindustan", "mahindra", "reliance", "tata"}
# Candidate words exclude legal words (the matcher's own LEGAL list), words under 3 characters and this
# fixed stoplist; otherwise "india" in "Coal India" would make almost every headline a candidate.
STOP = {"india", "indian", "the", "of", "and", "company"}


def sha16(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()[:16]


def matcher_unchanged():
    """research/gdelt_strict.py must be byte-identical to its 00bb4e0 version."""
    want = subprocess.run(["git", "show", f"{MATCHER_COMMIT}:research/gdelt_strict.py"], capture_output=True,
                          cwd=os.path.dirname(HERE)).stdout
    have = open(os.path.join(HERE, "gdelt_strict.py"), "rb").read()
    norm = lambda b: b.replace(b"\r\n", b"\n")
    return bool(want) and norm(want) == norm(have)


def categories(table, rx):
    """Section 5, in order of precedence A > B > C > D."""
    out = {}
    for sym, v in table.items():
        tick = re.sub(r"[^a-z0-9]", "", sym.lower())
        first = (G.NAME_OVERRIDE.get(sym, v["name"]) or v["name"] or "").split()[:1]
        terms = [x for x, _ in rx.get(sym, [])]
        if tick in G.DROP_TICKER and sym not in G.UPPER_ONLY:
            out[sym] = "A"
        elif first and first[0].lower() in GROUP_TOKENS:
            out[sym] = "B"
        elif sym in G.UPPER_ONLY or any(len(re.sub(r"[^a-z0-9]", "", x)) <= 4 for x in terms):
            out[sym] = "C"
        else:
            out[sym] = "D"
    return out


def candidate_words(table):
    words = {}
    for sym, v in table.items():
        src = [v.get("name") or "", sym] + list(G.ALIASES.get(sym, []))
        ws = set()
        for s in src:
            for w in re.findall(r"[a-z0-9&]+", G.norm(s)):
                if len(w) >= 3 and w not in STOP and w not in G.LEGAL:
                    ws.add(w)
        words[sym] = ws
    return words


def strong_terms(table):
    """Distinctive identifiers: the ticker, the hand-listed short names, every two-word fragment of the
    company's core name, and a one-word core name. Ordinary-word tickers and names (M-4's DROP_TICKER)
    are never strong."""
    out = {}
    for sym, v in table.items():
        ts = set()
        tick = re.sub(r"[^a-z0-9]", "", sym.lower())
        if len(tick) >= 3 and tick not in G.DROP_TICKER:
            ts.add(tick)
        for a in G.ALIASES.get(sym, []):
            a = G.norm(a)
            if a and a not in G.DROP_TICKER and len(a.replace(" ", "")) >= 3:
                ts.add(a)
        core = G.core(G.NAME_OVERRIDE.get(sym, v.get("name")) or v.get("name") or "")
        words = core.split()
        for i in range(len(words) - 1):
            pair = words[i:i + 2]
            if not all(w in STOP or w in G.LEGAL for w in pair):
                ts.add(" ".join(pair))
        if len(words) == 1 and words[0] not in G.DROP_TICKER and len(words[0]) >= 3:
            ts.add(words[0])
        out[sym] = ts
    return out


def headlines(days):
    """Unique titled headlines on the given days of the month, from TITLES_FROM on."""
    seen = set()
    for f in sorted(glob.glob(os.path.join(GDELT, "*.tsv.gz"))):
        d = os.path.basename(f)[:8]
        if int(d[6:8]) not in days or d < TITLES_FROM:
            continue
        with gzip.open(f, "rt", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                p = line.rstrip("\n").split("\t")
                if len(p) < 5 or not p[3] or p[3] in seen:
                    continue
                seen.add(p[3])
                yield d, p[1], p[3], p[4]


def sample(mode, out_dir, prereg_commit=None):
    if mode == "--final":
        assert prereg_commit, "--final needs the commit of the approved pre-registration"
        assert matcher_unchanged(), "research/gdelt_strict.py differs from 00bb4e0; refusing"
        assert sha16(NAMES) == NAMES_SHA16, "gdelt_names.json differs from the frozen list; refusing"
        days = FINAL_DAYS
    elif mode == "--dev":
        days = DEV_DAYS
    else:
        raise SystemExit("mode must be --dev or --final")
    assert not (days & RESERVE_DAYS)
    table = json.load(open(NAMES))
    rx, confirm, _ = G.build(NAMES)
    cw = candidate_words(table)
    alt = lambda ws: re.compile(r"(?<![a-z0-9&])(" + "|".join(sorted(map(re.escape, ws), key=len, reverse=True)) + r")(?![a-z0-9&])")
    word_rx = {sym: alt(ws) for sym, ws in cw.items() if ws}
    strong_rx = {sym: alt(ws) for sym, ws in strong_terms(table).items() if ws}
    P, Cs, Cw, R = [], [], [], []
    for d, src, title, orgs in headlines(days):
        m = G.match(title, orgs, rx, confirm)
        if m:
            P.append({"day": d, "source": src, "title": title, "matched": m})
            continue
        t = G.norm(html.unescape(title))
        cands = sorted(sym for sym, r in word_rx.items() if r.search(t))
        strong = sorted(sym for sym, r in strong_rx.items() if r.search(t))
        row = {"day": d, "source": src, "title": title, "candidates": cands, "strong": strong}
        (Cs if strong else Cw if cands else R).append(row)
    rnd = random.Random(SEED)
    pops = {"P": len(P), "Cs": len(Cs), "Cw": len(Cw), "R": len(R)}
    picks = {"P": rnd.sample(P, min(N_P, len(P))), "Cs": rnd.sample(Cs, min(N_CS, len(Cs))),
             "Cw": rnd.sample(Cw, min(N_CW, len(Cw))), "R": rnd.sample(R, min(N_R, len(R)))}
    os.makedirs(out_dir, exist_ok=True)
    json.dump({"mode": mode, "days": sorted(days), "seed": SEED, "populations": pops,
               "prereg_commit": prereg_commit, "samples": picks},
              open(os.path.join(out_dir, "samples.json"), "w", encoding="utf-8"), indent=1)
    print(json.dumps({"mode": mode, "days": sorted(days), "populations": pops,
                      "drawn": {k: len(v) for k, v in picks.items()}}))


def packet(out_dir):
    s = json.load(open(os.path.join(out_dir, "samples.json"), encoding="utf-8"))
    rows = [(k, r) for k in s["samples"] for r in s["samples"][k]]
    random.Random(SEED + 1).shuffle(rows)
    key, blind = [], []
    for i, (k, r) in enumerate(rows, 1):
        blind.append({"n": i, "date": r["day"], "source": r["source"], "headline": html.unescape(r["title"])})
        key.append({"n": i, "sample": k, "matched": r.get("matched"), "candidates": r.get("candidates")})
    table = json.load(open(NAMES))
    json.dump({"companies": {s_: v["name"] for s_, v in sorted(table.items())}, "headlines": blind},
              open(os.path.join(out_dir, "blind_packet.json"), "w", encoding="utf-8"), indent=1)
    json.dump(key, open(os.path.join(out_dir, "packet_key.json"), "w", encoding="utf-8"), indent=1)
    print(len(blind), "headlines in the blind packet; the key is kept separately")


def kappa(a, b):
    n = len(a)
    if not n:
        return None
    po = sum(x == y for x, y in zip(a, b)) / n
    ca, cb = collections.Counter(a), collections.Counter(b)
    pe = sum(ca[k] * cb[k] for k in set(ca) | set(cb)) / (n * n)
    return (po - pe) / (1 - pe) if pe < 1 else 1.0


def score(out_dir, labels_csv):
    """labels_csv columns: n, reader1, reader2, final (each a ';'-separated list of tickers, or 'none')."""
    s = json.load(open(os.path.join(out_dir, "samples.json"), encoding="utf-8"))
    key = {k["n"]: k for k in json.load(open(os.path.join(out_dir, "packet_key.json"), encoding="utf-8"))}
    cat = categories(json.load(open(NAMES)), G.build(NAMES)[0])
    lab = {int(r["n"]): r for r in csv.DictReader(open(labels_csv, encoding="utf-8"))}
    parse = lambda x: set() if not x or x.strip().lower() == "none" else {t.strip() for t in x.split(";") if t.strip()}
    pops, drawn = s["populations"], {k: len(v) for k, v in s["samples"].items()}
    tp = fp = 0
    by_cat = collections.defaultdict(lambda: [0, 0])
    miss = {k: 0 for k in s["populations"] if k != "P"}
    pairs = []
    for n, k in key.items():
        if n not in lab:
            continue
        truth = parse(lab[n]["final"])
        r1, r2 = parse(lab[n]["reader1"]), parse(lab[n]["reader2"])
        # Kappa over EVERY headline x company decision. The first version kept only pairs one reader
        # named, which drops the both-no cases kappa needs (fixed 2026-10-23, before any scoring).
        for sym in cat:
            pairs.append((sym in r1, sym in r2))
        if k["sample"] == "P":
            for sym in k["matched"]:
                ok = sym in truth
                tp += ok; fp += not ok
                by_cat[cat.get(sym, "?")][0] += ok; by_cat[cat.get(sym, "?")][1] += 1
        else:
            miss[k["sample"]] += len(truth)
    w = lambda k: pops[k] / max(drawn[k], 1)
    tp_pop, fp_pop = tp * w("P"), fp * w("P")
    fn_pop = sum(miss[k] * w(k) for k in miss)
    total = sum(pops.values())
    out = {
        "precision": tp / max(tp + fp, 1),
        "precision_by_category": {c: v[0] / v[1] for c, v in by_cat.items() if v[1]},
        "n_by_category": {c: v[1] for c, v in by_cat.items()},
        "recall": tp_pop / max(tp_pop + fn_pop, 1e-9),
        "false_matches_per_10000": 1e4 * fp_pop / max(total, 1),
        "kappa_any_company": kappa([a for a, _ in pairs], [b for _, b in pairs]) if pairs else None,
    }
    json.dump(out, open(os.path.join(out_dir, "metrics.json"), "w"), indent=1)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "categories":
        t = json.load(open(NAMES))
        c = categories(t, G.build(NAMES)[0])
        print(json.dumps(collections.Counter(c.values())), {k: sorted(s for s, v in c.items() if v == k)[:12] for k in "ABC"})
        if len(sys.argv) > 2:
            json.dump(c, open(sys.argv[2], "w"), indent=1, sort_keys=True)
    elif cmd == "sample":
        sample(sys.argv[2], sys.argv[3], sys.argv[sys.argv.index("--prereg") + 1] if "--prereg" in sys.argv else None)
    elif cmd == "packet":
        packet(sys.argv[2])
    elif cmd == "score":
        score(sys.argv[2], sys.argv[3])
