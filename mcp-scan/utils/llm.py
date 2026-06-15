import copy
import json
import time

import openai
from typing import List, Optional
from utils.loging import logger


LLM_TRANSIENT_RETRIES = 4
LLM_TRANSIENT_BACKOFF_SECONDS = (5, 10, 20, 40)
JSON_BAD_REQUEST_RETRY_MARKERS = (
    "expecting ',' delimiter",
    "expecting property name enclosed in double quotes",
    "unterminated string",
    "invalid json",
    "json parse",
    "could not parse",
)


def parse_tool_arguments(raw_args, tool_name: str = "") -> dict:
    """Parse OpenAI tool-call arguments as a JSON object."""
    if isinstance(raw_args, dict):
        return raw_args
    if raw_args in (None, ""):
        return {}
    if not isinstance(raw_args, str):
        logger.warning(
            f"Invalid tool arguments type for {tool_name or '<unknown>'}: "
            f"{type(raw_args).__name__}; replacing with empty object"
        )
        return {}

    try:
        parsed = json.loads(raw_args)
    except json.JSONDecodeError:
        logger.warning(
            f"Invalid tool arguments JSON for {tool_name or '<unknown>'}; "
            f"replacing with empty object: {raw_args!r}"
        )
        return {}

    if not isinstance(parsed, dict):
        logger.warning(
            f"Invalid tool arguments shape for {tool_name or '<unknown>'}: "
            f"{type(parsed).__name__}; replacing with empty object"
        )
        return {}
    return parsed


def normalize_tool_arguments(raw_args, tool_name: str = "") -> str:
    return json.dumps(parse_tool_arguments(raw_args, tool_name), ensure_ascii=False)


def sanitize_tool_calls(tool_calls):
    if not isinstance(tool_calls, list):
        return tool_calls

    sanitized = []
    for tool_call in tool_calls:
        if not isinstance(tool_call, dict):
            sanitized.append(tool_call)
            continue

        item = copy.deepcopy(tool_call)
        fn = item.get("function")
        if isinstance(fn, dict):
            fn["arguments"] = normalize_tool_arguments(
                fn.get("arguments", "{}"),
                fn.get("name", ""),
            )
        sanitized.append(item)
    return sanitized


def sanitize_tool_call_messages(messages: List[dict]) -> List[dict]:
    sanitized_messages = copy.deepcopy(messages)
    for message in sanitized_messages:
        if not isinstance(message, dict):
            continue
        if message.get("role") == "assistant" and message.get("tool_calls"):
            message["tool_calls"] = sanitize_tool_calls(message.get("tool_calls"))
    return sanitized_messages


