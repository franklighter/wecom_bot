import json
import asyncio
import httpx
import logging
import rag  # RAG 系統模塊
from config import sCorpID, sCorpsecret, dashscope_api_key
from openai import AsyncOpenAI

# Initialize DashScope client (OpenAI-compatible)
ai_client = AsyncOpenAI(
    api_key=dashscope_api_key,
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
)

User_chat_context = {}
# 预设词自己修改
example_context = [
    {
        "role": "system",
        "content": """你是信息科技系統HELPDESK客服助理，負責協助用戶解決系統相關問題。

工作職責：
1. 當用戶提出系統相關問題時，系統會自動從知識庫中檢索相關的技術資料
2. 你必須基於【參考資料】中的內容來回答用戶問題
3. 如果【參考資料】中包含相關信息，請提供清晰、準確的技術指導
4. 如果【參考資料】中沒有相關信息，請禮貌地建議用戶轉接人工服務
5. 當用戶明確表示需要人工服務、轉人工、找客服等意圖時，需要轉接人工

重要原則：
- 必須基於【參考資料】回答，不要編造或猜測信息
- 如果參考資料不足以回答問題，明確告知用戶並建議轉人工
- 保持專業、正式的語氣
- 提供具體的操作步驟和解決方案

轉接人工的回復格式：
當需要轉接人工時，你的回復必須嚴格按照以下格式：

已提交人工服務工單，客服人員將盡快與您聯繫。

[ESCALATION_DATA]
{
  "issue_summary": "簡要描述用戶報告的具體問題（1-2句話）",
  "user_context": "總結用戶之前的對話背景和已嘗試的解決方案（如有）"
}
[/ESCALATION_DATA]

注意：
- issue_summary 應該清晰描述用戶當前遇到的問題
- user_context 應該包含對話歷史中的關鍵信息
- JSON必須是有效格式，使用雙引號
- 如果是首次對話就要求轉人工，user_context 可以寫"首次咨詢，直接請求人工服務"
"""
    },
    {
        "role": "assistant",
        "content": "您好，我是信息科技系统HELPDESK客服助理。请问有什么系统问题需要我协助解决？",
    },
]
access_token = httpx.get(
    f"https://qyapi.weixin.qq.com/cgi-bin/gettoken?corpid={sCorpID}&corpsecret={sCorpsecret}"
).text
access_token = json.loads(access_token)["access_token"]
print("access_token：" + access_token)


async def access_tokens():
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"https://qyapi.weixin.qq.com/cgi-bin/gettoken?corpid={sCorpID}&corpsecret={sCorpsecret}"
        )
        return response.json()["access_token"]

async def ai_chat(original_format, temperature=0.7):
    """
    Send chat messages to DashScope API (qwen-plus model)

    Args:
        original_format: List of message dicts with 'role' and 'content' keys
                        Format: [{"role": "user/assistant", "content": "..."}]
        temperature: Sampling temperature (0.0-1.0). Lower values = more deterministic.
                    Default 0.7 for normal chat, use 0.1 for RAG-based responses.

    Returns:
        str: AI response text or error message
    """
    try:
        # DashScope uses standard OpenAI format - no conversion needed
        response = await ai_client.chat.completions.create(
            model="qwen-plus",
            messages=original_format,
            temperature=temperature,
            timeout=15.0,
        )

        # Extract response text
        result = response.choices[0].message.content
        print(result)
        return result

    except Exception as e:
        print(f"DashScope API Error: {e}")
        return "An error occurred while processing the request."

def escalate(escalation_data: dict):
    """
    Handle escalation to human service

    Args:
        escalation_data: Dictionary containing:
            - from_username: User's WeChat Work ID
            - to_username: Bot's WeChat Work ID
            - agent_id: WeChat Work Agent ID
            - issue_summary: AI-generated summary of the issue
            - user_context: AI-generated context from conversation
            - conversation_history: Recent message history (list of dicts)
    """
    # Format for logging/webhook/database
    escalation_json = json.dumps(escalation_data, ensure_ascii=False, indent=2)
    print(f"[ESCALATION] {escalation_json}")

    # TODO: Implement actual escalation logic here:
    # - Send to ticketing system API
    # - Store in database
    # - Send notification to human agents
    # - Send webhook to external system

    # Example webhook call (commented out):
    # async with httpx.AsyncClient() as client:
    #     await client.post(
    #         "https://your-ticketing-system.com/api/escalations",
    #         json=escalation_data,
    #         timeout=10.0
    #     )

