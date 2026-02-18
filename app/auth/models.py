import enum
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from app import db


class RoleEnum(enum.Enum):
    admin   = "admin"
    cashier = "cashier"


class User(db.Model):
    """Represents a system user (admin or cashier)."""
    __tablename__ = 'users'

    id            = db.Column(db.Integer, primary_key=True)
    name          = db.Column(db.String(120), nullable=False)
    username      = db.Column(db.String(64), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    role          = db.Column(db.Enum(RoleEnum), nullable=False, default=RoleEnum.cashier)
    created_at    = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    # ── Password helpers ──────────────────────────────────────────
    def set_password(self, plain_password: str) -> None:
        """Hash and store the password. Never stores plain text."""
        self.password_hash = generate_password_hash(plain_password)

    def check_password(self, plain_password: str) -> bool:
        """Return True if the supplied password matches the stored hash."""
        return check_password_hash(self.password_hash, plain_password)

    # ── Convenience ───────────────────────────────────────────────
    @property
    def is_admin(self) -> bool:
        return self.role == RoleEnum.admin

    def __repr__(self) -> str:
        return f"<User {self.username!r} role={self.role.value!r}>"
