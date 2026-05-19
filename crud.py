# pylint: disable=import-error,no-name-in-module
from sqlalchemy.orm import Session
from sqlalchemy import and_
import models
import schemas
from datetime import date, datetime
import hashlib
import os
from typing import List


# Хеширование пароля
def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


# Функции для комнат
def get_room(db: Session, room_id: int):
    return db.query(models.Room).filter(models.Room.id == room_id).first()


def get_rooms(db: Session, skip: int = 0, limit: int = 100):
    return db.query(models.Room).offset(skip).limit(limit).all()


def get_available_rooms(db: Session):
    return db.query(models.Room).filter(models.Room.is_available == True).all()


def create_room(db: Session, room: schemas.RoomCreate):
    db_room = models.Room(**room.dict())
    db.add(db_room)
    db.commit()
    db.refresh(db_room)
    return db_room


def update_room(db: Session, room_id: int, room_update: schemas.RoomUpdate):
    db_room = db.query(models.Room).filter(models.Room.id == room_id).first()
    if db_room:
        update_data = room_update.dict(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_room, field, value)
        db.commit()
        db.refresh(db_room)
    return db_room


def delete_room(db: Session, room_id: int):
    room = db.query(models.Room).filter(models.Room.id == room_id).first()
    if room:
        db.delete(room)
        db.commit()
    return room


# Функции для бронирований
def is_room_available(db: Session, room_id: int, check_in: date, check_out: date):
    conflicting_bookings = db.query(models.Booking).filter(
        and_(
            models.Booking.room_id == room_id,
            models.Booking.status == "confirmed",
            and_(
                models.Booking.check_in < check_out,
                models.Booking.check_out > check_in
            )
        )
    ).first()
    return conflicting_bookings is None


def get_room_bookings(db: Session, room_id: int):
    return db.query(models.Booking).filter(models.Booking.room_id == room_id).all()


def create_booking(db: Session, booking: schemas.BookingCreate):
    if not is_room_available(db, booking.room_id, booking.check_in, booking.check_out):
        raise ValueError("Комната уже забронирована на эти даты")
    
    room = get_room(db, booking.room_id)
    nights = (booking.check_out - booking.check_in).days
    total_price = room.price * nights
    
    db_booking = models.Booking(
        **booking.dict(),
        total_price=total_price
    )
    db.add(db_booking)
    db.commit()
    db.refresh(db_booking)
    return db_booking


def get_bookings(db: Session, skip: int = 0, limit: int = 100):
    return db.query(models.Booking).offset(skip).limit(limit).all()


def get_booking(db: Session, booking_id: int):
    return db.query(models.Booking).filter(models.Booking.id == booking_id).first()


def delete_booking(db: Session, booking_id: int):
    booking = db.query(models.Booking).filter(models.Booking.id == booking_id).first()
    if booking:
        db.delete(booking)
        db.commit()
    return booking


# Функции для администраторов
def create_admin_user(db: Session, username: str, password: str):
    hashed_password = hash_password(password)
    db_admin = models.AdminUser(username=username, password_hash=hashed_password)
    db.add(db_admin)
    db.commit()
    db.refresh(db_admin)
    return db_admin


def get_admin_user(db: Session, username: str):
    return db.query(models.AdminUser).filter(models.AdminUser.username == username).first()


def verify_admin_login(db: Session, username: str, password: str):
    admin = get_admin_user(db, username)
    if admin and admin.password_hash == hash_password(password):
        return admin
    return None


# Инициализация администратора по умолчанию
def init_admin_user(db: Session):
    if not get_admin_user(db, "admin"):
        create_admin_user(db, "admin", "admin123")