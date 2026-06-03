# 计划：空白点接口去认证 + 10 个专用 Hermes 容器

阶段 1：Build 基础镜像
 1 python deploy_docker.py --rebuild hermes,gateway --fast
│ 不需要重建 frontend/manage-front，只测 API。

阶段 2：创建 create_innovation_hermes.py

- 直接调用 Docker API 创建 10 个容器：hermes-innovation-00 ~ hermes-innovation-09
- 使用镜像：nanobot-hermes-agent:latest
- 接入网络：openclaw-internal（与 gateway 同网络，可直接通过容器名访问）
- 内部端口：18080
- 环境变量：API_SERVER_ENABLED=true, API_SERVER_HOST=0.0.0.0, API_SERVER_PORT=18080, API_SERVER_KEY=dev-hermes-bridge-key 等
- 支持 python create_innovation_hermes.py --create / --destroy / --status

阶段 3：修改 platform/app/routes/model_chat.py

- 去掉认证依赖：移除 get_current_user 和 User 模型引用
- 轮询容器：把 _resolve_hermes_url(user) 改为 _resolve_innovation_hermes_url()，用 itertools.cycle 轮询 http://hermes-innovation-{idx}:18080
- abort 逻辑中的 _resolve_hermes_url(user) 同步替换
- SSE 流式逻辑保持不变

阶段 4：修改 start_test_mining.sh

- 去掉任何 Authorization header
- 测试正常对话和 abort 功能
- 可以并发多跑几次验证轮询

# 实际部署,
1. 修改nginx的配置，因为我们使用platform容器作为管理空白点接口，使用的是 0.0.0.0:8080->8080
/etc/nginx/conf.d/innovation_zhishi.conf
改成        proxy_pass http://localhost:8080;  # 这里指定后端服务的地址
sudo systemctl reload nginx

2. base镜像制作,因为国内网络问题，镜像打包失败
登录新加坡服务器
克隆代码 /data/server/nanobot
切换分支为hermes_model_chat
buid镜像
bash build_base_image.sh
导出镜像
docker save -o hermes_base.zip hermes-base:latest
同步base镜像到本地,大概4.7GB，速度较慢
cd /data/server
rsync -avz root@agent0:/data/server/nanobot/hermes_base.zip .
加载同步的镜像
docker load -i hermes_base.zip
验证镜像导入成功
docker images | grep hermes-base:latest
hermes-base:latest                                                                                                                               7c748e56d589       6.43GB         6.43GB

3. 继续正常的部署和build流程即可
部署目录改成： /data/server/hermes_nanobot, 原有的/data/server/guo_data/nanobot还是作为openclaw_newfront分支
python deploy_docker.py --rebuild hermes,gateway,frontend,manage-front --fast

# 创建10个空白点容器
python create_innovation_hermes.py --destroy && python create_innovation_hermes.py --create

# 单个测试, 测试访问本机的8080，即platform对应的API完成测试
start_test_mining.sh

# 多个用户并发测试
# 轮询更多的Agent,防止Agent互相覆盖文件
python start_test_mining_multiuser.py --concurrency 5 --print-content --prompt "创建1个README.md文件，写上当前的时间戳"

# 部署到服务器后测试
curl -s -N --max-time 60 -X POST "https://innovation.yifuzhishi.com/api/model/chat" -H "Content-Type: application/json" \
  -d '{"linkId":"q1","sessionId":"quick-test-001","userId":1,"functionId":1,"messages":[{"role":"user","content":"say hello in one word"}],"type":0,"attachment":{},"callTools":true,"XAPIVersion":1}'
输出:
data: {"linkId": "q1", "sessionId": "quick-test-001", "userId": 1, "functionId": 1, "attachment": {}, "XAPIVersion": 1, "message": "Hello", "type": 4}
data: {"linkId": "q1", "sessionId": "quick-test-001", "userId": 1, "functionId": 1, "attachment": {}, "XAPIVersion": 1, "message": "[stop]", "reasoningMessage": "", "type": 4}

