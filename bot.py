from nonebot import logger, get_plugin_config
from nonebot.adapters.onebot.v11 import (
    Bot,
    MessageEvent,
    PrivateMessageEvent,
    GroupMessageEvent,
    PokeNotifyEvent,
    NoticeEvent,
    GroupRecallNoticeEvent,
    FriendRecallNoticeEvent,
)
from maim_message import UserInfo, GroupInfo, Seg ,BaseMessageInfo,MessageBase,FormatInfo,TemplateInfo
from .config import Config
from .util import local_file_to_base64,download_image_url
from typing import Optional

import httpx
import time
import re
import asyncio
import json
import base64



config = get_plugin_config(Config)

# 定义日志配置

class ChatBot:
    def __init__(self):
        self.bot = None  # bot 实例引用
        self._started = False
        self.fastapi_url =  config.fastapi_url
        self.client = httpx.AsyncClient(timeout=60)  # 创建异步HTTP客户端

    async def _ensure_started(self):
        """确保所有任务已启动"""
        if not self._started:
            self._started = True


    async def handle_message(self, event: MessageEvent, bot: Bot) -> None:
        """处理收到的消息"""

        message_content = ''

        self.bot = bot  # 更新 bot 实例
        if isinstance(event, PrivateMessageEvent):
            try:
                user_info = UserInfo(
                    user_id=event.user_id,
                    user_nickname=(await bot.get_stranger_info(user_id=event.user_id, no_cache=True))["nickname"],
                    user_cardname=None,
                    platform=config.platfrom,
                )
            except Exception as e:
                logger.error(f"获取陌生人信息失败: {e}")
                return
            logger.debug(user_info)

            message_content = event.get_plaintext()

            # group_info = GroupInfo(group_id=0, group_name="私聊", platform=config.platfrom)
            group_info = None

        # 处理群聊消息
        else:
            #白名单处理逻辑
            if len(config.allow_group_list) != 0 :
                if event.group_id not in config.allow_group_list:
                    return

            user_info = UserInfo(
                user_id=event.user_id,
                user_nickname=event.sender.nickname,
                user_cardname=event.sender.card or None,
                platform=config.platfrom,
            )
            
            group_info = GroupInfo(group_id=event.group_id, 
                                   group_name=(await bot.get_group_info(group_id = event.group_id,no_cache=True))["group_name"], 
                                   platform=config.platfrom)
            
            #这里是at信息的处理逻辑 可能会比较混乱，但是暂时没找到更好的解决方式
            msg = str(event.raw_message)
            logger.info(f"{msg}")
            qq_ids = list(set(re.findall(r'\[CQ:at,qq=(\d+)\]', msg)))
            if not qq_ids:  # 没有 @ 消息
                message_content = msg
            else:
                # 获取用户昵称，失败时提供默认值
                nicknames = {}
                for qq in qq_ids:
                    try:
                        info = await bot.get_stranger_info(user_id=int(qq))
                        nicknames[qq] = info.get("nickname", f"用户{qq}")
                    except Exception:
                        nicknames[qq] = f"用户{qq}"

                # 替换 @ 消息，避免 KeyError
                message_content = re.sub(
                    r'\[CQ:at,qq=(\d+)\]',
                    lambda m: f'@{nicknames.get(m.group(1), f"用户{m.group(1)}")}（id:{m.group(1)}）',
                    msg
                )
            
        
        message_info = BaseMessageInfo(
                platform = config.platfrom,
                message_id = event.message_id,
                time = time.time(),
                group_info = group_info,
                user_info = user_info,
        )

        message_seg = Seg(  
                    type = 'text',
                    data = message_content,  
            )


        message_base = MessageBase(message_info,message_seg,raw_message=message_content)

        await self.message_process(message_base)

    async def handle_group_announcement(self, event: MessageEvent, bot: Bot) -> None:
        """处理收到的消息"""

        self.bot = bot  # 更新 bot 实例
            #白名单处理逻辑
        if len(config.allow_group_list) != 0 :
            if event.group_id not in config.allow_group_list:
                return

        message_content = ""
        for segment in event.message:
            if segment.type == "json":
                try:

                    data = json.loads(segment.data["data"].replace("&#44;", ","))
                    mannounce = data["meta"]["mannounce"]
                    title = base64.b64decode(mannounce["title"]).decode("utf-8") if mannounce.get("title") else ""
                    text = base64.b64decode(mannounce["text"]).decode("utf-8") if mannounce.get("text") else ""
                    
                    message_content += f"{event.sender.nickname}({event.user_id})发布了【{title}】：\n{text}"

                    
                except (json.JSONDecodeError, KeyError, UnicodeDecodeError) as e:
                    print(f"解析群公告失败: {e}")

            
        group_info = GroupInfo(group_id=event.group_id, 
                                group_name=(await bot.get_group_info(group_id = event.group_id,no_cache=True))["group_name"], 
                                platform=config.platfrom)
        
        user_info = UserInfo(
            user_id=event.user_id,
            user_nickname=event.sender.nickname,
            user_cardname=event.sender.card or None,
            platform=config.platfrom,
        )

        message_info = BaseMessageInfo(
                platform = config.platfrom,
                message_id = event.message_id,
                time = time.time(),
                group_info = group_info,
                user_info = user_info,
        )

        message_seg = Seg(  
                    type = 'text',
                    data = message_content,  
            )


        message_base = MessageBase(message_info,message_seg,raw_message=message_content)

        await self.message_process(message_base)

    async def handle_notice(self, event: NoticeEvent, bot: Bot) -> None:
        """处理收到的通知"""
        if isinstance(event, PokeNotifyEvent):
            # 戳一戳 通知
            # 不处理其他人的戳戳
            if not event.is_tome():
                return

            #白名单处理逻辑
            if len(config.allow_group_list) != 0 :
                if event.group_id not in config.allow_group_list:
                    return

            nickname = (await bot.get_login_info())["nickname"]

            raw_message = f"[戳了戳]{nickname}"  # 默认类型
            if info := event.model_extra["raw_info"]:
                poke_type = info[2].get("txt", "戳了戳")  # 戳戳类型，例如“拍一拍”、“揉一揉”、“捏一捏”
                custom_poke_message = info[4].get("txt", "")  # 自定义戳戳消息，若不存在会为空字符串
                raw_message = f"[{poke_type}]{nickname}{custom_poke_message}"

                raw_message += "（这是一个类似摸摸头的友善行为，而不是恶意行为，请不要作出攻击发言）"

            user_info = UserInfo(
                user_id=event.user_id,
                user_nickname=(await bot.get_stranger_info(user_id=event.user_id, no_cache=True))["nickname"],
                user_cardname=None,
                platform=config.platfrom,
            )

            if event.group_id:
                group_info = GroupInfo(group_id=event.group_id, 
                        group_name=(await bot.get_group_info(group_id = event.group_id,no_cache=True))["group_name"], 
                        platform=config.platfrom)
            else:
                group_info = None

            message_info = BaseMessageInfo(
                    platform = config.platfrom,
                    message_id = None,
                    time = time.time(),
                    group_info= group_info,
                    user_info = user_info,
            )

            message_seg = Seg(
                    type = 'text',
                    data = raw_message,  
            )

            message_base = MessageBase(message_info,message_seg,raw_message=raw_message)

            await self.message_process(message_base)

        # 处理撤回消息存储的逻辑，先放着不动
        # elif isinstance(event, GroupRecallNoticeEvent) or isinstance(event, FriendRecallNoticeEvent):
        #     user_info = UserInfo(
        #         user_id=event.user_id,
        #         user_nickname=get_user_nickname(event.user_id) or None,
        #         user_cardname=get_user_cardname(event.user_id) or None,
        #         platform=config.platfrom,
        #     )

        #     if isinstance(event, GroupRecallNoticeEvent):
        #         group_info = GroupInfo(group_id=event.group_id, group_name=None, platform=config.platfrom)
        #     else:
        #         group_info = None

        #     chat = await chat_manager.get_or_create_stream(
        #         platform=user_info.platform, user_info=user_info, group_info=group_info
        #     )

        #     await self.storage.store_recalled_message(event.message_id, time.time(), chat)

    async def download_image_url(url: str) -> Optional[str]:
        """带重试和超时的图片下载函数"""
        async with httpx.AsyncClient(timeout=10) as client:
            for _ in range(3):  # 最多重试3次
                try:
                    resp = await client.get(url)
                    resp.raise_for_status()
                    return base64.b64encode(resp.content).decode("utf-8")
                except (httpx.RequestError, httpx.HTTPStatusError) as e:
                    await asyncio.sleep(1)
            return None

    async def handle_image_message(self, event: MessageEvent, bot: Bot) -> None:
        """修复后的图片消息处理器"""
        self.bot = bot
        
        #白名单处理逻辑
        if len(config.allow_group_list) != 0 :
            if event.group_id not in config.allow_group_list:
                return


        # 公共信息处理（移到循环外）
        try:
            if isinstance(event, PrivateMessageEvent):
                user_info = UserInfo(
                    user_id=event.user_id,
                    user_nickname=(await bot.get_stranger_info(user_id=event.user_id))["nickname"],
                    user_cardname=None,
                    platform= config.platfrom
                )
                group_info = None
            else:
                user_info = UserInfo(
                    user_id=event.user_id,
                    user_nickname=event.sender.nickname,
                    user_cardname=event.sender.card or None,
                    platform= config.platfrom
                )
                # 获取群信息添加默认值

                group_info = GroupInfo(group_id=event.group_id, 
                        group_name=(await bot.get_group_info(group_id = event.group_id,no_cache=True))["group_name"], 
                        platform=config.platfrom)

        except Exception as e:
            logger.error(f"基础信息获取失败: {e}")
            return

        seg_list = []
        # 处理图片段
        for segment in event.message:
            if segment.type == "image":
                # 优先从消息段提取 url 和 file 参数
                image_url = segment.data.get("url", "")  # 确保默认值防止 KeyError
                image_file = segment.data.get("file", "")
                subtype = segment.data.get("sub_type", 0)  # 默认 subtype=0 (普通图片)

                # 调试日志：打印关键参数
                logger.debug(f"开始处理图片段 | URL={image_url[:30]}... | File={image_file[:20]}...")

                base64_str = None
                retry_count = 0
                max_retries = 2  # 最大重试次数

                # 阶段1：优先使用 URL 下载
                while retry_count < max_retries and not base64_str:
                    try:
                        # 尝试通过 URL 下载图片 (优先方案)
                        base64_str = await download_image_url(image_url)
                        if base64_str:
                            logger.debug("通过 URL 下载图片成功")
                            break
                    except Exception as e:
                        logger.warning(f"URL 下载失败 (尝试 {retry_count + 1}/{max_retries}): {str(e)}")
                        retry_count += 1
                        await asyncio.sleep(0.5)  # 短暂等待后重试

                # 阶段2：如果 URL 无效，尝试通过 file 调用 API
                if not base64_str and image_file:
                    try:
                        # 有限时间内调用 get_image API (备用方案)
                        image_data = await asyncio.wait_for(
                            bot.get_image(file=image_file),
                            timeout=2
                            )
                        file_path = image_data.get("file", "")
                        if file_path:
                            base64_str = local_file_to_base64(file_path)
                            logger.debug("通过 file API 获取图片成功")
                        else:
                            logger.error("get_image 返回无效文件路径")
                    except ActionFailed as e:
                        logger.error(f"API 调用失败: {e.info}")
                    except (asyncio.TimeoutError, KeyError) as e:
                        logger.warning(f"备用方案超时或数据异常: {str(e)}")
                    except Exception as e:
                        logger.error(f"备用方案未知错误: {str(e)}")

                # 最终回退逻辑
                if not base64_str:
                    logger.error("所有图片获取方案均失败")
                    base64_str = "[图片丢失]"  # 可替换为默认占位图

                # 根据 subtype 标记类型
                image_type = "emoji" if subtype != 0 else "image"
                # logger.info(image_type)
                seg_list.append(Seg(type = image_type,data = base64_str))
            elif segment.type == "text" :
                seg_list.append(Seg(type = "text",data = str(segment.data.get("text",""))))
            elif segment.type == "at" :
                seg_at_id = str(segment.data.get("qq",""))
                user_nickname=(await bot.get_stranger_info(user_id=seg_at_id))["nickname"]
                seg_list.append(Seg(type = "text",data = f"@{user_nickname}({seg_at_id})"))
            else:
                continue

        if len(seg_list) == 1:
            message_content = seg_list[0]
        else :
            message_content = Seg(type="seglist",data = seg_list)

        message_info = BaseMessageInfo(
            platform = config.platfrom,
            message_id = event.message_id,
            time = time.time(),
            group_info= group_info,
            user_info = user_info,
        )
        message_base = MessageBase(message_info,message_content,raw_message="")   
        
        await self.message_process(message_base)    

    async def handle_reply_message(self, event: MessageEvent, bot: Bot) -> None:
        """处理收到的消息"""

        self.bot = bot  # 更新 bot 实例
        if isinstance(event, PrivateMessageEvent):
            try:
                user_info = UserInfo(
                    user_id=event.user_id,
                    user_nickname=(await bot.get_stranger_info(user_id=event.user_id, no_cache=True))["nickname"],
                    user_cardname=None,
                    platform=config.platfrom,
                )
            except Exception as e:
                logger.error(f"获取陌生人信息失败: {e}")
                return
            logger.debug(user_info)
            group_info = None

        # 处理群聊消息
        else:
            #白名单处理逻辑
            if len(config.allow_group_list) != 0 :
                if event.group_id not in config.allow_group_list:
                    return

            user_info = UserInfo(
                user_id=event.user_id,
                user_nickname=event.sender.nickname,
                user_cardname=event.sender.card or None,
                platform=config.platfrom,
            )
            
            group_info = GroupInfo(group_id=event.group_id, 
                                   group_name=(await bot.get_group_info(group_id = event.group_id,no_cache=True))["group_name"], 
                                   platform=config.platfrom)

        message_content =  f"回复{event.reply.sender.nickname}的消息({event.reply.message})，说："
        # message_content += f"-{event.reply.sender.nickname}(id{event.reply.user_id}):{event.reply.message}\n回复了以下信息："
        message_content+=event.get_plaintext()
        # logger.info(f"\n\n\n{message_content}\n\n\n")

        message_info = BaseMessageInfo(
                platform = config.platfrom,
                message_id = event.message_id,
                time = time.time(),
                group_info = group_info,
                user_info = user_info,
        )

        message_seg = Seg(  
                    type = 'text',
                    data = message_content,  
            )


        message_base = MessageBase(message_info,message_seg,raw_message=event.get_plaintext())

        await self.message_process(message_base)

    async def handle_forward_message(self, event: MessageEvent, bot: Bot) -> None:
        """专用于处理合并转发的消息处理器"""

        #白名单处理逻辑
        if len(config.allow_group_list) != 0 :
            if event.group_id not in config.allow_group_list:
                return


        # 获取合并转发消息的详细信息
        forward_info = await bot.get_forward_msg(message_id=event.message_id)
        messages = forward_info["messages"]

        # 构建合并转发消息的文本表示
        processed_messages = []
        
        for node in messages:
            # 提取发送者昵称
            nickname = node["sender"].get("nickname", "未知用户")

            # 递归处理消息内容
            message_content = await self.process_message_segments(node["message"], layer=0)

            # 拼接为【昵称】+ 内容
            processed_messages.append(f"{nickname}：{message_content}")

        # 组合所有消息
        combined_message = "\n".join(processed_messages)
        combined_message = f"转发了消息：\n{combined_message}"

        # 构建用户信息（使用转发消息的发送者）
        user_info = UserInfo(
            user_id=event.user_id,
            user_nickname=event.sender.nickname,
            user_cardname=event.sender.card if hasattr(event.sender, "card") else None,
            platform= config.platfrom,
        )

        # 构建群聊信息（如果是群聊）
        group_info = None
        if isinstance(event, GroupMessageEvent):
            group_info = GroupInfo(group_id=event.group_id, 
                    group_name=(await bot.get_group_info(group_id = event.group_id,no_cache=True))["group_name"], 
                    platform=config.platfrom)

        # 创建消息对象
        message_info = BaseMessageInfo(
                platform = config.platfrom,
                message_id = event.message_id,
                time = time.time(),
                group_info= group_info,
                user_info = user_info,
        )
        # logger.info (event.get_message())
        message_seg = Seg(
                type = 'text',
                data = combined_message,  
        )

        message_base = MessageBase(message_info,message_seg,raw_message=combined_message)

        # 进入标准消息处理流程
        await self.message_process(message_base)

    async def process_message_segments(self, segments: list, layer: int) -> str:
        """递归处理消息段"""
        parts = []
        for seg in segments:
            part = await self.process_segment(seg, layer + 1)
            parts.append(part)
        return "".join(parts)

    async def process_segment(self, seg: dict, layer: int) -> str:
        """处理单个消息段"""
        seg_type = seg["type"]
        if layer > 3:
            # 防止有那种100层转发消息炸飞麦麦
            return "【转发消息】"
        if seg_type == "text":
            return seg["data"]["text"]
        elif seg_type == "image":
            return "[图片]"
        elif seg_type == "face":
            return "[表情]"
        elif seg_type == "at":
            return f"@{seg['data'].get('qq', '未知用户')}"
        elif seg_type == "forward":
            # 递归处理嵌套的合并转发消息
            nested_nodes = seg["data"].get("content", [])
            nested_messages = []
            nested_messages.append("合并转发消息内容：")
            for node in nested_nodes:
                nickname = node["sender"].get("nickname", "未知用户")
                content = await self.process_message_segments(node["message"], layer=layer)
                # nested_messages.append('-' * layer)
                nested_messages.append(f"{'--' * layer}【{nickname}】{content}")
            # nested_messages.append(f"{'--' * layer}合并转发第【{layer}】层结束")
            return "\n".join(nested_messages)
        else:
            return f"[{seg_type}]"

    async def message_process(self, message_base: MessageBase) -> None:
        try:
            payload = message_base.to_dict()
            # logger.info(payload)
            logger.info("消息发送成功")

            response = await self.client.post(
                self.fastapi_url,
                json=payload,
                headers={"Content-Type": "application/json"}
            )
            
            # 检查响应状态
            if response.status_code != 200:
                logger.error(f"FastAPI返回错误状态码: {response.status_code}")
                logger.debug(f"响应内容: {response.text}")
            else:
                response_data = response.json()
                logger.success(f"收到服务端响应: {response_data}")
                logger.debug(f"响应内容: {response_data}")
        except httpx.RequestError as e:
            logger.error(f"请求发送失败，检查你和mmc的连接: {str(e)}")
            logger.debug(f"请求URL: {self.fastapi_url}")
            # logger.debug(f"请求数据: {payload}")
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP状态错误: {str(e)}")
            logger.debug(f"状态码: {e.response.status_code}")
            logger.debug(f"响应内容: {e.response.text}")
        except Exception as e:
            logger.error(f"处理消息时发生未知错误: {str(e)}")
            logger.debug(f"错误类型: {type(e).__name__}")
            logger.debug(f"错误详情: {str(e)}")


# 创建全局ChatBot实例
chat_bot = ChatBot()