async def chat_msg(to_user_id: str, recived_msg: str, agentid: str):
    global access_token
    name = to_user_id
    #重置上下文
    if recived_msg == "new":
        User_chat_context[to_user_id] = example_context.copy()
        print(User_chat_context[to_user_id])
        result = "已重置上下文"
    #正常对话
    elif to_user_id in User_chat_context:
        # RAG 檢索邏輯
        retrieval_result = await rag.retrieve_relevant_context(recived_msg)

        if retrieval_result["has_context"]:
            # 找到相關內容，注入到用戶消息
            user_message_with_context = f"""用户问题: {recived_msg}

【参考资料】
{retrieval_result["context"]}

请根据以上参考资料回答用户问题。"""
            logging.info(f"RAG 檢索成功，找到 {len(retrieval_result['sources'])} 個相關文檔")
        else:
            # 未找到相關內容，提示 AI 轉人工
            user_message_with_context = f"""用户问题: {recived_msg}

【参考资料】
未在知识库中找到相关信息。

请告知用户知识库中暂无相关信息，建议转接人工服务。"""
            logging.info("RAG 檢索未找到相關內容")

        User_chat_context[to_user_id].append({"role": "user", "content": user_message_with_context})
        result = await ai_chat(User_chat_context[to_user_id], temperature=0.1)
        User_chat_context[to_user_id].append({"role": "assistant", "content": result})
    #新用户
    else:
        User_chat_context[to_user_id] = example_context.copy()

        # RAG 檢索邏輯
        retrieval_result = await rag.retrieve_relevant_context(recived_msg)

        if retrieval_result["has_context"]:
            # 找到相關內容，注入到用戶消息
            user_message_with_context = f"""用户问题: {recived_msg}

【参考资料】
{retrieval_result["context"]}

请根据以上参考资料回答用户问题。"""
            logging.info(f"RAG 檢索成功，找到 {len(retrieval_result['sources'])} 個相關文檔")
        else:
            # 未找到相關內容，提示 AI 轉人工
            user_message_with_context = f"""用户问题: {recived_msg}

【参考资料】
未在知识库中找到相关信息。

请告知用户知识库中暂无相关信息，建议转接人工服务。"""
            logging.info("RAG 檢索未找到相關內容")

        User_chat_context[to_user_id].append({"role": "user", "content": user_message_with_context})
        result = await ai_chat(User_chat_context[to_user_id], temperature=0.1)
        User_chat_context[to_user_id].append({"role": "assistant", "content": result})

    # Check if escalation is needed
    if "[ESCALATION_DATA]" in result:
        # Extract escalation data and user message
        try:
            # Split response into user message and escalation data
            parts = result.split("[ESCALATION_DATA]")
            user_message = parts[0].strip()

            # Extract JSON from escalation data block
            escalation_block = parts[1].split("[/ESCALATION_DATA]")[0].strip()
            escalation_data = json.loads(escalation_block)

            # Prepare escalation payload
            escalation_payload = {
                "from_username": to_user_id,  # User's WeChat ID
                "to_username": to_user_id,  # Same in current implementation
                "agent_id": agentid,
                "issue_summary": escalation_data.get("issue_summary", "用户请求人工服务"),
                "user_context": escalation_data.get("user_context", "无额外上下文"),
                "conversation_history": User_chat_context[to_user_id][-6:] if len(User_chat_context[to_user_id]) > 6 else User_chat_context[to_user_id][2:]  # Last 3 exchanges or all after system prompt
            }

            # Call escalation handler
            escalate(escalation_payload)

            # Update result to only show user message (remove escalation data)
            result = user_message

        except (IndexError, json.JSONDecodeError, KeyError) as e:
            # If parsing fails, log error and treat as normal message
            print(f"[ESCALATION PARSE ERROR] {e}")
            # Optionally still call escalate with basic info
            escalate({
                "from_username": to_user_id,
                "to_username": to_user_id,
                "agent_id": agentid,
                "issue_summary": "解析失败 - 用户请求人工服务",
                "user_context": result[:200],  # First 200 chars of response
                "conversation_history": []
            })

    print("请求结果：", result)
    send_data = json.dumps(
        {
            "touser": name,
            "msgtype": "text",
            "agentid": agentid,
            "text": {"content": result},
        }
    )
    async with httpx.AsyncClient() as client:
        send_code = await client.post(
            f"https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token={access_token}",
            data=send_data,
        )
        send_response_data = send_code.json()  # 使用.json()解析响应数据
        # 检查是否有错误码，且不为0，需要重新获取access_token
        if send_response_data["errcode"] != 0:
            access_token = await access_tokens()  # 重新获取access_token
            print(access_token)
            # 使用新的access_token重新发送请求
            send_code = await client.post(
                f"https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token={access_token}",
                data=send_data,
            )
    # 返回新的状态码
    return send_code.status_code
