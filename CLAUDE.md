# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AI WeWork Robot 是一個基於 Python 的企業微信（WeChat Work）機器人，整合大型語言模型（預設為 DashScope qwen-plus）提供智能對話功能。

## Development Commands

### Setup
```bash
pip3 install -r requirements.txt
```

### Run Server
```bash
python3 main.py
```
Server runs on `0.0.0.0:6880`

### Configuration
Edit `config.py` with:
- `sToken`: WeChat Work application token
- `sEncodingAESKey`: Message encryption key
- `sCorpID`: Enterprise WeChat ID
- `sCorpsecret`: Application secret
- `dashscope_api_key`: Alibaba Cloud DashScope API key

## Architecture

### Message Flow
1. WeChat Work sends encrypted XML message to `/wechat` endpoint
2. `WXBizMsgCrypt` decrypts message using AES encryption
3. Message added to async queue for processing
4. `func.chat_msg()` handles AI conversation with context management
5. Response encrypted and sent back via WeChat Work API

### Key Components

**main.py** - FastAPI webhook server
- `GET /`: URL verification endpoint for WeChat Work setup
- `POST /wechat`: Message webhook with signature verification
- Async queue (`asyncio.Queue`) for non-blocking message processing
- `consume_queue()`: Background task that processes messages from queue
- Special commands: "ping", "help" return immediate responses

**func.py** - AI integration and message handling
- `chat_msg()`: Main message handler with context management
- `ai_chat()`: DashScope API integration with 15s timeout (using AsyncOpenAI client)
- `User_chat_context`: In-memory dict storing conversation history per AgentID
- `example_context`: Preset system prompt (customizable)
- Access token auto-refresh on API errors (errcode != 0)
- Special command "new": Resets conversation context

**WXBizMsgCrypt.py** - WeChat Work encryption/decryption
- `WXBizMsgCrypt`: Main class for message crypto operations
- `VerifyURL()`: Validates webhook URL during setup
- `DecryptMsg()`: Decrypts incoming messages with signature verification
- `EncryptMsg()`: Encrypts outgoing messages
- Uses AES-256-CBC with PKCS7 padding

**config.py** - Credentials configuration
- All values must be filled before running
- Obtain from WeChat Work admin console

**ierror.py** - Error code constants for crypto operations

### Context Management
- Conversations are stored per `AgentID` (not per user)
- Context persists in memory (lost on restart)
- Each user starts with `example_context` preset
- Send "new" to reset context for current agent

### API Integration
- WeChat Work API: `https://qyapi.weixin.qq.com/cgi-bin/`
- DashScope API: `https://dashscope.aliyuncs.com/compatible-mode/v1` (OpenAI-compatible)
- Model: qwen-plus
- Access token fetched on startup and refreshed on 401/expired errors

## Important Notes

### Message Processing
- Messages are processed asynchronously via queue to avoid blocking webhook
- Webhook returns immediately after queuing message
- Actual AI response sent separately via WeChat Work message API

### Security
- Never commit filled `config.py` with real credentials
- Message encryption/decryption follows WeChat Work official protocol
- Signature verification on all incoming messages

### Limitations
- No persistent storage - context lost on restart
- Single DashScope model (qwen-plus) hardcoded
- No rate limiting or queue size limits
- Access token stored in global variable (not thread-safe for multiple workers)
