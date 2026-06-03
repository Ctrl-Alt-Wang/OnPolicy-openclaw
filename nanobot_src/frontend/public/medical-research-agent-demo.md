# 医学科研智能体 Demo 使用说明

这个说明对应同目录下的 `medical-research-agent-demo.html`。这个页面不是静态看板，发送消息时会通过本地 Vite dev server 代理到本地 Platform Gateway，再走 `/api/shared-openclaw/chat` 调用当前 Hermes shared runtime。

## 1. 启动本地服务

不要直接双击 HTML，也不要用 `file://` 打开。页面里的 API 都是相对路径，需要通过前端 dev server 访问。

Linux、macOS、WSL 都可以在仓库根目录执行同一条启动命令。先进入你本机的 nanobot 仓库目录：

```bash
cd /path/to/nanobot
python3 start_local.py --only db,gateway,frontend --local-only
```

启动后打开：

```text
http://127.0.0.1:3080/medical-research-agent-demo.html
```

macOS 上如果 Docker Desktop 没开，可以先启动 Docker Desktop：

```bash
open -a Docker
```

如果 `open -a Docker` 找不到应用，就手动打开 Docker Desktop，等它启动完成后再运行 `start_local.py`。

WSL 里如果 Docker Desktop 没开，可以先执行：

```bash
python3 scripts/ensure_docker_desktop.py
```

如果要让同一局域网里的其他电脑访问你的演示机，改用：

```bash
python3 start_local.py --only db,gateway,frontend --public
```

然后把脚本打印出的局域网地址加上页面路径发给对方，例如：

```text
http://你的局域网IP:3080/medical-research-agent-demo.html
```

如果是在另一台电脑独立运行，也需要在那台电脑上启动同样的本地服务；这个页面没有上传到服务器。

## 2. 页面怎么用

1. 打开页面后，点击“一键创建临时演示身份”。
2. 顶部状态变成“临时身份 / shared”后，可以直接使用默认空白点 prompt。
3. 点击“发送并计时”。
4. 右侧“本次运行”会显示 elapsed、status、session、run。
5. “本页运行记录”会记录当前页面发起的 run。点击“打开会话”可以重新加载对应 session。
6. “会话历史”展示 shared workspace 里的会话；如果后端列表暂时没返回当前 session，页面会把当前 session 作为兜底记录显示出来。
7. “容器与逻辑隔离实现落点”会从后端读取当前代码位置，用来展示 `RuntimeRun`、`X-Hermes-Session-Key` 等实现边界。
8. “隔离演示”里点击“模拟越界读取”，可以演示不同 session 前缀之间的逻辑隔离。

## 3. 常见问题

### 页面能打开，但发送失败

先检查本地服务：

```bash
python3 check_status.py
```

至少需要 `Platform Gateway` 和 `Frontend Dev` 正常。首次创建临时身份时还需要本地数据库可用。

### 会话历史为空

先跑一次 chat。当前页面发起的 run 会先出现在“本页运行记录”，完成后可以点“打开会话”。后端 session list 返回较慢时，页面也会把当前 session 合并进“会话历史”。

### 还看到旧页面

浏览器强制刷新一次：

```text
Windows / Linux: Ctrl+F5
macOS: Cmd+Shift+R
```

或者重新打开 `http://127.0.0.1:3080/medical-research-agent-demo.html`。

### 想换一个临时演示身份

点击“一键创建临时演示身份”会新建一个 demo 专用 shared 用户。页面不会读取主站的二维码登录态，也不会使用 `openclaw_access_token`。

### 想清掉本页运行记录

点击“重置演示状态”。这会清掉当前页面的运行记录、会话选择和隔离演示状态；不会删除后端已经产生的 session。

## 4. 停止服务

如果 `start_local.py` 还在当前终端里运行，按：

```text
Ctrl+C
```

如果需要从另一个终端停止：

```bash
python3 start_local.py --stop
```
