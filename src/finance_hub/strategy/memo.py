"""Markdown memo rendering for deployment plans.

Memos are generated artifacts written under the gitignored ``workspace/``
tree. They carry a visible banner so they are never mistaken for the source
of truth. The canonical state lives in SQLite; memos are derived readouts.

Shape (PRD story 93):
  status block → inputs used → DCA lines → one-time lines →
  do-not-buy/watchlist → evidence appendix
"""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Optional

# Configurable workspace root — monkeypatched in tests.
WORKSPACE_ROOT: Path = Path("workspace")

_BANNER = (
    "> **GENERATED ARTIFACT — DO NOT EDIT AS SOURCE OF TRUTH.**\n"
    "> Canonical state lives in SQLite. Regenerate by re-running the plan tool."
)

_FRONT_MATTER_TEMPLATE = """\
---
plan_id: {plan_id}
output_mode: {output_mode}
status: {status}
generated_at: {generated_at}
---
"""


def _dollars(micros: int) -> str:
    return f"${Decimal(micros) / 1_000_000:,.2f}"


def _draft_memo_dir() -> Path:
    return WORKSPACE_ROOT / "drafts"


def _approved_memo_dir() -> Path:
    return WORKSPACE_ROOT / "approved"


def _allocation_review_dir() -> Path:
    return WORKSPACE_ROOT / "allocation-reviews"


def _memo_dir_for_mode(output_mode: str) -> Path:
    if output_mode == "deployment_draft":
        return _draft_memo_dir()
    if output_mode == "allocation_review":
        return _allocation_review_dir()
    return WORKSPACE_ROOT / output_mode.replace("_", "-")


def draft_memo_path(plan_id: str, output_mode: str = "deployment_draft") -> Path:
    return _memo_dir_for_mode(output_mode) / f"{plan_id}.md"


def approved_memo_path(plan_id: str) -> Path:
    return _approved_memo_dir() / f"{plan_id}_approved.md"


def _render_line_section(
    sections: list[str],
    *,
    title: str,
    lines: list[dict],
    empty_message: str,
    unallocated_micros: int,
    unallocated_label: str,
) -> None:
    """Append a bucket section (DCA or one-time) of plan lines to ``sections``."""
    sections.append(f"## {title}")
    sections.append("")
    if lines:
        for line in lines:
            sections.append(
                f"- **{line['ticker']}** ({line['sleeve_key']}) — "
                f"{_dollars(line['amount_micros'])} [rank #{line['rank']}]"
            )
            if line.get("rationale"):
                sections.append(f"  *{line['rationale']}*")
    else:
        sections.append(empty_message)
    if unallocated_micros > 0:
        sections.append(f"- *{unallocated_label}: {_dollars(unallocated_micros)}*")
    sections.append("")


