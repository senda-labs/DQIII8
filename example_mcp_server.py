#!/usr/bin/env python3
"""
Simple MCP Server Example - File System Operations
Demonstrates core MCP concepts with a basic file management server.
"""

import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


# MCP Protocol Messages
class MCPMessage:
    def __init__(self, id: Optional[str], method: str, params: Dict[str, Any]):
        self.id = id
        self.method = method
        self.params = params


class MCPResponse:
    def __init__(
        self,
        id: Optional[str],
        result: Optional[Dict] = None,
        error: Optional[Dict] = None,
    ):
        self.id = id
        self.result = result
        self.error = error

    def to_dict(self):
        response = {"jsonrpc": "2.0", "id": self.id}
        if self.error:
            response["error"] = self.error
        else:
            response["result"] = self.result
        return response


class SimpleMCPServer:
    def __init__(self, base_directory: str = "."):
        self.base_dir = Path(base_directory).resolve()
        self.server_info = {"name": "simple-filesystem-server", "version": "1.0.0"}

    def get_tools(self) -> List[Dict]:
        """Define available tools that the LLM can call"""
        return [
            {
                "name": "read_file",
                "description": "Read contents of a text file",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "filepath": {
                            "type": "string",
                            "description": "Path to the file to read",
                        }
                    },
                    "required": ["filepath"],
                },
            },
            {
                "name": "write_file",
                "description": "Write content to a file",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "filepath": {
                            "type": "string",
                            "description": "Path to the file to write",
                        },
                        "content": {
                            "type": "string",
                            "description": "Content to write to the file",
                        },
                    },
                    "required": ["filepath", "content"],
                },
            },
            {
                "name": "list_directory",
                "description": "List files and directories in a path",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "dirpath": {
                            "type": "string",
                            "description": "Directory path to list",
                        }
                    },
                    "required": ["dirpath"],
                },
            },
        ]

    def get_resources(self) -> List[Dict]:
        """Define available resources that can be read"""
        return [
            {
                "uri": "file://current_directory",
                "name": "Current Directory Listing",
                "description": "Contents of the current directory",
                "mimeType": "application/json",
            }
        ]

    async def handle_tool_call(
        self, tool_name: str, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute tool calls"""
        try:
            if tool_name == "read_file":
                return await self._read_file(arguments["filepath"])
            elif tool_name == "write_file":
                return await self._write_file(
                    arguments["filepath"], arguments["content"]
                )
            elif tool_name == "list_directory":
                return await self._list_directory(arguments["dirpath"])
            else:
                return {"error": f"Unknown tool: {tool_name}"}
        except Exception as e:
            return {"error": f"Tool execution failed: {str(e)}"}

    async def _read_file(self, filepath: str) -> Dict[str, Any]:
        """Read file content"""
        try:
            full_path = (self.base_dir / filepath).resolve()
            # Security check: ensure path is within base directory
            if not str(full_path).startswith(str(self.base_dir)):
                return {"error": "Access denied: path outside allowed directory"}

            content = full_path.read_text(encoding="utf-8")
            return {
                "content": [
                    {"type": "text", "text": f"Content of {filepath}:\n{content}"}
                ]
            }
        except FileNotFoundError:
            return {"error": f"File not found: {filepath}"}
        except Exception as e:
            return {"error": f"Read error: {str(e)}"}

    async def _write_file(self, filepath: str, content: str) -> Dict[str, Any]:
        """Write content to file"""
        try:
            full_path = (self.base_dir / filepath).resolve()
            # Security check
            if not str(full_path).startswith(str(self.base_dir)):
                return {"error": "Access denied: path outside allowed directory"}

            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(content, encoding="utf-8")
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"Successfully wrote {len(content)} characters to {filepath}",
                    }
                ]
            }
        except Exception as e:
            return {"error": f"Write error: {str(e)}"}

    async def _list_directory(self, dirpath: str) -> Dict[str, Any]:
        """List directory contents"""
        try:
            full_path = (self.base_dir / dirpath).resolve()
            # Security check
            if not str(full_path).startswith(str(self.base_dir)):
                return {"error": "Access denied: path outside allowed directory"}

            items = []
            for item in full_path.iterdir():
                items.append(
                    {
                        "name": item.name,
                        "type": "directory" if item.is_dir() else "file",
                        "size": item.stat().st_size if item.is_file() else None,
                    }
                )

            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"Directory listing for {dirpath}:\n"
                        + json.dumps(items, indent=2),
                    }
                ]
            }
        except Exception as e:
            return {"error": f"List error: {str(e)}"}

    async def handle_message(self, message_data: Dict) -> Dict:
        """Handle incoming MCP messages"""
        method = message_data.get("method")
        msg_id = message_data.get("id")
        params = message_data.get("params", {})

        try:
            if method == "initialize":
                result = {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}, "resources": {}},
                    "serverInfo": self.server_info,
                }
                return MCPResponse(msg_id, result=result).to_dict()

            elif method == "tools/list":
                result = {"tools": self.get_tools()}
                return MCPResponse(msg_id, result=result).to_dict()

            elif method == "resources/list":
                result = {"resources": self.get_resources()}
                return MCPResponse(msg_id, result=result).to_dict()

            elif method == "tools/call":
                tool_name = params.get("name")
                arguments = params.get("arguments", {})
                result = await self.handle_tool_call(tool_name, arguments)
                return MCPResponse(msg_id, result=result).to_dict()

            else:
                error = {"code": -32601, "message": f"Method not found: {method}"}
                return MCPResponse(msg_id, error=error).to_dict()

        except Exception as e:
            error = {"code": -32000, "message": f"Server error: {str(e)}"}
            return MCPResponse(msg_id, error=error).to_dict()


async def main():
    """Run the MCP server"""
    server = SimpleMCPServer("./mcp_sandbox")

    print(
        "Simple MCP Server started. Listening for JSON-RPC messages...", file=sys.stderr
    )

    # Create sandbox directory
    Path("./mcp_sandbox").mkdir(exist_ok=True)

    # Simple stdin/stdout transport
    while True:
        try:
            line = await asyncio.get_event_loop().run_in_executor(
                None, sys.stdin.readline
            )
            if not line:
                break

            message = json.loads(line.strip())
            response = await server.handle_message(message)
            print(json.dumps(response))
            sys.stdout.flush()

        except json.JSONDecodeError:
            error_response = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": "Parse error"},
            }
            print(json.dumps(error_response))
        except Exception as e:
            print(f"Server error: {e}", file=sys.stderr)


if __name__ == "__main__":
    asyncio.run(main())
