import base64
from pathlib import Path
import hashlib
import aiohttp
from nonebot import logger
import ssl
from PIL import Image
from io import BytesIO
from aiohttp import ClientSession, ClientTimeout, TCPConnector
from yarl import URL

def local_file_to_base64(file_path: str) -> str:
    # 读取本地图片文件
    with open(file_path, "rb") as f:
        image_data = f.read()
    
    # 拼接Base64字符串
    base64_str = base64.b64encode(image_data).decode("utf-8")
    return base64_str

def detect_image_type(data: bytes) -> str:
    """通过文件头识别常见图片格式"""
    if len(data) < 12:
        return "unknown"
    
    # 常见图片格式的魔数检测
    if data.startswith(b'\x89PNG\r\n\x1a\n'):
        return "png"
    elif data.startswith(b'\xff\xd8'):
        return "jpeg"
    elif data[:6] in (b'GIF87a', b'GIF89a'):
        return "gif"
    elif data.startswith(b'RIFF') and data[8:12] == b'WEBP':
        return "webp"
    elif data.startswith(b'\x00\x00\x01\x00'):
        return "ico"
    elif data.startswith(b'BM'):
        return "bmp"
    else:
        return "unknown"

def base64_to_image(base64_str: str, save_dir: str = "data/images") -> str:
    """处理Base64字符串并保存为哈希命名的图片，非GIF格式转为单帧GIF"""
    try:
        # 解码Base64
        image_data = base64.b64decode(base64_str)
        
        # 检测图片类型
        image_type = detect_image_type(image_data)
        
        # 计算哈希值（基于原始数据）
        file_hash = hashlib.md5(image_data).hexdigest()
        
        # 构建保存路径
        save_dir_path = Path(save_dir).resolve()
        save_dir_path.mkdir(parents=True, exist_ok=True)
        
        # 如果是GIF，直接保存原文件
        if image_type == "gif":
            save_path = save_dir_path / f"{file_hash}.gif"
            if not save_path.exists():
                with open(save_path, "wb") as f:
                    f.write(image_data)
            return f"file:///{save_path.absolute().as_posix()}"
        
        # 对于非GIF格式，转换为单帧GIF
        else:
            # 使用Pillow打开图片并转换为GIF
            img = Image.open(BytesIO(image_data))
            
            # 处理透明度（如果是PNG等有透明通道的格式）
            if image_type == "png" and img.mode in ('RGBA', 'LA'):
                background = Image.new('RGBA', img.size, (255, 255, 255))
                background.paste(img, mask=img.split()[-1])
                img = background.convert('RGB')
            
            # 转换为GIF格式
            gif_buffer = BytesIO()
            img.save(gif_buffer, format='GIF')
            gif_data = gif_buffer.getvalue()
            
            # 计算转换后GIF的哈希值（基于转换后的数据）
            gif_hash = hashlib.md5(gif_data).hexdigest()
            save_path = save_dir_path / f"{gif_hash}.gif"
            
            if not save_path.exists():
                with open(save_path, "wb") as f:
                    f.write(gif_data)
            
            return f"file:///{save_path.absolute().as_posix()}"
    
    except Exception as e:
        raise ValueError(f"图片处理失败: {str(e)}")

async def download_image_url(url: str) -> str:
        # 使用yarl解析URL获取主机名
        try:
            parsed_url = URL(url)
            hostname = parsed_url.host
        except Exception as e:
            logger.error(f"URL解析失败: {url} - {str(e)}")
            raise ValueError(f"无效的URL格式: {url}")

        # 确保成功提取主机名
        if not hostname:
            logger.error(f"无法从URL中提取主机名: {url}")
            raise ValueError("URL中缺少有效的主机名")

        # 创建自定义SSL上下文
        ssl_context = ssl.create_default_context()
        
        # 禁用不安全协议
        ssl_context.options |= (
            ssl.OP_NO_SSLv3 |
            ssl.OP_NO_TLSv1 |
            ssl.OP_NO_TLSv1_1
        )
        ssl_context.minimum_version = ssl.TLSVersion.TLSv1_2  # 强制使用TLSv1.2+

        # 配置加密套件：
        # - DEFAULT: 使用OpenSSL默认的安全套件
        # - !aNULL: 禁用无身份验证的套件（易受中间人攻击）
        # - !eNULL: 禁用无加密的套件
        # - !MD5: 禁用使用MD5哈希的套件（已不安全）
        # - !3DES: 禁用三重DES（性能差且存在SWEET32攻击风险）
        # - !DES: 禁用DES（密钥长度过短）
        ssl_context.set_ciphers('DEFAULT:!aNULL:!eNULL:!MD5:!3DES:!DES')

        # 显式设置SNI
        # 避免某些服务器因缺少SNI信息而拒绝连接
        ssl_context.server_hostname = hostname

        # 创建带自定义SSL上下文的连接器
        connector = TCPConnector(ssl=ssl_context)

        # 增加超时时间至20秒
        async with ClientSession(
            timeout=ClientTimeout(total=20),
            connector=connector
        ) as session:
            async with session.get(url) as resp:
                resp.raise_for_status()
                image_bytes = await resp.read()
                return base64.b64encode(image_bytes).decode("utf-8")
    except Exception as e:
        logger.error(f"图片下载失败: {str(e)}")
        raise
