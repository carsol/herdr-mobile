import re
import tempfile
import unittest
from unittest.mock import patch

from herdr_mobile import server


class AgentNameTest(unittest.TestCase):
    def test_normalizes_invalid_long_and_colliding_labels(self):
        valid = re.compile(r"[a-z][a-z0-9_-]{0,31}\Z")
        self.assertEqual(server._agent_name(" 42 Project / Demo! "), "agent-42-project-demo")
        long_name = server._agent_name("Project " + "x" * 80)
        self.assertLessEqual(len(long_name), 32)
        self.assertRegex(long_name, valid)
        self.assertEqual(server._agent_name("Project Name!", {"project-name"}), "project-name-2")

        with tempfile.TemporaryDirectory() as cwd:
            with patch.object(server.herdr, "agents", return_value=[{"name": "project-name"}]), \
                    patch.object(server.herdr, "workspace_create", return_value={"root_pane": {"pane_id": "p1"}}) as workspace, \
                    patch.object(server.herdr, "agent_start") as start:
                server.Handler._create(object(), {
                    "cwd": cwd, "name": "Project Name!", "kind": "codex",
                    "args": '--model "gpt 5"',
                })
            workspace.assert_called_once_with(cwd, label="Project Name!")
            self.assertEqual(start.call_args.args[2], "project-name-2")
            self.assertEqual(start.call_args.args[3], ["--model", "gpt 5"])

    def test_rejects_unclosed_extra_arg_quote(self):
        with tempfile.TemporaryDirectory() as cwd, \
                patch.object(server.herdr, "agents", return_value=[]), \
                patch.object(server.herdr, "workspace_create") as workspace:
            with self.assertRaisesRegex(server.herdr.HerdrError, "invalid extra args"):
                server.Handler._create(object(), {"cwd": cwd, "kind": "codex", "args": "'"})
            workspace.assert_not_called()


if __name__ == "__main__":
    unittest.main()
