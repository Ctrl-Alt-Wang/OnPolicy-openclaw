"""
Judge Proxy Server (port 20001)
- return_logprob=False  → 转发给 GPT-5.4 API（judge/eval 调用）
- return_logprob=True   → 转发给本地 SGLang:20000（teacher logprob 调用）

judge 输出格式要求：
  score: \boxed{1} 或 \boxed{-1}
  hint:  [HINT_START]...[HINT_END]
"""
import re, httpx, uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

SGLANG_URL  = "http://127.0.0.1:20000/generate"
GPT_URL     = "http://8.219.115.209:6600/v1/chat/completions"
GPT_KEY     = "sk-eb9bXqd0mJBUfeXkA9EfDaAa03Cb4692B59aB89471BdBfDd"
GPT_MODEL   = "gpt-5.4"

# Strip Qwen chat template tokens so GPT-5.4 sees clean text
_SPECIAL = re.compile(r"<\|im_start\|>(system|user|assistant)\n?|<\|im_end\|>\n?")

app = FastAPI()

@app.post("/generate")
async def generate(request: Request):
    payload = await request.json()
    return_logprob = payload.get("return_logprob", False)

    if return_logprob:
        # Teacher logprob call → forward to SGLang as-is
        async with httpx.AsyncClient(timeout=None) as client:
            r = await client.post(SGLANG_URL, json=payload)
            return JSONResponse(content=r.json())

    # Judge/eval call → GPT-5.4
    text = payload.get("text", "")
    sp   = payload.get("sampling_params", {})
    max_tokens = sp.get("max_new_tokens", 1024)

    # Clean special tokens for GPT readability
    clean_text = _SPECIAL.sub("", text).strip()

    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(
            GPT_URL,
            json={
                "model": GPT_MODEL,
                "messages": [{"role": "user", "content": clean_text}],
                "max_completion_tokens": min(max_tokens, 1024),
                "temperature": sp.get("temperature", 0.7),
            },
            headers={"Authorization": f"Bearer {GPT_KEY}"},
        )
        data = r.json()

    reply = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    return JSONResponse(content={"text": reply, "meta_info": {}})

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=20001)
