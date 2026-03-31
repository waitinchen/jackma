# Build stage
FROM node:20-alpine AS builder

WORKDIR /app

# 複製 package files
COPY package*.json ./

# 安裝依賴
RUN npm ci

# 複製原始碼
COPY . .

# 設定 API URL 環境變數並 build
ARG VITE_API_URL
RUN echo "VITE_API_URL=$VITE_API_URL" > .env && npm run build

# Production stage - 使用 nginx 來 serve 靜態檔案
FROM nginx:alpine

# 複製 nginx 設定
COPY nginx.conf /etc/nginx/nginx.conf

# 複製 build 產物 (vite 輸出到 ../web_static)
COPY --from=builder /web_static /usr/share/nginx/html

# Cloud Run 使用 PORT 環境變數
EXPOSE 8080

# 啟動 nginx
CMD ["nginx", "-g", "daemon off;"]
