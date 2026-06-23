import inspect
import copy
from typing import Any, Dict, List, Optional, TYPE_CHECKING
from tools.registry import get_tool_by_name, get_tool_names, needs_context, build_local_tool_schemas
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
        (MCP) stages we still inject a human-readable listing of the remote tools, resources,
        resource templates, and prompts, which gives the model attack-surface context and tells it
        what readonly content is inspectable.
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
            # Describe remote resource templates (best-effort; do not fail the prompt if this fails).
            try:
                mcp_resource_templates_xml = await manager.describe_mcp_resource_templates()
            except Exception as rte:
                logger.warning(f"Failed to fetch MCP resource templates description: {rte}")
                mcp_resource_templates_xml = ""
            # Describe remote prompts (best-effort; do not fail the prompt if this fails).
            try:
                mcp_prompts_xml = await manager.describe_mcp_prompts()
            except Exception as pe:
                logger.warning(f"Failed to fetch MCP prompts description: {pe}")
                mcp_prompts_xml = ""

            reserved_names = set(get_tool_names()) | set(manager._tools_schema.keys())
            used_names = set(reserved_names)
            manager.build_resource_tool_schemas(reserved_names=reserved_names, used_names=used_names)
            manager.build_prompt_tool_schemas(reserved_names=reserved_names, used_names=used_names)

            # Re-render context so resources/prompts include callable/skipped markers.
            try:
                mcp_resources_xml = await manager.describe_mcp_resources()
            except Exception as re:
                logger.warning(f"Failed to fetch MCP resources description after tool mapping: {re}")
            try:
                mcp_resource_templates_xml = await manager.describe_mcp_resource_templates()
            except Exception as rte:
                logger.warning(f"Failed to fetch MCP resource templates description after tool mapping: {rte}")
            try:
                mcp_prompts_xml = await manager.describe_mcp_prompts()
            except Exception as pe:
                logger.warning(f"Failed to fetch MCP prompts description after tool mapping: {pe}")

            return prompt_manager.format_prompt(
                "dynamic/system_prompt",
                mcp_tools=mcp_tools_xml,
                mcp_resources=mcp_resources_xml,
                mcp_resource_templates=mcp_resource_templates_xml,
                mcp_prompts=mcp_prompts_xml,
            )
        except Exception as e:
            logger.error(f"Failed to fetch MCP tools/resources/templates/prompts description: {e}")
            return ""

    async def get_tool_definitions(self) -> List[Dict[str, Any]]:
        """Build OpenAI-native tool definitions for the current stage.

        Mirrors the tool-set logic of ``get_all_tools_prompt``:
        - Normal stages: local ``finish, think, read_file, execute_shell``.
        - Dynamic (MCP) stages: local ``finish, think`` plus one native function per remote MCP
          tool, resource, resource template, and prompt.
        """
        common_tools = ['finish', 'think']

        if self.mcp_server_url:
            definitions = build_local_tool_schemas(common_tools)

            manager = await self._ensure_mcp_manager()
            if not manager:
                raise RuntimeError("Failed to connect to MCP server")

            await manager.describe_mcp_tools()
            try:
                await manager.describe_mcp_resources()
            except Exception as re:
                logger.warning(f"Failed to fetch MCP resources for tool definitions: {re}")
            try:
                await manager.describe_mcp_resource_templates()
            except Exception as rte:
                logger.warning(f"Failed to fetch MCP resource templates for tool definitions: {rte}")
            try:
                await manager.describe_mcp_prompts()
            except Exception as pe:
                logger.warning(f"Failed to fetch MCP prompts for tool definitions: {pe}")

            remote_tool_definitions = manager.get_tool_schemas()
            definitions.extend(remote_tool_definitions)

            reserved_names = set(get_tool_names()) | set(manager._tools_schema.keys())
            used_names = set(reserved_names)
            definitions.extend(manager.build_resource_tool_schemas(
                reserved_names=reserved_names,
                used_names=used_names,
            ))
            definitions.extend(manager.build_prompt_tool_schemas(
                reserved_names=reserved_names,
                used_names=used_names,
            ))
            return definitions

        normal_tools = copy.copy(common_tools)
        normal_tools.extend(['read_file', 'execute_shell'])
        return build_local_tool_schemas(normal_tools)

    def _is_remote_tool(self, tool_name: str) -> bool:
        return bool(self.mcp_tools_manager and tool_name in self.mcp_tools_manager._tools_schema)

    def _is_remote_resource_tool(self, tool_name: str) -> bool:
        return bool(self.mcp_tools_manager and self.mcp_tools_manager.is_resource_tool(tool_name))

    def _is_remote_prompt_tool(self, tool_name: str) -> bool:
        return bool(self.mcp_tools_manager and self.mcp_tools_manager.is_prompt_tool(tool_name))

    async def call_tool(self, tool_name: str, args: Dict[str, Any], context: Optional["ToolContext"] = None) -> str:
        """统一调用入口：自动识别是本地还是远程工具"""
        # 1. 优先尝试作为真实远程 MCP 工具调用（原生 tool calling 下每个远程工具都是一个独立函数）
        if self._is_remote_tool(tool_name):
            try:
                if context is not None:
                    result = await context.call_mcp_tools(tool_name, args)
                else:
                    result = await self.mcp_tools_manager.call_remote_tool(tool_name, **args)
            except Exception as e:
                return f"Error: {e}"
            return self._format_result(result)

        # 2. 尝试作为远程 MCP resource/resource template 的独立函数调用
        if self._is_remote_resource_tool(tool_name):
            try:
                result = await self.mcp_tools_manager.call_resource_tool(tool_name, args)
            except Exception as e:
                return f"Error: {e}"
            return self._format_result(result)

        # 3. 尝试作为远程 MCP prompt 的独立函数调用
        if self._is_remote_prompt_tool(tool_name):
            try:
                result = await self.mcp_tools_manager.call_prompt_tool(tool_name, args)
            except Exception as e:
                return f"Error: {e}"
            return self._format_result(result)

        # 4. 尝试作为本地兼容工具调用
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
