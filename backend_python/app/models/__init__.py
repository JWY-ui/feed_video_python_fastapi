"""
模型聚合导出——所有 ORM Model 在这里统一 import。

为什么需要一个 __init__.py？
  1. main.py 只需要 from app.models import Account, Video, ... 一行
     不需要知道每个 Model 在哪个子文件里
  2. import 时会触发 SQLAlchemy 的 __init_subclass__，
     把每个 Model 注册到 Base.metadata 中
     Base.metadata.create_all() 靠这个注册表知道要建哪些表

如果加新表：
  1. 在 models/ 下新建文件定义 Model
  2. 在下面加一行 from app.models.xxx import Xxx
  3. 在 __all__ 里加 "Xxx"
"""
from app.models.account import Account
from app.models.video import Video, OutboxMsg
from app.models.like import Like
from app.models.comment import Comment
from app.models.social import Social
from app.models.tag import Tag, VideoTag
from app.models.message import Message
from app.models.notification import Notification

__all__ = [
    "Account",
    "Video", "OutboxMsg",
    "Like",
    "Comment",
    "Social",
    "Tag", "VideoTag",
    "Message",
    "Notification",
]
