import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from langchain.mcp import MCPAdapter

from ai_agent.tools.file_read_write import file as file_tools


def _tool_text(result: object) -> str:
    if isinstance(result, list):
        return "\n".join(
            block["text"]
            for block in result
            if isinstance(block, dict)
            and isinstance(block.get("text"), str)
        )
    return str(result)


class DesktopFileMCPTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.desktop = tempfile.TemporaryDirectory()
        self.desktop_path = Path(self.desktop.name).resolve()
        patcher = patch.object(file_tools, "DESKTOP_PATH", self.desktop_path)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.desktop.cleanup)

    async def test_file_tools_are_discoverable_and_operable(self) -> None:
        async with MCPAdapter(file_tools.mcp) as adapter:
            tools = {
                tool.name: tool
                for tool in await adapter.list_tools()
            }

            self.assertEqual(
                set(tools),
                {
                    "read_desktop_file",
                    "write_desktop_file",
                    "append_desktop_file",
                },
            )

            write_result = await tools["write_desktop_file"].ainvoke(
                {"filename": "notes.txt", "content": "Hello"}
            )
            self.assertEqual(
                _tool_text(write_result),
                "Successfully saved file: notes.txt",
            )

            append_result = await tools["append_desktop_file"].ainvoke(
                {"filename": "notes.txt", "content": " world"}
            )
            self.assertEqual(
                _tool_text(append_result),
                "Successfully appended to file: notes.txt",
            )

            read_result = await tools["read_desktop_file"].ainvoke(
                {"filename": "notes.txt"}
            )
            self.assertEqual(_tool_text(read_result), "Hello world")
            self.assertEqual(
                (self.desktop_path / "notes.txt").read_text(encoding="utf-8"),
                "Hello world",
            )

    async def test_file_tools_reject_paths_outside_desktop(self) -> None:
        async with MCPAdapter(file_tools.mcp) as adapter:
            read_tool = next(
                tool
                for tool in await adapter.list_tools()
                if tool.name == "read_desktop_file"
            )

            result = await read_tool.ainvoke(
                {"filename": "../outside.txt"}
            )

        self.assertEqual(
            _tool_text(result),
            "Unable to read the file. Check its path, permissions, and encoding.",
        )
