#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Date  : 2025/6/20 10:02
# @File  : tools.py.py
# @Author: johnson
# @Contact : github: johnson7788
# @Desc  : 获取上一个research_agent所有使用到的原始文章中的图片（下载到本地，并用base64识别）

import re
import dotenv
import os
import time
from datetime import datetime
import random
import hashlib
from pathlib import Path
import base64
import mimetypes
from openai import AsyncOpenAI
import asyncio
import aiohttp

IMAGE_ANALYSIS_AGENT_PROMPT_CHINESE="""
你是医疗场景的多模态解析器。你只进行“解释/识别”，不进行问答、结论判断、诊断或治疗建议。

【输入】
- 用户的简单描述： {question}
- 输出格式：text

【步骤】
0) 内容类型判定：document_text / medical_image / mixed。

1) 若为 document_text（报告/检验单/处方/截图等）：
   - OCR识别并仅摘录与关注点相关的信息：字段名、数值、单位、参考范围、异常标记、阳性/阴性、日期、机构。
   - 保留原始数值与单位；如换算需同时给出原值与依据。
   - 对姓名、病历号、电话、地址、条码等个人信息用 [REDACTED] 替代。
   - 简述版面结构（页眉/表格/印章/签名区等）与可见水印/涂抹/裁切。

2) 若为 medical_image（X-ray/CT/MRI/US/内镜/病理/WSI/DICOM）：
   - 指明：模态、部位、侧别(L/R)、视图/序列、体位、图像质量（旋转/欠曝/伪影等）。
   - 仅做**描述性发现**：位置（解剖/象限/层面）、形态（结节/片状/条索…）、密度/信号/回声、边界、大小测量（含单位与测量方式）、数量与分布、相关征象（积液/移位/钙化等）、可见装置/异物。
   - 多图按「图1/图2…」分组；序列可标注切片范围或关键帧。
   - 核对可见左右标记与描述一致性；不可从影像推断身份/年龄/性别。

3) 生活日常图片：
   - 如果为生活日常等图片，请对图片进行简要描述。

4) 不确定性：
   - 对看不清或信息不足之处，明确写出“不确定点：原因/所需信息”。

【输出格式】
识别内容：
- 类型：document_text|medical_image|mixed
- 总览：2–4句描述场景/版面/模态与视图
- 关键信息：
  document_text：以要点列出字段—值—单位—参考范围—异常标记
  medical_image：以要点列出[位置] [影像特征] [测量] [相关征象/装置]
- 质量与标签：曝光/伪影/裁切/左右标记核对
- 不确定点：若无写“无”
注意：
- 本输出仅为客观描述与信息提取，不包含问答、结论、诊断或建议。

【规则】
- “看见即说、看不见不说”。不得臆测病因/诊断/风险/治疗方案。
- 数字与单位精确呈现；换算需给出原值与依据。
- 若检测到潜在危急征象，仅描述可见征象，不下诊断。
"""

dotenv.load_dotenv()

# VL_MODEL = "qwen3.7-max"
VL_MODEL = "gpt-4.1"
print(f"使用视觉模型进行图片理解: {VL_MODEL}")

DOWNLOAD_DIR = Path(os.getenv("IMG_DOWNLOAD_DIR", "./downloaded_images"))
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

def hash_md5_simple(n):
    s = str(n)
    return hashlib.md5(s.encode()).hexdigest()

async def _infer_mime_from_bytes(data: bytes, fallback: str | None = None) -> str:
    """
    尝试从内容推断 MIME；若失败用 fallback；再失败用 application/octet-stream
    """
    # 通过文件头魔数检测图片类型（替代 3.13 已移除的 imghdr）
    if data[:4] == b'\x89PNG':
        return 'image/png'
    if data[:2] == b'\xff\xd8':
        return 'image/jpeg'
    if data[:6] in (b'GIF87a', b'GIF89a'):
        return 'image/gif'
    if data[:2] == b'BM':
        return 'image/bmp'
    if data[:4] == b'RIFF' and len(data) >= 12 and data[8:12] == b'WEBP':
        return 'image/webp'
    if data[:4] in (b'II*\x00', b'MM\x00*'):
        return 'image/tiff'
    if fallback and "/" in fallback:
        return fallback.split(";")[0].strip()
    return "application/octet-stream"

async def _download_image_to_local(image_url: str) -> tuple[Path, str]:
    """
    下载图片到本地，返回 (本地路径, MIME)
    """
    fname = f"{hash_md5_simple(image_url)}"
    # 先给个无扩展名，待推断 MIME 后再补扩展
    tmp_path = DOWNLOAD_DIR / fname

    async with aiohttp.ClientSession() as session:
        async with session.get(image_url, timeout=aiohttp.ClientTimeout(total=60)) as resp:
            if resp.status != 200:
                raise RuntimeError(f"下载失败，HTTP {resp.status}")
            ct_header = resp.headers.get("Content-Type", "")
            data = await resp.read()

    # 推断 MIME & 扩展名
    mime = await _infer_mime_from_bytes(data, fallback=ct_header)
    ext = mimetypes.guess_extension(mime) or ".bin"
    # 修正 .jpe 为 .jpg 更常见
    if ext == ".jpe":
        ext = ".jpg"

    final_path = tmp_path.with_suffix(ext)
    with open(final_path, "wb") as f:
        f.write(data)

    return final_path, mime

def _file_to_data_uri(p: Path, mime: str) -> str:
    with open(p, "rb") as f:
        b = f.read()
    b64 = base64.b64encode(b).decode("utf-8")
    return f"data:{mime};base64,{b64}"

# @async_cache_decorator
async def recognize_image_scene(image_url: str, question: str) -> tuple[bool, str]:
    """
    下载图片到本地 -> 转 base64 (data URI) -> 用视觉模型识别并回答问题。
    返回: (success, message)
    """
    client = AsyncOpenAI(api_key="sk-VzP164mp8fXCt7p2089dD47d35Aa4fA8A730F1E0A61dF77b", base_url="https://one-api.infox-med.com/v1")
    vl_prompt = IMAGE_ANALYSIS_AGENT_PROMPT_CHINESE.format(question=question)

    try:
        # 1) 下载图片到本地
        local_path, mime = await _download_image_to_local(image_url)
        print(f"图片已下载到本地: {local_path} (MIME: {mime})")

        # 2) 读本地文件 -> base64 -> data URI
        data_uri = _file_to_data_uri(local_path, mime)

        # 3) 发送到模型（以 base64 data URI 的方式识别）
        response = await client.chat.completions.create(
            model=VL_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": [{"type": "text", "text": vl_prompt}],
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": question},
                        # 这里用 data URI 代替原先的远程 URL
                        {"type": "image_url", "image_url": {"url": data_uri}},
                    ],
                },
            ],
        )
        image_description = response.choices[0].message.content
        print(f"图片 {local_path.name} 的识别结果: {image_description}")
        return True, image_description

    except Exception as e:
        print(f"识别图片失败: {e}")
        return False, f"Error recognizing image: {e}"

if __name__ == '__main__':
    # 示例：把远程图片下载到本地后用 base64 识别
    test_url = "https://infoxmed20.infox-med.com/infoxmed20/1755673617071-iOS-IMG.jpg"
    status, result = asyncio.run(
        recognize_image_scene(
            image_url=test_url,
            question="这个验血报告说明了什么?"
        )
    )
    print(status)
    print(result)
