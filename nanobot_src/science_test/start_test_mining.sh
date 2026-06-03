#!/usr/bin/env bash
# 快速测试 /api/science/chat 接口（空白点模式，无需认证）
URL="http://localhost:8080/api/science/chat"

echo "=== 1. 缺linkId(应返回400) ==="
curl -s -X POST "$URL" -H "Content-Type: application/json" \
  -d '{"sessionId":"s1","messages":[{"role":"user","content":"hi"}],"type":0}'
echo -e "\n"

echo "=== 2. 停止会话 ==="
curl -s -X POST "$URL" -H "Content-Type: application/json" \
  -d '{"linkId":"l1","sessionId":"s1","messages":[],"type":-1}'
echo -e "\n"

echo "=== 3. 正常对话(SSE流式) ==="
curl -s -N --max-time 60 -X POST "$URL" -H "Content-Type: application/json" \
  -d '{"linkId":"q1","sessionId":"quick-test-001","userId":1,"functionId":1,"messages":[{"role":"user","content":"say hello in one word"}],"type":0,"attachment":{},"callTools":true,"XAPIVersion":1}'
echo -e "\n=== done ==="

echo ""
echo "=== 4. 轮询测试：连续发送3个请求验证容器轮询 ==="
for i in 1 2 3; do
  echo "--- Request $i ---"
  curl -s -N --max-time 60 -X POST "$URL" -H "Content-Type: application/json" \
    -d "{\"linkId\":\"poll-$i\",\"sessionId\":\"poll-test-$i\",\"userId\":1,\"functionId\":1,\"messages\":[{\"role\":\"user\",\"content\":\"用一句话介绍自己\"}],\"type\":0,\"attachment\":{},\"callTools\":true,\"XAPIVersion\":1}" | grep -v '"message":"","reasoningMessage":"","type":4'
  echo -e "\n--- Request $i done ---\n"
  sleep 1
done
