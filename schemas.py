from pydantic import BaseModel
from datetime import date, datetime
from typing import Optional, List


class RoomBase(BaseModel):
    number: str
    type: str
    price: float
    capacity: int
    description: str
    is_available: bool
    image_url: Optional[str] = "/static/images/room-default.jpg"


class RoomCreate(RoomBase):
    pass


class RoomUpdate(BaseModel):
    number: Optional[str] = None
    type: Optional[str] = None
    price: Optional[float] = None
    capacity: Optional[int] = None
    description: Optional[str] = None
    is_available: Optional[bool] = None
    image_url: Optional[str] = None


class Room(RoomBase):
    id: int
    created_at: datetime
    
    class Config:
        from_attributes = True


class BookingBase(BaseModel):
    room_id: int
    guest_name: str
    guest_email: str
    guest_phone: str
    check_in: date
    check_out: date


class BookingCreate(BookingBase):
    pass


class Booking(BookingBase):
    id: int
    total_price: float
    status: str
    created_at: datetime
    
    class Config:
        from_attributes = True


class AdminLogin(BaseModel):
    username: str
    password: str


class AdminUser(BaseModel):
    id: int
    username: str
    created_at: datetime
    
    class Config:
        from_attributes = True