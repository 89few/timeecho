from app.models import Base

# Import all models so Alembic can see the metadata.
from app.models.user import User  # noqa: F401
from app.models.letter import Letter  # noqa: F401
from app.models.chat import (  # noqa: F401
    AnonymousIdentity,
    AnonymousMatch,
    ChatRoom,
    ChatMessage,
    MatchExclusion,
    MatchParticipant,
    RecentMatch,
    UserMatchState,
    UserBlock,
)
from app.models.notification import UserNotification  # noqa: F401
from app.models.security import AdminAuditLog, AdminLoginLog, AdminSession, AdminUser, PrivateMedia, UserSession  # noqa: F401
from app.models.complaint import Complaint  # noqa: F401
from app.models.punishment import Punishment  # noqa: F401
from app.models.system_config import SystemConfig  # noqa: F401
from app.models.sensitive_word import SensitiveWord  # noqa: F401
from app.models.social import (  # noqa: F401
    FriendRequest,
    FriendRemark,
    Friendship,
    PostComment,
    PostLike,
    PostMedia,
    SocialPost,
)
