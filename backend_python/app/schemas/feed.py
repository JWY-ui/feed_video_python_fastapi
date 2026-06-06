"""
Feed 流请求/响应 Pydantic 模型。

定义了 5 种 Feed 流的请求参数和返回格式。

游标分页的核心：每个 Request 都有游标字段，每个 Response 都有 next_xxx 字段。
前端把上一页返回的 next_xxx 原样传入下一页请求的 xxx 字段，实现无限滚动。
"""
from pydantic import BaseModel, Field


class FeedAuthor(BaseModel):
    """视频作者——Feed 流每条视频都带的作者信息"""
    id: int
    username: str


class FeedVideoItem(BaseModel):
    """
    Feed 流中单条视频的返回格式。

    注意和 VideoInfo（schemas/video.py）的区别：
      - FeedVideoItem 是"列表中的摘要"，包含 is_liked（个性化）
      - VideoInfo 是"详情"，不包含 is_liked（详情页单独查）
    """
    id: int
    author: FeedAuthor
    title: str
    description: str | None = None
    play_url: str
    cover_url: str
    create_time: int          # Unix 秒时间戳
    likes_count: int
    is_liked: bool = False    # 当前用户是否已赞（匿名用户永远 False）


# ═══════════════════ 1. 最新视频流 ═══════════════════

class ListLatestRequest(BaseModel):
    """最新视频流请求——游标是 create_time 毫秒时间戳"""
    limit: int = Field(default=10, gt=0, le=50)
    latest_time: int = 0     # 0=首页；非0=上一页最后一条的 create_time（毫秒）


class ListLatestResponse(BaseModel):
    """最新视频流响应"""
    video_list: list[FeedVideoItem]
    next_time: int = 0       # 本页最后一条的 create_time（毫秒），传给下一页的 latest_time
    has_more: bool = False   # False=没有更多数据了


# ═══════════════════ 2. 点赞排行 ═══════════════════

class ListLikesCountRequest(BaseModel):
    """点赞排行请求——复合游标 (likes_count, id)"""
    limit: int = Field(default=10, gt=0, le=50)
    likes_count_before: int | None = None   # 上页最后一条的点赞数
    id_before: int | None = None            # 上页最后一条的视频 ID
    # 两个参数必须同时传或同时不传


class ListLikesCountResponse(BaseModel):
    """点赞排行响应"""
    video_list: list[FeedVideoItem]
    next_likes_count_before: int | None = None   # 本页最后一条的点赞数
    next_id_before: int | None = None            # 本页最后一条的视频 ID
    has_more: bool = False


# ═══════════════════ 3. 热度榜 ═══════════════════

class ListByPopularityRequest(BaseModel):
    """热度榜请求——三元复合游标"""
    limit: int = Field(default=10, gt=0, le=50)
    as_of: int = 0                          # 快照时间（Redis 用）。0=服务端自动取当前分钟
    offset: int = 0                         # 快照内的分页偏移
    latest_id_before: int | None = None     # 上页最后一条的视频 ID
    latest_popularity: int = 0              # 上页最后一条的热度值
    latest_before: str = ""                 # 上页最后一条的创建时间（ISO 格式）


class ListByPopularityResponse(BaseModel):
    """热度榜响应"""
    video_list: list[FeedVideoItem]
    as_of: int = 0                                    # 本页使用的快照时间
    next_offset: int = 0                              # 下一页的 offset
    has_more: bool = False
    next_latest_popularity: int | None = None         # MySQL 降级路径的游标
    next_latest_before: str | None = None
    next_latest_id_before: int | None = None


# ═══════════════════ 4. 关注流 ═══════════════════

class ListByFollowingRequest(BaseModel):
    """关注流请求——游标是 create_time Unix 秒时间戳"""
    limit: int = Field(default=10, gt=0, le=50)
    latest_time: int = 0     # 0=首页；非0=上页最后一条的 create_time（秒）


class ListByFollowingResponse(BaseModel):
    """关注流响应"""
    video_list: list[FeedVideoItem]
    next_time: int = 0       # 本页最后一条的 create_time（秒）
    has_more: bool = False


# ═══════════════════ 5. 话题流 ═══════════════════

class ListByTagRequest(BaseModel):
    """话题流请求——不翻页，一次性加载"""
    tag_name: str = Field(..., min_length=1)
    limit: int = Field(default=10, gt=0, le=50)
