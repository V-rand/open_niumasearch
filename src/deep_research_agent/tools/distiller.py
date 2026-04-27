from __future__ import annotations

from typing import Any
from deep_research_agent.dashscope_backend import ModelBackend

DISTILL_SYSTEM_PROMPT = """
你是专业研究员的【证据提取助手】。
你的唯一任务是：从给定的长文中，提取出与用户【研究意图 (Intent)】高度相关的原始证据。

### 核心铁律：
1. **高保真提取**：严禁对原文进行任何总结、概括或修饰。必须使用 Markdown 的块引用格式 `> ` 提取原文。
2. **事实清单**：如果原文中有关键数字、日期、专有名词，请以无序列表形式列出。
3. **拒绝脑补**：严禁引入任何长文之外的外部知识。
4. **诚实原则**：如果长文中完全没有提到 Intent 相关内容，请直接回复：“原文未提及相关信息。”
5. **极简回显**：不要寒暄，直接输出提取到的证据块。
""".strip()

def distill_evidence(
    model_backend: ModelBackend,
    text: str,
    focus_query: str,
) -> str:
    """Uses a sub-agent to extract high-fidelity evidence. Includes context window protection."""
    if not focus_query:
        return text[:1500] + "\n\n... (Snippet only; provide focus_query for better results) ..."

    # Context Window Protection: 
    # Qwen-Plus typically handles 128k, but we use a safer limit for the 'lite' call
    # and to ensure the response isn't cut off.
    max_chars = 60000 
    if len(text) > max_chars:
        # If too long, take the first 40% and last 40% (common heuristic for long docs)
        half = int(max_chars * 0.4)
        text = text[:half] + "\n\n... [Content Truncated due to Length] ...\n\n" + text[-half:]

    messages = [
        {"role": "system", "content": DISTILL_SYSTEM_PROMPT},
        {"role": "user", "content": f"<intent>\n{focus_query}\n</intent>\n\n<source_text>\n{text}\n</source_text>"}
    ]
    
    try:
        return model_backend.complete_lite(messages)
    except Exception as e:
        return f"Error during distillation: {e}\n\nFalling back to snippet:\n{text[:1000]}"
