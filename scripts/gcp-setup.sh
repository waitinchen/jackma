#!/bin/bash
# GCP 快速設定腳本 - 江彬語氣靈
# 使用方式: ./scripts/gcp-setup.sh

set -e

# 顏色輸出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  江彬語氣靈 - GCP 部署設定${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# 檢查 gcloud 是否已安裝
if ! command -v gcloud &> /dev/null; then
    echo -e "${RED}錯誤: 請先安裝 gcloud CLI${NC}"
    echo "下載: https://cloud.google.com/sdk/docs/install"
    exit 1
fi

# 取得專案 ID
echo -e "${YELLOW}請輸入 GCP 專案 ID (例如: jiangbin-voice):${NC}"
read PROJECT_ID

if [ -z "$PROJECT_ID" ]; then
    echo -e "${RED}錯誤: 專案 ID 不能為空${NC}"
    exit 1
fi

# 設定專案
echo -e "${GREEN}設定專案: $PROJECT_ID${NC}"
gcloud config set project $PROJECT_ID

# 取得區域
echo -e "${YELLOW}請選擇區域 (預設: asia-east1):${NC}"
read REGION
REGION=${REGION:-asia-east1}

# 啟用 API
echo -e "${GREEN}啟用必要的 GCP API...${NC}"
gcloud services enable \
    cloudbuild.googleapis.com \
    run.googleapis.com \
    sqladmin.googleapis.com \
    secretmanager.googleapis.com \
    containerregistry.googleapis.com

# 建立 Cloud SQL
echo ""
echo -e "${YELLOW}是否要建立 Cloud SQL 實例? (y/n)${NC}"
read CREATE_SQL

if [ "$CREATE_SQL" = "y" ]; then
    echo -e "${YELLOW}請輸入資料庫密碼:${NC}"
    read -s DB_PASSWORD
    
    echo -e "${GREEN}建立 Cloud SQL 實例 (這可能需要幾分鐘)...${NC}"
    gcloud sql instances create jiangbin-db \
        --database-version=POSTGRES_15 \
        --tier=db-f1-micro \
        --region=$REGION \
        --storage-size=10GB \
        --storage-auto-increase
    
    echo -e "${GREEN}設定資料庫密碼...${NC}"
    gcloud sql users set-password postgres \
        --instance=jiangbin-db \
        --password=$DB_PASSWORD
    
    echo -e "${GREEN}建立資料庫...${NC}"
    gcloud sql databases create jiangbin \
        --instance=jiangbin-db
    
    CONNECTION_NAME=$(gcloud sql instances describe jiangbin-db --format="value(connectionName)")
    echo -e "${GREEN}Cloud SQL 連線名稱: $CONNECTION_NAME${NC}"
fi

# 設定 Secrets
echo ""
echo -e "${YELLOW}是否要設定 API Keys (Secret Manager)? (y/n)${NC}"
read SETUP_SECRETS

if [ "$SETUP_SECRETS" = "y" ]; then
    echo -e "${YELLOW}請輸入 Gemini API Key:${NC}"
    read GEMINI_KEY
    echo -n "$GEMINI_KEY" | gcloud secrets create gemini-api-key --data-file=- 2>/dev/null || \
        echo -n "$GEMINI_KEY" | gcloud secrets versions add gemini-api-key --data-file=-
    
    echo -e "${YELLOW}請輸入 OpenAI API Key:${NC}"
    read OPENAI_KEY
    echo -n "$OPENAI_KEY" | gcloud secrets create openai-api-key --data-file=- 2>/dev/null || \
        echo -n "$OPENAI_KEY" | gcloud secrets versions add openai-api-key --data-file=-
    
    echo -e "${YELLOW}請輸入 ElevenLabs API Key:${NC}"
    read ELEVENLABS_KEY
    echo -n "$ELEVENLABS_KEY" | gcloud secrets create elevenlabs-api-key --data-file=- 2>/dev/null || \
        echo -n "$ELEVENLABS_KEY" | gcloud secrets versions add elevenlabs-api-key --data-file=-
    
    echo -e "${YELLOW}請輸入 ElevenLabs Voice ID:${NC}"
    read VOICE_ID
    echo -n "$VOICE_ID" | gcloud secrets create elevenlabs-voice-id --data-file=- 2>/dev/null || \
        echo -n "$VOICE_ID" | gcloud secrets versions add elevenlabs-voice-id --data-file=-
    
    echo -e "${YELLOW}請輸入 ElevenLabs Agent ID (可選，直接按 Enter 跳過):${NC}"
    read AGENT_ID
    if [ -n "$AGENT_ID" ]; then
        echo -n "$AGENT_ID" | gcloud secrets create elevenlabs-agent-id --data-file=- 2>/dev/null || \
            echo -n "$AGENT_ID" | gcloud secrets versions add elevenlabs-agent-id --data-file=-
    fi
    
    # 產生 JWT Secret
    echo -e "${GREEN}產生 JWT Secret...${NC}"
    JWT_SECRET=$(openssl rand -hex 32)
    echo -n "$JWT_SECRET" | gcloud secrets create jwt-secret-key --data-file=- 2>/dev/null || \
        echo -n "$JWT_SECRET" | gcloud secrets versions add jwt-secret-key --data-file=-
    
    # 授權 Cloud Run 存取 secrets
    echo -e "${GREEN}設定 Secret 存取權限...${NC}"
    PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format="value(projectNumber)")
    
    for SECRET in gemini-api-key openai-api-key elevenlabs-api-key elevenlabs-voice-id jwt-secret-key; do
        gcloud secrets add-iam-policy-binding $SECRET \
            --member="serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" \
            --role="roles/secretmanager.secretAccessor" \
            --quiet
    done
    
    if [ -n "$AGENT_ID" ]; then
        gcloud secrets add-iam-policy-binding elevenlabs-agent-id \
            --member="serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" \
            --role="roles/secretmanager.secretAccessor" \
            --quiet
    fi
fi

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  設定完成！${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "下一步:"
echo -e "1. 執行 ${YELLOW}./scripts/gcp-deploy.sh${NC} 部署應用程式"
echo -e "2. 或推送到 GitHub 觸發自動部署"
echo ""
