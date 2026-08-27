from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, CHAR, DateTime, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(Text, nullable=False)
    country_code: Mapped[str] = mapped_column(CHAR(2), nullable=False)
    default_currency: Mapped[str] = mapped_column(CHAR(3), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    vehicles: Mapped[list["Vehicle"]] = relationship(back_populates="organization", cascade="all, delete-orphan")


class Vehicle(Base):
    __tablename__ = "vehicles"
    __table_args__ = (UniqueConstraint("organization_id", "registration_number"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    registration_number: Mapped[str] = mapped_column(Text, nullable=False)
    make: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    fuel_type: Mapped[str] = mapped_column(Text, default="diesel", nullable=False)
    expected_litres_per_100km: Mapped[float] = mapped_column(Numeric(8, 2), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    organization: Mapped[Organization] = relationship(back_populates="vehicles")
