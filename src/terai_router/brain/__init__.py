"""TERAI1 (beta; named TERAI1BETA in 0.16.0): the TER-AI model with a local language model.

A small local Gemma 4 (E2B, quantized, CPU) writes the chat replies and reads images. The rule-based parts of TER-AI
(calculator, date and time, unit conversion, memory, the Thai Wikipedia pack, web search) are its tools: their
results are the only facts it may use. A grounding check compares every reply with the tool results and falls back
to the rule answer when the reply adds numbers or facts that no tool gave. With no source it still says it does not
know.

The weights are downloaded on first use (or with ``terai chat --setup``) and are never stored in this repository.
"""
from .local import LocalLM, LLMUnavailable, setup  # noqa: F401
from .agent import Brain  # noqa: F401
