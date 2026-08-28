"""Where this tax year stands, as four ordered steps.

The app is a pipeline — documents in, figures out, income entered, moves
suggested — but four tabs side by side say nothing about order, about what is
still missing, or about a report computed from documents that have since
changed. This module answers those questions in one place so the UI can show
the state of the work rather than a row of containers.

Every step reports a `state`:

    todo       nothing done here yet
    attention  done, but something is wrong, missing or out of date
    done       nothing left to do

`next` is the first step that is not `done` — the one thing to do now.
"""

from datetime import date

from core import coverage, planner_ctx, repo, self_assessment, tax_years
from core import tips as tips_module

# Steps in the order they have to happen, because each one feeds the next.
STEP_ORDER = ("documents", "income", "report", "plan")

STEP_TITLES = {
    "documents": "Documents",
    "income": "Income",
    "report": "Report",
    "plan": "Plan",
}


def _has_p60(inputs: dict) -> bool:
    """Whether PAYE can be reconciled: pay AND a tax figure actually entered.

    Pay alone is not enough — a missing tax deducted read as nil would turn the
    whole year's PAYE into a shortfall."""
    for row in inputs.get("employments") or []:
        if not isinstance(row, dict):
            continue
        pay = row.get("pay")
        if pay in (None, "") or float(pay) <= 0:
            continue
        if row.get("tax_deducted") not in (None, ""):
            return True
    return False


def _documents_step(checklist: dict) -> dict:
    overall = checklist["overall"]
    accounts = checklist["accounts"]
    gaps = sum(len(a["gaps"]) for a in accounts)
    if overall == "no_accounts":
        return {
            "state": "todo",
            "headline": "No accounts yet",
            "detail": "Add each broker and bank you hold money with, then upload their exports.",
            "action": "Add an account",
        }
    if overall == "missing":
        return {
            "state": "attention",
            "headline": "No documents uploaded",
            "detail": "An account has no export yet, so its transactions are missing entirely.",
            "action": "Upload exports",
        }
    if overall == "gaps":
        needs = len(checklist["needs"])
        parts = []
        if gaps:
            parts.append(f"{gaps} period{'' if gaps == 1 else 's'} with no document")
        if needs:
            parts.append(f"{needs} account{'' if needs == 1 else 's'} still needed")
        return {
            "state": "attention",
            "headline": " · ".join(parts) or "History incomplete",
            "detail": (
                "Capital gains replay every purchase you ever made, so a gap anywhere in the "
                "history can move this year's figures."
            ),
            "action": "Fill the gaps",
        }
    n = len(accounts)
    return {
        "state": "done",
        "headline": f"{n} account{'' if n == 1 else 's'}, full history",
        "detail": "Every account is covered from its first activity to the end of the year.",
        "action": None,
    }


def _income_step(inputs: dict) -> dict:
    if not inputs:
        return {
            "state": "todo",
            "headline": "Nothing entered",
            "detail": (
                "Your P60, pension contributions and any income no broker export covers. "
                "Tax on investments depends on the rate band your salary puts you in, so "
                "none of it can be worked out without these."
            ),
            "action": "Enter your income",
        }
    if not _has_p60(inputs):
        return {
            "state": "attention",
            "headline": "No P60 — investments only",
            "detail": (
                "Without pay and tax deducted, the bill covers investment income alone and "
                "says nothing about what PAYE got wrong on your salary — routinely the "
                "larger half of what a return asks for."
            ),
            "action": "Add your P60",
        }
    return {
        "state": "done",
        "headline": "P60 entered",
        "detail": "Enough to reconcile PAYE and price the whole bill.",
        "action": None,
    }


def _report_step(user_id: int, tax_year: int, checklist: dict, current_hash: str | None) -> dict:
    run = repo.latest_ok_run(user_id, tax_year)
    if not run:
        return {
            "state": "todo",
            "headline": "Not calculated yet",
            "detail": "Replays your whole transaction history against HMRC's rules.",
            "action": "Calculate",
            "stale": False,
            "run_at": None,
        }
    # No hash from the caller means staleness is simply unknown — better to say
    # nothing than to call a good report out of date, or a stale one current.
    stale = current_hash is not None and run["input_hash"] != current_hash
    run_at = run["finished_at"] or run["created_at"]
    if stale:
        return {
            "state": "attention",
            "headline": "Out of date",
            "detail": (
                "Documents or settings changed since this ran, so the figures on it are not "
                "the ones your current documents produce."
            ),
            "action": "Recalculate",
            "stale": True,
            "run_at": run_at,
        }
    if checklist["overall"] not in ("ok",):
        return {
            "state": "attention",
            "headline": "Provisional",
            "detail": "Computed from an incomplete document set — the figures may move.",
            "action": "Fill document gaps",
            "stale": False,
            "run_at": run_at,
        }
    return {
        "state": "done",
        "headline": "Up to date",
        "detail": "Computed from every document currently uploaded.",
        "action": None,
        "stale": False,
        "run_at": run_at,
    }


