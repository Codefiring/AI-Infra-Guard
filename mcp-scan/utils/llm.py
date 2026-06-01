import time

import openai
from typing import List, Optional
from utils.loging import logger


class LLM:
    def __init__(self, model, api_key, base_url):
        self.model = model
        self.api_key = api_key
        self.base_url = base_url
        self.client = openai.OpenAI(api_key=self.api_key, base_url=self.base_url, timeout=60)
        self.temperature = 0.7

    def chat(self, message: List[dict], p=False):
        ret = ''
        retry = 0
        while True:
            for word in self.chat_stream(message):
                # if p:
                #     print(word, end='', flush=True)
                ret += word
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
        response = self.client.chat.completions.create(
            model=self.model,
            messages=message,
            temperature=self.temperature,
            stream=True
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
            content, tool_calls = self._stream_with_tools(message, tools)
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
            msg["tool_calls"] = tool_calls
        return msg

    def _stream_with_tools(self, message: List[dict], tools: Optional[List[dict]]):
        """Single streamed call. Returns (content_str, tool_calls_list)."""
        kwargs = dict(
            model=self.model,
            messages=message,
            temperature=self.temperature,
            stream=True,
        )
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        response = self.client.chat.completions.create(**kwargs)

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
                "function": {"name": slot["name"], "arguments": slot["arguments"] or "{}"},
            })

        return "".join(content_parts), tool_calls
