from __future__ import annotations

from collections import defaultdict

from redis.asyncio import Redis
from sqlalchemy import and_, delete, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import ensure_user_can_post
from app.core.exceptions import AppException
from app.core.security import utcnow
from app.models.notification import NotificationType, UserNotification
from app.models.social import (
    FriendRequest,
    FriendRequestStatus,
    FriendRemark,
    Friendship,
    PostComment,
    PostLike,
    PostMedia,
    PostVisibility,
    SocialPost,
)
from app.models.user import User, UserStatus
from app.models.security import PrivateMedia
from app.schemas.social import CommentCreate, PostCreate
from app.services.notification_service import create_notification
from app.services.risk_service import check_content
from app.services.block_service import blocked_user_ids, ensure_not_blocked
from app.services.media_service import signed_media_url


def _pair(user_a_id: int, user_b_id: int) -> tuple[int, int]:
    return min(user_a_id, user_b_id), max(user_a_id, user_b_id)


def social_user_payload(user: User, *, is_friend: bool = False) -> dict:
    username = getattr(user, "username", None)
    return {
        "id": user.id,
        "uid": user.uid,
        "username": username,
        "display_name": username or user.anonymous_name,
        "avatar_url": getattr(user, "avatar_url", None),
        "bio": getattr(user, "bio", None),
        "is_friend": is_friend,
    }


async def _friendship(db: AsyncSession, user_a_id: int, user_b_id: int) -> Friendship | None:
    low, high = _pair(user_a_id, user_b_id)
    return await db.scalar(
        select(Friendship).where(Friendship.user_low_id == low, Friendship.user_high_id == high)
    )


async def _pending_request(db: AsyncSession, user_a_id: int, user_b_id: int) -> FriendRequest | None:
    return await db.scalar(
        select(FriendRequest)
        .where(
            FriendRequest.status == FriendRequestStatus.PENDING,
            or_(
                and_(FriendRequest.requester_id == user_a_id, FriendRequest.addressee_id == user_b_id),
                and_(FriendRequest.requester_id == user_b_id, FriendRequest.addressee_id == user_a_id),
            ),
        )
        .order_by(FriendRequest.id.desc())
    )


async def friend_ids(db: AsyncSession, user_id: int) -> set[int]:
    rows = (
        await db.execute(
            select(Friendship).where(
                or_(Friendship.user_low_id == user_id, Friendship.user_high_id == user_id)
            )
        )
    ).scalars().all()
    return {
        row.user_high_id if row.user_low_id == user_id else row.user_low_id
        for row in rows
    }


async def friend_remark(
    db: AsyncSession, owner_id: int, friend_id: int
) -> str | None:
    return await db.scalar(
        select(FriendRemark.remark).where(
            FriendRemark.owner_id == owner_id,
            FriendRemark.friend_id == friend_id,
        )
    )


async def set_friend_remark(
    db: AsyncSession, current_user: User, friend_user_id: int, remark: str | None
) -> dict:
    if not await _friendship(db, current_user.id, friend_user_id):
        raise AppException("NOT_FRIENDS", "只能为好友设置备注", 403)
    row = await db.scalar(
        select(FriendRemark).where(
            FriendRemark.owner_id == current_user.id,
            FriendRemark.friend_id == friend_user_id,
        )
    )
    if remark:
        if row is None:
            row = FriendRemark(
                owner_id=current_user.id,
                friend_id=friend_user_id,
                remark=remark,
            )
            db.add(row)
        else:
            row.remark = remark
    elif row is not None:
        await db.delete(row)
    await db.commit()
    return {"friend_user_id": friend_user_id, "remark": remark}