def _plan_step(tips: list[dict], inputs: dict, in_progress: bool) -> dict:
    if not inputs:
        return {
            "state": "todo",
            "headline": "Needs your income",
            "detail": "Tips are priced at your marginal rate, which the income step establishes.",
            "action": None,
        }
    win = sum(t["estimated_win_gbp"] or 0 for t in tips)
    urgent = [t for t in tips if t.get("status") in ("expiring", "lost")]
    if not tips:
        return {
            "state": "done",
            "headline": "Nothing actionable",
            "detail": "No move this tool can price would improve the year.",
            "action": None,
        }
    headline = f"{len(tips)} tip{'' if len(tips) == 1 else 's'}"
    if win > 0:
        headline += f" · save ~£{win:,.0f}"
    return {
        "state": "attention" if urgent else "done",
        "headline": headline,
        "detail": (
            "Moves still open to you before 5 April."
            if in_progress
            else "What was and wasn't used — the record, not a to-do list."
        ),
        "action": "Review the tips" if urgent else None,
    }


def build(
    user_id: int,
    tax_year: int,
    today: date | None = None,
    current_hash: str | None = None,
) -> dict | None:
    """Every step's state for one tax year, plus the one thing to do next.

    `current_hash` is the input hash the engine would compute for the documents
    as they stand now; passing it is what lets the report step notice that it
    was calculated from a document set that has since changed. It is passed in
    rather than computed here so that this module stays clear of the engine."""
    year = tax_years.get_year(tax_year)
    if not year:
        return None
    today = today or date.today()
    checklist = coverage.checklist(user_id, tax_year)
    ctx = planner_ctx.build(user_id, tax_year, today)
    inputs = ctx["inputs"] if ctx else {}
    tips = tips_module.build_tips(ctx) if ctx else []
    in_progress = tax_year == tax_years.tax_year_of(today)

    steps = {
        "documents": _documents_step(checklist),
        "income": _income_step(inputs),
        "report": _report_step(user_id, tax_year, checklist, current_hash),
        "plan": _plan_step(tips, inputs, in_progress),
    }
    for key, step in steps.items():
        step["key"] = key
        step["title"] = STEP_TITLES[key]

    # The one thing to do now: the earliest step that is not finished. Steps
    # later in the chain are computed from the earlier ones, so fixing the first
    # broken link is always what changes the most.
    nxt = next(
        (steps[k] for k in STEP_ORDER if steps[k]["state"] != "done"),
        None,
    )

    bill = None
    if ctx:
        result = self_assessment.compute_for(inputs, year, ctx["invest"])
        bill = {
            "reconciled": result["reconciled"],
            "amount": round(float(result["sa_bill"]), 2),
            "investment_only": round(float(result["investment_only"]), 2),
            "due_date": tax_years.balancing_payment_due(tax_year).isoformat(),
        }

    return {
        "tax_year": tax_year,
        "label": tax_years.label(tax_year),
        "in_progress": in_progress,
        "year_end": tax_years.tax_year_end(tax_year).isoformat(),
        "filing_deadline": tax_years.filing_deadline(tax_year).isoformat(),
        # What the clock is actually running towards: an unfinished year still
        # has moves left in it, a finished one only has a return to file.
        "deadline": {
            "what": "act" if in_progress else "file",
            "date": (
                tax_years.tax_year_end(tax_year)
                if in_progress
                else tax_years.filing_deadline(tax_year)
            ).isoformat(),
            "days": (
                (
                    tax_years.tax_year_end(tax_year)
                    if in_progress
                    else tax_years.filing_deadline(tax_year)
                )
                - today
            ).days,
        },
        "steps": [steps[k] for k in STEP_ORDER],
        "next": {
            "key": nxt["key"],
            "title": nxt["title"],
            "action": nxt["action"],
            "why": nxt["detail"],
        }
        if nxt
        else None,
        "bill": bill,
    }
