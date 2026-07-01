# SYLANNE 官网 · 静态站 Docker 镜像（nginx:alpine）
FROM nginx:1.27-alpine

# 站点文件（运行时）
COPY site/ /usr/share/nginx/html/
# 站点 nginx 配置（gzip + 缓存）
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
HEALTHCHECK --interval=30s --timeout=3s CMD wget -q -O /dev/null http://127.0.0.1/ || exit 1