async def search_users(
    db: AsyncSession, current_user: User, query: str, page: int, page_size: int
) -> dict:
    normalized = query.strip()
    if len(normalized) < 2:
        raise AppException("SEARCH_QUERY_REQUIRED", "请输入要查找的账号", 422)
    escaped = normalized.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    stmt = (
        select(User)
        .where(
            User.id != current_user.id,
            User.status != UserStatus.BANNED,
            or_(
                User.uid == normalized,
                User.username.ilike(f"{escaped}%", escape="\\"),
                func.lower(User.email) == normalized.lower(),
            ),
        )
        .order_by(User.username.asc(), User.id.asc())
        .offset((page - 1) * page_size)
        .limit(page_size + 1)
    )
    blocked = await blocked_user_ids(db, current_user.id)
    if blocked:
        stmt = stmt.where(User.id.not_in(blocked))
    rows = list((await db.execute(stmt)).scalars().all())
    has_more = len(rows) > page_size
    rows = rows[:page_size]
    friends = await friend_ids(db, current_user.id)
    candidate_ids = {user.id for user in rows if user.id not in friends}
    pending_by_user: dict[int, FriendRequest] = {}
    if candidate_ids:
        pending_rows = (
            await db.execute(
                select(FriendRequest).where(
                    FriendRequest.status == FriendRequestStatus.PENDING,
                    or_(
                        and_(
                            FriendRequest.requester_id == current_user.id,
                            FriendRequest.addressee_id.in_(candidate_ids),
                        ),
                        and_(
                            FriendRequest.addressee_id == current_user.id,
                            FriendRequest.requester_id.in_(candidate_ids),
                        ),
                    ),
                )
            )
        ).scalars().all()
        for pending in pending_rows:
            other_id = (
                pending.addressee_id
                if pending.requester_id == current_user.id
                else pending.requester_id
            )
            pending_by_user[other_id] = pending
    items = []
    for user in rows:
        pending = pending_by_user.get(user.id)
        payload = social_user_payload(user, is_friend=user.id in friends)
        if user.id in friends:
            relationship = "FRIEND"
        elif pending and pending.requester_id == current_user.id:
            relationship = "OUTGOING_PENDING"
        elif pending:
            relationship = "INCOMING_PENDING"
        else:
            relationship = "NONE"
        payload.update(
            relationship=relationship,
            pending_request_id=pending.id if pending else None,
        )
        items.append(payload)
    return {"items": items, "page": page, "page_size": page_size, "has_more": has_more}


async def send_friend_request(
    db: AsyncSession, current_user: User, target_user_id: int, message: str | None
) -> dict:
    if target_user_id == current_user.id:
        raise AppException("CANNOT_FRIEND_SELF", "不能添加自己为好友", 400)
    target = await db.get(User, target_user_id)
    if not target or target.status == UserStatus.BANNED:
        raise AppException("USER_NOT_FOUND", "用户不存在", 404)
    await ensure_not_blocked(db, current_user.id, target_user_id)
    if await _friendship(db, current_user.id, target_user_id):
        raise AppException("ALREADY_FRIENDS", "你们已经是好友", 409)

    pending = await _pending_request(db, current_user.id, target_user_id)
    if pending:
        code = "FRIEND_REQUEST_EXISTS" if pending.requester_id == current_user.id else "INCOMING_REQUEST_EXISTS"
        message_text = "好友申请已经发送" if pending.requester_id == current_user.id else "对方已经向你发送好友申请"
        raise AppException(code, message_text, 409)

    previous = await db.scalar(
        select(FriendRequest)
        .where(
            or_(
                and_(FriendRequest.requester_id == current_user.id, FriendRequest.addressee_id == target_user_id),
                and_(FriendRequest.requester_id == target_user_id, FriendRequest.addressee_id == current_user.id),
            )
        )
        .order_by(FriendRequest.id.desc())
    )
    if previous:
        low, high = _pair(current_user.id, target_user_id)
        now = utcnow()
        previous.requester_id = current_user.id
        previous.addressee_id = target_user_id
        previous.pair_low_id = low
        previous.pair_high_id = high
        previous.status = FriendRequestStatus.PENDING
        previous.message = message
        previous.responded_at = None
        previous.created_at = now
        previous.updated_at = now
        request = previous
    else:
        low, high = _pair(current_user.id, target_user_id)
        request = FriendRequest(
            requester_id=current_user.id,
            addressee_id=target_user_id,
            pair_low_id=low,
            pair_high_id=high,
            status=FriendRequestStatus.PENDING,
            message=message,
        )
        db.add(request)
    await db.flush()
    await create_notification(
        db,
        user_id=target.id,
        actor_id=current_user.id,
        notification_type=NotificationType.FRIEND_REQUEST,
        title="新的好友申请",
        message=f"{current_user.username or current_user.anonymous_name} 想添加你为好友",
        data={"request_id": request.id, "actor_id": current_user.id},
        commit=False,
    )
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise AppException("FRIEND_REQUEST_EXISTS", "你们之间已有好友申请", 409) from exc
    await db.refresh(request)
    return _request_payload(request, target, is_friend=False)


