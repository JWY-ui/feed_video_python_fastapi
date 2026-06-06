"""
Account 模块的请求/响应 Pydantic 模型

每一个接口的入参和出参都在这里定义，FastAPI 自动完成：
  1. JSON body → Pydantic 对象（自动校验字段类型、长度、必填）
  2. Pydantic 对象 → JSON 响应（response_model 自动过滤多余字段）
  3. 自动生成 Swagger 文档

为什么 Model 和 Schema 要分开？
  - Model（SQLAlchemy）：描述数据库表结构，包含所有字段（含密码、token）
  - Schema（Pydantic）：描述接口收发格式，只暴露该接口需要的字段（密码永远不返回）
  合在一起会造成安全问题（密码泄露）和接口耦合。
"""
from pydantic import BaseModel, Field


# ━━━ 请求模型 ━━━

class RegisterRequest(BaseModel):
    """注册请求"""
    username: str = Field(..., min_length=1, max_length=255, description="用户名")
    password: str = Field(..., min_length=6, max_length=72, description="密码，bcrypt 限制 72 字节")


class LoginRequest(BaseModel):
    """登录请求"""
    username: str
    password: str


class RefreshRequest(BaseModel):
    """刷新 token 请求——两个 token 一起传"""
    refresh_token: str
    access_token: str   # 过期的 access token，用于提取 account_id


class ChangePasswordRequest(BaseModel):
    """改密请求"""
    username: str
    old_password: str
    new_password: str = Field(..., min_length=6, max_length=72)


class FindByIDRequest(BaseModel):
    """按 ID 查用户"""
    id: int


class FindByUsernameRequest(BaseModel):
    """按用户名查用户"""
    username: str


class RenameRequest(BaseModel):
    """改名请求"""
    new_username: str = Field(..., min_length=1, max_length=255)


class UpdateProfileRequest(BaseModel):
    """更新个人资料"""
    avatar_url: str | None = None
    bio: str | None = None


class GetProfileRequest(BaseModel):
    """获取用户主页"""
    account_id: int


# ━━━ 响应模型 ━━━

class AccountInfo(BaseModel):
    """
    公开的用户信息 —— 注意没有 password 和 token 字段

    用 response_model=AccountInfo 时，FastAPI 会自动把 Model 里多出来的字段
    （password、token、refresh_token）过滤掉，保证敏感信息不泄露。
    """
    id: int
    username: str
    avatar_url: str | None = None
    bio: str | None = None


class LoginResponse(BaseModel):
    """登录/刷新 token 的返回"""
    token: str
    refresh_token: str
    account_id: int
    username: str


class GetProfileResponse(BaseModel):
    """用户主页：基本信息 + 统计数据"""
    account: AccountInfo
    video_count: int
    total_likes: int
    follower_count: int
    vlogger_count: int
