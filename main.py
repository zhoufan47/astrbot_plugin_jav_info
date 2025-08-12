import httpx
from astrbot.api import logger
# 导入 AstrBot 核心 API
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.core.message.components import Image
from .crawlers import javdb

# 2. 创建 Plugin 实例，这是 AstrBot 插件的标准写法
@register("JavDB 查询插件", "棒棒糖", "根据用户发送的番号，从 JavDB 查询影片信息", "1.0.1")
class JavInfo(Star):

    def __init__(self, context: Context):
        super().__init__(context)
        self.client = httpx.AsyncClient(http2=True, follow_redirects=True)
        logger.info("插件 [JavDB] 已初始化。")

# 4. 使用 on_unload 钩子，在插件卸载时释放资源

    async def terminate(self):
        """
        清理函数，用于关闭 aiohttp 客户端会话，释放资源。
        """
        if self.client and not self.client.is_closed:
            await self.client.aclose()
            logger.info("JavDB 插件已卸载，HTTP 客户端已关闭。")


# 5. 使用 plugin 实例的 on_command 装饰器来注册命令
    @filter.command("jav")
    async def handle_javdb_query(self,event: AstrMessageEvent,movie_id: str):
        """
        处理用户查询番号的指令
        """
        # 6. 通过 plugin.config 获取配置
        # cookie = self.config.get("cookie")
        base_url = "https://javdb.com"
        # 从消息事件中获取参数文本
        # cookie = ""
        if not movie_id:
            yield event.plain_result("🤔 请输入要查询的番号。\n用法示例： /javdb SSIS-001")
            return

        logger.info(f"正在查询 {movie_id}，请稍候... ⏳")
        # yield event.plain_result()

        try:
            data = await javdb.fetch_movie_data(movie_id,self.client,base_url )
            if "error" in data:
                yield event.plain_result(f"查询失败：\n{data['error']}")
            else:
                text_info = (
                    f"✅ 查询成功！\n"
                    f"--------------------\n"
                    f"🎬 标题: {data.get('title', 'N/A')}\n"
                    f"🔢 番号: {data.get('number', 'N/A')}\n"
                    f"📅 发行日: {data.get('release', 'N/A')}\n"
                    f"⏰ 时长: {data.get('runtime', 'N/A')} 分钟\n"
                    f"🏢 片商: {data.get('studio', 'N/A')}\n"
                    f"👯‍♀️ 演员: {data.get('actor', 'N/A')}\n"
                    f"🏷️ 标签: {data.get('tags', 'N/A')}\n"
                    f"--------------------\n"
                    f"🔗 详情链接: {data.get('website', 'N/A')}\n"
                    f"--------------------\n"
                    f"😃 评分: {data.get('score', 'N/A')}\n"

                )
                # 使用 Message 对象包装后发送
                yield event.plain_result(text_info)
                try:
                    if data.get("thumb"):
                        logger.info("检测到封面，地址" + data.get("thumb"))
                        headers = {
                            # "Cookie": cookie,
                            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"
                        }
                        img_response = await self.client.get(data.get("thumb"), headers=headers, timeout=30.0)
                        img_response.raise_for_status()
                        img_data = await img_response.aread()
                        img_data = await image_obfus(img_data)
                        chain = [
                            Image.fromBytes(img_data)
                        ]
                        yield event.chain_result(chain)
                    # else:
                    #     chain = [
                    #         Plain(text=text_info)
                    #     ]
                    #     yield event.chain_result(chain)
                except Exception as img_err:
                    logger.error(f"处理封面异常: {img_err}", )
                    yield event.plain_result("😭 获取封面失败 ")

        except Exception as e:
            logger.error(f"处理 JavDB 查询时发生意外错误: {e}",)
            yield event.plain_result("🤖 查询过程中发生未知内部错误，请联系管理员检查后台日志。")

async def image_compress(img_data):
    """介由图片格式压缩以破坏图片哈希"""
    from PIL import Image as ImageP
    from io import BytesIO
    import random

    try:
        with BytesIO(img_data) as input_buffer:
            with ImageP.open(input_buffer) as img:
                with BytesIO() as output:
                    img.save(output, format="JPEG",subsampling=1, quality=80)
                    return output.getvalue()

    except Exception as e:
        logger.warning(f"破坏图片哈希时发生错误: {str(e)}")
        return img_data
