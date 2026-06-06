"""
JWT 工具——Access Token 和 Refresh Token 的生成与解析。

双 Token 机制：

  Access Token（JWT，15 分钟）
    - 每次 HTTP 请求携带在 Authorization: Bearer <token> 头里
    - 服务端解码后拿到 account_id 和 username，不需要查数据库就知道是谁
    - 15 分钟短有效期：即使泄露，攻击窗口也只有 15 分钟

  Refresh Token（随机字符串，7 天）
    - 只在 Access Token 过期时用一次，换取新的 Access Token
    - 不随每次请求发送，泄露风险低
    - 存在数据库里，可以随时撤销（异常登录时直接删掉）

HS256 算法：
  - 对称加密：签发和验证用同一个密钥（settings.jwt_secret）
  - 适合单体应用；微服务架构建议换 RS256（公私钥，各服务只持有公钥）
"""
import secrets
from datetime import datetime, timedelta

from jose import JWTError, jwt

from app.config import settings

# Access Token 过期时间（分钟）——15 分钟是安全性和用户体验的平衡点
ACCESS_TOKEN_EXPIRE_MINUTES = 15


def create_access_token(account_id: int, username: str) -> str:
    """
    生成 Access Token（JWT）。

    参数：
      account_id: 用户 ID，JWT 解码后直接可用，不用查数据库
      username: 用户名，Feed 流发布视频时直接取，不用 JOIN accounts

    返回：
      JWT 字符串，格式：header.payload.signature
      前端存在 localStorage 或 cookie 中

    JWT payload 字段说明：
      - account_id / username : 自定义字段，业务数据
      - exp : 过期时间（Expiration Time），jwt.decode() 会自动校验
      - iat : 签发时间（Issued At）
      - nbf : 生效时间（Not Before），设为和 iat 相同，立即生效
    """
    now = datetime.utcnow()
    payload = {
        "account_id": account_id,
        "username": username,
        "exp": now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
        "iat": now,
        "nbf": now,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def create_refresh_token() -> str:
    """
    生成 Refresh Token——不是 JWT，就是 64 位随机 hex 字符串。

    为什么不用 JWT？
      Refresh Token 只有"换 Access Token"一个用途，不需要携带业务数据。
      随机字符串更短、更容易安全存储、更容易在数据库里查找和撤销。

    secrets.token_hex(32) = 32 字节随机数 → 64 字符 hex 字符串
    足够安全：2^256 种可能，暴力破解不现实。
    """
    return secrets.token_hex(32)


def decode_token(token_string: str) -> dict:
    """
    解析并验证 Access Token。

    参数：
      token_string: 从 Authorization: Bearer <token> 头中提取的 JWT

    返回：
      {"account_id": int, "username": str}
      这两个字段来自 JWT payload，不需要查数据库

    异常：
      ExpiredSignatureError : Token 过期了（exp < now）
      JWTError             : 签名不对、格式错误、nbf 还没到等

    jwt.decode() 做了什么：
      1. 用 settings.jwt_secret 验证签名（HMAC-SHA256）
      2. 检查 exp 是否已过期
      3. 检查 nbf 是否已到生效时间
      所有这些在 jwt.decode() 内部自动完成，不需要手动编码。
    """
    payload = jwt.decode(token_string, settings.jwt_secret, algorithms=["HS256"])
    return {
        "account_id": payload["account_id"],
        "username": payload["username"],
    }


def decode_token_skip_expiry(token_string: str) -> dict:
    """
    解码 JWT 但不验证过期时间——Refresh 接口专用。

    Access Token 过期后客户端把它连同 Refresh Token 一起发过来，
    服务端从过期 Token 里提取 account_id，再用它查数据库验证 Refresh Token。

    只跳过 exp 验证，签名验证仍然执行——防止伪造 Token。
    """
    payload = jwt.decode(
        token_string, settings.jwt_secret, algorithms=["HS256"],
        options={"verify_exp": False},  # 不验过期，其余全验（签名、nbf 等）
    )
    return {
        "account_id": payload["account_id"],
        "username": payload["username"],
    }
