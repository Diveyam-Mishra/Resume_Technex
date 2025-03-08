import uuid
import enum
from datetime import datetime
from typing import List, Optional

from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, Integer, String, Text, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database.db import Base


class Provider(str, enum.Enum):
    EMAIL = "email"
    GITHUB = "github"
    GOOGLE = "google"
    OPENID = "openid"


class Visibility(str, enum.Enum):
    PUBLIC = "public"
    PRIVATE = "private"


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False, index=True)
    username = Column(String, unique=True, nullable=False, index=True)
    locale = Column(String, nullable=False, default="en-US")
    picture = Column(String, nullable=True)
    provider = Column(Enum(Provider), nullable=False, default=Provider.EMAIL)
    emailVerified = Column(Boolean, nullable=False, default=False)
    twoFactorEnabled = Column(Boolean, nullable=False, default=False)
    createdAt = Column(DateTime, nullable=False, default=datetime.utcnow)
    updatedAt = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    secrets = relationship("Secrets", back_populates="user", uselist=False, cascade="all, delete-orphan")
    resumes = relationship("Resume", back_populates="user", cascade="all, delete-orphan")


class Secrets(Base):
    __tablename__ = "secrets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    userId = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    password = Column(String, nullable=True)
    resetToken = Column(String, nullable=True, unique=True, index=True)
    verificationToken = Column(String, nullable=True)
    twoFactorSecret = Column(String, nullable=True)
    twoFactorBackupCodes = Column(JSON, nullable=False, default=list)
    refreshToken = Column(String, nullable=True)
    lastSignedIn = Column(DateTime, nullable=True)
    createdAt = Column(DateTime, nullable=False, default=datetime.utcnow)
    updatedAt = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="secrets")


class Resume(Base):
    __tablename__ = "resumes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    userId = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title = Column(String, nullable=False)
    slug = Column(String, nullable=False)
    visibility = Column(Enum(Visibility), nullable=False, default=Visibility.PRIVATE)
    locked = Column(Boolean, nullable=False, default=False)
    data = Column(JSON, nullable=False)
    createdAt = Column(DateTime, nullable=False, default=datetime.utcnow)
    updatedAt = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # # Composite unique constraint on userId and id
    # __table_args__ = (
    #     {"unique": (userId, id)},
    #     {"unique": (userId, slug)},
    # )

    # Relationships
    user = relationship("User", back_populates="resumes")
    statistics = relationship("Statistics", back_populates="resume", uselist=False, cascade="all, delete-orphan")


class Statistics(Base):
    __tablename__ = "statistics"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    resumeId = Column(UUID(as_uuid=True), ForeignKey("resumes.id", ondelete="CASCADE"), unique=True, nullable=False)
    views = Column(Integer, nullable=False, default=0)
    downloads = Column(Integer, nullable=False, default=0)
    createdAt = Column(DateTime, nullable=False, default=datetime.utcnow)
    updatedAt = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    resume = relationship("Resume", back_populates="statistics")