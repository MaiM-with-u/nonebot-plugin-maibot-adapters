from pydantic import BaseModel


class Config(BaseModel):
    """Plugin Config Here"""
    url : str = "ws://127.0.0.1:8000/ws"  # 你的FastAPI地址 /
    platfrom :str = "nonebot-qq"    #如果你不知道这是什么那你就不要动它
    allow_group_list :list[str]  = []     #留空则为不启动QQ端白名单