def _request_payload(request: FriendRequest, other_user: User, *, is_friend: bool) -> dict:
    return {
        "id": request.id,
        "user": social_user_payload(other_user, is_friend=is_friend),
        "status": request.status.value,
        "message": request.message,
        "created_at": request.created_at,
        "responded_at": request.responded_at,
    }


async def list_friend_requests(
    db: AsyncSession,
    current_user: User,
    box: str,
    status: FriendRequestStatus | None,
    page: int,
    page_size: int,
) -> dict:
    id_column = FriendRequest.addressee_id if box == "incoming" else FriendRequest.requester_id
    stmt = select(FriendRequest).where(id_column == current_user.id)
    if status:
        stmt = stmt.where(FriendRequest.status == status)
    stmt = stmt.order_by(FriendRequest.created_at.desc(), FriendRequest.id.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size + 1)
    rows = list((await db.execute(stmt)).scalars().all())
    has_more = len(rows) > page_size
    rows = rows[:page_size]
    friends = await friend_ids(db, current_user.id)
    other_ids = {
        request.requester_id if box == "incoming" else request.addressee_id
        for request in rows
    }
    users = (
        {
            value.id: value
            for value in (
                await db.execute(select(User).where(User.id.in_(other_ids)))
            ).scalars().all()
        }
        if other_ids
        else {}
    )
    items = []
    for request in rows:
        other_id = request.requester_id if box == "incoming" else request.addressee_id
        other = users.get(other_id)
        if other:
            items.append(_request_payload(request, other, is_friend=other_id in friends))
    return {"items": items, "page": page, "page_size": page_size, "has_more": has_more}


async def respond_friend_request(
    db: AsyncSession, current_user: User, request_id: int, accept: bool
) -> dict:
    request = await db.get(FriendRequest, request_id)
    if not request or request.addressee_id != current_user.id:
        raise AppException("FRIEND_REQUEST_NOT_FOUND", "好友申请不存在", 404)
    if request.status != FriendRequestStatus.PENDING:
        raise AppException("FRIEND_REQUEST_ALREADY_HANDLED", "该好友申请已经处理", 409)
    requester = await db.get(User, request.requester_id)
    if not requester or requester.status == UserStatus.BANNED:
        raise AppException("USER_NOT_FOUND", "申请用户不存在", 404)
    await ensure_not_blocked(db, current_user.id, requester.id)

    request.status = FriendRequestStatus.ACCEPTED if accept else FriendRequestStatus.REJECTED
    request.responded_at = utcnow()
    await db.execute(
        update(UserNotification)
        .where(
            UserNotification.user_id == current_user.id,
            UserNotification.actor_id == request.requester_id,
            UserNotification.type == NotificationType.FRIEND_REQUEST,
            UserNotification.is_read.is_(False),
        )
        .values(is_read=True)
    )
    if accept:
        low, high = _pair(request.requester_id, request.addressee_id)
        existing = await _friendship(db, low, high)
        if not existing:
            db.add(Friendship(user_low_id=low, user_high_id=high, created_at=utcnow()))
    await create_notification(
        db,
        user_id=requester.id,
        actor_id=current_user.id,
        notification_type=(
            NotificationType.FRIEND_ACCEPTED if accept else NotificationType.FRIEND_REJECTED
        ),
        title="好友申请已通过" if accept else "好友申请未通过",
        message=(
            f"{current_user.username or current_user.anonymous_name} 已通过你的好友申请"
            if accept
            else f"{current_user.username or current_user.anonymous_name} 拒绝了你的好友申请"
        ),
        data={"request_id": request.id, "actor_id": current_user.id},
        commit=False,
    )
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise AppException("FRIEND_REQUEST_ALREADY_HANDLED", "该好友申请已经处理", 409) from exc
    await db.refresh(request)
    return _request_payload(request, requester, is_friend=accept)


