"""
ElevenLabs MCP Server for TTS Text Cleaning
提供 TTS 文本清洗功能，修正多音字發音錯誤
"""
import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# 添加項目路徑
sys.path.insert(0, str(Path(__file__).parent))

from app.services.tts_cleaner import clean_for_tts
from app.services.pronunciation_fix import fix_pronunciation, get_all_rules

app = FastAPI(title="TTS Cleaner MCP Server")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# MCP 協議實現
class MCPServer:
    """Model Context Protocol Server for TTS Cleaning"""
    
    def __init__(self):
        self.tools = [
            {
                "name": "clean_tts_text",
                "description": "清洗文本以優化 TTS 發音，修正多音字發音錯誤。例如：將「重來」替換為「再來一次」。",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "text": {
                            "type": "string",
                            "description": "需要清洗的原始文本"
                        }
                    },
                    "required": ["text"]
                }
            },
            {
                "name": "get_pronunciation_rules",
                "description": "獲取所有發音修正規則列表",
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            }
        ]
    
    def list_tools(self) -> List[Dict[str, Any]]:
        """列出所有可用的工具"""
        return self.tools
    
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """調用指定的工具"""
        if tool_name == "clean_tts_text":
            text = arguments.get("text", "")
            if not text:
                return {
                    "isError": True,
                    "content": [{"type": "text", "text": "錯誤：缺少 text 參數"}]
                }
            
            try:
                # 應用 TTS 清洗
                cleaned_text = clean_for_tts(text, use_pronunciation_fix=True)
                
                return {
                    "isError": False,
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps({
                                "original": text,
                                "cleaned": cleaned_text,
                                "changed": text != cleaned_text
                            }, ensure_ascii=False, indent=2)
                        }
                    ]
                }
            except Exception as e:
                return {
                    "isError": True,
                    "content": [{"type": "text", "text": f"錯誤：{str(e)}"}]
                }
        
        elif tool_name == "get_pronunciation_rules":
            try:
                rules = get_all_rules()
                return {
                    "isError": False,
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(rules, ensure_ascii=False, indent=2)
                        }
                    ]
                }
            except Exception as e:
                return {
                    "isError": True,
                    "content": [{"type": "text", "text": f"錯誤：{str(e)}"}]
                }
        
        else:
            return {
                "isError": True,
                "content": [{"type": "text", "text": f"未知工具：{tool_name}"}]
            }

mcp_server = MCPServer()

@app.get("/health")
async def health():
    """健康檢查"""
    return {"status": "ok", "service": "TTS Cleaner MCP Server"}

@app.post("/mcp/v1/tools/list")
async def list_tools():
    """列出所有工具（MCP 協議）"""
    return {
        "tools": mcp_server.list_tools()
    }

@app.post("/mcp/v1/tools/call")
async def call_tool(request: Request):
    """調用工具（MCP 協議）"""
    try:
        body = await request.json()
        tool_name = body.get("name")
        arguments = body.get("arguments", {})
        
        if not tool_name:
            return {
                "isError": True,
                "content": [{"type": "text", "text": "錯誤：缺少工具名稱"}]
            }
        
        result = await mcp_server.call_tool(tool_name, arguments)
        return result
    except Exception as e:
        return {
            "isError": True,
            "content": [{"type": "text", "text": f"錯誤：{str(e)}"}]
        }

@app.get("/mcp/v1/initialize")
async def initialize():
    """初始化 MCP 服務器（MCP 協議）"""
    return {
        "protocolVersion": "2024-11-05",
        "capabilities": {
            "tools": {}
        },
        "serverInfo": {
            "name": "tts-cleaner-mcp-server",
            "version": "1.0.0"
        }
    }

@app.get("/")
async def root():
    """根路徑，返回服務器信息"""
    return {
        "service": "TTS Cleaner MCP Server",
        "version": "1.0.0",
        "endpoints": {
            "health": "/health",
            "list_tools": "/mcp/v1/tools/list",
            "call_tool": "/mcp/v1/tools/call",
            "initialize": "/mcp/v1/initialize"
        },
        "tools": [
            {
                "name": "clean_tts_text",
                "description": "清洗文本以優化 TTS 發音"
            },
            {
                "name": "get_pronunciation_rules",
                "description": "獲取所有發音修正規則"
            }
        ]
    }

if __name__ == "__main__":
    import os
    port = int(os.getenv("MCP_SERVER_PORT", "8001"))
    host = os.getenv("MCP_SERVER_HOST", "0.0.0.0")
    
    print(f"🚀 Starting TTS Cleaner MCP Server on {host}:{port}")
    print(f"📋 Available tools:")
    for tool in mcp_server.list_tools():
        print(f"  - {tool['name']}: {tool['description']}")
    print(f"\n🌐 Server URL: http://{host}:{port}")
    print(f"🔗 MCP Endpoint: http://{host}:{port}/mcp/v1/tools/call")
    
    uvicorn.run(app, host=host, port=port)
