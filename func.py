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
    {"role": "user", "content": "角色扮演，现在你是鱼开发的机器人，名叫咸鱼"},
    {
        "role": "assistant",
        "content": "你好，我是咸鱼，一个鱼开发的机器人。我很高兴见到你。\n\n作为咸鱼，我可以帮助你完成很多事情。",
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

async def chat_msg(to_user_id: str, recived_msg: str, agentid: str):
    global access_token
    name = to_user_id
    #重置上下文
    if recived_msg == "new":
        User_chat_context[agentid] = example_context.copy()
        print(User_chat_context[agentid])
        result = "已重置上下文"
    #正常对话
    elif agentid in User_chat_context:
        User_chat_context[agentid].append({"role": "user", "content": recived_msg})
        result = await ai_chat(User_chat_context[agentid])
        User_chat_context[agentid].append({"role": "assistant", "content": result})
    #新用户
    #新用户
    else:
        User_chat_context[agentid] = example_context.copy()
        User_chat_context[agentid].append({"role": "user", "content": recived_msg})
        result = await ai_chat(User_chat_context[agentid])
        User_chat_context[agentid].append({"role": "assistant", "content": result})

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
