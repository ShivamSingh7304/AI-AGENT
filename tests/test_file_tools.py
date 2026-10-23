import json
import logging
from logging.handlers import RotatingFileHandler
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
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

    async def test_jsonrpc_trace_records_tool_requests_and_responses(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        trace_path = Path(temp_dir.name) / "mcp_jsonrpc.jsonl"
        request_message = {
            "jsonrpc": "2.0",
            "id": 7,
            "method": "tools/call",
            "params": {
                "name": "write_desktop_file",
                "arguments": {"filename": "trace.txt", "content": "trace content"},
            },
        }
        response_message = {
            "jsonrpc": "2.0",
            "id": 7,
            "result": {"content": [{"type": "text", "text": "Saved"}]},
        }

        async def fake_mcp_app(_scope, receive, send):
            self.assertEqual(_scope["type"], "http")
            await receive()
            await send(
                {
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [(b"content-type", b"text/event-stream")],
                }
            )
            event = f"event: message\ndata: {json.dumps(response_message)}\n\n"
            await send(
                {
                    "type": "http.response.body",
                    "body": event.encode("utf-8"),
                    "more_body": False,
                }
            )

        middleware = file_tools.JsonRpcTraceMiddleware(
            fake_mcp_app,
            trace_path,
        )
        trace_logger = logging.getLogger("ai_agent.mcp.jsonrpc")
        trace_handler = next(
            handler
            for handler in trace_logger.handlers
            if isinstance(handler, RotatingFileHandler)
            and Path(handler.baseFilename) == trace_path.resolve()
        )

        def close_trace_handler() -> None:
            trace_logger.removeHandler(trace_handler)
            trace_handler.close()

        self.addCleanup(close_trace_handler)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=middleware),
            base_url="http://test",
        ) as client:
            await client.post("/mcp", json=request_message)

        entries = [
            json.loads(line)
            for line in trace_path.read_text(encoding="utf-8").splitlines()
        ]
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["request"], request_message)
        self.assertEqual(entries[0]["response"], response_message)
