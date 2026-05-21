import concurrent.futures
import json
import logging
import os
import re
import time

from openai import OpenAI
from tqdm import tqdm

logger = logging.getLogger("castflux")

SYSTEM_PROMPT = """你是一个短视频运营专家，擅长将直播中的问答内容提炼为爆款短视频。

下面是一段"粉丝提问→博主回答"的完整文字记录。请完成以下任务：
1. 提取核心信息：明确指出目标人群、具体问题、博主给出的解决方法（一句话总结）。
2. 生成一个爆款短视频标题（15字以内），必须包含"人群+问题+解决方法"的结构，吸引点击。
3. 找出一句最具冲突、干货或情绪冲击的句子作为"前情提要"（20字以内），用于视频开头抓人。

请按JSON格式返回，不要加其他文字：
{
  "crowd": "目标人群",
  "problem": "遇到的问题",
  "solution": "解决方法",
  "title": "爆款标题",
  "teaser": "前情提要文字"
}"""


def _call_llm(block_text: str, client: OpenAI) -> dict:
    for attempt in range(3):
        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": SYSTEM_PROMPT + "\n\n" + block_text}],
                temperature=0.7,
                max_tokens=300,
                timeout=30,
            )
            content = response.choices[0].message.content
            json_match = re.search(r"\{.*\}", content, re.DOTALL)
            data = json.loads(json_match.group()) if json_match else json.loads(content)
            return {
                "teaser": data.get("teaser", "").strip(),
                "title": data.get("title", "").strip(),
                "crowd": data.get("crowd", "").strip(),
                "problem": data.get("problem", "").strip(),
                "solution": data.get("solution", "").strip(),
            }
        except Exception as e:
            logger.warning(f"  LLM 调用失败 (尝试 {attempt + 1}/3): {e}")
            time.sleep(1)

    logger.error("  LLM 调用全部失败，使用默认值")
    return {
        "teaser": "精彩问答片段",
        "title": "直播精华问答",
        "crowd": "用户",
        "problem": "常见问题",
        "solution": "专家解答",
    }


def batch_generate(blocks: list[dict], max_workers: int = 5) -> list[dict]:
    logger.info(f"步骤5/6: 生成标题和提要 (并发 {max_workers})...")
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"], timeout=30)

    results = [None] * len(blocks)

    def task(i: int, block: dict) -> tuple[int, dict]:
        return i, _call_llm(block["full_text"], client)

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(task, i, b): i for i, b in enumerate(blocks)}
        for future in tqdm(
            concurrent.futures.as_completed(futures),
            total=len(futures),
            desc="  生成标题",
        ):
            idx, meta = future.result()
            results[idx] = meta

    return results
