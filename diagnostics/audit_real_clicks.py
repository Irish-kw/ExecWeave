"""Audit existing fold contract with native pointer clicks and headed Chromium.

This is an audit probe, not the acceptance harness. Fixture injection in the
existing contract remains synthetic and does not prove provider capture.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from uuid import uuid4

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tests"))
import test_dashboard_round_fold_state_e2e as contract  # noqa: E402


def main() -> int:
    out = REPO / ".execweave-acceptance" / "real-click-audit" / uuid4().hex[:8]
    out.mkdir(parents=True)
    evidence: dict = {
        "fixture": "synthetic Codex four children, two root rounds",
        "clicks": [],
        "errors": [],
        "status": "FAIL",
    }

    def launch(playwright, executable):
        browser = playwright.chromium.launch(
            headless=False, **({"executable_path": executable} if executable else {})
        )
        browser.on("disconnected", lambda: evidence.update(browser_closed=True))
        return browser

    def click(page, node_id):
        if not getattr(page, "_audit_registered", False):
            page._audit_registered = True
            page.on("pageerror", lambda error: evidence["errors"].append(str(error)))
            page.on(
                "console",
                lambda message: (
                    evidence["errors"].append(message.text) if message.type == "error" else None
                ),
            )
        target = page.locator(".node[data-id=" + json.dumps(node_id) + "]")
        target.click(timeout=10000)
        page.wait_for_timeout(250)
        details = page.locator("#details")
        record = {
            "node": node_id,
            "live": page.url.startswith("http"),
            "details": details.inner_text(),
            "box": details.bounding_box(),
        }
        evidence["clicks"].append(record)
        page.screenshot(path=str(out / f"click-{len(evidence['clicks']):02d}.png"))

    contract._launch = launch
    contract._click_id = click
    try:
        contract.test_round_fold_state_survives_live_polling_payload_changes_and_agent_switches(out)
        assert not evidence["errors"], evidence["errors"]
        evidence["status"] = "PASS"
    except Exception as error:
        evidence["failure"] = f"{type(error).__name__}: {error}"
    finally:
        (out / "result.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "path": str(out),
                "status": evidence["status"],
                "failure": evidence.get("failure"),
                "clicks": len(evidence["clicks"]),
            }
        )
    )
    return 0 if evidence["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
