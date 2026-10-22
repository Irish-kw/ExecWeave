"""Explicit, instance-only chat history correction for MetaGPT 1.0.0.

This is behavior-changing and separate from recording. It does not enable
system prompts, change generation options, or repair stream configuration.
"""

from __future__ import annotations

from copy import deepcopy


class PreserveOllamaChatHistory:
    def __init__(self, original):
        if original.api_suffix != "/chat":
            raise ValueError("History compatibility correction supports /chat only")
        self.original = original

    def __getattr__(self, name):
        return getattr(self.original, name)

    def apply(self, messages):
        result = []
        for message in deepcopy(messages):
            content = message["content"]
            if isinstance(content, list):
                texts, images = [], list(message.get("images", []))
                for part in content:
                    if part["type"] == "text":
                        texts.append(part["text"])
                    elif part["type"] == "image_url":
                        url = part["image_url"]["url"]
                        if not url.startswith("data:image/") or ";base64," not in url:
                            raise ValueError(
                                "Only base64 data images supported by Ollama chat correction"
                            )
                        images.append(url.split(";base64,", 1)[1])
                    else:
                        raise ValueError("Unsupported Ollama chat content part")
                message["content"] = "\n".join(texts)
                if images:
                    message["images"] = images
            result.append(message)
        return {
            **deepcopy(self.original.additional_kwargs),
            "model": self.original.model,
            "messages": result,
        }


def enable_chat_history_compatibility(llm):
    """Opt in for this LLM only; preserve the original adapter for inspection."""
    if not isinstance(llm.ollama_message, PreserveOllamaChatHistory):
        llm.ollama_message = PreserveOllamaChatHistory(llm.ollama_message)
    llm._ollama_compatibility = "preserve_chat_history"
