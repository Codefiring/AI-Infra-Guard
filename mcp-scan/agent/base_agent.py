import json
import os.path
import time
import uuid
from datetime import datetime
from typing import List, Optional
from tools.dispatcher import ToolDispatcher
from utils.config import base_dir
from utils.llm import LLM
from utils.loging import logger
from utils.tool_context import ToolContext
from utils.aig_logger import mcpLogger
from utils.prompt_manager import prompt_manager


class BaseAgent:

    def __init__(
            self,
            name: str,
            instruction: str,
            llm: LLM,
            dispatcher: ToolDispatcher,
            specialized_llms: dict = None,
            log_step_id: str = None,
            debug: bool = False,
            capabilities: List[str] = None,
            output_format: Optional[str] = None,
            output_check_fn: callable = None,
            language: str = "zh"
    ):
        self.llm = llm
        self.name = name
        self.dispatcher = dispatcher
        self.specialized_llms = specialized_llms or {}
        self.instruction = instruction
        self.capabilities = capabilities or ["standard"]
        self.output_format = output_format
        self.history = []
        self.tools = []
        self.max_iter = 80
        self.iter = 0
        self.is_finished = False
        self.step_id = log_step_id
        self.debug = debug
        self.repo_dir = ""
        self.output_check_fn = output_check_fn
        self.language = language

    async def initialize(self):
        """异步初始化系统提示词与原生工具定义"""
        if not self.history:
            system_prompt = await self.generate_system_prompt()
            self.history.append({"role": "system", "content": system_prompt})
        if not self.tools:
            self.tools = await self.dispatcher.get_tool_definitions()

    def add_user_message(self, message: str):
        self.history.append({"role": "user", "content": message})

    def set_repo_dir(self, repo_dir: str):
        self.repo_dir = repo_dir

    def compact_history(self):
        if len(self.history) < 3:
            return

        prompt = prompt_manager.load_template("compact")
        history = self.history[1:]
        history.append({"role": "user", "content": prompt})
        response = self.llm.chat(history)

        system_prompt = self.history[0]
        user_messages = f"我希望你完成:{self.history[1]['content']} \n\n有以下上下文提供你参考:\n" + response
        self.history = [system_prompt, {"role": "user", "content": user_messages}]

    async def generate_system_prompt(self):

        tools_prompt = await self.dispatcher.get_all_tools_prompt()

        template_name = "system_prompt"
        format_kwargs = {
            "generate_tools": tools_prompt,
            "name": self.name,
            "instruction": self.instruction
        }

        return prompt_manager.format_prompt(template_name, **format_kwargs)

    def next_prompt(self):
        return prompt_manager.format_prompt("next_prompt", round=self.iter)

    async def run(self):
        await self.initialize()
        return await self._run()

    async def _run(self):
        logger.info(f"Agent {self.name} started with max_iter={self.max_iter}")
        result = ""
        while not self.is_finished and self.iter < self.max_iter:
            self.iter += 1
            logger.debug(f"\n{'=' * 50}\nIteration {self.iter}\n{'=' * 50}")
            message = self.llm.chat_with_tools(self.history, self.tools)
            logger.debug(f"LLM Response: {message}")
            self.history.append(message)
            res = await self.handle_response(message)
            if res is not None:
                result = res
            if not self.is_finished and self.iter >= self.max_iter:
                logger.warning(f"Max iterations ({self.max_iter}) reached")
                self.compact_history()
        return result

    async def handle_response(self, message: dict):
        description = message.get("content") or ""
        tool_calls = message.get("tool_calls") or []

        display = description
        if display == "":
            display = "我将继续执行"
            if self.language == "en":
                display = "I will continue to execute"

        mcpLogger.status_update(self.step_id, display, "", "running")

        if not tool_calls:
            return await self.handle_no_tool(display)

        result = None
        for tool_call in tool_calls:
            res = await self.process_tool_call(tool_call, display)
            if res is not None:
                result = res
            if self.is_finished:
                break

        mcpLogger.status_update(self.step_id, display, "", "completed")
        return result

    async def process_tool_call(self, tool_call: dict, description: str):
        tool_id = tool_call.get("id") or uuid.uuid4().__str__()
        fn = tool_call.get("function", {})
        tool_name = fn.get("name", "")
        raw_args = fn.get("arguments", "") or "{}"
        try:
            tool_args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse tool arguments for {tool_name}: {raw_args!r}")
            tool_args = {}
        if not isinstance(tool_args, dict):
            tool_args = {}

        params = json.dumps(tool_args, ensure_ascii=False) if tool_args else ""
        if isinstance(params, str):
            params = params.replace(self.repo_dir, "")

        mcpLogger.tool_used(self.step_id, tool_id, tool_name, "done", tool_name, f"{params}")

        if tool_name == "finish":
            self.is_finished = True
            logger.info(f"Finish tool called, final result formatted.")
            # Answer the tool call so the conversation history stays well-formed.
            self.history.append({
                "role": "tool",
                "tool_call_id": tool_id,
                "content": "Task completion acknowledged.",
            })
            result = await self._format_final_output()
            mcpLogger.action_log(tool_id, tool_name, self.step_id, result)
            return result

        # 构造上下文
        context = ToolContext(
            llm=self.llm,
            history=self.history,
            agent_name=self.name,
            iteration=self.iter,
            specialized_llms=self.specialized_llms,
            folder=self.repo_dir,
            tool_dispatcher=self.dispatcher
        )

        # 通过 Dispatcher 调用工具（本地工具或远程 MCP 工具）
        tool_result = await self.dispatcher.call_tool(tool_name, tool_args, context)
        result_message = f"{tool_result}"

        # 以 role:"tool" 消息回送结果，匹配本次 tool_call 的 id
        self.history.append({
            "role": "tool",
            "tool_call_id": tool_id,
            "content": result_message,
        })

        if tool_name != "read_file":
            mcpLogger.action_log(tool_id, tool_name, self.step_id, f"```\n{result_message}\n```")

        return None

    async def handle_no_tool(self, description: str):
        # 模型未调用任何工具时，提示其继续调用工具或调用 finish 结束。
        nudge = "请通过调用工具继续完成任务；当任务完成时调用 finish 工具结束。"
        if self.language == "en":
            nudge = "Please continue by calling a tool; call the finish tool when the task is complete."
        self.history.append({"role": "user", "content": nudge})
        return None

    async def _format_final_output(self) -> str:
        """使用 LLM 根据历史记录和预设格式生成最终输出"""
        # 取最近的对话历史作为参考
        recent_history = self.history[1:]
        formatting_prompt = prompt_manager.format_prompt(
            "format_report",
            output_format=self.output_format
        )
        recent_history.append({"role": "user", "content": formatting_prompt})
        final_output = ""
        for _ in range(3):
            final_output = self.llm.chat(recent_history)
            logger.info(f"Final Output: {final_output}")
            if self.output_check_fn:
                ret = self.output_check_fn(final_output)
                if isinstance(ret, bool) and ret:
                    break
            else:
                break
        return final_output
