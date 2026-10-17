#!/usr/bin/env bash
# 部署面里每条隐式默认值的唯一声明（p15 建议 4 / P02）。
#
# 消费者：scripts/compose_smoke.sh —— source 本文件，按 id 读期望值并真跑该形态。
# 期望值只在这里出现一次；消费者不写第二份，声明里缺字段或整条缺记录，那条检查立刻转红。
#
# 记录：BR_DEPLOY_DEFAULTS[<id>] = '<surface>|<anchor>|<k=v;k=v>'
#   surface : 这条默认值写进哪个文件（相对仓库根）
#   anchor  : 该文件里必须逐字出现的文本（默认值的声明位）
#   k=v     : 真跑该形态时该读到的值；消费它的检查逐条读，读不到即判红
declare -A BR_DEPLOY_DEFAULTS=(
  # P29：index.html 不许被浏览器缓存，内容哈希的 /assets/ 可以永久缓存。
  [spa-cache-headers]='deploy/nginx.conf|add_header Cache-Control|index_path=/;index_header=no-store;asset_header=immutable'
  # P35：api/worker 起来前必须有一个一次性迁移作业把 schema 推到 head。
  [one-shot-migrate]='compose.yaml|command: ["alembic", "upgrade", "head"]|service=migrate;exec=alembic current;marker=(head)'
  # M6 P11：容器以非 root 跑，root 写不了挂载出来的 data/。
  [containers-non-root]='apps/api/Dockerfile|USER app|services=api,worker;forbidden_uid=0'
  # M6 P12：upstream 是变量 + Docker 内嵌 DNS，扩容出来的副本才会被 nginx 看见。
  [dynamic-upstream]='deploy/nginx.conf|resolver 127.0.0.11 valid=10s ipv6=off|samples=12;min_instances=2;instance_header=x-instance-id'
  # P11：SSE/WS 不许吃 nginx 默认的 60s 空闲超时。
  [ws-idle-timeout]='deploy/nginx.conf|proxy_read_timeout 300s|directive=proxy_read_timeout;seconds=300'
)
