from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class InstalledSkill(Base):
    __tablename__ = "installed_skills"

    name: Mapped[str] = mapped_column(String(100), primary_key=True)
    version: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    source: Mapped[str] = mapped_column(String(50), nullable=False, default="local")
    manifest_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    installed_path: Mapped[str] = mapped_column(String(500), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    installed_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
