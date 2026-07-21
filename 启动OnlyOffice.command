#!/bin/bash
# 本地启动 OnlyOffice Document Server（供后评估小助手预览/在线编辑生成的 docx/xlsx）
# 前提：已安装并启动 Docker Desktop。首次运行会拉取 ~2GB 镜像、容器初始化需 1-2 分钟。
cd "$(dirname "$0")"

IMAGE="onlyoffice/documentserver:9.3.1"
NAME="onlyoffice-ds"
PORT=8080

echo "=== 1/4 检查 Docker ==="
if ! command -v docker >/dev/null 2>&1; then
  echo "✗ 未安装 Docker。请先安装 Docker Desktop（Apple Silicon 版）并启动。"; exit 1
fi
if ! docker info >/dev/null 2>&1; then
  echo "✗ Docker 守护进程未运行。请打开 Docker Desktop 等它变成 Running 再重试。"; exit 1
fi
echo "✓ Docker 就绪"

echo "=== 2/4 读取 JWT 密钥（与 Gateway 必须一致，不回显）==="
set -a; source MainAgent/.env 2>/dev/null; set +a
if [ -z "$ONLYOFFICE_JWT_SECRET" ]; then
  echo "✗ MainAgent/.env 里没有 ONLYOFFICE_JWT_SECRET"; exit 1
fi
echo "✓ 已读取密钥（长度 ${#ONLYOFFICE_JWT_SECRET}）"

echo "=== 3/4 启动容器 ==="
if [ "$(docker ps -aq -f name=^${NAME}$)" ]; then
  echo "容器已存在，重启中…"
  docker start "$NAME" >/dev/null
else
  echo "拉取镜像（首次约 2GB，请耐心）…"
  docker pull "$IMAGE" || exit 1
  docker run -d --name "$NAME" -p ${PORT}:80 \
    -e JWT_ENABLED=true \
    -e JWT_SECRET="$ONLYOFFICE_JWT_SECRET" \
    -e JWT_HEADER=Authorization \
    -e JWT_IN_BODY=true \
    -e WOPI_ENABLED=false \
    -e USE_UNAUTHORIZED_STORAGE=true \
    -v onlyoffice-logs:/var/log/onlyoffice \
    -v onlyoffice-data:/var/www/onlyoffice/Data \
    -v onlyoffice-lib:/var/lib/onlyoffice \
    -v onlyoffice-db:/var/lib/postgresql \
    --restart unless-stopped \
    "$IMAGE" || exit 1
fi

echo "=== 4/4 等待文档服务器就绪（首启需 1-2 分钟）==="
# 注意：容器内 nginx 会先于内部服务起来，期间 /healthcheck 可能先返回 true、随后又变 502
# （内部服务还在建库/迁移）。所以要求**连续 3 次成功**才算真就绪，避免"假就绪"。
ok=0
for i in $(seq 1 100); do
  if [ "$(curl -s -m 3 http://localhost:${PORT}/healthcheck 2>/dev/null)" = "true" ]; then
    ok=$((ok+1))
  else
    ok=0
  fi
  if [ $ok -ge 3 ]; then
    echo ""
    echo "✅ OnlyOffice 已就绪: http://localhost:${PORT}"
    echo "   下一步：确保 config.yaml 的 onlyoffice 段为本地值（doc_server_url/doc_server_public_url=http://localhost:${PORT}，"
    echo "   callback_url/file_url_template 主机=host.docker.internal:8001），然后重启后端。"
    exit 0
  fi
  printf "  等待中… %ds\r" $((i*3)); sleep 3
done
echo ""
echo "⚠️ 等待超时。用 'docker logs -f ${NAME}' 看初始化进度。"