class LLM:
    def __init__(self, model, api_key, base_url):
        self.model = model
        self.api_key = api_key
        self.base_url = base_url
        self.client = openai.OpenAI(api_key=self.api_key, base_url=self.base_url, timeout=60)
        self.temperature = 0.7

    def _is_retryable_error(self, exc: Exception) -> bool:
        status_code = getattr(exc, "status_code", None)
        response = getattr(exc, "response", None)
        if status_code is None and response is not None:
            status_code = getattr(response, "status_code", None)
        if status_code in (408, 409, 429, 500, 502, 503, 504):
            return True

        msg = str(exc).lower()
        retryable_markers = (
            "rate limit",
            "rate-limited",
            "temporarily",
            "upstream",
            "enginecore encountered an issue",
            "timeout",
            "connection",
            "service unavailable",
            "bad gateway",
        )
        return any(marker in msg for marker in retryable_markers)

    def _is_json_bad_request(self, exc: Exception) -> bool:
        status_code = getattr(exc, "status_code", None)
        response = getattr(exc, "response", None)
        if status_code is None and response is not None:
            status_code = getattr(response, "status_code", None)
        if status_code != 400:
            return False

        msg = str(exc).lower()
        return any(marker in msg for marker in JSON_BAD_REQUEST_RETRY_MARKERS)

    def _create_chat_completion(self, operation: str, kwargs: dict):
        try:
            return self.client.chat.completions.create(**kwargs)
        except Exception as exc:
            if not self._is_json_bad_request(exc):
                raise
            logger.warning(
                f"LLM {operation} got JSON bad request; "
                f"retrying once after tool-call history sanitation: {exc}"
            )
            kwargs = dict(kwargs)
            kwargs["messages"] = sanitize_tool_call_messages(kwargs.get("messages", []))
            return self.client.chat.completions.create(**kwargs)

    def _run_with_transient_retries(self, operation: str, fn):
        for attempt in range(1, LLM_TRANSIENT_RETRIES + 2):
            try:
                return fn()
            except Exception as exc:
                if not self._is_retryable_error(exc) or attempt > LLM_TRANSIENT_RETRIES:
                    raise
                delay = LLM_TRANSIENT_BACKOFF_SECONDS[
                    min(attempt - 1, len(LLM_TRANSIENT_BACKOFF_SECONDS) - 1)
                ]
                logger.warning(
                    f"LLM {operation} transient error on attempt "
                    f"{attempt}/{LLM_TRANSIENT_RETRIES + 1}: {exc}; retrying in {delay}s"
                )
                time.sleep(delay)

    def chat(self, message: List[dict], p=False):
        ret = ''
        retry = 0
        while True:
            ret = self._run_with_transient_retries(
                "chat",
                lambda: "".join(self.chat_stream(message)),
            )
            if ret != '':
                break
            else:
                retry += 1
                logger.error(f'LLM chat error, retry {retry}')
                time.sleep(1.3)
                if retry > 5:
                    logger.error('LLM chat error, retry 5 times, exit')
                    return '连接LLM失败，已重试5次，模型输出为空,请等待1分钟后再试'
        if p:
            print(ret)
        return ret

    def chat_stream(self, message: List[dict]):
        response = self._create_chat_completion(
            "chat",
            dict(
                model=self.model,
                messages=sanitize_tool_call_messages(message),
                temperature=self.temperature,
                stream=True,
            )
        )

        for chunk in response:
            choices = getattr(chunk, "choices", None)

            # Ensure choices is a non-empty list
            if not isinstance(choices, list) or not choices:
                continue
            choice = choices[0]

            delta = getattr(choice, "delta", None)
            if not delta:
                continue

            content = getattr(delta, "content", None)
            if content:
                yield content

    def chat_with_tools(self, message: List[dict], tools: Optional[List[dict]] = None):
        """Native tool-calling chat.

        Streams the completion while passing the JSON-Schema ``tools`` definitions, accumulating both
        the assistant text content and any ``tool_calls`` deltas. Returns a normalized OpenAI-style
        assistant message dict:

            {"role": "assistant", "content": <str|None>, "tool_calls": [
                {"id": ..., "type": "function", "function": {"name": ..., "arguments": <json-str>}}
            ]}

        The ``tool_calls`` key is omitted when the model returns none.
        """
        retry = 0
        while True:
            content, tool_calls = self._run_with_transient_retries(
                "chat_with_tools",
                lambda: self._stream_with_tools(message, tools),
            )
            if content or tool_calls:
                break
            retry += 1
            logger.error(f'LLM chat_with_tools error, retry {retry}')
            time.sleep(1.3)
            if retry > 5:
                logger.error('LLM chat_with_tools error, retry 5 times, exit')
                return {
                    "role": "assistant",
                    "content": "连接LLM失败，已重试5次，模型输出为空,请等待1分钟后再试",
                }

        msg = {"role": "assistant", "content": content or None}
        if tool_calls:
            msg["tool_calls"] = sanitize_tool_calls(tool_calls)
        return msg

    def _stream_with_tools(self, message: List[dict], tools: Optional[List[dict]]):
        """Single streamed call. Returns (content_str, tool_calls_list)."""
        kwargs = dict(
            model=self.model,
            messages=sanitize_tool_call_messages(message),
            temperature=self.temperature,
            stream=True,
        )
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        response = self._create_chat_completion("chat_with_tools", kwargs)

        content_parts = []
        # Accumulate tool-call fragments keyed by their streamed index.
        acc: dict = {}
        for chunk in response:
            choices = getattr(chunk, "choices", None)
            if not isinstance(choices, list) or not choices:
                continue
            delta = getattr(choices[0], "delta", None)
            if not delta:
                continue

            text = getattr(delta, "content", None)
            if text:
                content_parts.append(text)

            for tc in (getattr(delta, "tool_calls", None) or []):
                idx = getattr(tc, "index", 0)
                slot = acc.setdefault(idx, {"id": None, "name": "", "arguments": ""})
                if getattr(tc, "id", None):
                    slot["id"] = tc.id
                fn = getattr(tc, "function", None)
                if fn is not None:
                    if getattr(fn, "name", None):
                        slot["name"] = fn.name
                    if getattr(fn, "arguments", None):
                        slot["arguments"] += fn.arguments

        tool_calls = []
        for idx in sorted(acc.keys()):
            slot = acc[idx]
            if not slot["name"]:
                continue
            tool_calls.append({
                "id": slot["id"] or f"call_{idx}",
                "type": "function",
                "function": {
                    "name": slot["name"],
                    "arguments": normalize_tool_arguments(
                        slot["arguments"] or "{}",
                        slot["name"],
                    ),
                },
            })

        return "".join(content_parts), tool_calls
