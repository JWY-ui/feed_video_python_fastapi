"""
全局配置——整个项目所有魔法数字和敏感信息的唯一来源。

为什么用 pydantic-settings 而不是 os.environ？
  1. 自动从 .env 文件读取，开发方便
  2. 环境变量优先级高于 .env，Docker/K8s 部署时可直接注入
  3. 有类型校验（port 是 int 而不是 str），拼 DSN 时不会出错
  4. IDE 有自动补全

用法：其他模块只需要 from app.config import settings，然后 settings.mysql_host。
"""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """应用配置类——所有字段都有默认值，可被 .env 或环境变量覆盖"""

    # 服务器端口，默认 8080。环境变量 SERVER_PORT 可覆盖
    server_port: int = 8080

    # ━━ MySQL 连接 ━━
    # 如果 .env 里没写，就用下面这些默认值
    mysql_host: str = "localhost"
    mysql_port: int = 3306
    mysql_user: str = "root"
    mysql_password: str = "123456"
    mysql_database: str = "feedsystem"

    # ━━ JWT 签名密钥 ━━
    # 生产环境一定要改！否则攻击者可以自己签发 Token。
    # 生成方式：python -c "import secrets; print(secrets.token_hex(32))"
    jwt_secret: str = "change-me-to-a-random-string"

    # ━━ Redis 缓存（可选）━━━
    # 留空或连不上都不会报错——整个项目设计为 Redis 不可用时自动降级
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_password: str |None = None
    redis_db: int = 0

    # 告诉 pydantic-settings 去读项目根目录的 .env 文件
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


# 全局单例——整个项目 import 这一个实例就够了，不需要重复创建
settings = Settings()