async def list_friends(db: AsyncSession, current_user: User, page: int, page_size: int) -> dict:
    ids = sorted(await friend_ids(db, current_user.id))
    if not ids:
        return {"items": [], "page": page, "page_size": page_size, "has_more": False}
    stmt = (
        select(User)
        .where(User.id.in_(ids), User.status != UserStatus.BANNED)
        .order_by(User.username.asc().nullslast(), User.id.asc())
        .offset((page - 1) * page_size)
        .limit(page_size + 1)
    )
    rows = list((await db.execute(stmt)).scalars().all())
    has_more = len(rows) > page_size
    items = []
    for user in rows[:page_size]:
        payload = social_user_payload(user, is_friend=True)
        remark = await friend_remark(db, current_user.id, user.id)
        payload["remark"] = remark
        if remark:
            payload["display_name"] = remark
        items.append(payload)
    return {
        "items": items,
        "page": page,
        "page_size": page_size,
        "has_more": has_more,
    }


async def remove_friend(db: AsyncSession, current_user: User, friend_user_id: int) -> None:
    low, high = _pair(current_user.id, friend_user_id)
    result = await db.execute(
        delete(Friendship).where(Friendship.user_low_id == low, Friendship.user_high_id == high)
    )
    if not result.rowcount:
        await db.rollback()
        raise AppException("FRIEND_NOT_FOUND", "该用户不在好友列表中", 404)
    await db.execute(
        delete(FriendRemark).where(
            or_(
                and_(
                    FriendRemark.owner_id == current_user.id,
                    FriendRemark.friend_id == friend_user_id,
                ),
                and_(
                    FriendRemark.owner_id == friend_user_id,
                    FriendRemark.friend_id == current_user.id,
                ),
            )
        )
    )
    await db.commit()


def _validate_post(payload: PostCreate) -> None:
    if not payload.text and not payload.media:
        raise AppException("EMPTY_POST", "动态内容不能为空", 422)
    urls: set[str] = set()
    video_count = 0
    for media in payload.media:
        if not media.url.startswith("/api/media/"):
            raise AppException("INVALID_MEDIA_URL", "媒体地址无效", 422)
        if media.thumbnail_url and not media.thumbnail_url.startswith("/api/media/"):
            raise AppException("INVALID_MEDIA_URL", "缩略图地址无效", 422)
        if media.url in urls:
            raise AppException("DUPLICATE_MEDIA", "不能重复添加同一个媒体", 422)
        urls.add(media.url)
        video_count += int(media.kind == "video")
    if video_count > 1 or (video_count and len(payload.media) > 1):
        raise AppException("INVALID_MEDIA_COMBINATION", "单条动态只能发布一个视频", 422)


