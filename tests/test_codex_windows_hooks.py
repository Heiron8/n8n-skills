"""Regression tests for the fork's Codex Windows hooks. No n8n calls."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid


REPOSITORY = Path(__file__).resolve().parents[1]
RUNNER = REPOSITORY / "hooks/codex_hooks.py"
CONFIG = json.loads((REPOSITORY / "hooks/hooks.json").read_text(encoding="utf-8"))


class CodexWindowsHookTests(unittest.TestCase):
    def setUp(self):
        # Keep fixtures outside deep checkout paths to avoid Windows MAX_PATH.
        self.temporary_root = Path(tempfile.gettempdir()).resolve()
        self.fixture = self.temporary_root / ("windows-hooks-" + uuid.uuid4().hex)
        self.fixture.mkdir()
        self.addCleanup(self.clean_fixture)
        self.plugin = self.fixture / "plugin with spaces ' and & characters"
        (self.plugin / "hooks").mkdir(parents=True)
        for filename in ["codex_hooks.py", "codex-hook-guidance.json"]:
            (self.plugin / "hooks" / filename).write_bytes((REPOSITORY / "hooks" / filename).read_bytes())
        protocol = self.plugin / "skills/using-n8n-skills-official/SKILL.md"
        protocol.parent.mkdir(parents=True)
        protocol.write_text("# Using n8n Skills\nSynthetic protocol: caf\u00e9 \u65e5\u672c\u8a9e\n", encoding="utf-8")
        self.environment = os.environ.copy()
        self.environment["CLAUDE_PLUGIN_ROOT"] = str(self.plugin)
        self.environment["N8N_HOOK_STATE_DIR"] = str(self.fixture / "state")

    def clean_fixture(self):
        if (self.fixture.resolve().parent != self.temporary_root.resolve()
                or not self.fixture.name.startswith("windows-hooks-")):
            raise ValueError("Refusing cleanup outside the test fixture")
        shutil.rmtree(self.fixture)

    def invoke(self, action, tool_input=None, session="test-session", source="startup"):
        payload = {"session_id": session, "source": source, "tool_input": tool_input or {}}
        process = subprocess.run([sys.executable, str(RUNNER), action],
                                 input=json.dumps(payload), capture_output=True, text=True,
                                 encoding="utf-8", env=self.environment, timeout=10)
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertFalse(process.stderr)
        return json.loads(process.stdout) if process.stdout.strip() else None

    def context(self, output, event="PreToolUse"):
        self.assertEqual(output["hookSpecificOutput"]["hookEventName"], event)
        return output["hookSpecificOutput"]["additionalContext"]

    def test_startup_and_resume_preserve_protocol_and_existing_markers(self):
        self.invoke("create-workflow")
        for source in ["startup", "resume"]:
            with self.subTest(source=source):
                text = self.context(self.invoke("session-start", source=source), "SessionStart")
                self.assertIn("caf\u00e9 \u65e5\u672c\u8a9e", text)
                self.assertIsNone(self.invoke("create-workflow"))

    def test_clear_and_compact_reset_only_the_current_session(self):
        for source in ["clear", "compact"]:
            with self.subTest(source=source):
                self.invoke("create-workflow", session="current")
                self.invoke("create-workflow", session="other")
                self.invoke("session-start", session="current", source=source)
                self.assertIsNotNone(self.invoke("create-workflow", session="current"))
                self.assertIsNone(self.invoke("create-workflow", session="other"))

    def test_shared_reminders_emit_once_per_session(self):
        for action in ["create-workflow", "update-workflow", "validate-workflow",
                       "execute-workflow", "test-workflow", "agent-build"]:
            with self.subTest(action=action):
                self.assertIn("n8n-", self.context(self.invoke(action)))
                self.assertIsNone(self.invoke(action))

    def test_generic_node_reminder_dedupes_but_specific_warnings_repeat(self):
        normal = {"ids": ["n8n-nodes-base.noOp"]}
        self.assertIn("Before configuring", self.context(self.invoke("get-node", normal)))
        self.assertIsNone(self.invoke("get-node", normal))
        for node in ["set", "code", "merge", "splitInBatches", "dateTime", "dataTable"]:
            with self.subTest(node=node):
                requested = {"ids": [{"name": "n8n-nodes-base." + node}]}
                warning = self.context(self.invoke("get-node", requested))
                self.assertIn("STOP", warning)
                self.assertEqual(warning, self.context(self.invoke("get-node", requested)))

    def test_post_validation_routes_all_guidance_categories(self):
        nodes = ["merge", "set", "code", "splitInBatches", "dateTime", "dataTable",
                 "executeWorkflowTrigger", "httpRequest", "webhook", "messageAnAgent"]
        code = ";".join('node({type: "n8n-nodes-base.' + node + '"})' for node in nodes)
        code += ';node({type: "@n8n/n8n-nodes-langchain.agent"})'
        text = self.context(self.invoke("post-validate", {"code": code}), "PostToolUse")
        for category in ["node-configuration", "expressions", "code-nodes", "loops",
                         "subworkflows", "data-tables", "credentials-and-security",
                         "error-handling", "workflow-lifecycle", "ai-nodes", "agents"]:
            self.assertIn("n8n-" + category + "-official", text)

    def test_post_validation_has_fallback_and_never_executes_submitted_code(self):
        self.assertIn("VALIDATION_CHECKLIST", self.context(self.invoke("post-validate"), "PostToolUse"))
        canary = self.fixture / "must-not-exist"
        code = f'__import__("pathlib").Path({str(canary)!r}).touch()'
        first = self.context(self.invoke("post-validate", {"code": code}), "PostToolUse")
        self.assertEqual(first, self.context(self.invoke("post-validate", {"code": code}), "PostToolUse"))
        self.assertFalse(canary.exists())

    def test_session_identifier_is_not_used_as_a_path(self):
        self.invoke("create-workflow", session="../../escape\\bad:*?\u65e5\u672c\u8a9e")
        files = list((self.fixture / "state").iterdir())
        self.assertEqual(len(files), 1)
        self.assertRegex(files[0].name, r"^[0-9a-f]{64}-lifecycle-subworkflows\.loaded$")

    def test_unwritable_marker_does_not_corrupt_context_json(self):
        blocked = self.fixture / "state-is-a-file"
        blocked.write_text("fixture")
        self.environment["N8N_HOOK_STATE_DIR"] = str(blocked)
        first = self.context(self.invoke("create-workflow"))
        self.assertEqual(first, self.context(self.invoke("create-workflow")))

    def test_invalid_json_returns_an_advisory_warning(self):
        process = subprocess.run([sys.executable, str(RUNNER), "create-workflow"],
                                 input="{invalid", capture_output=True, text=True,
                                 encoding="utf-8", env=self.environment, timeout=10)
        self.assertEqual(process.returncode, 0)
        self.assertEqual(set(json.loads(process.stdout)), {"systemMessage"})

    @unittest.skipUnless(os.name == "nt", "Requires Windows PowerShell")
    def test_all_ten_portable_windows_commands_with_special_character_paths(self):
        checked = 0
        for event, groups in CONFIG["hooks"].items():
            for group in groups:
                for handler in group["hooks"]:
                    with self.subTest(event=event, matcher=group.get("matcher")):
                        payload = {"session_id": uuid.uuid4().hex, "source": "startup",
                                   "tool_input": {"ids": ["n8n-nodes-base.code"],
                                                  "code": 'node({type: "n8n-nodes-base.code"})'}}
                        process = subprocess.run(
                            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", handler["commandWindows"]],
                            input=json.dumps(payload), capture_output=True, text=True,
                            encoding="utf-8", env=self.environment, timeout=15)
                        self.assertEqual(process.returncode, 0, process.stderr)
                        self.assertFalse(process.stderr)
                        context = self.context(json.loads(process.stdout), event)
                        self.assertIn("n8n", context.lower())
                        if event == "SessionStart":
                            self.assertIn("caf\u00e9 \u65e5\u672c\u8a9e", context)
                        checked += 1
        self.assertEqual(checked, 10)


if __name__ == "__main__":
    unittest.main()
