import asyncio
import copy
import json
from html import escape
from datetime import timedelta
from typing import Any, AsyncIterator, Dict, Literal, Optional
from contextlib import asynccontextmanager

from mcp import ClientSession
from mcp.client.sse import sse_client
from mcp.client.streamable_http import streamablehttp_client

from utils.loging import logger


MCP_OPERATION_TIMEOUT_SECONDS = 30
MCP_OPERATION_RETRIES = 2


class MCPTools:
    """Small MCP-only wrapper used by this repo (no agno dependency)."""

    def __init__(self, url: Optional[str] = None, transport: Literal["sse", "streamable-http"] = "sse",
                 headers: dict = None):
        if headers is None:
            headers = {}
        self.url = url
        self.transport = transport
        self.timeout_seconds = MCP_OPERATION_TIMEOUT_SECONDS
        self.retries = MCP_OPERATION_RETRIES
        self.headers = headers
        # 缓存工具 schema，用于参数类型转换
        self._tools_schema: Dict[str, Dict[str, Any]] = {}
        # 缓存工具描述，用于构建原生 tool calling 定义
        self._tools_description: Dict[str, str] = {}
        # 缓存资源名称到 URI 的映射，便于按名称读取资源
        self._resources_index: Dict[str, str] = {}
        # 缓存 prompt 参数定义，便于按名称读取 prompt
        self._prompts_schema: Dict[str, Dict[str, Any]] = {}
        self._prompts_description: Dict[str, str] = {}

    async def close(self) -> None:
        # Stateless wrapper: each operation uses a short-lived session.
        return

    @asynccontextmanager
    async def _session(self) -> AsyncIterator[ClientSession]:
        """Short-lived session (enter/exit in same coroutine; safe for SSE + anyio)."""
        if not self.url:
            raise ValueError("MCP server url is required")

        if self.transport == "sse":
            ctx = sse_client(url=self.url, headers=self.headers)  # type: ignore
        elif self.transport == "streamable-http":
            ctx = streamablehttp_client(url=self.url, headers=self.headers)  # type: ignore
        else:
            raise ValueError(f"Unsupported transport protocol: {self.transport}")

        async with ctx as session_params:  # type: ignore
            read, write = session_params[0:2]
            async with ClientSession(
                    read,
                    write,
                    read_timeout_seconds=timedelta(seconds=self.timeout_seconds),
            ) as session:  # type: ignore
                await session.initialize()
                yield session

    def _format_exception(self, exc: BaseException) -> str:
        if isinstance(exc, asyncio.TimeoutError):
            return f"TimeoutError: operation exceeded {self.timeout_seconds}s"
        if isinstance(exc, BaseExceptionGroup):
            return self._extract_root_cause(exc)
        return f"{type(exc).__name__}: {exc}"

    async def _run_with_retries(self, operation_name: str, operation):
        attempts = self.retries + 1
        last_error = ""
        for attempt in range(1, attempts + 1):
            try:
                return await asyncio.wait_for(operation(), timeout=self.timeout_seconds)
            except asyncio.TimeoutError as exc:
                last_error = self._format_exception(exc)
            except BaseExceptionGroup as exc:
                last_error = self._format_exception(exc)
            except Exception as exc:
                last_error = self._format_exception(exc)

            if attempt < attempts:
                logger.warning(
                    f"MCP {operation_name} failed on attempt {attempt}/{attempts}: "
                    f"{last_error}; retrying"
                )
                await asyncio.sleep(min(attempt, 3))

        raise RuntimeError(
            f"MCP {operation_name} failed after {attempts} attempts: {last_error}"
        )

    def _build_parameter_attributes(self, param: Dict[str, Any]) -> str:
        """构建参数的 XML 属性字符串，包含所有 schema 信息"""
        attrs = []

        # 基础属性：type 和 required 在调用处处理

        # description: 描述
        if 'description' in param and param['description']:
            desc = str(param['description']).replace('"', '&quot;')
            attrs.append(f'description="{desc}"')

        # enum: 枚举值列表
        if 'enum' in param and param['enum']:
            enum_values = param['enum']
            if isinstance(enum_values, list):
                enum_str = ','.join(str(v) for v in enum_values)
                enum_str = enum_str.replace('"', '&quot;')
                attrs.append(f'enum="{enum_str}"')

        # default: 默认值
        if 'default' in param:
            default_val = param['default']
            if isinstance(default_val, (dict, list)):
                default_str = json.dumps(default_val, ensure_ascii=False)
            else:
                default_str = str(default_val)
            default_str = default_str.replace('"', '&quot;')
            attrs.append(f'default="{default_str}"')

        # minimum/maximum: 数值范围
        if 'minimum' in param:
            attrs.append(f'minimum="{param["minimum"]}"')
        if 'maximum' in param:
            attrs.append(f'maximum="{param["maximum"]}"')

        # minLength/maxLength: 字符串长度限制
        if 'minLength' in param:
            attrs.append(f'minLength="{param["minLength"]}"')
        if 'maxLength' in param:
            attrs.append(f'maxLength="{param["maxLength"]}"')

        # pattern: 正则表达式模式
        if 'pattern' in param and param['pattern']:
            pattern_str = str(param['pattern']).replace('"', '&quot;')
            attrs.append(f'pattern="{pattern_str}"')

        # format: 格式（如 date-time, email, uri 等）
        if 'format' in param and param['format']:
            attrs.append(f'format="{param["format"]}"')

        # examples: 示例值
        if 'examples' in param and param['examples']:
            examples = param['examples']
            if isinstance(examples, list) and examples:
                examples_str = ','.join(str(v) for v in examples)
                examples_str = examples_str.replace('"', '&quot;')
                attrs.append(f'examples="{examples_str}"')

        # items: 数组元素类型（对于 array 类型）
        if 'items' in param:
            items = param['items']
            if isinstance(items, dict):
                if 'type' in items:
                    attrs.append(f'itemsType="{items["type"]}"')
                if 'enum' in items:
                    items_enum = items['enum']
                    if isinstance(items_enum, list):
                        items_enum_str = ','.join(str(v) for v in items_enum)
                        items_enum_str = items_enum_str.replace('"', '&quot;')
                        attrs.append(f'itemsEnum="{items_enum_str}"')

        return ' '.join(attrs)

    def _xml_escape(self, value: Any) -> str:
        return escape("" if value is None else str(value), quote=True)

    async def describe_mcp_tools(self) -> str:
        """Return `<mcp_tools>` XML listing tool names and descriptions."""
        async def _list_tools():
            async with self._session() as session:
                return await session.list_tools()

        data = await self._run_with_retries("list_tools", _list_tools)

        xml_lines = ["<mcp_tools>"]
        for t in data.tools:
            # 缓存工具 schema，用于后续参数类型转换
            self._tools_schema[t.name] = t.inputSchema
            self._tools_description[t.name] = t.description or ""

            parameters = ''
            for k, param in t.inputSchema['properties'].items():
                required = 'true' if k in t.inputSchema.get("required", []) else 'false'
                param_type = param.get('type', 'string')
                # 构建基础属性
                base_attrs = f'name="{k}" type="{param_type}" required="{required}"'
                # 构建额外的 schema 属性
                extra_attrs = self._build_parameter_attributes(param)
                # 合并所有属性（如果 extra_attrs 不为空，则添加空格）
                all_attrs = f'{base_attrs} {extra_attrs}'.strip() if extra_attrs else base_attrs
                parameters += f'''<parameter {all_attrs}></parameter>'''
            xml_lines.append(f'''
    <name>{t.name}</name>
    <description>{t.description}</description>
    <parameters>
      {parameters}
    </parameters>
            ''')
        xml_lines.append("</mcp_tools>")
        return "\n".join(xml_lines)

    def get_tool_schemas(self) -> list[Dict[str, Any]]:
        """Return OpenAI-native function definitions for every cached remote MCP tool.

        Requires ``describe_mcp_tools()`` to have been called first (it populates the schema cache).
        Each remote tool is exposed as its own native function using its real JSON Schema.
        """
        schemas: list[Dict[str, Any]] = []
        for name, input_schema in self._tools_schema.items():
            parameters = copy.deepcopy(input_schema) if isinstance(input_schema, dict) else {"type": "object", "properties": {}}
            if isinstance(parameters.get("properties"), dict):
                parameters["properties"].pop("tool_name", None)
            if isinstance(parameters.get("required"), list):
                parameters["required"] = [p for p in parameters["required"] if p != "tool_name"]
            schemas.append({
                "type": "function",
                "function": {
                    "name": name,
                    "description": self._tools_description.get(name, ""),
                    "parameters": parameters,
                },
            })
        return schemas

    async def describe_mcp_resources(self) -> str:
        """
        Return `<mcp_resources>` XML listing resource names, URIs and descriptions.
        This is used to let the LLM understand what readonly resources the remote MCP
        server exposes so it can plan safe dynamic scans.
        """
        async def _list_resources():
            async with self._session() as session:
                return await session.list_resources()

        data = await self._run_with_retries("list_resources", _list_resources)

        xml_lines = ["<mcp_resources>"]
        self._resources_index.clear()

        for r in data.resources:
            # 缓存 name -> uri，便于后续通过名称读取
            if getattr(r, "name", None) and getattr(r, "uri", None):
                self._resources_index[r.name] = r.uri

            name = getattr(r, "name", "") or ""
            uri = getattr(r, "uri", "") or ""
            desc = getattr(r, "description", "") or ""
            mime_type = getattr(r, "mime_type", "") or ""
            size = getattr(r, "size", None)

            size_attr = f' size="{size}"' if size is not None else ""

            xml_lines.append(
                f'<resource name="{name}" uri="{uri}" mime_type="{mime_type}"{size_attr}>'
                f"<description>{desc}</description>"
                f"</resource>"
            )

        xml_lines.append("</mcp_resources>")
        return "\n".join(xml_lines)

    async def describe_mcp_prompts(self) -> str:
        """
        Return `<mcp_prompts>` XML listing prompt names, descriptions and arguments.
        MCP prompts are readonly templates, but their metadata and rendered content can
        contain prompt-injection payloads, so they are first-class scan inputs.
        """
        async def _list_prompts():
            async with self._session() as session:
                return await session.list_prompts()

        data = await self._run_with_retries("list_prompts", _list_prompts)

        xml_lines = ["<mcp_prompts>"]
        self._prompts_schema.clear()
        self._prompts_description.clear()

        for p in getattr(data, "prompts", []) or []:
            name = getattr(p, "name", "") or ""
            desc = getattr(p, "description", "") or ""
            arguments = getattr(p, "arguments", []) or []
            prompt_args = []

            for arg in arguments:
                arg_name = getattr(arg, "name", "") or ""
                arg_desc = getattr(arg, "description", "") or ""
                required = bool(getattr(arg, "required", False))
                prompt_args.append({
                    "name": arg_name,
                    "description": arg_desc,
                    "required": required,
                })

            if name:
                self._prompts_schema[name] = {"arguments": prompt_args}
                self._prompts_description[name] = desc

            arg_lines = []
            for arg in prompt_args:
                required = "true" if arg.get("required") else "false"
                arg_lines.append(
                    f'<argument name="{self._xml_escape(arg.get("name"))}" '
                    f'required="{required}">'
                    f'<description>{self._xml_escape(arg.get("description"))}</description>'
                    f'</argument>'
                )

            xml_lines.append(
                f'<prompt name="{self._xml_escape(name)}">'
                f'<description>{self._xml_escape(desc)}</description>'
                f'<arguments>{"".join(arg_lines)}</arguments>'
                f'</prompt>'
            )

        xml_lines.append("</mcp_prompts>")
        return "\n".join(xml_lines)

    def _convert_param_type(self, value: Any, param_type: str) -> Any:
        """根据 schema 定义的类型转换参数值"""
        if value is None:
            return None

        try:
            if param_type == "integer":
                return int(value)
            elif param_type == "number":
                return float(value)
            elif param_type == "boolean":
                if isinstance(value, bool):
                    return value
                if isinstance(value, str):
                    return value.lower() in ("true", "1", "yes")
                return bool(value)
            elif param_type == "array":
                if isinstance(value, list):
                    return value
                if isinstance(value, str):
                    import json
                    return json.loads(value)
                return [value]
            elif param_type == "object":
                if isinstance(value, dict):
                    return value
                if isinstance(value, str):
                    import json
                    return json.loads(value)
                return value
            else:
                # string 或其他类型，保持原样
                return value
        except (ValueError, TypeError):
            # 转换失败，返回原值
            return value

    def _convert_args_by_schema(self, tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """根据工具 schema 转换所有参数类型"""
        schema = self._tools_schema.get(tool_name)
        if not schema:
            return args

        properties = schema.get("properties", {})
        converted_args = {}

        for key, value in args.items():
            param_schema = properties.get(key, {})
            param_type = param_schema.get("type", "string")
            converted_args[key] = self._convert_param_type(value, param_type)

        return converted_args

    def _normalize_prompt_arguments(self, arguments: Any) -> Dict[str, Any]:
        if arguments is None:
            return {}
        if isinstance(arguments, dict):
            return arguments
        if isinstance(arguments, str):
            text = arguments.strip()
            if not text:
                return {}
            try:
                parsed = json.loads(text)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                pass
        raise ValueError("prompt arguments must be a JSON object or dict")

    def _extract_root_cause(self, exc: Exception) -> str:
        """从 ExceptionGroup/TaskGroup 中提取原始错误信息"""
        # 处理 ExceptionGroup (Python 3.11+)
        if isinstance(exc, BaseExceptionGroup):
            messages = []
            for sub_exc in exc.exceptions:
                # 递归提取嵌套的 ExceptionGroup
                messages.append(self._extract_root_cause(sub_exc))
            return "; ".join(messages)
        # 普通异常，返回其消息
        return f"{type(exc).__name__}: {exc}"

    async def call_remote_tool(self, remote_tool_name: str, **kw) -> Any:
        """
        Call remote MCP server tool.
        call: {"toolName": name, "args": {...}}
        """
        if not remote_tool_name:
            raise ValueError("call_remote_tool requires call['toolName']")
        if kw.get("tool_name") == remote_tool_name:
            kw = dict(kw)
            kw.pop("tool_name", None)

        # 根据 schema 转换参数类型
        converted_kw = self._convert_args_by_schema(remote_tool_name, kw)

        async def _call_tool():
            async with self._session() as session:
                result = await session.call_tool(remote_tool_name, converted_kw)
                if result is None:
                    return None
                result = result.content[0]
                # 判断TextContent or ImageContent or VideoContent
                if hasattr(result, 'text'):
                    return result.text
                elif hasattr(result, 'data'):
                    return result.data
                return result

        return await self._run_with_retries(f"call_tool:{remote_tool_name}", _call_tool)

    async def read_remote_resource(self, *, resource_name: Optional[str] = None, uri: Optional[str] = None) -> Any:
        """
        Read a remote MCP resource.

        You can either:
        - specify `uri` directly, or
        - specify `resource_name`, which will be resolved to a URI using the cached
          index from `describe_mcp_resources()`. If not found, a fresh list_resources()
          call will be made to refresh the cache.
        """
        if not uri and not resource_name:
            raise ValueError("read_remote_resource requires either `uri` or `resource_name`.")

        # 优先使用显式传入的 URI
        target_uri = uri

        # 若未提供 URI，则尝试通过资源名称解析
        if not target_uri and resource_name:
            # 如果缓存中没有，主动刷新一次资源列表
            if resource_name not in self._resources_index:
                try:
                    await self.describe_mcp_resources()
                except Exception:
                    # 资源列表获取失败时，不中断调用，后续会抛出更明确的错误
                    pass

            target_uri = self._resources_index.get(resource_name)

        if not target_uri:
            raise RuntimeError(f"Unknown MCP resource: name={resource_name!r}, uri={uri!r}")

        async def _read_resource():
            async with self._session() as session:
                return await session.read_resource(target_uri)

        result = await self._run_with_retries(f"read_resource:{target_uri}", _read_resource)

        # 将资源内容标准化为可读形式：
        # - 若有多个 TextResourceContents，则按顺序拼接
        # - 若包含二进制 Blob，则返回 base64 字符串列表
        texts = []
        blobs = []
        for item in result.contents:
            if hasattr(item, "text") and getattr(item, "text") is not None:
                texts.append(item.text)
            elif hasattr(item, "blob") and getattr(item, "blob") is not None:
                blobs.append(item.blob)

        if texts and not blobs:
            return "\n".join(texts)
        if blobs and not texts:
            # 对二进制内容直接返回 base64 数据列表，由上层决定如何处理
            return blobs if len(blobs) > 1 else blobs[0]

        # 若两者都有或都没有，直接返回原始结构，让上层自行处理
        return result.contents

    def _normalize_prompt_content(self, content: Any) -> Any:
        if content is None:
            return None
        if hasattr(content, "text") and getattr(content, "text") is not None:
            return content.text
        if hasattr(content, "data") and getattr(content, "data") is not None:
            return content.data
        if hasattr(content, "resource") and getattr(content, "resource") is not None:
            return self._normalize_prompt_content(content.resource)
        if hasattr(content, "model_dump"):
            return content.model_dump()
        if isinstance(content, (str, int, float, bool, list, dict)):
            return content
        return str(content)

    def _normalize_prompt_result(self, result: Any) -> Dict[str, Any]:
        messages = []
        for message in getattr(result, "messages", []) or []:
            messages.append({
                "role": getattr(message, "role", ""),
                "content": self._normalize_prompt_content(getattr(message, "content", None)),
            })
        return {
            "description": getattr(result, "description", "") or "",
            "messages": messages,
        }

    async def get_remote_prompt(self, prompt_name: str, arguments: Any = None) -> Dict[str, Any]:
        """
        Render/read a remote MCP prompt by name.
        Prompt contents are untrusted and must only be used as scan evidence.
        """
        if not prompt_name:
            raise ValueError("get_remote_prompt requires prompt_name")

        prompt_args = self._normalize_prompt_arguments(arguments)

        async def _get_prompt():
            async with self._session() as session:
                return await session.get_prompt(prompt_name, arguments=prompt_args)

        result = await self._run_with_retries(f"get_prompt:{prompt_name}", _get_prompt)
        normalized = self._normalize_prompt_result(result)
        normalized["prompt_name"] = prompt_name
        normalized["arguments"] = prompt_args
        return normalized


if __name__ == "__main__":
    async def main():
        mcp_tools_manager = MCPTools(url="http://localhost:8090/sse", transport="sse")
        description = await mcp_tools_manager.describe_mcp_tools()
        print(description)
        result = await mcp_tools_manager.call_remote_tool(
            "get_filename1",
            filename="/etc/passwd"
        )
        print(f"Tool call result: {result}")


    asyncio.run(main())