async def create_post(
    db: AsyncSession, redis: Redis | None, current_user: User, payload: PostCreate
) -> dict:
    ensure_user_can_post(current_user)
    _validate_post(payload)
    for media in payload.media:
        public_id = media.url.split("?", 1)[0].rsplit("/", 1)[-1]
        owned = await db.scalar(
            select(PrivateMedia.id).where(
                PrivateMedia.public_id == public_id,
                PrivateMedia.owner_id == current_user.id,
            )
        )
        if not owned:
            raise AppException("INVALID_MEDIA_URL", "媒体不存在或不属于当前用户", 422)
    if payload.text:
        risk = await check_content(db, redis, payload.text)
        if not risk.allowed:
            raise AppException("POST_BLOCKED", risk.reason or "动态内容不符合社区规范", 400)
    post = SocialPost(
        author_id=current_user.id,
        text=payload.text,
        visibility=payload.visibility,
    )
    db.add(post)
    await db.flush()
    now = utcnow()
    for index, item in enumerate(payload.media):
        media_url = item.url.split("?", 1)[0] if item.url.startswith("/api/media/") else item.url
        thumbnail_url = (
            item.thumbnail_url.split("?", 1)[0]
            if item.thumbnail_url and item.thumbnail_url.startswith("/api/media/")
            else item.thumbnail_url
        )
        db.add(
            PostMedia(
                post_id=post.id,
                kind=item.kind,
                url=media_url,
                thumbnail_url=thumbnail_url,
                duration_ms=item.duration_ms,
                width=item.width,
                height=item.height,
                sort_order=index,
                created_at=now,
            )
        )
    await db.commit()
    await db.refresh(post)
    return (await post_payloads(db, [post], current_user.id))[0]


async def _get_visible_post(db: AsyncSession, post_id: int, viewer_id: int) -> SocialPost:
    post = await db.get(SocialPost, post_id)
    if not post or post.deleted_at is not None:
        raise AppException("POST_NOT_FOUND", "动态不存在", 404)
    author_status = await db.scalar(select(User.status).where(User.id == post.author_id))
    if author_status is None or author_status == UserStatus.BANNED:
        raise AppException("POST_NOT_FOUND", "动态不存在", 404)
    if post.author_id == viewer_id or post.visibility == PostVisibility.PUBLIC:
        return post
    if post.visibility == PostVisibility.FRIENDS and await _friendship(db, post.author_id, viewer_id):
        return post
    raise AppException("POST_NOT_FOUND", "动态不存在", 404)


async def post_payloads(db: AsyncSession, posts: list[SocialPost], viewer_id: int) -> list[dict]:
    if not posts:
        return []
    post_ids = [post.id for post in posts]
    author_ids = {post.author_id for post in posts}
    users = {
        user.id: user
        for user in (
            await db.execute(select(User).where(User.id.in_(author_ids)))
        ).scalars().all()
    }
    viewer_friends = await friend_ids(db, viewer_id)
    media_by_post: dict[int, list[PostMedia]] = defaultdict(list)
    media_rows = (
        await db.execute(
            select(PostMedia)
            .where(PostMedia.post_id.in_(post_ids))
            .order_by(PostMedia.post_id.asc(), PostMedia.sort_order.asc())
        )
    ).scalars().all()
    for media in media_rows:
        media_by_post[media.post_id].append(media)
    like_counts = dict(
        (
            await db.execute(
                select(PostLike.post_id, func.count(PostLike.id))
                .where(PostLike.post_id.in_(post_ids))
                .group_by(PostLike.post_id)
            )
        ).all()
    )
    comment_counts = dict(
        (
            await db.execute(
                select(PostComment.post_id, func.count(PostComment.id))
                .where(PostComment.post_id.in_(post_ids), PostComment.deleted_at.is_(None))
                .group_by(PostComment.post_id)
            )
        ).all()
    )
    liked = set(
        (
            await db.execute(
                select(PostLike.post_id).where(
                    PostLike.post_id.in_(post_ids), PostLike.user_id == viewer_id
                )
            )
        ).scalars().all()
    )
    result = []
    for post in posts:
        author = users.get(post.author_id)
        result.append(
            {
                "id": post.id,
                "author": social_user_payload(
                    author, is_friend=post.author_id in viewer_friends
                ) if author else None,
                "text": post.text,
                "media": [
                    {
                        "id": item.id,
                        "kind": item.kind,
                        "url": signed_media_url(item.url, viewer_id),
                        "thumbnail_url": signed_media_url(item.thumbnail_url, viewer_id),
                        "duration_ms": item.duration_ms,
                        "width": item.width,
                        "height": item.height,
                    }
                    for item in media_by_post[post.id]
                ],
                "visibility": post.visibility.value,
                "like_count": int(like_counts.get(post.id, 0)),
                "comment_count": int(comment_counts.get(post.id, 0)),
                "liked_by_me": post.id in liked,
                "created_at": post.created_at,
                "updated_at": post.updated_at,
                "is_mine": post.author_id == viewer_id,
            }
        )
    return result