def render_draft_memo(plan: dict, generated_at: str) -> str:
    """Render a draft memo for any output mode."""
    plan_id = plan["plan_id"]
    output_mode = plan.get("output_mode", "deployment_draft")
    status = plan.get("status", "proposed")

    sections: list[str] = []

    # Front matter
    sections.append(
        _FRONT_MATTER_TEMPLATE.format(
            plan_id=plan_id,
            output_mode=output_mode,
            status=status,
            generated_at=generated_at,
        ).strip()
    )
    sections.append("")

    # Banner
    sections.append(_BANNER)
    sections.append("")

    # Title
    sections.append(f"# Deployment Plan: {plan_id}")
    sections.append("")

    # Status block
    sections.append("## Status")
    sections.append("")
    sections.append(f"- **Output mode:** `{output_mode}`")
    sections.append(f"- **Status:** `{status}`")
    snap_id = plan.get("portfolio_snapshot_id")
    if snap_id:
        sections.append(f"- **Portfolio snapshot:** `{snap_id}`")
    strat_id = plan.get("strategy_version_id")
    if strat_id:
        sections.append(f"- **Strategy version:** `{strat_id}`")
    band = plan.get("snapshot_freshness_band")
    if band:
        sections.append(f"- **Snapshot freshness:** `{band}` ({plan.get('snapshot_days_old', '?')} days old)")
    warnings = plan.get("warnings", [])
    if warnings:
        sections.append(f"- **Warnings/blocks:** {len(warnings)} item(s)")
    sections.append("")

    # Inputs used
    sections.append("## Inputs Used")
    sections.append("")
    sections.append(f"- **Deployable cash:** {_dollars(plan.get('deployable_cash_micros', 0))}")
    sections.append(f"- **DCA budget:** {_dollars(plan.get('dca_budget_micros', 0))}")
    sections.append(f"- **One-time budget:** {_dollars(plan.get('one_time_buy_budget_micros', 0))}")
    sections.append(f"- **Benchmark:** `{plan.get('benchmark_ticker', 'SPY')}`")
    sections.append(f"- **Risk mode:** `{plan.get('risk_mode', 'balanced')}`")
    cadence = plan.get("dca_cadence")
    if cadence:
        sections.append(f"- **DCA cadence:** {cadence} (memo context only; no automation)")
    sections.append("")

    lines = plan.get("lines", [])
    dca_lines = [l for l in lines if l["bucket"] == "dca"]
    one_time_lines = [l for l in lines if l["bucket"] == "one_time"]

    _render_line_section(
        sections,
        title="DCA Lines",
        lines=dca_lines,
        empty_message="*No DCA lines.*",
        unallocated_micros=plan.get("dca_unallocated_micros", 0),
        unallocated_label="Unallocated DCA cash",
    )
    _render_line_section(
        sections,
        title="One-Time Lines",
        lines=one_time_lines,
        empty_message="*No one-time buy lines.*",
        unallocated_micros=plan.get("one_time_unallocated_micros", 0),
        unallocated_label="Unallocated one-time cash",
    )

    # Warnings / blocks
    if warnings:
        sections.append("## Warnings and Blocks")
        sections.append("")
        for w in warnings:
            severity_tag = "[BLOCK]" if w["severity"] == "block" else "[warn]"
            ticker_part = f" ({w['ticker']})" if w.get("ticker") else ""
            sections.append(f"- {severity_tag} **{w['code']}**{ticker_part}: {w['message']}")
        sections.append("")

    # Do-not-buy / watchlist
    watchlist = plan.get("watchlist", [])
    if watchlist:
        sections.append("## Watchlist / Do-Not-Buy")
        sections.append("")
        for entry in watchlist:
            detail = f" — {entry['detail']}" if entry.get("detail") else ""
            sections.append(f"- **{entry['ticker']}** ({entry['reason']}){detail}")
        sections.append("")

    # Evidence appendix
    evidence = plan.get("evidence", [])
    if evidence:
        sections.append("## Evidence Appendix")
        sections.append("")
        sections.append("*References stored at plan generation time.*")
        sections.append("")
        by_ticker: dict[str, list[dict]] = {}
        for ev in evidence:
            t = ev.get("ref_key", "?")
            by_ticker.setdefault(t, []).append(ev)
        for ticker, refs in sorted(by_ticker.items()):
            sections.append(f"### {ticker}")
            for ref in refs:
                summary = ref.get("summary") or ""
                sections.append(
                    f"- `{ref['evidence_type']}` → `{ref['ref_table']}:{ref['ref_key']}`"
                    + (f" — {summary}" if summary else "")
                )
            sections.append("")

    return "\n".join(sections)


def render_approved_memo(plan: dict, approved_at: str) -> str:
    """Render a separate, immutable approved memo for an approved plan."""
    plan_id = plan["plan_id"]

    sections: list[str] = []

    # Front matter
    sections.append(
        _FRONT_MATTER_TEMPLATE.format(
            plan_id=plan_id,
            output_mode=plan.get("output_mode", "deployment_draft"),
            status="approved",
            generated_at=approved_at,
        ).strip()
    )
    sections.append("")

    # Banner
    sections.append(_BANNER)
    sections.append("")

    sections.append(f"# APPROVED Deployment Plan: {plan_id}")
    sections.append("")
    sections.append(f"> **Approved at:** {approved_at}")
    sections.append("")

    # Delegate the body to the draft renderer then strip the front matter and title
    draft_body = render_draft_memo(plan, generated_at=approved_at)
    # Skip front matter (--- ... ---) and first heading
    lines_iter = iter(draft_body.split("\n"))
    in_front_matter = False
    past_front_matter = False
    past_title = False
    body_lines: list[str] = []
    for line in lines_iter:
        if line == "---" and not past_front_matter:
            in_front_matter = not in_front_matter
            if not in_front_matter:
                past_front_matter = True
            continue
        if in_front_matter:
            continue
        if not past_title and line.startswith("# "):
            past_title = True
            continue
        body_lines.append(line)

    sections.extend(body_lines)
    return "\n".join(sections)


def write_memo(content: str, path: Path) -> None:
    """Write memo content to path, creating parent directories as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def write_draft_memo(plan: dict, generated_at: str) -> Optional[Path]:
    """Write the draft memo and return its path, or None if mode has no memo dir."""
    output_mode = plan.get("output_mode", "deployment_draft")
    if output_mode not in ("deployment_draft", "allocation_review"):
        return None
    path = draft_memo_path(plan["plan_id"], output_mode)
    content = render_draft_memo(plan, generated_at=generated_at)
    write_memo(content, path)
    return path


def write_approved_memo(plan_id: str, content: str) -> Path:
    """Write the approved memo and return its path."""
    path = approved_memo_path(plan_id)
    write_memo(content, path)
    return path
