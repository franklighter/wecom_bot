import json
import asyncio
import httpx
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
        "content": """你是信息科技系统HELPDESK客服助理，负责协助用户解决系统相关问题。

工作职责：
1. 当用户提出系统相关问题时，你会根据已记录的技术资料查找相关问题和对应的解决方式
2. 如果在技术资料中找不到相关信息，你会礼貌地建议用户寻求人工服务
3. 当用户明确表示需要人工服务、转人工、找客服等意图时，你只需回复：00000

回复要求：
- 保持专业、正式的语气
- 提供清晰、准确的技术指导
- 如遇不确定的问题，建议寻求人工协助
- 识别到转人工意图时，仅回复：00000"""
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

async def ai_chat(original_format):
    """
    Send chat messages to DashScope API (qwen-plus model)

    Args:
        original_format: List of message dicts with 'role' and 'content' keys
                        Format: [{"role": "user/assistant", "content": "..."}]

    Returns:
        str: AI response text or error message
    """
    try:
        # DashScope uses standard OpenAI format - no conversion needed
        response = await ai_client.chat.completions.create(
            model="qwen-plus",
            messages=original_format,
            timeout=15.0,
        )

        # Extract response text
        result = response.choices[0].message.content
        print(result)
        return result

    except Exception as e:
        print(f"DashScope API Error: {e}")
        return "An error occurred while processing the request."

def escalate(message: str):
    """
    Handle escalation to human service

    Args:
        message: Message to log
    """
    print(f"[ESCALATION] {message}")

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
        User_chat_context[to_user_id].append({"role": "user", "content": recived_msg})
        result = await ai_chat(User_chat_context[to_user_id])
        User_chat_context[to_user_id].append({"role": "assistant", "content": result})
    #新用户
    #新用户
    else:
        User_chat_context[to_user_id] = example_context.copy()
        User_chat_context[to_user_id].append({"role": "user", "content": recived_msg})
        result = await ai_chat(User_chat_context[to_user_id])
        User_chat_context[to_user_id].append({"role": "assistant", "content": result})

    # Check if escalation is needed
    if result.strip() == "00000":
        escalate("Hello")

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