async def list_posts(
    db: AsyncSession,
    current_user: User,
    page: int,
    page_size: int,
    author_id: int | None = None,
) -> dict:
    friends = await friend_ids(db, current_user.id)
    blocked = await blocked_user_ids(db, current_user.id)
    visible = [
        SocialPost.author_id == current_user.id,
        SocialPost.visibility == PostVisibility.PUBLIC,
    ]
    if friends:
        visible.append(
            and_(
                SocialPost.visibility == PostVisibility.FRIENDS,
                SocialPost.author_id.in_(friends),
            )
        )
    visible_authors = select(User.id).where(User.status != UserStatus.BANNED)
    stmt = select(SocialPost).where(
        SocialPost.deleted_at.is_(None),
        SocialPost.author_id.in_(visible_authors),
        or_(*visible),
    )
    if blocked:
        stmt = stmt.where(SocialPost.author_id.not_in(blocked))
    if author_id is not None:
        stmt = stmt.where(SocialPost.author_id == author_id)
    stmt = stmt.order_by(SocialPost.created_at.desc(), SocialPost.id.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size + 1)
    rows = list((await db.execute(stmt)).scalars().all())
    has_more = len(rows) > page_size
    return {
        "items": await post_payloads(db, rows[:page_size], current_user.id),
        "page": page,
        "page_size": page_size,
        "has_more": has_more,
    }


async def get_post(db: AsyncSession, current_user: User, post_id: int) -> dict:
    post = await _get_visible_post(db, post_id, current_user.id)
    await ensure_not_blocked(db, current_user.id, post.author_id)
    return (await post_payloads(db, [post], current_user.id))[0]


async def toggle_post_like(db: AsyncSession, current_user: User, post_id: int) -> dict:
    ensure_user_can_post(current_user)
    post = await _get_visible_post(db, post_id, current_user.id)
    await ensure_not_blocked(db, current_user.id, post.author_id)
    existing = await db.scalar(
        select(PostLike).where(PostLike.post_id == post_id, PostLike.user_id == current_user.id)
    )
    if existing:
        await db.delete(existing)
        liked = False
    else:
        db.add(PostLike(post_id=post_id, user_id=current_user.id, created_at=utcnow()))
        liked = True
        if post.author_id != current_user.id:
            await create_notification(
                db,
                user_id=post.author_id,
                actor_id=current_user.id,
                notification_type=NotificationType.POST_LIKE,
                title="有人喜欢了你的动态",
                message=f"{current_user.username or current_user.anonymous_name} 喜欢了你的动态",
                data={"post_id": post.id, "actor_id": current_user.id},
                commit=False,
            )
    await db.commit()
    count = await db.scalar(select(func.count(PostLike.id)).where(PostLike.post_id == post_id))
    return {"post_id": post_id, "liked": liked, "like_count": int(count or 0)}


