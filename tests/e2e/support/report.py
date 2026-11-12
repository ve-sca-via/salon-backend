"""Checklist-style result collection + console/markdown report for the E2E suite."""
from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

ICONS = {
    "passed": "✅",
    "failed": "❌",
    "error": "❌",
    "skipped": "⏭",
    "xfailed": "🐞",   # known backend bug / incomplete feature (reason starts BUG:/INCOMPLETE:)
    "xpassed": "✨",   # was marked as a known bug but now passes - remove the marker
    "notrun": "·",
}


@dataclass
class StepResult:
    nodeid: str
    flow: str
    flow_title: str
    index: int
    title: str
    outcome: str = "notrun"
    reason: str = ""
    duration: float = 0.0


@dataclass
class Collector:
    steps: dict[str, StepResult] = field(default_factory=dict)
    order: list[str] = field(default_factory=list)
    started: datetime = field(default_factory=datetime.now)
    meta: dict[str, str] = field(default_factory=dict)
    cleanup: dict[str, int] | None = None
    notes: list[str] = field(default_factory=list)

    def register(self, item) -> None:
        module = item.module
        flow = getattr(module, "FLOW", module.__name__.rsplit(".", 1)[-1])
        flow_title = getattr(module, "FLOW_TITLE", flow)
        doc = (getattr(item.function, "__doc__", None) or "").strip().splitlines()
        title = doc[0].strip() if doc else item.name
        callspec = getattr(item, "callspec", None)
        if callspec is not None:
            title += f" [{callspec.id}]"
        index = sum(1 for s in self.steps.values() if s.flow == flow) + 1
        self.steps[item.nodeid] = StepResult(item.nodeid, flow, flow_title, index, title)
        self.order.append(item.nodeid)

    def record(self, report) -> None:
        step = self.steps.get(report.nodeid)
        if step is None:
            return
        step.duration += getattr(report, "duration", 0.0) or 0.0
        wasxfail = getattr(report, "wasxfail", None)
        if report.when == "call":
            if wasxfail is not None:
                step.outcome = "xfailed" if report.skipped else "xpassed"
                step.reason = wasxfail or ""
            elif report.passed:
                step.outcome = "passed"
            elif report.failed:
                step.outcome = "failed"
                step.reason = _failure_text(report)
            elif report.skipped:
                step.outcome = "skipped"
                step.reason = _skip_reason(report)
        elif report.when == "setup":
            if report.skipped:
                if wasxfail is not None:
                    step.outcome, step.reason = "xfailed", wasxfail
                else:
                    step.outcome, step.reason = "skipped", _skip_reason(report)
            elif report.failed:
                step.outcome, step.reason = "error", "setup error: " + _failure_text(report)
        elif report.when == "teardown" and report.failed and step.outcome == "passed":
            step.outcome, step.reason = "error", "teardown error: " + _failure_text(report)

    # ------------------------------------------------------------------
    def flows(self) -> list[tuple[str, str, list[StepResult]]]:
        out: dict[str, tuple[str, list[StepResult]]] = {}
        for nodeid in self.order:
            s = self.steps[nodeid]
            out.setdefault(s.flow, (s.flow_title, []))[1].append(s)
        return [(k, v[0], v[1]) for k, v in out.items()]

    def totals(self) -> dict[str, int]:
        t: dict[str, int] = {}
        for s in self.steps.values():
            t[s.outcome] = t.get(s.outcome, 0) + 1
        return t

    def console_lines(self) -> list[str]:
        lines = ["", "=" * 78, f"E2E CHECKLIST  {self.meta.get('base_url', '')}  run={self.meta.get('run_id', '')}", "=" * 78]
        for flow, title, steps in self.flows():
            ok = sum(1 for s in steps if s.outcome == "passed")
            lines.append(f"\n[{flow}] {title}  ({ok}/{len(steps)} passed)")
            for s in steps:
                line = f"  {ICONS.get(s.outcome, '?')} {s.index:>2}. {s.title}"
                if s.outcome != "passed" and s.reason:
                    line += f"\n        -> {_one_line(s.reason, 220)}"
                lines.append(line)
        t = self.totals()
        lines.append("\n" + "-" * 78)
        lines.append("TOTAL: " + ", ".join(f"{k}={v}" for k, v in sorted(t.items())))
        if self.cleanup is not None:
            lines.append("cleanup: " + (", ".join(f"{k}={v}" for k, v in sorted(self.cleanup.items())) or "nothing to delete"))
        return lines

    def markdown(self) -> str:
        t = self.totals()
        md = [
            f"# E2E run {self.meta.get('run_id', '')}",
            "",
            f"- **Target:** `{self.meta.get('base_url', '')}`",
            f"- **Started:** {self.started.strftime('%Y-%m-%d %H:%M:%S')}  ",
            f"- **Git:** `{self.meta.get('git', '?')}`",
            f"- **Payments (Razorpay) steps:** {self.meta.get('payments', 'disabled')}",
            f"- **Totals:** " + ", ".join(f"{ICONS.get(k, '')} {k} {v}" for k, v in sorted(t.items())),
            "",
            "Legend: ✅ passed · ❌ failed/error · ⏭ skipped · 🐞 known backend bug / incomplete (xfail) · ✨ known bug now passing",
            "",
        ]
        for flow, title, steps in self.flows():
            ok = sum(1 for s in steps if s.outcome == "passed")
            md += [f"## {title} (`{flow}`) — {ok}/{len(steps)} passed", ""]
            for s in steps:
                box = "x" if s.outcome == "passed" else " "
                line = f"- [{box}] {ICONS.get(s.outcome, '?')} **{s.index}. {s.title}**"
                if s.outcome != "passed" and s.reason:
                    line += f" — {_one_line(s.reason, 600)}"
                md.append(line)
            md.append("")
        known = [s for s in self.steps.values() if s.outcome == "xfailed"]
        if known:
            md += ["## Known backend bugs / incomplete features observed", ""]
            md += [f"- `{s.flow}` step {s.index} ({s.title}): {_one_line(s.reason, 600)}" for s in known]
            md.append("")
        if self.notes:
            md += ["## Notes", ""] + [f"- {n}" for n in self.notes] + [""]
        if self.cleanup is not None:
            md += ["## Cleanup", "", ", ".join(f"{k}: {v}" for k, v in sorted(self.cleanup.items())) or "nothing to delete", ""]
        return "\n".join(md)

    def write(self, reports_dir: Path) -> Path:
        reports_dir.mkdir(parents=True, exist_ok=True)
        path = reports_dir / f"{self.started.strftime('%Y%m%d-%H%M%S')}.md"
        path.write_text(self.markdown(), encoding="utf-8")
        return path


def git_rev() -> str:
    try:
        sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=10).stdout.strip()
        branch = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True, timeout=10).stdout.strip()
        return f"{branch}@{sha}" if sha else "?"
    except Exception:  # noqa: BLE001
        return "?"


def _skip_reason(report) -> str:
    lr = report.longrepr
    if isinstance(lr, tuple) and len(lr) == 3:
        return str(lr[2]).removeprefix("Skipped: ")
    return str(lr)


def _failure_text(report) -> str:
    crash = getattr(getattr(report, "longrepr", None), "reprcrash", None)
    if crash is not None and getattr(crash, "message", None):
        return crash.message
    return str(report.longrepr)[-800:]


def _one_line(text: str, limit: int) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 3] + "..."
