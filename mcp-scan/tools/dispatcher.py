import inspect
import copy
from typing import Any, Dict, List, Optional, TYPE_CHECKING
from tools.registry import get_tool_by_name, needs_context, build_local_tool_schemas
from utils.mcp_tools import MCPTools
from utils.loging import logger
from utils.prompt_manager import prompt_manager

if TYPE_CHECKING:  # pragma: no cover
    from utils.tool_context import ToolContext
    from utils.mcp_oauth import OAuthManager


class ToolDispatcher:
    def __init__(self, mcp_server_url: Optional[str] = None,
                 mcp_headers: Optional[Dict[str, str]] = None,
                 oauth_manager: Optional["OAuthManager"] = None):
        """
        NOTE: __init__ must be synchronous. We do lazy MCP connection on first remote usage.

        Args:
            mcp_server_url: Remote MCP server URL.
            mcp_headers: Static headers supplied by the caller (API keys, custom headers).
                         Never mutated; OAuth Bearer token is layered on top separately.
            oauth_manager: Optional OAuthManager for automatic token injection.
        """
        self.mcp_server_url = mcp_server_url
        self.mcp_tools_manager: Optional[MCPTools] = None
        self.mcp_transport = None
        # Caller-supplied headers; immutable reference point for rebuilding effective headers.
        self._base_headers: Dict[str, str] = dict(mcp_headers or {})
        # Effective headers used for MCP connections (may include OAuth Bearer token).
        self.mcp_headers: Dict[str, str] = dict(self._base_headers)
        self.oauth_manager = oauth_manager

    async def inject_oauth_token(self) -> None:
        """
        Fetch a fresh OAuth token and merge it into the effective headers.
        No-op if no OAuthManager is configured.
        """
        if self.oauth_manager is None:
            return
        token = await self.oauth_manager.get_token()
        # Rebuild effective headers: base headers + OAuth Bearer token (OAuth takes priority).
        self.mcp_headers = {**self._base_headers, "Authorization": f"Bearer {token}"}
        logger.debug("ToolDispatcher: OAuth Bearer token injected into MCP headers")

    async def connect(self) -> None:
        """
        Establish a fresh connection to the MCP server and verify reachability.
        Raises RuntimeError if the server cannot be reached.
        """
        manager = await self._ensure_mcp_manager()
        if manager is None:
            raise RuntimeError(
                f"ToolDispatcher: Unable to connect to MCP server: {self.mcp_server_url}"
            )

    async def _ensure_mcp_manager(self) -> Optional[MCPTools]:
        if not self.mcp_server_url:
            return None
        if self.mcp_tools_manager:
            return self.mcp_tools_manager

        transports = [self.mcp_transport] if self.mcp_transport else ["streamable-http", "sse"]
        for transport in transports:
            if not transport:
                continue
            try:
                manager = MCPTools(self.mcp_server_url, transport, headers=self.mcp_headers)  # type: ignore[arg-type]
                # verify connectivity
                await manager.describe_mcp_tools()
                self.mcp_tools_manager = manager
                logger.info(f"ToolDispatcher: MCP tools manager initialized with transport: {transport}")
                return self.mcp_tools_manager
            except Exception:
                continue

        logger.error(f"ToolDispatcher: Failed to connect to MCP server: {self.mcp_server_url}")
        return None

    async def get_all_tools_prompt(self) -> str:
        """Build the tool-context section of the system prompt.

        Tool *call* schemas are now delivered via the native ``tools=`` API (see
        ``get_tool_definitions``), so the local-tool XML dump is no longer emitted here. For dynamic
        (MCP) stages we still inject a human-readable listing of the remote tools, resources, and
        prompts, which gives the model attack-surface context and tells it what readonly content is
        inspectable.
        """
        if not self.mcp_server_url:
            return ""

        manager = await self._ensure_mcp_manager()
        if not manager:
            raise RuntimeError("Failed to connect to MCP server")
        try:
            # Describe remote tools (also populates the schema cache used by get_tool_definitions).
            mcp_tools_xml = await manager.describe_mcp_tools()
            # Describe remote resources (best-effort; do not fail the prompt if this fails).
            try:
                mcp_resources_xml = await manager.describe_mcp_resources()
            except Exception as re:
                logger.warning(f"Failed to fetch MCP resources description: {re}")
                mcp_resources_xml = ""
            # Describe remote prompts (best-effort; do not fail the prompt if this fails).
            try:
                mcp_prompts_xml = await manager.describe_mcp_prompts()
            except Exception as pe:
                logger.warning(f"Failed to fetch MCP prompts description: {pe}")
                mcp_prompts_xml = ""

            return prompt_manager.format_prompt(
                "dynamic/system_prompt",
                mcp_tools=mcp_tools_xml,
                mcp_resources=mcp_resources_xml,
                mcp_prompts=mcp_prompts_xml,
            )
        except Exception as e:
            logger.error(f"Failed to fetch MCP tools/resources/prompts description: {e}")
            return ""

    async def get_tool_definitions(self) -> List[Dict[str, Any]]:
        """Build OpenAI-native tool definitions for the current stage.

        Mirrors the tool-set logic of ``get_all_tools_prompt``:
        - Normal stages: local ``finish, think, read_file, execute_shell``.
        - Dynamic (MCP) stages: local ``finish, think, mcp_resource, mcp_prompt`` plus one native function per
          remote MCP tool (using its real JSON Schema).
        """
        common_tools = ['finish', 'think']

        if self.mcp_server_url:
            local_tools = copy.copy(common_tools)
            local_tools.append('mcp_resource')
            local_tools.append('mcp_prompt')
            definitions = build_local_tool_schemas(local_tools)

            manager = await self._ensure_mcp_manager()
            if not manager:
                raise RuntimeError("Failed to connect to MCP server")
            # Ensure the remote tool schema cache is populated before reading it.
            await manager.describe_mcp_tools()
            definitions.extend(manager.get_tool_schemas())
            return definitions

        normal_tools = copy.copy(common_tools)
        normal_tools.extend(['read_file', 'execute_shell'])
        return build_local_tool_schemas(normal_tools)

    def _is_remote_tool(self, tool_name: str) -> bool:
        return bool(self.mcp_tools_manager and tool_name in self.mcp_tools_manager._tools_schema)

    async def call_tool(self, tool_name: str, args: Dict[str, Any], context: Optional["ToolContext"] = None) -> str:
        """统一调用入口：自动识别是本地还是远程工具"""
        # 1. 尝试作为本地工具调用
        tool_func = get_tool_by_name(tool_name)
        if tool_func:
            if needs_context(tool_name) and context:
                args["context"] = context

            try:
                result = tool_func(**args)
            except Exception as e:
                return f"Error: {e}"
            if inspect.isawaitable(result):
                result = await result
            return self._format_result(result)

        # 2. 否则尝试作为远程 MCP 工具调用（原生 tool calling 下每个远程工具都是一个独立函数）
        if self._is_remote_tool(tool_name):
            try:
                if context is not None:
                    result = await context.call_mcp_tools(tool_name, args)
                else:
                    result = await self.mcp_tools_manager.call_remote_tool(tool_name, **args)
            except Exception as e:
                return f"Error: {e}"
            return self._format_result(result)

        return f"Error: Tool '{tool_name}' not found locally or MCP server is unavailable"

    def _format_result(self, result: Any) -> str:
        if isinstance(result, dict):
            ret = ""
            for k, v in result.items():
                ret += f"<{k}>{v}</{k}>\n"
            return ret
        return str(result)

    async def close(self) -> None:
        if self.mcp_tools_manager:
            await self.mcp_tools_manager.close()
            self.mcp_tools_manager = None
            logger.info("ToolDispatcher: MCP tools manager closed and reset")
