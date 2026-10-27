#!/usr/bin/env python3
"""Windows hook adapter for n8n-skills 1.3.0 (Apache-2.0).

Added 2026-10-27 for the Heiron8 fork. Uses the original reminder text packaged
in codex-hook-guidance.json. No shell execution, networking, or credential access.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile


HERE = Path(__file__).resolve().parent
GUIDANCE = json.loads((HERE / "codex-hook-guidance.json").read_text(encoding="utf-8"))


def plugin_root():
    return Path(os.environ.get("CLAUDE_PLUGIN_ROOT") or os.environ.get("PLUGIN_ROOT")
                or str(HERE.parent))


def state_dir():
    explicit = os.environ.get("N8N_HOOK_STATE_DIR")
    if explicit:
        return Path(explicit)
    data = os.environ.get("PLUGIN_DATA") or os.environ.get("CLAUDE_PLUGIN_DATA")
    return (Path(data) / "windows-hook-state" if data
            else Path(tempfile.gettempdir()) / "n8n-skills-python-state")


def marker(session, name):
    # Session IDs are data, never path components or glob expressions.
    digest = hashlib.sha256(session.encode("utf-8")).hexdigest()
    return state_dir() / f"{digest}-{name}.loaded"


def post_validation(code):
    header = "[validate_workflow returned. Validation is necessary, not sufficient.]"
    if not code:
        return header + " Load n8n-workflow-lifecycle-official and walk references/VALIDATION_CHECKLIST.md section 2 before publish."
    has = lambda name: name in code
    rules = [
        (has("n8n-nodes-base.merge"), "n8n-node-configuration-official references/MERGE_NODE.md"),
        (any(has(x) for x in ["n8n-nodes-base.set", "n8n-nodes-base.dateTime", "$json."]), "n8n-expressions-official"),
        (has("n8n-nodes-base.code"), "n8n-code-nodes-official"),
        (any(has(x) for x in ["n8n-nodes-base.splitInBatches", "n8n-nodes-base.httpRequest"]), "n8n-loops-official"),
        (has("n8n-nodes-base.executeWorkflowTrigger"), "n8n-subworkflows-official"),
        (has("n8n-nodes-base.dataTable"), "n8n-data-tables-official"),
        (any(has(x) for x in ["newCredential(", "n8n-nodes-base.httpRequest", "n8n-nodes-base.webhook", "n8n-nodes-base.respondToWebhook"]), "n8n-credentials-and-security-official"),
        (any(has(x) for x in ["n8n-nodes-base.webhook", "n8n-nodes-base.respondToWebhook", "n8n-nodes-base.scheduleTrigger", "langchain.chatTrigger", "n8n-nodes-langchain.agent", "n8n-nodes-base.messageAnAgent"]), "n8n-error-handling-official"),
        (len(re.findall(r"type:\s*['\"]n8n-", code)) > 6, "n8n-workflow-lifecycle-official"),
        (has("n8n-nodes-langchain.agent"), "n8n-ai-nodes-official"),
        (has("n8n-nodes-base.messageAnAgent"), "n8n-agents-official"),
    ]
    suggestions = ["- " + skill for matched, skill in rules if matched]
    return header + "\n\n" + ("Load the relevant guidance:\n" + "\n".join(suggestions)
        if suggestions else "No high-risk patterns surfaced. Load n8n-workflow-lifecycle-official for any non-trivial workflow.") + (
        "\n\nWalk these BEFORE publish_workflow. Validation passing means the SDK is well-formed; it does NOT mean the workflow is correct.")


def dispatch(action, data):
    session = data.get("session_id", "")
    if not isinstance(session, str):
        raise ValueError("session_id must be a string")
    tool_input = data.get("tool_input", {})
    if not isinstance(tool_input, dict):
        raise ValueError("tool_input must be an object")
    pending_marker = None
    if action == "session-start":
        if session and data.get("source") in {"clear", "compact"}:
            # Enumerate only fixed marker names owned by this adapter.
            for name in [v["marker"] for v in GUIDANCE["reminders"].values()] + ["node-config"]:
                marker(session, name).unlink(missing_ok=True)
        context = (plugin_root() / "skills/using-n8n-skills-official/SKILL.md").read_text(encoding="utf-8-sig")
        event = "SessionStart"
    elif action == "post-validate":
        code = tool_input.get("code", "")
        if not isinstance(code, str):
            raise ValueError("code must be a string")
        context, event = post_validation(code), "PostToolUse"
    elif action == "get-node":
        if not session:
            return None
        pending_marker = marker(session, "node-config")
        context = "" if pending_marker.exists() else GUIDANCE["generic_node"]
        ids = tool_input.get("ids", [])
        if not isinstance(ids, list):
            raise ValueError("ids must be an array")
        names = [item.get("name", "") if isinstance(item, dict) else item for item in ids]
        for node, warning in GUIDANCE["node_warnings"].items():
            if any(isinstance(name, str) and name.rsplit(".", 1)[-1].lower() == node.lower() for name in names):
                context += warning
        event = "PreToolUse"
    elif action in GUIDANCE["reminders"]:
        if not session:
            return None
        reminder = GUIDANCE["reminders"][action]
        pending_marker = marker(session, reminder["marker"])
        if pending_marker.exists():
            return None
        context, event = reminder["text"], "PreToolUse"
    else:
        raise ValueError("Unknown n8n hook action")
    if not context:
        return None
    return {"hookSpecificOutput": {"hookEventName": event, "additionalContext": context}}, pending_marker


def main():
    # Explicit UTF-8 avoids Windows console code-page failures on skill text.
    sys.stdin.reconfigure(encoding="utf-8-sig")
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        if len(sys.argv) != 2:
            raise ValueError("Expected one n8n hook action")
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            raise ValueError("Expected a JSON object")
        result = dispatch(sys.argv[1], data)
        if result:
            output, pending_marker = result
            print(json.dumps(output, ensure_ascii=False), flush=True)
            # Mark only after the context was successfully encoded and emitted.
            if pending_marker:
                try:
                    pending_marker.parent.mkdir(parents=True, exist_ok=True)
                    pending_marker.touch()
                except OSError:
                    pass  # Keep valid emitted JSON; retry the reminder next time.
    except (OSError, ValueError, TypeError) as exc:
        # Advisory hooks fail visibly but never approve or execute another action.
        print(json.dumps({"systemMessage": "n8n hook could not load: " + str(exc)}), flush=True)


if __name__ == "__main__":
    main()
