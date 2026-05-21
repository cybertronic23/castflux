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

PROVIDER_CONFIG = {
    "deepseek": {
        "base_url": "https://api.deepseek.com/v1",
        "default_model": "deepseek-chat",
        "api_key_env": "DEEPSEEK_API_KEY",
    },
    "qwen": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "default_model": "qwen-plus",
        "api_key_env": "QWEN_API_KEY",
    },
    "glm": {
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "default_model": "glm-4-plus",
        "api_key_env": "GLM_API_KEY",
    },
    "minimax": {
        "base_url": "https://api.minimax.chat/v1",
        "default_model": "minimax-text-01",
        "api_key_env": "MINIMAX_API_KEY",
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "default_model": "gpt-4o-mini",
        "api_key_env": "OPENAI_API_KEY",
    },
}

DEFAULT_PROVIDER = "deepseek"


def resolve_llm_config(provider: str | None = None, model: str | None = None) -> dict:
    provider = provider or os.environ.get("LLM_PROVIDER") or DEFAULT_PROVIDER
    provider = provider.lower()

    cfg = PROVIDER_CONFIG.get(provider)
    if not cfg:
        available = ", ".join(PROVIDER_CONFIG)
        logger.warning(f"未知 provider '{provider}'，可用: {available}，回退到 {DEFAULT_PROVIDER}")
        cfg = PROVIDER_CONFIG[DEFAULT_PROVIDER]

    api_key = os.environ.get(cfg["api_key_env"]) or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        logger.error(
            f"缺少 API key: 请设置 {cfg['api_key_env']} 环境变量\n"
            f"  你也可以设置 OPENAI_API_KEY 作为通用回退"
        )
        raise RuntimeError(f"未找到 {cfg['api_key_env']} 环境变量")

    resolved_model = model or os.environ.get("LLM_MODEL") or cfg["default_model"]

    logger.info(f"  LLM provider: {provider}, model: {resolved_model}")
    return {
        "api_key": api_key,
        "base_url": cfg["base_url"],
        "model": resolved_model,
    }


def _call_llm(block_text: str, client: OpenAI, model: str) -> dict:
    for attempt in range(3):
        try:
            response = client.chat.completions.create(
                model=model,
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


def batch_generate(
    blocks: list[dict],
    max_workers: int = 5,
    provider: str | None = None,
    model: str | None = None,
) -> list[dict]:
    logger.info(f"步骤5/6: 生成标题和提要 (并发 {max_workers})...")
    llm_cfg = resolve_llm_config(provider, model)
    client = OpenAI(api_key=llm_cfg["api_key"], base_url=llm_cfg["base_url"], timeout=30)

    results = [None] * len(blocks)

    def task(i: int, block: dict) -> tuple[int, dict]:
        return i, _call_llm(block["full_text"], client, llm_cfg["model"])

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
