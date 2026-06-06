"""
密码工具——bcrypt 哈希与验证。

为什么选 bcrypt 而不是 SHA256？
  1. bcrypt 自带 salt（盐值）——相同密码两次哈希结果不同
     攻击者不能直接查彩虹表，必须逐个密码暴力尝试
  2. bcrypt 可调节 cost（计算轮数）——默认 12 轮，每增加 1 轮破解时间翻倍
     可以随着硬件性能提升而增加轮数
  3. bcrypt 故意很慢——正常登录验证只需要几百毫秒，暴力破解需要几百年

bcrypt 的限制：
  最多处理 72 字节的输入。所以超长密码需要截断到前 72 字节。
  本项目前端和 Pydantic schema 都限制了密码长度，这里的截断是最后一道防线。
"""
import bcrypt


def hash_password(password: str) -> str:
    """
    对明文密码做 bcrypt 哈希。

    参数：
      password: 用户输入的明文密码（如 "123456"）

    返回：
      bcrypt 哈希字符串，格式：$2b$12$salt...hash...
      可以直接存入数据库的 password 字段

    流程：
      1. 把密码编码成 bytes（bcrypt 只能处理 bytes）
      2. 截断到前 72 字节（bcrypt 的输入上限）
      3. bcrypt.gensalt() 生成随机盐值
      4. bcrypt.hashpw() 用盐值哈希密码
      5. 解码回 str 存入数据库
    """
    pwd_bytes = password.encode("utf-8")[:72]
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pwd_bytes, salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    验证明文密码是否匹配数据库中存储的哈希值。

    参数：
      plain_password: 用户登录时输入的明文密码
      hashed_password: 数据库中存储的 bcrypt 哈希（如 "$2b$12$..."）

    返回：
      True = 密码正确
      False = 密码错误

    不需要自己提取盐值——bcrypt.checkpw 会从 hashed_password 中自动解析盐值。
    盐值就嵌在 bcrypt 的输出字符串里（$2b$12$<22字符盐值><31字符哈希>）。
    """
    pwd_bytes = plain_password.encode("utf-8")[:72]
    hashed_bytes = hashed_password.encode("utf-8")
    return bcrypt.checkpw(pwd_bytes, hashed_bytes)
