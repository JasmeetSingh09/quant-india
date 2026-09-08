"""
metric_applicability.py — some metrics are not missing, they do not exist.

SBIN's page showed a dash against EV/EBITDA, Gross Margin, D/E, Current Ratio
and Quick Ratio. That reads as "we tried and failed", and it is wrong. A bank
has no cost of goods sold, so gross margin has no denominator. Its liabilities
are customer deposits, so a current ratio measures nothing. It does not report
EBITDA, because interest is operating revenue rather than a financing cost.
Those figures are absent from the data because they are absent from the
concept.

Measured across fourteen securities: every gap was in the financial sector, and
the eleven non-financials had none at all. So this is not a collection failure
to be fixed by fetching harder. It is a taxonomy the app was not carrying.

Why this belongs on the server
------------------------------
It is a claim about accounting, it needs testing, and it is needed by anything
that renders or scores these fields. Encoding it in a JSX ternary would put an
untested accounting judgement in a template.

What it deliberately does NOT do
--------------------------------
It never says a metric is inapplicable in order to hide a value that IS present.
Applicability is about the concept; presence is about the data. A bank that
somehow reports a current ratio still gets it displayed, and the caller is told
both things separately rather than being handed a single conflated verdict.
"""

_BANK_ONLY = {
    "debt_to_equity": (
        "A bank's leverage is a regulatory capital question — CRAR and tier-1 "
        "ratios — not debt over equity. Deposits are its raw material, not "
        "borrowing."),
}

_FINANCIALS = {
    "ev_ebitda": (
        "Banks and lenders do not report EBITDA, so there is no denominator. "
        "Interest is operating revenue here, not a financing cost to add back."),
    "ebitda": (
        "Not reported by financial companies: interest is operating revenue "
        "rather than a financing cost."),
    "gross_margin": (
        "There is no cost of goods sold in lending, so gross margin has no "
        "denominator."),
    "current_ratio": (
        "A lender's current liabilities are customer deposits. The ratio "
        "measures nothing about its ability to meet them; capital adequacy "
        "does."),
    "quick_ratio": (
        "Same reason as the current ratio — the balance sheet is not a working "
        "capital cycle."),
}

# Matched against the industry string yfinance supplies, lower-cased.
_BANK_WORDS = ("bank",)
_FINANCIAL_WORDS = ("credit services", "capital markets", "asset management",
                    "insurance", "financial data", "mortgage", "financial "
                    "conglomerate", "shell companies", "reinsurance")


def _kind(sector: str = None, industry: str = None) -> str:
    s = (sector or "").strip().lower()
    i = (industry or "").strip().lower()
    if any(w in i for w in _BANK_WORDS):
        return "bank"
    if any(w in i for w in _FINANCIAL_WORDS):
        return "financial"
    # Sector alone is a weaker signal: "Financial Services" covers exchanges and
    # fintech, where these ratios can be perfectly meaningful. Only the industry
    # is trusted to make the call.
    return "other"


def applicability(sector: str = None, industry: str = None) -> dict:
    """
    Which metrics are not meaningful for this kind of company, and why.

    Returns {metric: reason}. A metric absent from the mapping is applicable.
    """
    kind = _kind(sector, industry)
    if kind == "other":
        return {}
    out = dict(_FINANCIALS)
    if kind == "bank":
        out.update(_BANK_ONLY)
    return out


def annotate(metrics: dict) -> dict:
    """
    The applicability block to travel with a metrics payload.

    `not_applicable` is the reason map. `unavailable` is the separate list of
    metrics that DO apply to this company and are still missing — which is the
    honest "we do not have this" set, now distinguishable from "this does not
    exist for a bank".
    """
    if not isinstance(metrics, dict):
        return {"not_applicable": {}, "unavailable": [], "company_kind": "other"}
    sector = metrics.get("sector")
    industry = metrics.get("industry")
    na = applicability(sector, industry)

    watched = ("pe_ratio", "forward_pe", "peg_ratio", "ev_ebitda", "ebitda",
               "price_to_book", "roe", "roa", "gross_margin",
               "operating_margin", "profit_margin", "debt_to_equity",
               "current_ratio", "quick_ratio")
    unavailable = [k for k in watched
                   if k not in na and metrics.get(k) is None]
    return {
        "company_kind": _kind(sector, industry),
        "not_applicable": na,
        "unavailable": unavailable,
        "note": ("not_applicable means the metric does not exist for this kind "
                 "of company. unavailable means it does exist and we do not "
                 "have it. Showing both as a dash conflated them."),
    }
