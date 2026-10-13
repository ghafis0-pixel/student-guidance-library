"""Read-only work-register checks and an explicit, user-approved update boundary."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import tempfile
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

try:
    from . import privacy_guard
    from . import check_weekly_plan_gate
except ImportError:
    import privacy_guard
    import check_weekly_plan_gate

ROOT = Path(__file__).resolve().parents[1]
ACTION_TYPES = {"executive_action", "weekly_plan_execution"}
STATES = {
    "daily_incident": {"recorded", "diagnosing"},
    "followup_case": {"active", "closed"},
    "executive_action": {"proposed", "approved", "ready_for_execution", "output_created", "executed", "closed"},
    "weekly_plan_execution": {"proposed", "approved", "ready_for_execution", "output_created", "executed", "closed"},
    "created_output": {"output_created"},
}
ORIGINS = {"user_input", "approved_plan", "diagnostic_action"}
COMMON_FIELDS = {
    "work_id", "type", "title", "status", "origin", "decision_refs", "output_refs",
    "evidence_refs", "information_refs", "next_action", "status_updated_at", "status_reason",
}
TYPE_FIELDS = {
    "daily_incident": {"followup_assessment"},
    "followup_case": {"incident_refs", "followup_assessment", "information_assessment", "reopening", "closure"},
    "created_output": set(),
    **{kind: {"requires_execution_cycle", "evidence_required_for_closure", "approval",
              "execution_status", "execution", "closure", "gate"} for kind in ACTION_TYPES},
}


def text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def iso_date(value: Any) -> bool:
    try:
        return text(value) and bool(date.fromisoformat(value))
    except ValueError:
        return False


def digest(data: Any) -> str:
    return hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def file_at(root: Path, relative: Any) -> Path | None:
    if not text(relative):
        return None
    path = (root / relative).resolve()
    return path if path.is_relative_to(root.resolve()) and path.is_file() else None


def reference_ok(root: Path, value: Any) -> bool:
    if not text(value):
        return False
    if value.startswith(("user_input:", "restricted:")):
        return bool(value.split(":", 1)[1].strip())
    if re.fullmatch(r"DEC-\d{3}", value):
        return f"## {value}\n" in (root / "context/decisions.md").read_text(encoding="utf-8")
    return file_at(root, value) is not None


def validate_register(data: Any, root: Path = ROOT, previous: dict | None = None,
                      *, audience: str = "public", authorization_ref: str | None = None) -> list[str]:
    errors = [f"privacy: {finding['location']} {finding['code']}" for finding in
              privacy_guard.scan_data(data, audience=audience, authorization_ref=authorization_ref)]
    if not isinstance(data, dict) or data.get("schema_version") != "1.1" or not iso_date(data.get("updated_at")):
        return ["register: expected schema 1.1 and updated_at ISO date"]
    items = data.get("items")
    if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
        return ["register.items must be an array of objects"]
    by_id: dict[str, dict] = {}
    for item in items:
        ident = item.get("work_id")
        if not text(ident) or not re.fullmatch(r"(WORK|INC|CASE|ACT|OUT)-\d{3,}", ident):
            errors.append("record: invalid work_id")
            continue
        if ident in by_id:
            errors.append(f"{ident}: duplicate work_id")
        by_id[ident] = item
    for ident, item in by_id.items():
        def check(condition: bool, message: str) -> None:
            if not condition:
                errors.append(f"{ident}: {message}")

        kind, state = item.get("type"), item.get("status")
        if not isinstance(kind, str) or kind not in STATES:
            check(False, "unknown record type")
            continue
        check(not set(item) - COMMON_FIELDS - TYPE_FIELDS[kind], "unknown fields for record type")
        if not isinstance(state, str) or state not in STATES[kind]:
            check(False, "invalid status for record type")
            continue
        check(text(item.get("title")), "title required")
        origin = item.get("origin", {})
        check(isinstance(origin, dict) and isinstance(origin.get("kind"), str) and origin.get("kind") in ORIGINS
              and reference_ok(root, origin.get("reference")), "valid authorized origin required")
        if isinstance(origin, dict) and origin.get("kind") == "approved_plan":
            check(reference_ok(root, origin.get("approval_ref")), "approved plan origin needs approval_ref")
        valid_refs = True
        for field in ("output_refs", "evidence_refs", "decision_refs", "information_refs"):
            refs = item.get(field, [])
            valid = isinstance(refs, list) and all(reference_ok(root, ref) for ref in refs)
            check(valid, f"{field} must contain resolvable references")
            valid_refs = valid_refs and valid
        if not valid_refs:
            continue
        execution_status = item.get("execution_status", "not_reported")
        check(isinstance(execution_status, str) and execution_status in {"not_reported", "executed", "not_required"},
              "invalid execution_status")
        if not isinstance(execution_status, str) or execution_status not in {"not_reported", "executed", "not_required"}:
            continue
        if kind not in ACTION_TYPES:
            check(execution_status == "not_reported" and not item.get("execution"),
                  "incident/case/output record is not an executed action")
        if kind in {"created_output"} or state == "output_created":
            check(bool(item.get("output_refs")), "created output needs output_refs")
            check(execution_status == "not_reported", "creating a document is not execution")
        if kind == "daily_incident":
            check(isinstance(origin, dict) and origin.get("kind") == "user_input",
                  "daily incident must originate in user input")
            check(not item.get("reopening") and not item.get("closure"), "incident is not a case lifecycle")
            evaluation = item.get("followup_assessment")
            if evaluation is not None:
                check(isinstance(evaluation, dict) and type(evaluation.get("warrants_followup")) is bool
                      and text(evaluation.get("reason")), "repeat requires professional followup assessment")
                if isinstance(evaluation, dict):
                    linked = evaluation.get("related_incident_ids", [])
                    check(isinstance(linked, list) and bool(linked) and all(
                        isinstance(ref, str) and ref in by_id and by_id[ref].get("type") == "daily_incident" for ref in linked
                    ), "repeat assessment needs linked prior incidents")
        if kind == "followup_case":
            linked = item.get("incident_refs", [])
            check(isinstance(linked, list) and bool(linked) and all(
                isinstance(ref, str) and ref in by_id and by_id[ref].get("type") == "daily_incident" for ref in linked
            ), "followup case must retain original daily incidents")
            assessment = item.get("followup_assessment", {})
            check(isinstance(assessment, dict) and assessment.get("warrants_followup") is True
                  and text(assessment.get("reason")), "opening a case requires an affirmative assessment")
            if isinstance(assessment, dict):
                check(assessment.get("related_incident_ids") == linked, "assessment must address original incidents")
            information_assessment = item.get("information_assessment")
            if information_assessment is not None:
                check(isinstance(information_assessment, dict)
                      and type(information_assessment.get("warrants_followup")) is bool
                      and text(information_assessment.get("reason"))
                      and information_assessment.get("new_information_ref") in item.get("information_refs", []),
                      "new case information requires a linked professional assessment")
        if kind in ACTION_TYPES:
            check(type(item.get("requires_execution_cycle")) is bool, "requires_execution_cycle must be boolean")
            check(type(item.get("evidence_required_for_closure")) is bool, "evidence policy must be explicit")
            approval = item.get("approval", {})
            check(isinstance(approval, dict) and type(approval.get("required")) is bool,
                  "approval.required must be boolean")
            if isinstance(approval, dict):
                if not isinstance(approval.get("status"), str) or approval.get("status") not in {"approved", "pending", "not_required"}:
                    check(False, "invalid approval status")
                    continue
                if item.get("requires_execution_cycle") is True:
                    check(approval.get("required") is True, "execution cycle requires its approval step")
                if approval.get("required"):
                    check(approval.get("status") in {"approved", "pending"}, "required approval cannot be omitted")
                    if state != "proposed":
                        check(approval.get("status") == "approved", "action needs required approval")
                else:
                    check(approval.get("status") in {"approved", "not_required"}, "simple action approval contradiction")
                if approval.get("status") == "approved":
                    check(reference_ok(root, approval.get("reference")), "approved action needs approval reference")
            if state == "executed":
                check(execution_status == "executed", "executed status needs actual execution")
            if state in {"proposed", "approved", "ready_for_execution"}:
                check(execution_status == "not_reported", "pre-execution status cannot claim execution")
            if execution_status == "executed":
                execution = item.get("execution", {})
                check(isinstance(execution, dict) and iso_date(execution.get("at"))
                      and text(execution.get("summary")) and reference_ok(root, execution.get("input_ref")),
                      "actual execution needs date, summary and input reference")
            else:
                check(not item.get("execution"), "execution information contradicts non-executed status")
            if kind == "weekly_plan_execution" and state == "ready_for_execution":
                check(isinstance(approval, dict) and approval.get("status") == "approved",
                      "weekly plan readiness requires approved content")
                gate = item.get("gate", {})
                try:
                    assessment_path = file_at(root, gate.get("assessment_ref"))
                    result_path = file_at(root, gate.get("result_ref"))
                    plan_path = file_at(root, gate.get("plan_ref"))
                    check(all((assessment_path, result_path, plan_path)), "current Gate files must exist")
                    if all((assessment_path, result_path, plan_path)):
                        assessment, result = load(assessment_path), load(result_path)
                        plan_hash = hashlib.sha256(plan_path.read_bytes()).hexdigest()
                        check(gate.get("status") == result.get("gate_status")
                              and result.get("gate_status") in {"APPROVED", "APPROVED_WITH_WARNINGS"},
                              "ready plan needs successful Gate")
                        check(gate.get("plan_sha256") == assessment.get("plan_sha256")
                              == result.get("plan_sha256") == plan_hash, "Gate must match current plan hash")
                        check(gate.get("phase") == assessment.get("phase") == result.get("phase") == "DESIGN",
                              "Gate phase mismatch")
                        check(result.get("references_checked") == assessment.get("references_checked"),
                              "Gate assessment/result references differ")
                        check(all(file_at(root, ref["path"]) and hashlib.sha256(
                            file_at(root, ref["path"]).read_bytes()
                        ).hexdigest() == ref["sha256"] for ref in assessment["references_checked"]),
                              "Gate references changed")
                        current_errors = check_weekly_plan_gate.verify_current_result(assessment, plan_path, result, root=root)
                        check(not current_errors, "fresh Gate verification failed: " + "; ".join(current_errors))
                except (AttributeError, KeyError, TypeError, ValueError, OSError):
                    check(False, "invalid current Gate binding")
        if state == "closed":
            closure = item.get("closure", {})
            check(isinstance(closure, dict) and text(closure.get("reason")) and text(closure.get("result"))
                  and iso_date(closure.get("at")), "closure needs reason, result and date")
            if kind in ACTION_TYPES:
                check(execution_status in {"executed", "not_required"}, "cannot close an unexecuted required action")
                basis = closure.get("proof_basis", {}) if isinstance(closure, dict) else {}
                valid_basis = isinstance(basis, dict) and basis.get("kind") in {
                    "not_applicable", "documented_result"
                } and text(basis.get("summary")) and reference_ok(root, basis.get("reference"))
                if item.get("evidence_required_for_closure"):
                    check(bool(item.get("evidence_refs")) or valid_basis, "closure requires evidence or proof basis")
                if execution_status == "not_required":
                    check(valid_basis and basis.get("kind") == "not_applicable", "no-action closure needs applicability basis")
        reopening = item.get("reopening")
        if reopening is not None:
            check(kind == "followup_case" and state == "active" and isinstance(reopening, dict)
                  and text(reopening.get("reason")) and iso_date(reopening.get("at"))
                  and iso_date(reopening.get("previous_closed_at"))
                  and reference_ok(root, reopening.get("new_information_ref")),
                  "reopening needs new information, reason, date and prior closure")
            if isinstance(reopening, dict):
                check(reopening.get("new_information_ref") in item.get("information_refs", []),
                      "reopening information must remain linked")
                assessment = item.get("information_assessment", {})
                check(isinstance(assessment, dict) and assessment.get("warrants_followup") is True
                      and assessment.get("new_information_ref") == reopening.get("new_information_ref"),
                      "reopening requires affirmative assessment of the new information")
        if previous is not None:
            old = next((record for record in previous.get("items", []) if record.get("work_id") == ident), None)
            if old:
                check(old.get("type") == kind, "cannot convert incident/output into another record type")
                if old.get("status") == "closed" and state != "closed":
                    check(kind == "followup_case" and reopening is not None, "closed record cannot reopen automatically")
                    if isinstance(reopening, dict):
                        check(reopening.get("previous_closed_at") == old.get("closure", {}).get("at"),
                              "reopening must retain actual previous closure date")
                if kind == "followup_case" and old.get("status") == "closed":
                    new_information = set(item.get("information_refs", [])) - set(old.get("information_refs", []))
                    if new_information:
                        check(isinstance(item.get("information_assessment"), dict),
                              "assess new information against closed case history before update")
                if kind == "followup_case":
                    check(set(old.get("incident_refs", [])) <= set(item.get("incident_refs", [])),
                          "case must preserve original incident links")
                    check(set(old.get("information_refs", [])) <= set(item.get("information_refs", [])),
                          "case must preserve linked information history")
                if old.get("execution_status") == "executed":
                    check(execution_status == "executed", "cannot erase reported execution")
    if previous is not None:
        old_ids = {item.get("work_id") for item in previous.get("items", [])}
        if not old_ids <= by_id.keys():
            errors.append("update cannot discard original records")
    return errors


def _restricted_scope(root: Path, destination: Path | None, restricted_home: Path | None,
                      authorization_ref: str | None) -> dict:
    if destination is None or restricted_home is None or not text(authorization_ref):
        raise ValueError("restricted persistence needs an explicit home, destination and authorization reference")
    destination, restricted_home, root = destination.resolve(), restricted_home.resolve(), root.resolve()
    if (not restricted_home.is_dir() or not destination.is_relative_to(restricted_home)
            or destination == restricted_home or restricted_home.is_relative_to(root)
            or destination.is_relative_to(root)):
        raise ValueError("restricted persistence must stay inside its authorized home outside the public project")
    if any((parent / ".git").exists() for parent in (destination.parent, *destination.parents)):
        raise ValueError("restricted persistence cannot target a Git checkout")
    if privacy_guard.scan_data(authorization_ref):
        raise ValueError("use a non-identifying authorization reference")
    return {"audience": "restricted", "destination": str(destination),
            "restricted_home": str(restricted_home), "authorization_ref": authorization_ref}


def propose_update(before: dict, after: dict, summary: str, root: Path = ROOT,
                   *, audience: str = "public", authorization_ref: str | None = None,
                   destination: Path | None = None, restricted_home: Path | None = None) -> dict:
    """Return reviewable data only; never write or open a case on its own."""
    errors = validate_register(after, root, previous=before, audience=audience, authorization_ref=authorization_ref)
    if errors or not text(summary):
        raise ValueError("; ".join(errors) or "change summary required")
    proposal = {"before_sha256": digest(before), "after": copy.deepcopy(after), "summary": summary}
    if audience == "restricted":
        proposal["scope"] = _restricted_scope(root, destination, restricted_home, authorization_ref)
    elif destination is not None or restricted_home is not None or authorization_ref is not None:
        raise ValueError("restricted arguments cannot silently change public persistence scope")
    return {**proposal, "proposal_sha256": digest(proposal), "status": "proposed"}


def _append_audit(path: Path, record: dict) -> None:
    """Append and flush one safe record. The caller chooses the authorized audit home."""
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def save_approved_update(path: Path, proposal: dict, approval: dict, root: Path = ROOT,
                         *, audit_path: Path | None = None, audience: str = "public",
                         authorization_ref: str | None = None, restricted_home: Path | None = None) -> dict:
    """Persist only the exact displayed proposal explicitly approved by the user."""
    payload = {key: proposal[key] for key in ("before_sha256", "after", "summary")}
    if "scope" in proposal:
        payload["scope"] = proposal["scope"]
    if proposal.get("status") != "proposed" or proposal.get("proposal_sha256") != digest(payload):
        raise ValueError("proposal changed after preparation")
    if (approval.get("status") != "approved" or approval.get("approved_by") != "user"
            or approval.get("proposal_sha256") != proposal["proposal_sha256"]
            or not text(approval.get("reference"))):
        raise ValueError("explicit user approval of this exact proposal is required")
    path = path.resolve()
    audit_path = (audit_path or path.with_name(path.name + ".audit.jsonl")).resolve()
    if audience == "restricted":
        scope = _restricted_scope(root, path, restricted_home, authorization_ref)
        if proposal.get("scope") != scope:
            raise ValueError("restricted destination or authorization differs from the approved proposal")
        _restricted_scope(root, audit_path, restricted_home, authorization_ref)
    elif (audience != "public" or "scope" in proposal or authorization_ref is not None
          or restricted_home is not None):
        raise ValueError("persistence scope differs from the approved proposal")
    before = load(path)
    if digest(before) != proposal["before_sha256"]:
        raise ValueError("register changed since proposal was displayed")
    errors = validate_register(proposal["after"], root, previous=before,
                               audience=audience, authorization_ref=authorization_ref)
    if errors:
        raise ValueError("; ".join(errors))
    output_bytes = (json.dumps(proposal["after"], ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    if audience == "public":
        privacy_guard.require_public_bytes(output_bytes, ".json")
    approval_findings = privacy_guard.scan_data(approval["reference"])
    if approval_findings:
        raise privacy_guard.PrivacyReviewRequired(approval_findings)
    if audit_path == path:
        raise ValueError("audit journal must differ from the register")
    entry = {"audit_version": "1.0", "transaction_id": str(uuid.uuid4()),
             "before_sha256": proposal["before_sha256"], "proposal_sha256": proposal["proposal_sha256"],
             "approval_ref": approval["reference"], "proposed_result_sha256": digest(proposal["after"]),
             "at": datetime.now(timezone.utc).isoformat(), "status": "prepared", "audience": audience}
    # A failed audit preflight cannot change the register. No sensitive payload/summary is journaled.
    _append_audit(audit_path, entry)
    temporary: Path | None = None
    persisted = False
    try:
        descriptor, name = tempfile.mkstemp(prefix=".register-", suffix=".tmp", dir=path.parent)
        temporary = Path(name)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(output_bytes)
            stream.flush()
            os.fsync(stream.fileno())
        if digest(load(path)) != proposal["before_sha256"]:
            raise ValueError("register changed before atomic replacement")
        temporary.replace(path)
        persisted = True
        actual_hash = digest(load(path))
        if actual_hash != entry["proposed_result_sha256"]:
            raise OSError("persisted register verification failed")
        saved = {**entry, "at": datetime.now(timezone.utc).isoformat(), "status": "saved", "result_sha256": actual_hash}
        _append_audit(audit_path, saved)
        return saved
    except Exception:
        failure = {**entry, "at": datetime.now(timezone.utc).isoformat(),
                   "status": "state_persisted_audit_unconfirmed" if persisted else "failed_before_persistence"}
        try:
            _append_audit(audit_path, failure)
        except OSError:
            pass
        if persisted:
            raise RuntimeError("state persisted but successful audit completion is unconfirmed; inspect state and journal") from None
        raise
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--register", type=Path, default=ROOT / "work/register.json")
    args = parser.parse_args()
    errors = validate_register(load(args.register))
    print(json.dumps({"status": "pass" if not errors else "fail", "errors": errors}, ensure_ascii=False, indent=2))
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
