#!/bin/bash
# GCP 手動部署腳本 - 江彬語氣靈
# 使用方式: ./scripts/gcp-deploy.sh

set -e

# 顏色輸出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  江彬語氣靈 - 部署到 Cloud Run${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# 取得專案資訊
PROJECT_ID=$(gcloud config get-value project)
if [ -z "$PROJECT_ID" ]; then
    echo -e "${RED}錯誤: 請先設定 GCP 專案${NC}"
    echo "執行: gcloud config set project YOUR_PROJECT_ID"
    exit 1
fi

echo -e "${GREEN}專案: $PROJECT_ID${NC}"

# 取得區域
echo -e "${YELLOW}請選擇區域 (預設: asia-east1):${NC}"
read REGION
REGION=${REGION:-asia-east1}

# 取得 Cloud SQL 連線名稱
echo -e "${YELLOW}請輸入 Cloud SQL 連線名稱 (格式: PROJECT:REGION:INSTANCE):${NC}"
echo -e "${YELLOW}(可執行 gcloud sql instances list 查看)${NC}"
read SQL_CONNECTION

if [ -z "$SQL_CONNECTION" ]; then
    echo -e "${RED}錯誤: Cloud SQL 連線名稱不能為空${NC}"
    exit 1
fi

# 取得資料庫密碼
echo -e "${YELLOW}請輸入資料庫密碼:${NC}"
read -s DB_PASSWORD

# 建構 DATABASE_URL
DATABASE_URL="postgresql://postgres:${DB_PASSWORD}@/jiangbin?host=/cloudsql/${SQL_CONNECTION}"

# 建置 Docker 映像
echo ""
echo -e "${GREEN}建置 Docker 映像...${NC}"
docker build -t gcr.io/$PROJECT_ID/jiangbin-api:latest .

# 推送到 Container Registry
echo -e "${GREEN}推送映像到 Container Registry...${NC}"
docker push gcr.io/$PROJECT_ID/jiangbin-api:latest

# 部署到 Cloud Run
echo -e "${GREEN}部署到 Cloud Run...${NC}"

# 檢查 elevenlabs-agent-id secret 是否存在
AGENT_SECRET=""
if gcloud secrets describe elevenlabs-agent-id &>/dev/null; then
    AGENT_SECRET=",ELEVENLABS_AGENT_ID=elevenlabs-agent-id:latest"
fi

gcloud run deploy jiangbin-api \
    --image gcr.io/$PROJECT_ID/jiangbin-api:latest \
    --region $REGION \
    --platform managed \
    --allow-unauthenticated \
    --add-cloudsql-instances $SQL_CONNECTION \
    --set-env-vars "DATABASE_URL=${DATABASE_URL}" \
    --set-secrets "GEMINI_API_KEY=gemini-api-key:latest,OPENAI_API_KEY=openai-api-key:latest,ELEVENLABS_API_KEY=elevenlabs-api-key:latest,ELEVENLABS_VOICE_ID=elevenlabs-voice-id:latest,JWT_SECRET_KEY=jwt-secret-key:latest${AGENT_SECRET}" \
    --memory 1Gi \
    --cpu 1 \
    --timeout 300 \
    --concurrency 80

# 取得服務 URL
SERVICE_URL=$(gcloud run services describe jiangbin-api --region $REGION --format="value(status.url)")

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  部署完成！${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "服務網址: ${YELLOW}$SERVICE_URL${NC}"
echo ""
echo -e "測試 API:"
echo -e "  curl $SERVICE_URL/health"
echo ""
