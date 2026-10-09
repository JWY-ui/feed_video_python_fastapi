from langchain_core.tools import tool

from app.database import AsyncSessionLocal
from app.repositories.feed_repo import FeedRepository
from app.repositories.like_repo import LikeRepository
from app.repositories.social_repo import SocialRepository
from app.repositories.comment_repo import CommentRepository
from app.repositories.notification_repo import NotificationRepository
from app.repositories.video_repo import VideoRepository
from app.repositories.account_repo import AccountRepository
from app.repositories.message_repo import MessageRepository
from app.services.feed_service import FeedService
from app.services.like_service import LikeService
from app.services.social_service import SocialService
from app.services.comment_service import CommentService
from app.services.notification_service import NotificationService
from app.services.video_service import VideoService
from app.services.account_service import AccountService
from app.services.message_service import MessageService


def make_tools(account_id: int, username: str) -> list:

    @tool
    async def list_latest_feed(limit: int = 10) -> str:
        """Browse latest videos, ordered by publish time descending."""
        async with AsyncSessionLocal() as session:
            svc = FeedService(FeedRepository(session), LikeRepository(session))
            resp = await svc.list_latest(limit, 0, account_id)
            return str([{
                "id": v.id, "title": v.title, "author": v.author.username,
                "likes": v.likes_count,
            } for v in resp.video_list])

    @tool
    async def list_hot_feed(limit: int = 10) -> str:
        """Browse most-liked videos, ranked by like count descending."""
        async with AsyncSessionLocal() as session:
            svc = FeedService(FeedRepository(session), LikeRepository(session))
            resp = await svc.list_likes_count(limit, None, None, account_id)
            return str([{
                "id": v.id, "title": v.title, "author": v.author.username,
                "author_id": v.author.id, "likes": v.likes_count,
            } for v in resp.video_list])

    @tool
    async def list_following_feed(limit: int = 10) -> str:
        """Browse videos from users you follow."""
        async with AsyncSessionLocal() as session:
            svc = FeedService(FeedRepository(session), LikeRepository(session))
            resp = await svc.list_by_following(limit, 0, account_id)
            return str([{
                "id": v.id, "title": v.title, "author": v.author.username,
            } for v in resp.video_list])

    @tool
    async def search_user(query: str) -> str:
        """Find a user by username (exact match)."""
        async with AsyncSessionLocal() as session:
            svc = AccountService(AccountRepository(session))
            try:
                user = await svc.find_by_username(query)
                return str({"id": user["id"], "username": user["username"]})
            except ValueError:
                return "user not found"

    @tool
    async def get_video_detail(video_id: int) -> str:
        """Get detailed info about a specific video."""
        async with AsyncSessionLocal() as session:
            svc = VideoService(VideoRepository(session), session)
            try:
                video = await svc.get_detail(video_id)
                return str(video)
            except ValueError:
                return "video not found"

    @tool
    async def follow_user(vlogger_id: int) -> str:
        """Follow a user by their account ID."""
        async with AsyncSessionLocal() as session:
            svc = SocialService(SocialRepository(session), AccountRepository(session))
            try:
                await svc.follow(account_id, vlogger_id)
                await session.commit()
                return "followed successfully"
            except ValueError as e:
                return str(e)

    @tool
    async def unfollow_user(vlogger_id: int) -> str:
        """Unfollow a user by their account ID."""
        async with AsyncSessionLocal() as session:
            svc = SocialService(SocialRepository(session), AccountRepository(session))
            try:
                await svc.unfollow(account_id, vlogger_id)
                await session.commit()
                return "unfollowed successfully"
            except ValueError as e:
                return str(e)

    @tool
    async def get_following_list() -> str:
        """List users you are following."""
        async with AsyncSessionLocal() as session:
            svc = SocialService(SocialRepository(session), AccountRepository(session))
            vloggers, _ = await svc.get_all_vloggers(account_id)
            return str([{"id": u["id"], "username": u["username"]} for u in vloggers])

    @tool
    async def get_followers_list() -> str:
        """List your followers."""
        async with AsyncSessionLocal() as session:
            svc = SocialService(SocialRepository(session), AccountRepository(session))
            followers, _ = await svc.get_all_followers(account_id)
            return str([{"id": u["id"], "username": u["username"]} for u in followers])

    @tool
    async def like_video(video_id: int) -> str:
        """Like a video by its ID."""
        async with AsyncSessionLocal() as session:
            svc = LikeService(LikeRepository(session), VideoRepository(session))
            try:
                await svc.like(video_id, account_id)
                await session.commit()
                return "liked successfully"
            except ValueError as e:
                return str(e)

    @tool
    async def unlike_video(video_id: int) -> str:
        """Remove your like from a video."""
        async with AsyncSessionLocal() as session:
            svc = LikeService(LikeRepository(session), VideoRepository(session))
            try:
                await svc.unlike(video_id, account_id)
                await session.commit()
                return "unliked successfully"
            except ValueError as e:
                return str(e)

    @tool
    async def publish_comment(video_id: int, content: str) -> str:
        """Post a comment on a video. Supports @mentions."""
        async with AsyncSessionLocal() as session:
            svc = CommentService(CommentRepository(session), VideoRepository(session))
            try:
                result = await svc.publish(video_id, account_id, username, content)
                await session.commit()
                return str(result)
            except ValueError as e:
                return str(e)

    @tool
    async def list_comments(video_id: int) -> str:
        """Get all comments on a video."""
        async with AsyncSessionLocal() as session:
            svc = CommentService(CommentRepository(session), VideoRepository(session))
            try:
                comments = await svc.get_all(video_id)
                return str([{
                    "id": c["id"], "author": c["username"],
                    "content": c["content"],
                } for c in comments])
            except ValueError as e:
                return str(e)

    @tool
    async def list_notifications() -> str:
        """Get your recent notifications (likes, comments, follows)."""
        async with AsyncSessionLocal() as session:
            svc = NotificationService(NotificationRepository(session))
            notifs = await svc.list_by_user(account_id)
            return str([{
                "type": n["type"], "content": n["content"],
                "read": n.get("is_read", False),
            } for n in notifs])

    @tool
    async def send_message(to_id: int, content: str) -> str:
        """Send a private message (DM) to another user by their account ID."""
        async with AsyncSessionLocal() as session:
            svc = MessageService(MessageRepository(session))
            try:
                result = await svc.send(account_id, to_id, content)
                await session.commit()
                return f"message sent to user {to_id}"
            except ValueError as e:
                return str(e)

    return [
        list_latest_feed, list_hot_feed, list_following_feed,
        search_user, get_video_detail,
        follow_user, unfollow_user, get_following_list, get_followers_list,
        like_video, unlike_video,
        publish_comment, list_comments,
        list_notifications,
        send_message,
    ]
