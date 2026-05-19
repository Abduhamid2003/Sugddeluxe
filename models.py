# pylint: disable=import-error,no-name-in-module,not-callable
from sqlalchemy import Column, Integer, String, Float, Boolean, Date, DateTime, Text, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from database import Base


class Room(Base):
    __tablename__ = "rooms"
    
    id = Column(Integer, primary_key=True, index=True)
    number = Column(String(10), unique=True, index=True)
    type = Column(String(50))
    price = Column(Float)
    capacity = Column(Integer)
    description = Column(Text)
    is_available = Column(Boolean, default=True)
    image_url = Column(String(255), default="/static/images/room-default.jpg")
    created_at = Column(DateTime, default=func.now())
    
    # Связь с бронированиями
    bookings = relationship("Booking", back_populates="room")


class Booking(Base):
    __tablename__ = "bookings"
    
    id = Column(Integer, primary_key=True, index=True)
    room_id = Column(Integer, ForeignKey("rooms.id"))
    guest_name = Column(String(100))
    guest_email = Column(String(100))
    guest_phone = Column(String(20))
    check_in = Column(Date)
    check_out = Column(Date)
    total_price = Column(Float)
    status = Column(String(20), default="confirmed")
    created_at = Column(DateTime, default=func.now())
    
    # Связь с комнатой
    room = relationship("Room", back_populates="bookings")


class AdminUser(Base):
    __tablename__ = "admin_users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True)
    password_hash = Column(String(255))
    created_at = Column(DateTime, default=func.now())