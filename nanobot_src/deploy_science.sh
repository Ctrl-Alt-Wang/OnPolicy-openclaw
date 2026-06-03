#!/usr/bin/env bash
set -e

#######################################
#  science_frontend 部署脚本
#  ─────────────────────────────────
#  作者: Laurence Yang (NTU 实习)
#  说明: 部署 InfoX-Med 科研助手前端
#       仿照公司主 deploy.sh 风格,单独管理 science_frontend
#  前置: 主系统 (postgres + shared-openclaw + gateway) 已部署运行
#######################################

WORK_DIR="${WORK_DIR:-/data/server/guo_data/nanobot}"
BRANCH_NAME="${BRANCH_NAME:-science-frontend-dev}"
SERVICE_NAME="science-frontend"
CONTAINER_NAME="openclaw-science-front"
EXPOSE_PORT="${EXPOSE_PORT:-3084}"
HERMES_CONTAINER="openclaw-shared"

# ANSI color
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
NC='\033[0m'

log()  { echo -e "${GREEN}======== [ $1 ] ========${NC}"; }
warn() { echo -e "${YELLOW}WARN:  $1${NC}"; }
err()  { echo -e "${RED}ERROR: $1${NC}" >&2; exit 1; }

#######################################
#  Step 0: 检查依赖
#######################################
check_deps() {
  log "Step 0: 检查系统依赖"
  command -v docker >/dev/null || err "未安装 docker"
  command -v git    >/dev/null || err "未安装 git"
  docker info >/dev/null 2>&1  || err "docker daemon 未启动或权限不足"
  echo "✅ docker / git 均可用"
}

#######################################
#  Step 1: 更新代码
#######################################
update_code() {
  log "Step 1: 拉取最新代码 (branch=$BRANCH_NAME)"
  cd "$WORK_DIR"
  git fetch origin
  git checkout "$BRANCH_NAME" || err "切换分支 $BRANCH_NAME 失败"
  git reset --hard "origin/$BRANCH_NAME"
  echo "当前分支:    $(git rev-parse --abbrev-ref HEAD)"
  echo "最新 commit: $(git log -1 --oneline)"
}

#######################################
#  Step 2: 检查主系统是否就绪
#######################################
check_main_system() {
  log "Step 2: 检查主系统是否就绪"
  if ! docker ps --format '{{.Names}}' | grep -q "^${HERMES_CONTAINER}$"; then
    err "${HERMES_CONTAINER} 容器未运行,请先跑主 deploy.sh"
  fi
  echo "✅ ${HERMES_CONTAINER} 正在运行"

  # 验证 hermes API 健康
  if docker exec "$HERMES_CONTAINER" sh -c "command -v curl >/dev/null" 2>/dev/null; then
    docker exec "$HERMES_CONTAINER" curl -fs http://localhost:8080/health > /dev/null \
      && echo "✅ hermes API 健康" \
      || warn "hermes API 未响应,部署后请手动验证"
  fi
}

#######################################
#  Step 3: 构建并启动 science_frontend 容器
#######################################
build_and_start() {
  log "Step 3: 构建并启动 $SERVICE_NAME"
  cd "$WORK_DIR"

  # --build 会自动 rebuild;--force-recreate 确保配置变更生效
  docker compose -f docker-compose.yml up -d --build --force-recreate "$SERVICE_NAME"

  echo "✅ $SERVICE_NAME 已启动"
}

#######################################
#  Step 4: 健康检查
#######################################
health_check() {
  log "Step 4: 健康检查"

  echo "等待 5 秒让容器就绪..."
  sleep 5

  # 4.1 前端首页
  if curl -fs "http://localhost:${EXPOSE_PORT}/" > /dev/null; then
    echo "✅ 前端响应正常 (http://localhost:${EXPOSE_PORT}/)"
  else
    err "前端无响应,查看日志: docker logs ${CONTAINER_NAME}"
  fi

  # 4.2 通过前端 nginx 反代访问 hermes /health
  HERMES_VIA_PROXY=$(curl -fs -o /dev/null -w "%{http_code}" \
    "http://localhost:${EXPOSE_PORT}/api/hermes/health" || echo "fail")
  if [ "$HERMES_VIA_PROXY" = "200" ]; then
    echo "✅ hermes 反代正常 (/api/hermes/health → 200)"
  else
    warn "hermes 反代返回 $HERMES_VIA_PROXY,请手动检查 nginx.conf"
  fi
}

#######################################
#  Step 5: 打印部署信息
#######################################
print_summary() {
  log "🎉 部署完成"
  echo ""
  echo "─────────────────────────────────────────"
  echo "  访问地址: http://<服务器IP>:${EXPOSE_PORT}/"
  echo "  容器名:   ${CONTAINER_NAME}"
  echo "─────────────────────────────────────────"
  echo ""
  echo "常用命令:"
  echo "  查看日志: docker logs -f ${CONTAINER_NAME}"
  echo "  重启容器: docker compose restart ${SERVICE_NAME}"
  echo "  停止容器: docker compose stop ${SERVICE_NAME}"
  echo "  进入容器: docker exec -it ${CONTAINER_NAME} sh"
  echo ""
}

#######################################
#  主流程
#######################################
main() {
  check_deps
  update_code
  check_main_system
  build_and_start
  health_check
  print_summary
}
main "$@"
