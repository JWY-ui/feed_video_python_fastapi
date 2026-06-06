"""
用户账号表 (accounts)

设计要点：
  1. token / refresh_token 存数据库——JWT 无状态但需要"主动撤销"
     登出/改密时清空这两个字段，旧 JWT 即使未过期也立即失效
  2. password 存 bcrypt 哈希，不存明文
     即使数据库泄露，攻击者也无法还原用户密码
  3. username 设唯一索引——注册和登录的高频查询字段

被哪些查询使用：
  - 注册：INSERT + 唯一索引冲突检测
  - 登录：SELECT WHERE username = ?
  - 鉴权：SELECT WHERE id = ?（高频，主键查最快）
  - 刷新 Token：全表扫描 find_all（低频，未来用 Redis 替代）
  - Feed 流：不 JOIN accounts 表（Video 冗余了 username）
"""
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Account(Base):
    __tablename__ = "accounts"

    # 主键，自增。SQLAlchemy session.get() 查主键最快（先查 identity map，再发 SQL）
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # 用户名，唯一约束。登录和注册都靠这个字段查询
    username: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    # bcrypt 哈希后的密码（60 字符 + salt）。绝不出现在 API 返回中
    password: Mapped[str] = mapped_column(String(255), nullable=False)
    # 当前有效的 access token（JWT）。登出/改密时清空 → 旧 token 即时失效
    token: Mapped[str] = mapped_column(String(512), default="")
    # 当前有效的 refresh token（随机 hex 字符串，7 天有效）
    refresh_token: Mapped[str] = mapped_column(String(512), default="")
    # 头像 URL。可空（新用户没头像）
    avatar_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # 个人简介，最长 255 字符
    bio: Mapped[str | None] = mapped_column(String(255), nullable=True)
