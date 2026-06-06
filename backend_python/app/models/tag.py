"""
话题标签表 (tags) + 视频-标签关联表 (video_tags)

视频和标签是多对多关系：
  一个视频可以有多个 #话题
  一个 #话题 可以对应多个视频

通过 video_tags 中间表关联。

数据流：
  发布视频 → 正则提取 #话题 → INSERT tags (FirstOrCreate) → INSERT video_tags
  话题流查询 → JOIN videos + video_tags + tags WHERE tags.name = ?

为什么不用逗号分隔字段（如 tag_list = "美食,旅游"）？
  1. 无法建索引——WHERE tag_list LIKE '%美食%' 走不了索引，全表扫描
  2. 更新删除困难——去掉一个标签需要字符串拼接
  3. 标签表可扩展——未来可以加标签图标、标签简介等字段
"""
from sqlalchemy import String, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # 标签名（不含 # 号）。唯一索引确保同一话题不重复创建
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)


class VideoTag(Base):
    __tablename__ = "video_tags"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # 视频 ID。idx 用于话题流查询时的 JOIN
    video_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    # 标签 ID。idx 同上
    tag_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