async def create_comment(
    db: AsyncSession,
    redis: Redis | None,
    current_user: User,
    post_id: int,
    payload: CommentCreate,
) -> dict:
    ensure_user_can_post(current_user)
    post = await _get_visible_post(db, post_id, current_user.id)
    await ensure_not_blocked(db, current_user.id, post.author_id)
    risk = await check_content(db, redis, payload.text)
    if not risk.allowed:
        raise AppException("COMMENT_BLOCKED", risk.reason or "评论内容不符合社区规范", 400)
    if payload.parent_comment_id:
        parent = await db.get(PostComment, payload.parent_comment_id)
        if not parent or parent.post_id != post_id or parent.deleted_at is not None:
            raise AppException("PARENT_COMMENT_NOT_FOUND", "回复的评论不存在", 404)
    comment = PostComment(
        post_id=post_id,
        author_id=current_user.id,
        parent_comment_id=payload.parent_comment_id,
        text=payload.text,
    )
    db.add(comment)
    await db.flush()
    if post.author_id != current_user.id:
        await create_notification(
            db,
            user_id=post.author_id,
            actor_id=current_user.id,
            notification_type=NotificationType.POST_COMMENT,
            title="你的动态有新评论",
            message=f"{current_user.username or current_user.anonymous_name} 评论了你的动态",
            data={"post_id": post.id, "comment_id": comment.id, "actor_id": current_user.id},
            commit=False,
        )
    await db.commit()
    await db.refresh(comment)
    return comment_payload(comment, current_user, is_friend=False)


def comment_payload(comment: PostComment, author: User, *, is_friend: bool) -> dict:
    return {
        "id": comment.id,
        "post_id": comment.post_id,
        "author": social_user_payload(author, is_friend=is_friend),
        "text": comment.text,
        "parent_comment_id": comment.parent_comment_id,
        "created_at": comment.created_at,
    }


async def list_comments(
    db: AsyncSession, current_user: User, post_id: int, page: int, page_size: int
) -> dict:
    await _get_visible_post(db, post_id, current_user.id)
    blocked = await blocked_user_ids(db, current_user.id)
    stmt = (
        select(PostComment)
        .where(PostComment.post_id == post_id, PostComment.deleted_at.is_(None))
        .order_by(PostComment.created_at.asc(), PostComment.id.asc())
        .offset((page - 1) * page_size)
        .limit(page_size + 1)
    )
    if blocked:
        stmt = stmt.where(PostComment.author_id.not_in(blocked))
    rows = list((await db.execute(stmt)).scalars().all())
    has_more = len(rows) > page_size
    rows = rows[:page_size]
    author_ids = {row.author_id for row in rows}
    authors = {
        user.id: user
        for user in (
            await db.execute(select(User).where(User.id.in_(author_ids)))
        ).scalars().all()
    } if author_ids else {}
    friends = await friend_ids(db, current_user.id)
    return {
        "items": [
            comment_payload(row, authors[row.author_id], is_friend=row.author_id in friends)
            for row in rows
            if row.author_id in authors
        ],
        "page": page,
        "page_size": page_size,
        "has_more": has_more,
    }


async def delete_post(db: AsyncSession, current_user: User, post_id: int) -> None:
    post = await db.get(SocialPost, post_id)
    if not post or post.deleted_at is not None:
        raise AppException("POST_NOT_FOUND", "动态不存在", 404)
    if post.author_id != current_user.id:
        raise AppException("FORBIDDEN", "只能删除自己的动态", 403)
    post.deleted_at = utcnow()
    await db.commit()


async def delete_comment(db: AsyncSession, current_user: User, comment_id: int) -> None:
    comment = await db.get(PostComment, comment_id)
    if not comment or comment.deleted_at is not None:
        raise AppException("COMMENT_NOT_FOUND", "评论不存在", 404)
    post = await db.get(SocialPost, comment.post_id)
    if comment.author_id != current_user.id and (not post or post.author_id != current_user.id):
        raise AppException("FORBIDDEN", "无权删除这条评论", 403)
    comment.deleted_at = utcnow()
    await db.commit()
