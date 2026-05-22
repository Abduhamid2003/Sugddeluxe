"""
FastAPI приложение для отеля СУҒДДЕЛЮКС с DeepSeek AI и email уведомлениями
Поддержка трёх языков: таджикский (tg), русский (ru), английский (en)
"""

import os
import requests
import json
from datetime import date
from typing import List
from datetime import datetime
from typing import Optional, Dict, Any
from fastapi import FastAPI, Request, Form, HTTPException, status, Depends, WebSocket, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel
import sqlite3
from pathlib import Path
import asyncio
import uuid
import re
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import logging

app = FastAPI(title="СУҒДДЕЛЮКС")

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Создаем папки
os.makedirs("static/uploads/rooms", exist_ok=True)
os.makedirs("static/images", exist_ok=True)
os.makedirs("templates", exist_ok=True)

# Монтируем static
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Базовая аутентификация
security = HTTPBasic()

# Конфигурация DeepSeek API
DEEPSEEK_API_KEY = "sk-e6ec88dbec5340a0bc5c71d53f6c854b"
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"

# Конфигурация email
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
EMAIL_ADDRESS = "urunovabduhamid2003@gmail.com"
EMAIL_PASSWORD = "nogghrulvadjypth"


def detect_language(text: str) -> str:
    """Определение языка сообщения (таджикский, русский, английский)"""
    text_lower = text.lower()
    
    # === ПРОВЕРКА НА РУССКИЙ ЯЗЫК (СНАЧАЛА!) ===
    russian_words = [
        'номер', 'бронь', 'гостиница', 'здравствуйте', 'спасибо', 
        'свободен', 'доступен', 'контакты', 'связь', 'помощь',
        'мои брони', 'бронирование', 'забронировать', 'отменить',
        'цены', 'услуги', 'ресторан', 'бассейн', 'как добраться'
    ]
    
    for word in russian_words:
        if word in text_lower:
            print(f"🔍 Определён русский язык по слову: {word}")
            return 'ru'
    
    # === ПРОВЕРКА НА АНГЛИЙСКИЙ ЯЗЫК ===
    english_words = [
        'room', 'book', 'hotel', 'hello', 'thank', 'available', 
        'contact', 'help', 'my bookings', 'booking', 'cancel',
        'prices', 'services', 'restaurant', 'pool', 'how to get'
    ]
    
    for word in english_words:
        if word in text_lower:
            print(f"🔍 Определён английский язык по слову: {word}")
            return 'en'
    
    # === ПРОВЕРКА НА ТАДЖИКСКИЙ ЯЗЫК ===
    tajik_words = [
        'ҳуҷра', 'брон', 'меҳмонхона', 'салом', 'ташаккур', 
        'озод', 'дастрас', 'тамос', 'кумак', 'фармоишҳои ман',
        'бекор кардан', 'нарх', 'хизмат', 'ошхона', 'расидан'
    ]
    
    for word in tajik_words:
        if word in text_lower:
            print(f"🔍 Определён таджикский язык по слову: {word}")
            return 'tg'
    
    # === ПРОВЕРКА ПО БУКВАМ ===
    tajik_chars = set('ғӣқўҳӯҷ')
    tajik_count = sum(1 for c in text_lower if c in tajik_chars)
    
    if tajik_count > 0:
        return 'tg'
    
    cyrillic_chars = set('абвгдеёжзийклмнопрстуфхцчшщъыьэюя')
    cyrillic_count = sum(1 for c in text_lower if c in cyrillic_chars)
    
    if cyrillic_count > 0:
        return 'ru'
    
    if text_lower and text_lower[0].isalpha():
        return 'en'
    
    return 'en'


def get_language_system_prompt(lang: str) -> str:
    """Возвращает system prompt для AI на нужном языке"""
    prompts = {
        'tg': """Ту ёрдамчии AI-и меҳмонхонаи "СУҒДДЕЛЮКС" ҳастӣ. 
        Ҷавобҳоро бо забони тоҷикӣ диҳ. Кӯтоҳ ва муфид ҷавоб деҳ.
        
Маълумот дар бораи меҳмонхона:
- Номҳо: Стандарт (350 сом.), Люкс (450 сом.), Оилавӣ (400 сом.)
- Хизматҳо: тарабхона, ҳавз, SPA, Wi-Fi, истгоҳи автомобил
- Тамос: +992 88 999 30 90
- Суроға: шаҳри Хуҷанд, кӯчаи Раҳим Ҷалил, 24

Ту наметавонӣ ба ҳама гуна саволҳо ҷавоб диҳӣ. Агар савол ба меҳмонхона алоқаманд набошад, ҷавоб надеҳ.""",
        
        'ru': """Ты AI-помощник отеля "СУГДДЕЛЮКС".
        Отвечай на русском языке. Будь полезен и дружелюбен.
        
Информация об отеле:
- Номера: Стандарт (350 сом.), Люкс (450 сом.), Оилавӣ (400 сом.)
- Услуги: ресторан, бассейн, SPA, Wi-Fi, парковка
- Контакты: +992 88 999 30 90
- Адрес: г. Худжанд, ул. Рахим Джалил, 24

Ты не можешь отвечать на любые вопросы. Если вопрос не связан с отелем, не отвечай.""",
        
        'en': """You are an AI assistant for "SUGDDELUXE" hotel.
        Answer in English. Be helpful and friendly.
        
Hotel information:
- Rooms: Standard (350 som.), Lux (450 som.), Family (400 som.)
- Services: restaurant, pool, SPA, Wi-Fi, parking
- Contacts: +992 88 999 30 90
- Address: Khujand, Rahim Jalil street, 24

You can answer any questions. If the question is not related to the hotel, answer as a general AI assistant."""
    }
    return prompts.get(lang, prompts['en'])


def send_email(to_email: str, subject: str, html_content: str) -> bool:
    """Отправка email через SMTP"""
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = EMAIL_ADDRESS
        msg['To'] = to_email
        
        html_part = MIMEText(html_content, 'html', 'utf-8')
        msg.attach(html_part)
        
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        server.send_message(msg)
        server.quit()
        
        logger.info(f"✅ Email отправлен на {to_email}")
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка отправки email: {e}")
        return False


def create_booking_email_html(booking_data: Dict[str, Any], lang: str = 'tg') -> str:
    """Создание HTML письма для подтверждения бронирования на нужном языке"""
    
    # Функция для перевода типа комнаты
    def translate_room_type(room_type: str, target_lang: str) -> str:
        translations = {
            'ru': {
                'Стандарт': 'Стандарт',
                'Люкс': 'Люкс',
                'Семейный': 'Семейный',
                'Премиум': 'Премиум',
                'Боҳашамат': 'Люкс',
                'Оилавӣ': 'Семейный',
                'Олӣ': 'Премиум'
            },
            'en': {
                'Стандарт': 'Standard',
                'Люкс': 'Luxury',
                'Семейный': 'Family',
                'Премиум': 'Premium',
                'Боҳашамат': 'Luxury',
                'Оилавӣ': 'Family',
                'Олӣ': 'Premium'
            },
            'tg': {
                'Стандарт': 'Стандарт',
                'Люкс': 'Люкс',
                'Семейный': 'Оилавӣ',
                'Премиум': 'Олӣ',
                'Боҳашамат': 'Люкс',
                'Оилавӣ': 'Оилавӣ',
                'Олӣ': 'Олӣ'
            }
        }
        return translations.get(target_lang, {}).get(room_type, room_type)
    
    room_type_translated = translate_room_type(booking_data['room_type'], lang)
    
    if lang == 'ru':
        return f"""
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <title>Подтверждение бронирования - СУГДДЕЛЮКС</title>
    <style>
        body {{ font-family: 'Segoe UI', sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px; background: #f9f9f9; }}
        .header {{ background: linear-gradient(135deg, #2c5aa0, #3a7bd5); color: white; padding: 30px; text-align: center; border-radius: 10px 10px 0 0; }}
        .content {{ background: white; padding: 30px; border-radius: 0 0 10px 10px; }}
        .booking-details {{ background: #f8f9fa; padding: 20px; border-radius: 8px; margin: 20px 0; border-right: 4px solid #3a7bd5; }}
        .detail-row {{ display: flex; justify-content: space-between; margin-bottom: 10px; padding: 8px 0; border-bottom: 1px solid #e9ecef; }}
        .detail-label {{ font-weight: bold; }}
        .detail-value {{ color: #2c5aa0; font-weight: 600; }}
        .footer {{ text-align: center; margin-top: 30px; padding-top: 20px; border-top: 1px solid #dee2e6; color: #6c757d; font-size: 14px; }}
        .hotel-name {{ font-size: 28px; font-weight: bold; margin-bottom: 10px; }}
    </style>
</head>
<body>
    <div class="header">
        <div class="hotel-name">СУГДДЕЛЮКС</div>
        <h1>Бронирование подтверждено! 🎉</h1>
    </div>
    <div class="content">
        <h2>Уважаемый(ая) {booking_data['guest_name']},</h2>
        <p>Ваше бронирование в отеле СУГДДЕЛЮКС успешно подтверждено. Благодарим за выбор!</p>
        <div class="booking-details">
            <h3>📋 Детали бронирования</h3>
            <div class="detail-row"><span class="detail-label">№ брони:</span><span class="detail-value">#{booking_data['id']}</span></div>
            <div class="detail-row"><span class="detail-label">Номер:</span><span class="detail-value">{booking_data['room_number']} ({room_type_translated})</span></div>
            <div class="detail-row"><span class="detail-label">Заезд:</span><span class="detail-value">{booking_data['check_in']}</span></div>
            <div class="detail-row"><span class="detail-label">Выезд:</span><span class="detail-value">{booking_data['check_out']}</span></div>
            <div class="detail-row"><span class="detail-label">Ночей:</span><span class="detail-value">{booking_data.get('nights', 1)}</span></div>
            <div class="detail-row"><span class="detail-label">Итого:</span><span class="detail-value">{booking_data['total_price']} сомони</span></div>
        </div>
        <p><strong>Важно:</strong> Заезд с 14:00, выезд до 12:00. Бесплатная отмена за 24 часа.</p>
        <p>С уважением,<br><strong>Команда СУГДДЕЛЮКС</strong> 🏨</p>
    </div>
    <div class="footer"><p>© 2025 СУГДДЕЛЮКС. Все права защищены.</p></div>
</body>
</html>"""
    
    elif lang == 'en':
        return f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Booking Confirmation - SUGDDELUXE</title>
    <style>
        body {{ font-family: 'Segoe UI', sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px; background: #f9f9f9; }}
        .header {{ background: linear-gradient(135deg, #2c5aa0, #3a7bd5); color: white; padding: 30px; text-align: center; border-radius: 10px 10px 0 0; }}
        .content {{ background: white; padding: 30px; border-radius: 0 0 10px 10px; }}
        .booking-details {{ background: #f8f9fa; padding: 20px; border-radius: 8px; margin: 20px 0; border-right: 4px solid #3a7bd5; }}
        .detail-row {{ display: flex; justify-content: space-between; margin-bottom: 10px; padding: 8px 0; border-bottom: 1px solid #e9ecef; }}
        .detail-label {{ font-weight: bold; }}
        .detail-value {{ color: #2c5aa0; font-weight: 600; }}
        .footer {{ text-align: center; margin-top: 30px; padding-top: 20px; border-top: 1px solid #dee2e6; color: #6c757d; font-size: 14px; }}
        .hotel-name {{ font-size: 28px; font-weight: bold; margin-bottom: 10px; }}
    </style>
</head>
<body>
    <div class="header">
        <div class="hotel-name">SUGDDELUXE</div>
        <h1>Booking Confirmed! 🎉</h1>
    </div>
    <div class="content">
        <h2>Dear {booking_data['guest_name']},</h2>
        <p>Your booking at SUGDDELUXE Hotel has been confirmed. Thank you for choosing us!</p>
        <div class="booking-details">
            <h3>📋 Booking Details</h3>
            <div class="detail-row"><span class="detail-label">Booking #:</span><span class="detail-value">#{booking_data['id']}</span></div>
            <div class="detail-row"><span class="detail-label">Room:</span><span class="detail-value">{booking_data['room_number']} ({room_type_translated})</span></div>
            <div class="detail-row"><span class="detail-label">Check-in:</span><span class="detail-value">{booking_data['check_in']}</span></div>
            <div class="detail-row"><span class="detail-label">Check-out:</span><span class="detail-value">{booking_data['check_out']}</span></div>
            <div class="detail-row"><span class="detail-label">Nights:</span><span class="detail-value">{booking_data.get('nights', 1)}</span></div>
            <div class="detail-row"><span class="detail-label">Total:</span><span class="detail-value">{booking_data['total_price']} somoni</span></div>
        </div>
        <p><strong>Note:</strong> Check-in from 14:00, check-out until 12:00. Free cancellation 24 hours before.</p>
        <p>Best regards,<br><strong>SUGDDELUXE Team</strong> 🏨</p>
    </div>
    <div class="footer"><p>© 2025 SUGDDELUXE. All rights reserved.</p></div>
</body>
</html>"""
    
    else:  # таджикский по умолчанию
        return f"""
<!DOCTYPE html>
<html lang="tg">
<head>
    <meta charset="UTF-8">
    <title>Таҳияи брон - СУҒДДЕЛЮКС</title>
    <style>
        body {{ font-family: 'Segoe UI', sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px; background: #f9f9f9; }}
        .header {{ background: linear-gradient(135deg, #2c5aa0, #3a7bd5); color: white; padding: 30px; text-align: center; border-radius: 10px 10px 0 0; }}
        .content {{ background: white; padding: 30px; border-radius: 0 0 10px 10px; }}
        .booking-details {{ background: #f8f9fa; padding: 20px; border-radius: 8px; margin: 20px 0; border-right: 4px solid #3a7bd5; }}
        .detail-row {{ display: flex; justify-content: space-between; margin-bottom: 10px; padding: 8px 0; border-bottom: 1px solid #e9ecef; }}
        .detail-label {{ font-weight: bold; }}
        .detail-value {{ color: #2c5aa0; font-weight: 600; }}
        .footer {{ text-align: center; margin-top: 30px; padding-top: 20px; border-top: 1px solid #dee2e6; color: #6c757d; font-size: 14px; }}
        .hotel-name {{ font-size: 28px; font-weight: bold; margin-bottom: 10px; }}
    </style>
</head>
<body>
    <div class="header">
        <div class="hotel-name">СУҒДДЕЛЮКС</div>
        <h1>Брон таҳия шуд! 🎉</h1>
    </div>
    <div class="content">
        <h2>Ҷаноби {booking_data['guest_name']},</h2>
        <p>Брони шумо дар меҳмонхонаи СУҒДДЕЛЮКС бо муваффақият қабул карда шуд. Ташаккур барои интихоби мо!</p>
        <div class="booking-details">
            <h3>🔄 Маълумоти брон</h3>
            <div class="detail-row"><span class="detail-label">Рақами брон:</span><span class="detail-value">#{booking_data['id']}</span></div>
            <div class="detail-row"><span class="detail-label">Ҳуҷра:</span><span class="detail-value">{booking_data['room_number']} ({room_type_translated})</span></div>
            <div class="detail-row"><span class="detail-label">Воридшавӣ:</span><span class="detail-value">{booking_data['check_in']}</span></div>
            <div class="detail-row"><span class="detail-label">Баромад:</span><span class="detail-value">{booking_data['check_out']}</span></div>
            <div class="detail-row"><span class="detail-label">Шабҳо:</span><span class="detail-value">{booking_data.get('nights', 1)}</span></div>
            <div class="detail-row"><span class="detail-label">Нархи умумӣ:</span><span class="detail-value">{booking_data['total_price']} сомонӣ</span></div>
        </div>
        <p><strong>Ёддошт:</strong> Воридишавӣ аз соати 14:00, баромад то 12:00. Бекор кардани брон то 24 соат пеш ройгон аст.</p>
        <p>Бо эҳтиром,<br><strong>Дастаи СУҒДДЕЛЮКС</strong> 🏨</p>
    </div>
    <div class="footer"><p>© 2025 СУҒДДЕЛЮКС. Ҳамаи ҳуқуқҳо ҳифз шудаанд.</p></div>
</body>
</html>"""


def create_cancellation_email_html(booking_data: Dict[str, Any], lang: str = 'tg') -> str:
    """HTML письмо для отмены бронирования на нужном языке"""
    
    # Функция для перевода типа комнаты
    def translate_room_type(room_type: str, target_lang: str) -> str:
        translations = {
            'ru': {
                'Стандарт': 'Стандарт',
                'Люкс': 'Люкс',
                'Семейный': 'Семейный',
                'Премиум': 'Премиум',
                'Боҳашамат': 'Люкс',
                'Оилавӣ': 'Семейный',
                'Олӣ': 'Премиум'
            },
            'en': {
                'Стандарт': 'Standard',
                'Люкс': 'Luxury',
                'Семейный': 'Family',
                'Премиум': 'Premium',
                'Боҳашамат': 'Luxury',
                'Оилавӣ': 'Family',
                'Олӣ': 'Premium'
            },
            'tg': {
                'Стандарт': 'Стандарт',
                'Люкс': 'Люкс',
                'Семейный': 'Оилавӣ',
                'Премиум': 'Олӣ',
                'Боҳашамат': 'Люкс',
                'Оилавӣ': 'Оилавӣ',
                'Олӣ': 'Олӣ'
            }
        }
        return translations.get(target_lang, {}).get(room_type, room_type)
    
    room_type_translated = translate_room_type(booking_data['room_type'], lang)
    
    if lang == 'ru':
        return f"""
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><title>Бронирование отменено</title>
<style>
    body {{ font-family: Arial; max-width: 600px; margin: 0 auto; padding: 20px; }}
    .header {{ background: #dc3545; color: white; padding: 20px; text-align: center; border-radius: 10px 10px 0 0; }}
    .content {{ background: #f8f9fa; padding: 20px; border-radius: 0 0 10px 10px; }}
</style>
</head>
<body>
    <div class="header"><h2>❌ Бронирование отменено</h2></div>
    <div class="content">
        <h3>Уважаемый(ая) {booking_data['guest_name']},</h3>
        <p>Ваше бронирование #{booking_data['id']} успешно отменено.</p>
        <p><strong>Детали отменённого бронирования:</strong></p>
        <ul>
            <li>Номер: {booking_data['room_number']} ({room_type_translated})</li>
            <li>Даты: {booking_data['check_in']} - {booking_data['check_out']}</li>
        </ul>
        <p>Будем рады видеть вас снова!</p>
        <p>С уважением,<br>Команда СУГДДЕЛЮКС</p>
    </div>
</body>
</html>"""
    
    elif lang == 'en':
        return f"""
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><title>Booking Cancelled</title>
<style>
    body {{ font-family: Arial; max-width: 600px; margin: 0 auto; padding: 20px; }}
    .header {{ background: #dc3545; color: white; padding: 20px; text-align: center; border-radius: 10px 10px 0 0; }}
    .content {{ background: #f8f9fa; padding: 20px; border-radius: 0 0 10px 10px; }}
</style>
</head>
<body>
    <div class="header"><h2>❌ Booking Cancelled</h2></div>
    <div class="content">
        <h3>Dear {booking_data['guest_name']},</h3>
        <p>Your booking #{booking_data['id']} has been successfully cancelled.</p>
        <p><strong>Cancelled booking details:</strong></p>
        <ul>
            <li>Room: {booking_data['room_number']} ({room_type_translated})</li>
            <li>Dates: {booking_data['check_in']} - {booking_data['check_out']}</li>
        </ul>
        <p>We hope to see you again!</p>
        <p>Best regards,<br>SUGDDELUXE Team</p>
    </div>
</body>
</html>"""
    
    else:  # таджикский
        return f"""
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><title>Брон бекор карда шуд</title>
<style>
    body {{ font-family: Arial; max-width: 600px; margin: 0 auto; padding: 20px; }}
    .header {{ background: #dc3545; color: white; padding: 20px; text-align: center; border-radius: 10px 10px 0 0; }}
    .content {{ background: #f8f9fa; padding: 20px; border-radius: 0 0 10px 10px; }}
</style>
</head>
<body>
    <div class="header"><h2>❌ Брон бекор карда шуд</h2></div>
    <div class="content">
        <h3>Ҷаноби {booking_data['guest_name']},</h3>
        <p>Брони шумо #{booking_data['id']} бо муваффақият бекор карда шуд.</p>
        <p><strong>Маълумоти брон:</strong></p>
        <ul>
            <li>Ҳуҷра: {booking_data['room_number']} ({room_type_translated})</li>
            <li>Санаҳо: {booking_data['check_in']} - {booking_data['check_out']}</li>
        </ul>
        <p>Умедворем, ки боз дидор хоҳем дошт!</p>
        <p>Бо эҳтиром,<br>Дастаи СУҒДДЕЛЮКС</p>
    </div>
</body>
</html>"""


def call_deepseek_api(messages, max_tokens=500, temperature=0.7):
    """Универсальная функция для вызова DeepSeek API"""
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}"
    }
    
    payload = {
        "model": "deepseek-chat",
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": False
    }
    
    try:
        response = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        result = response.json()
        
        if "choices" in result and len(result["choices"]) > 0:
            return result["choices"][0]["message"]["content"]
        else:
            return "Извините, возникла ошибка при обработке запроса."
    except Exception as e:
        print(f"❌ Ошибка DeepSeek API: {e}")
        return "Сервис временно недоступен. Пожалуйста, попробуйте позже."


# ==================== БАЗА ДАННЫХ ====================

def init_db():
    conn = sqlite3.connect('hotel.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS rooms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            number TEXT UNIQUE,
            type TEXT,
            price REAL,
            capacity INTEGER,
            description TEXT,
            is_available BOOLEAN DEFAULT TRUE,
            image_url TEXT DEFAULT '/static/images/room-default.jpg',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            room_id INTEGER,
            guest_name TEXT,
            guest_email TEXT,
            guest_phone TEXT,
            check_in DATE,
            check_out DATE,
            total_price REAL,
            status TEXT DEFAULT 'confirmed',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS admin_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password_hash TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute("SELECT COUNT(*) FROM rooms")
    if cursor.fetchone()[0] == 0:
        cursor.execute('''
            INSERT INTO rooms (number, type, price, capacity, description, image_url) 
            VALUES 
            ('101', 'Стандарт', 2500, 2, 'Уютный номер с одной двуспальной кроватью', '/static/images/room-default.jpg'),
            ('102', 'Люкс', 4500, 3, 'Просторный номер с гостиной зоной', '/static/images/room-default.jpg'),
            ('201', 'Семейный', 3500, 4, 'Идеальный вариант для семьи', '/static/images/room-default.jpg')
        ''')
        print("✅ Тестовые комнаты добавлены")
    
    cursor.execute("SELECT COUNT(*) FROM admin_users WHERE username = 'admin'")
    if cursor.fetchone()[0] == 0:
        import hashlib
        password_hash = hashlib.sha256("admin123".encode()).hexdigest()
        cursor.execute(
            "INSERT INTO admin_users (username, password_hash) VALUES (?, ?)",
            ('admin', password_hash)
        )
        print("✅ Администратор создан: admin / admin123")
    
    conn.commit()
    conn.close()
    print("✅ База данных инициализирована")


init_db()


def get_db_connection():
    conn = sqlite3.connect('hotel.db')
    conn.row_factory = sqlite3.Row
    return conn


def hash_password(password: str) -> str:
    import hashlib
    return hashlib.sha256(password.encode()).hexdigest()


def verify_admin_login(username: str, password: str):
    conn = get_db_connection()
    admin = conn.execute(
        "SELECT * FROM admin_users WHERE username = ?", 
        (username,)
    ).fetchone()
    conn.close()
    
    if admin and admin['password_hash'] == hash_password(password):
        return admin
    return None


def get_current_admin(credentials: HTTPBasicCredentials = Depends(security)):
    admin = verify_admin_login(credentials.username, credentials.password)
    if not admin:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверные учетные данные",
            headers={"WWW-Authenticate": "Basic"},
        )
    return admin


def get_booking_by_id(booking_id: int) -> Optional[Dict[str, Any]]:
    try:
        conn = get_db_connection()
        booking = conn.execute('''
            SELECT b.*, r.type as room_type, r.number as room_number, r.price as room_price
            FROM bookings b 
            JOIN rooms r ON b.room_id = r.id 
            WHERE b.id = ?
        ''', (booking_id,)).fetchone()
        conn.close()
        
        if booking:
            booking_dict = dict(booking)
            if (isinstance(booking_dict.get('check_in'), str) and 
                isinstance(booking_dict.get('check_out'), str)):
                try:
                    check_in = datetime.fromisoformat(booking_dict['check_in'])
                    check_out = datetime.fromisoformat(booking_dict['check_out'])
                    booking_dict['nights'] = (check_out - check_in).days
                except:
                    booking_dict['nights'] = 1
            return booking_dict
        return None
    except Exception as e:
        print(f"Ошибка при получении бронирования: {e}")
        return None


def get_available_rooms(check_in: str = None, check_out: str = None):
    conn = get_db_connection()
    
    if check_in and check_out:
        available_rooms = conn.execute('''
            SELECT r.* FROM rooms r
            WHERE r.is_available = 1 
            AND r.id NOT IN (
                SELECT b.room_id FROM bookings b 
                WHERE b.status = 'confirmed'
                AND ((b.check_in < ? AND b.check_out > ?) OR (b.check_in < ? AND b.check_out > ?))
            )
        ''', (check_out, check_in, check_in, check_out)).fetchall()
    else:
        available_rooms = conn.execute('SELECT * FROM rooms WHERE is_available = 1').fetchall()
    
    conn.close()
    return [dict(room) for room in available_rooms]


def get_user_bookings(email: str):
    conn = get_db_connection()
    try:
        bookings = conn.execute('''
            SELECT b.*, r.number as room_number, r.type as room_type 
            FROM bookings b 
            JOIN rooms r ON b.room_id = r.id 
            WHERE b.guest_email = ? AND b.status = 'confirmed'
            ORDER BY b.check_in DESC
        ''', (email,)).fetchall()
        
        bookings_list = []
        for booking in bookings:
            booking_dict = dict(booking)
            for key in ['check_in', 'check_out', 'created_at']:
                if booking_dict.get(key) and isinstance(booking_dict[key], (date, datetime)):
                    booking_dict[key] = booking_dict[key].isoformat()
            bookings_list.append(booking_dict)
        return bookings_list
    except Exception as e:
        print(f"❌ Ошибка при получении бронирований: {e}")
        return []
    finally:
        conn.close()


def cancel_booking(booking_id: int, email: str, lang: str = 'tg'):
    conn = get_db_connection()
    
    try:
        booking = conn.execute('''
            SELECT * FROM bookings WHERE id = ? AND guest_email = ? AND status = 'confirmed'
        ''', (booking_id, email)).fetchone()
        
        if not booking:
            conn.close()
            msgs = {
                'tg': "Брон ёфт нашуд ё аллакай бекор шудааст",
                'ru': "Бронирование не найдено или уже отменено",
                'en': "Booking not found or already cancelled"
            }
            return False, msgs.get(lang, msgs['tg'])
        
        full_booking = conn.execute('''
            SELECT b.*, r.number as room_number, r.type as room_type 
            FROM bookings b 
            JOIN rooms r ON b.room_id = r.id 
            WHERE b.id = ?
        ''', (booking_id,)).fetchone()
        
        conn.execute('UPDATE bookings SET status = "cancelled" WHERE id = ?', (booking_id,))
        conn.commit()
        
        if full_booking:
            booking_dict = dict(full_booking)
            for key in ['check_in', 'check_out', 'created_at']:
                if booking_dict.get(key) and isinstance(booking_dict[key], (date, datetime)):
                    booking_dict[key] = booking_dict[key].isoformat()
            
            if 'check_in' in booking_dict and 'check_out' in booking_dict:
                try:
                    check_in = datetime.fromisoformat(booking_dict['check_in'])
                    check_out = datetime.fromisoformat(booking_dict['check_out'])
                    booking_dict['nights'] = (check_out - check_in).days
                except:
                    booking_dict['nights'] = 1
            
            cancellation_html = create_cancellation_email_html(booking_dict, lang)
            send_email(email, "Брон бекор карда шуд" if lang == 'tg' else ("Бронирование отменено" if lang == 'ru' else "Booking Cancelled"), cancellation_html)
        
        msgs = {
            'tg': f"Брони #{booking_id} бо муваффақият бекор карда шуд",
            'ru': f"Бронирование #{booking_id} успешно отменено",
            'en': f"Booking #{booking_id} successfully cancelled"
        }
        return True, msgs.get(lang, msgs['tg'])
    except Exception as e:
        conn.rollback()
        return False, f"Хато: {str(e)}"
    finally:
        conn.close()


def create_booking_via_ai(room_id: int, guest_data: dict, lang: str = 'tg'):
    conn = get_db_connection()
    
    room = conn.execute('SELECT * FROM rooms WHERE id = ?', (room_id,)).fetchone()
    if not room:
        conn.close()
        msgs = {'tg': "Ҳуҷра ёфт нашуд", 'ru': "Номер не найден", 'en': "Room not found"}
        return False, msgs.get(lang, msgs['tg'])
    
    conflicting = conn.execute('''
        SELECT * FROM bookings 
        WHERE room_id = ? AND status = 'confirmed'
        AND ((check_in < ? AND check_out > ?) OR (check_in < ? AND check_out > ?))
    ''', (room_id, guest_data['check_out'], guest_data['check_in'], 
          guest_data['check_in'], guest_data['check_out'])).fetchone()
    
    if conflicting:
        conn.close()
        msgs = {'tg': "Ҳуҷра аллакай брон шудааст", 'ru': "Номер уже забронирован", 'en': "Room already booked"}
        return False, msgs.get(lang, msgs['tg'])
    
    check_in_date = date.fromisoformat(guest_data['check_in'])
    check_out_date = date.fromisoformat(guest_data['check_out'])
    nights = (check_out_date - check_in_date).days
    total_price = room['price'] * nights
    
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO bookings (room_id, guest_name, guest_email, guest_phone, check_in, check_out, total_price)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (room_id, guest_data['guest_name'], guest_data['guest_email'], 
          guest_data['guest_phone'], guest_data['check_in'], 
          guest_data['check_out'], total_price))
    
    booking_id = cursor.lastrowid
    
    new_booking = conn.execute('''
        SELECT b.*, r.number as room_number, r.type as room_type 
        FROM bookings b 
        JOIN rooms r ON b.room_id = r.id 
        WHERE b.id = ?
    ''', (booking_id,)).fetchone()
    
    conn.commit()
    conn.close()
    
    if new_booking:
        booking_dict = dict(new_booking)
        for key in ['check_in', 'check_out', 'created_at']:
            if booking_dict.get(key) and isinstance(booking_dict[key], (date, datetime)):
                booking_dict[key] = booking_dict[key].isoformat()
        booking_dict['nights'] = nights
        
        email_html = create_booking_email_html(booking_dict, lang)
        send_email(guest_data['guest_email'], 
                   "Брон таҳия шуд" if lang == 'tg' else ("Бронирование подтверждено" if lang == 'ru' else "Booking Confirmed"),
                   email_html)
    
    return True, booking_id


# ==================== УМНЫЙ AI АССИСТЕНТ ====================

def smart_ai_assistant(user_message: str, user_email: str = None):
    """Умный ассистент с определением языка - ОТВЕЧАЕТ НА ЛЮБЫЕ ВОПРОСЫ"""
    
    lang = detect_language(user_message)
    user_message_lower = user_message.lower()
    
    print(f"🔍 Определён язык: {lang} для сообщения: {user_message[:50]}")
    
    def check_command(words_list, text):
        for word in words_list:
            if word in text:
                return True
        return False
    
    # СВОБОДНЫЕ НОМЕРА
    if check_command(['озод', 'дастрас', 'холӣ', 'свободен', 'available', 'free'], user_message_lower):
        available_rooms = get_available_rooms()
        
        if lang == 'tg':
            if not available_rooms:
                return {"type": "response", "message": "Мутаассифона, ҳамаи ҳуҷраҳо ҳозир ишғол шудаанд. 🏨 Санаҳои дигарро санҷед!", "action": None}
            rooms_list = "\n".join([f"• {room['number']} - {room['type']} ({room['price']} сом./шаб)" for room in available_rooms])
            return {"type": "response", "message": f"🎉 **Ҳуҷраҳои озод:**\n{rooms_list}\n\nҲуҷраи муайянро брон кардан мехоҳед?", "action": "show_rooms"}
        
        elif lang == 'ru':
            if not available_rooms:
                return {"type": "response", "message": "К сожалению, все номера сейчас заняты. 🏨 Попробуйте другие даты!", "action": None}
            rooms_list = "\n".join([f"• {room['number']} - {room['type']} ({room['price']} сом./ночь)" for room in available_rooms])
            return {"type": "response", "message": f"🎉 **Свободные номера:**\n{rooms_list}\n\nХотите забронировать конкретный номер?", "action": "show_rooms"}
        
        else:
            if not available_rooms:
                return {"type": "response", "message": "Unfortunately, all rooms are currently occupied. 🏨 Try other dates!", "action": None}
            rooms_list = "\n".join([f"• {room['number']} - {room['type']} ({room['price']} som./night)" for room in available_rooms])
            return {"type": "response", "message": f"🎉 **Available rooms:**\n{rooms_list}\n\nWould you like to book a specific room?", "action": "show_rooms"}
    
    # МОИ БРОНИРОВАНИЯ
    elif check_command(['брониҳои ман', 'фармоишҳои ман', 'мои брони', 'my bookings'], user_message_lower) and user_email:
        bookings = get_user_bookings(user_email)
        
        if lang == 'tg':
            if not bookings:
                return {"type": "response", "message": "Шумо бронҳои фаъол надоред. 🎯 Мехоҳед ҳуҷра брон кунед?", "action": "show_rooms"}
            bookings_list = "\n".join([f"• #{b['id']}: {b['room_number']} ({b['room_type']}) - {b['check_in']} → {b['check_out']}" for b in bookings])
            return {"type": "response", "message": f"📋 **Брониҳои шумо:**\n{bookings_list}\n\nБарои бекор кардан бронро интихоб кунед:", "action": "show_cancel_buttons", "bookings": bookings}
        
        elif lang == 'ru':
            if not bookings:
                return {"type": "response", "message": "У вас нет активных бронирований. 🎯 Хотите забронировать номер?", "action": "show_rooms"}
            bookings_list = "\n".join([f"• #{b['id']}: {b['room_number']} ({b['room_type']}) - {b['check_in']} → {b['check_out']}" for b in bookings])
            return {"type": "response", "message": f"📋 **Ваши бронирования:**\n{bookings_list}\n\nВыберите бронь для отмены:", "action": "show_cancel_buttons", "bookings": bookings}
        
        else:
            if not bookings:
                return {"type": "response", "message": "You have no active bookings. 🎯 Would you like to book a room?", "action": "show_rooms"}
            bookings_list = "\n".join([f"• #{b['id']}: {b['room_number']} ({b['room_type']}) - {b['check_in']} → {b['check_out']}" for b in bookings])
            return {"type": "response", "message": f"📋 **Your bookings:**\n{bookings_list}\n\nSelect a booking to cancel:", "action": "show_cancel_buttons", "bookings": bookings}
    
    # ОТМЕНА БРОНИРОВАНИЯ
    elif check_command(['бекор', 'нест кардан', 'отмена', 'отменить', 'cancel'], user_message_lower) and user_email:
        bookings = get_user_bookings(user_email)
        
        if not bookings:
            if lang == 'tg':
                return {"type": "response", "message": "❌ Шумо бронҳои фаъол барои бекор кардан надоред.", "action": None}
            elif lang == 'ru':
                return {"type": "response", "message": "❌ У вас нет активных бронирований для отмены.", "action": None}
            else:
                return {"type": "response", "message": "❌ You have no active bookings to cancel.", "action": None}
        
        if lang == 'tg':
            bookings_list = "\n".join([f"• #{b['id']}: {b['room_number']} ({b['room_type']}) - {b['check_in']} → {b['check_out']}" for b in bookings])
            return {"type": "response", "message": f"📋 **Брониҳои шумо:**\n{bookings_list}\n\nБарои бекор кардан бронро интихоб кунед:", "action": "show_cancel_buttons", "bookings": bookings}
        elif lang == 'ru':
            bookings_list = "\n".join([f"• #{b['id']}: {b['room_number']} ({b['room_type']}) - {b['check_in']} → {b['check_out']}" for b in bookings])
            return {"type": "response", "message": f"📋 **Ваши бронирования:**\n{bookings_list}\n\nВыберите бронь для отмены:", "action": "show_cancel_buttons", "bookings": bookings}
        else:
            bookings_list = "\n".join([f"• #{b['id']}: {b['room_number']} ({b['room_type']}) - {b['check_in']} → {b['check_out']}" for b in bookings])
            return {"type": "response", "message": f"📋 **Your bookings:**\n{bookings_list}\n\nSelect a booking to cancel:", "action": "show_cancel_buttons", "bookings": bookings}
    
    # БРОНИРОВАНИЕ НОМЕРА
    elif check_command(['брон', 'гирифтан', 'мехоҳам', 'забронировать', 'хочу', 'book', 'want'], user_message_lower):
        room_match = re.search(r'(\d+)', user_message_lower)
        
        if room_match:
            room_number = room_match.group(1)
            conn = get_db_connection()
            room = conn.execute('SELECT * FROM rooms WHERE number = ?', (room_number,)).fetchone()
            conn.close()
            
            if room:
                if lang == 'tg':
                    return {"type": "redirect", "message": f"🎯 Аъло! Ба саҳифаи брони ҳуҷраи {room_number} меравам...", "url": f"/booking/{room['id']}", "action": "redirect_booking"}
                elif lang == 'ru':
                    return {"type": "redirect", "message": f"🎯 Отлично! Перехожу на страницу бронирования номера {room_number}...", "url": f"/booking/{room['id']}", "action": "redirect_booking"}
                else:
                    return {"type": "redirect", "message": f"🎯 Great! Taking you to booking page for room {room_number}...", "url": f"/booking/{room['id']}", "action": "redirect_booking"}
            else:
                if lang == 'tg':
                    return {"type": "response", "message": f"❌ Ҳуҷраи {room_number} ёфт нашуд. Рӯйхати ҳуҷраҳои дастрасро бубинед!", "action": "show_rooms"}
                elif lang == 'ru':
                    return {"type": "response", "message": f"❌ Номер {room_number} не найден. Посмотрите список доступных номеров!", "action": "show_rooms"}
                else:
                    return {"type": "response", "message": f"❌ Room {room_number} not found. Check the list of available rooms!", "action": "show_rooms"}
        else:
            if lang == 'tg':
                return {"type": "response", "message": "🎯 Мехоҳед ҳуҷра брон кунед? Рақами ҳуҷраро муайян кунед (масалан: 'ҳуҷраи 101-ро брон кунед') ё ҳуҷраҳои дастрасро бубинед!", "action": "show_rooms"}
            elif lang == 'ru':
                return {"type": "response", "message": "🎯 Хотите забронировать номер? Укажите номер комнаты (например: 'забронируйте номер 101') или посмотрите доступные номера!", "action": "show_rooms"}
            else:
                return {"type": "response", "message": "🎯 Want to book a room? Specify the room number (e.g., 'book room 101') or check available rooms!", "action": "show_rooms"}
    
    # ДОСТОПРИМЕЧАТЕЛЬНОСТИ
    elif check_command(['ҷойҳои диданибобӣ', 'тамошобоб', 'достопримечательности', 'attractions'], user_message_lower):
        if lang == 'tg':
            return {"type": "response", "message": "🏛️ **Ҷойҳои диданибобӣ дар наздикии Хуҷанд:**\n\n📌 **Қалъаи Хуҷанд** - қалъаи қадим дар соҳили Сирдарё\n📌 **Майдони Панҷшанбе** - бозори марказӣ\n📌 **Ҳайкали Камоли Хуҷандӣ** - шоири бузург\n📌 **Осорхонаи таърихӣ** - таърихи бойи минтақа\n\n✨ Масофа: 5-15 дақиқа бо мошин", "action": None}
        elif lang == 'ru':
            return {"type": "response", "message": "🏛️ **Достопримечательности рядом с Худжандом:**\n\n📌 **Худжандская крепость** - древняя крепость\n📌 **Площадь Панджшанбе** - центральный рынок\n📌 **Памятник Камолу Худжанди** - великому поэту\n📌 **Исторический музей** - богатая история\n\n✨ Расстояние: 5-15 минут на машине", "action": None}
        else:
            return {"type": "response", "message": "🏛️ **Attractions near Khujand:**\n\n📌 **Khujand Fortress** - ancient fortress\n📌 **Panjshanbe Square** - central market\n📌 **Kamol Khujandi Monument** - great poet\n📌 **Historical Museum** - rich history\n\n✨ Distance: 5-15 minutes by car", "action": None}
    
    # РЕСТОРАНЫ
    elif check_command(['ошхона', 'ресторан', 'кафе', 'restaurant', 'cafe', 'еда'], user_message_lower):
        if lang == 'tg':
            return {"type": "response", "message": "🍽️ **Ресторанҳо ва кафеҳои наздик:**\n\n🥘 **«Хуҷанд»** - таомҳои миллӣ\n🍕 **«Аврупо»** - таомҳои аврупоӣ\n🍜 **«Ошхона Марказ»** - хӯрокҳои арзон (аз 30 сом.)\n☕ **«Bon»** - қаҳва, ширинӣ\n\n📞 Мо дар брон кардани ҷой кӯмак мекунем", "action": None}
        elif lang == 'ru':
            return {"type": "response", "message": "🍽️ **Рестораны и кафе рядом:**\n\n🥘 **«Худжанд»** - национальная кухня\n🍕 **«Европа»** - европейская кухня\n🍜 **«Ошхона Марказ»** - доступные обеды (от 30 сом.)\n☕ **«Bon»** - кофе, десерты\n\n📞 Поможем с бронированием столика", "action": None}
        else:
            return {"type": "response", "message": "🍽️ **Nearby restaurants and cafes:**\n\n🥘 **'Khujand'** - national cuisine\n🍕 **'Europe'** - European cuisine\n🍜 **'Oshkhona Markaz'** - affordable lunches (from 30 som.)\n☕ **'Bon'** - coffee, desserts\n\n📞 We can help with table reservation", "action": None}
    
    # КАК ДОБРАТЬСЯ
    elif check_command(['расидан', 'роҳ', 'добраться', 'how to get', 'get'], user_message_lower):
        if lang == 'tg':
            return {"type": "response", "message": "🚗 **Чӣ гуна расидан:**\n\n✈️ **Аз фурудгоҳ (15 км):** таксӣ 60-80 сом., 20-30 дақ.\n🚆 **Аз вокзали роҳи оҳан (8 км):** таксӣ 40-50 сом., 15 дақ.\n🚌 **Аз вокзали авто (5 км):** таксӣ 30 сом., 10 дақ.\n📍 **Суроғаи мо:** шаҳри Хуҷанд, кӯчаи Раҳим Ҷалил, 24\n📞 **Трансфер:** +992 88 999 30 90", "action": None}
        elif lang == 'ru':
            return {"type": "response", "message": "🚗 **Как добраться:**\n\n✈️ **Из аэропорта (15 км):** такси 60-80 сом., 20-30 мин\n🚆 **С ж/д вокзала (8 км):** такси 40-50 сом., 15 мин\n🚌 **С автовокзала (5 км):** такси 30 сом., 10 мин\n📍 **Наш адрес:** г. Худжанд, ул. Рахим Джалила, 24\n📞 **Трансфер:** +992 88 999 30 90", "action": None}
        else:
            return {"type": "response", "message": "🚗 **How to get:**\n\n✈️ **From Airport (15 km):** taxi 60-80 som., 20-30 min\n🚆 **From Railway Station (8 km):** taxi 40-50 som., 15 min\n🚌 **From Bus Station (5 km):** taxi 30 som., 10 min\n📍 **Address:** Khujand, Rahim Jalil street, 24\n📞 **Transfer:** +992 88 999 30 90", "action": None}
    
    # КОНТАКТЫ/ТАМОС
    elif check_command(['тамос', 'контакт', 'contact', 'связь'], user_message_lower):
        if lang == 'tg':
            return {"type": "response", "message": "📞 **Тамос бо мо:**\n\n📍 Суроға: шаҳри Хуҷанд, кӯчаи Раҳим Ҷалил, 24\n📞 Телефон: +992 88 999 30 90\n✉️ Email: info@sugdhotel.com\n🕒 Соатҳои корӣ: Шабонарӯзӣ, 365 рӯз дар як сол", "action": None}
        elif lang == 'ru':
            return {"type": "response", "message": "📞 **Свяжитесь с нами:**\n\n📍 Адрес: г. Худжанд, ул. Рахим Джалил, 24\n📞 Телефон: +992 88 999 30 90\n✉️ Email: info@sugdhotel.com\n🕒 Режим работы: Круглосуточно, 365 дней в году", "action": None}
        else:
            return {"type": "response", "message": "📞 **Contact us:**\n\n📍 Address: Khujand, Rahim Jalil street, 24\n📞 Phone: +992 88 999 30 90\n✉️ Email: info@sugdhotel.com\n🕒 Working hours: 24/7, 365 days a year", "action": None}
    
    # НАРХҲО/ЦЕНЫ/PRICES
    elif check_command(['нарх', 'price', 'цена'], user_message_lower):
        if lang == 'tg':
            return {"type": "response", "message": "💰 **Нархҳои ҳуҷраҳо:**\n\n• Стандарт: 250 сом. / шаб\n• Люкс: 450 сом. / шаб\n• Оилавӣ: 350 сом. / шаб\n\n💎 Ҳамаи нархҳо бо андоз ва хизматрасонии меҳмонхона дохил мебошанд.", "action": None}
        elif lang == 'ru':
            return {"type": "response", "message": "💰 **Цены на номера:**\n\n• Стандарт: 250 сом. / ночь\n• Люкс: 450 сом. / ночь\n• Семейный: 350 сом. / ночь\n\n💎 Все цены указаны с учетом налогов и обслуживания.", "action": None}
        else:
            return {"type": "response", "message": "💰 **Room prices:**\n\n• Standard: 250 сом. / night\n• Lux: 450 сом. / night\n• Family: 350 сом. / night\n\n💎 All prices include taxes and hotel service.", "action": None}
    
    # ХИЗМАТРАСОНӢ/УСЛУГИ/SERVICES
    elif check_command(['хизмат', 'услуг', 'service'], user_message_lower):
        if lang == 'tg':
            return {"type": "response", "message": "🎁 **Хизматрасониҳои мо:**\n\n• Тарабхона (7:00 - 23:00)\n• Ҳавзи шиноварӣ\n• Маркази SPA ва Wellness\n• Фитнес марказ (шабонарӯзӣ)\n• Маркази тиҷоратӣ\n• Wi-Fi баландсуръат\n• Истгоҳи мошин (ройгон)\n• Хизматрасонии ҳуҷра (24/7)", "action": None}
        elif lang == 'ru':
            return {"type": "response", "message": "🎁 **Наши услуги:**\n\n• Ресторан (7:00 - 23:00)\n• Бассейн\n• SPA и Wellness центр\n• Фитнес центр (круглосуточно)\n• Бизнес центр\n• Высокоскоростной Wi-Fi\n• Парковка (бесплатно)\n• Обслуживание номеров (24/7)", "action": None}
        else:
            return {"type": "response", "message": "🎁 **Our services:**\n\n• Restaurant (7:00 - 23:00)\n• Swimming pool\n• SPA & Wellness center\n• Fitness center (24/7)\n• Business center\n• High-speed Wi-Fi\n• Free parking\n• Room service (24/7)", "action": None}
    
    # ЛЮБЫЕ ДРУГИЕ ВОПРОСЫ - DEEPSEEK
    else:
        system_prompt = get_language_system_prompt(lang)
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ]
        
        ai_response = call_deepseek_api(messages, max_tokens=500)
        
        return {"type": "response", "message": ai_response, "action": None}


# ==================== WEBSOCKET ====================

@app.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    await websocket.accept()
    print("✅ WebSocket подключен для AI-чата")
    
    user_email = None
    
    try:
        while True:
            data = await websocket.receive_text()
            message_data = json.loads(data)
            user_message = message_data.get("message", "")
            
            if "email" in message_data:
                user_email = message_data["email"]
            
            requested_lang = message_data.get("language", detect_language(user_message))
            print(f"👤 Сообщение: {user_message} | Язык: {requested_lang}")
            
            await websocket.send_text(json.dumps({"type": "typing", "status": True}))
            await asyncio.sleep(0.5)
            
            ai_response = smart_ai_assistant(user_message, user_email)
            
            await websocket.send_text(json.dumps({"type": "typing", "status": False}))
            
            response_data = {
                "type": ai_response["type"],
                "message": ai_response["message"],
                "action": ai_response.get("action")
            }
            
            if "bookings" in ai_response:
                bookings_data = []
                for booking in ai_response["bookings"]:
                    if hasattr(booking, '_asdict'):
                        booking_dict = booking._asdict()
                    else:
                        booking_dict = dict(booking)
                    for key, value in booking_dict.items():
                        if isinstance(value, (date, datetime)):
                            booking_dict[key] = value.isoformat()
                    bookings_data.append(booking_dict)
                response_data["bookings"] = bookings_data
            
            if "url" in ai_response:
                response_data["url"] = ai_response["url"]
            
            await websocket.send_text(json.dumps(response_data))
            print(f"🤖 Ответ отправлен на языке: {requested_lang}")
                
    except Exception as e:
        print(f"❌ WebSocket ошибка: {e}")
    finally:
        print("🔌 WebSocket отключен")


# ==================== API ====================

# Роут для скачивания APK файла
@app.get("/download-app")
async def download_app():
    """Роут для скачивания APK файла"""
    file_path = "static/apk/app-release.apk"
    
    # Проверяем существует ли файл
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Файл не найден")
    
    # Возвращаем файл для скачивания
    return FileResponse(
        path=file_path,
        filename="SUGDDELUXE.apk",  # Имя файла при скачивании
        media_type="application/vnd.android.package-archive",  # MIME тип для APK
        headers={
            "Content-Disposition": "attachment; filename=SUGDDELUXE.apk",
            "Content-Type": "application/vnd.android.package-archive"
        }
    )

# Альтернативный роут с параметром версии
@app.get("/download-app/{version}")
async def download_app_version(version: str):
    """Скачивание конкретной версии приложения"""
    file_path = f"static/apk/app-{version}.apk"
    
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"Версия {version} не найдена")
    
    return FileResponse(
        path=file_path,
        filename=f"SUGDDELUXE_{version}.apk",
        media_type="application/vnd.android.package-archive"
    )

# Роут для получения информации о версии
@app.get("/app-info")
async def app_info():
    """Получение информации о приложении"""
    file_path = "static/apk/app-release.apk"
    
    if os.path.exists(file_path):
        file_size = os.path.getsize(file_path)
        # Переводим размер в МБ
        size_mb = round(file_size / (1024 * 1024), 2)
        
        return {
            "version": "1.0.0",
            "size": size_mb,
            "size_bytes": file_size,
            "filename": "SUGDDELUXE.apk",
            "update_date": os.path.getmtime(file_path)
        }
    else:
        return {"error": "Файл не найден"}

@app.post("/api/cancel-booking")
async def api_cancel_booking(
    booking_id: int = Form(...),
    email: str = Form(...),
    lang: str = Form('tg')
):
    success, message = cancel_booking(booking_id, email, lang)
    if success:
        return {"status": "success", "message": message}
    else:
        raise HTTPException(status_code=400, detail=message)


@app.get("/api/user-bookings/{email}")
async def api_get_user_bookings(email: str):
    bookings = get_user_bookings(email)
    return {"status": "success", "bookings": bookings}


# ==================== ОСНОВНЫЕ МАРШРУТЫ ====================

def get_template_with_lang(template_name: str, lang: str):
    if lang == 'ru':
        return template_name.replace('.html', '_ru.html')
    elif lang == 'en':
        return template_name.replace('.html', '_en.html')
    else:
        return template_name


@app.get("/", response_class=HTMLResponse)
async def home(request: Request, lang: str = 'tg'):
    # Вызываем функцию для завершения просроченных бронирований
    complete_expired_bookings()
    
    conn = get_db_connection()
    rooms = conn.execute('SELECT * FROM rooms WHERE is_available = 1 LIMIT 3').fetchall()
    conn.close()
    
    template_name = get_template_with_lang("index.html", lang)
    return templates.TemplateResponse(template_name, {"request": request, "rooms": rooms, "current_lang": lang})


@app.get("/rooms", response_class=HTMLResponse)
async def rooms_page(request: Request, lang: str = 'tg'):
    # Вызываем функцию для завершения просроченных бронирований
    complete_expired_bookings()
    
    conn = get_db_connection()
    rooms = conn.execute('SELECT * FROM rooms').fetchall()
    
    rooms_with_status = []
    for room in rooms:
        # Проверяем ТОЛЬКО активные бронирования (с учётом дат)
        bookings = conn.execute('''
            SELECT * FROM bookings 
            WHERE room_id = ? AND status = 'confirmed'
            AND check_in <= date('now') AND check_out > date('now')
        ''', (room['id'],)).fetchall()
        
        is_occupied = len(bookings) > 0
        rooms_with_status.append({
            'room': room,
            'is_occupied': is_occupied
        })
    
    conn.close()
    
    template_name = get_template_with_lang("rooms.html", lang)
    return templates.TemplateResponse(template_name, {
        "request": request, 
        "rooms_with_occupancy": rooms_with_status,
        "current_lang": lang
    })


@app.get("/about", response_class=HTMLResponse)
async def about_page(request: Request, lang: str = 'tg'):
    template_name = get_template_with_lang("about.html", lang)
    return templates.TemplateResponse(template_name, {"request": request, "current_lang": lang})


@app.get("/booking/{room_id}", response_class=HTMLResponse)
async def booking_page(request: Request, room_id: int, lang: str = 'tg'):
    # Вызываем функцию для завершения просроченных бронирований
    complete_expired_bookings()
    
    conn = get_db_connection()
    room = conn.execute('SELECT * FROM rooms WHERE id = ?', (room_id,)).fetchone()
    
    # Получаем занятые даты (только активные бронирования)
    occupied_dates = conn.execute('''
        SELECT check_in, check_out FROM bookings 
        WHERE room_id = ? AND status = 'confirmed'
        AND check_out > date('now')
        ORDER BY check_in ASC
    ''', (room_id,)).fetchall()
    
    conn.close()
    
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    
    occupied_list = []
    for booking in occupied_dates:
        occupied_list.append({
            'check_in': booking['check_in'],
            'check_out': booking['check_out']
        })
    
    template_name = get_template_with_lang("booking.html", lang)
    return templates.TemplateResponse(template_name, {
        "request": request, 
        "room": room, 
        "current_lang": lang,
        "occupied_dates": occupied_list
    })


@app.post("/book")
async def create_booking(
    room_id: int = Form(...),
    guest_name: str = Form(...),
    guest_email: str = Form(...),
    guest_phone: str = Form(...),
    check_in: str = Form(...),
    check_out: str = Form(...),
    lang: str = Form('tg')
):
    conn = get_db_connection()
    
    room = conn.execute('SELECT * FROM rooms WHERE id = ?', (room_id,)).fetchone()
    if not room:
        conn.close()
        raise HTTPException(status_code=404, detail="Room not found")
    
    conflicting_bookings = conn.execute('''
        SELECT * FROM bookings 
        WHERE room_id = ? AND status = "confirmed"
        AND ((check_in < ? AND check_out > ?) OR (check_in < ? AND check_out > ?))
    ''', (room_id, check_out, check_in, check_in, check_out)).fetchone()
    
    if conflicting_bookings:
        conn.close()
        raise HTTPException(status_code=400, detail="Комната уже забронирована на эти даты")
    
    check_in_date = date.fromisoformat(check_in)
    check_out_date = date.fromisoformat(check_out)
    nights = (check_out_date - check_in_date).days
    total_price = room['price'] * nights
    
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO bookings (room_id, guest_name, guest_email, guest_phone, check_in, check_out, total_price)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (room_id, guest_name, guest_email, guest_phone, check_in, check_out, total_price))
    
    booking_id = cursor.lastrowid
    
    new_booking = conn.execute('''
        SELECT b.*, r.number as room_number, r.type as room_type 
        FROM bookings b 
        JOIN rooms r ON b.room_id = r.id 
        WHERE b.id = ?
    ''', (booking_id,)).fetchone()
    
    conn.commit()
    conn.close()
    
    if new_booking:
        booking_dict = dict(new_booking)
        for key in ['check_in', 'check_out', 'created_at']:
            if booking_dict.get(key) and isinstance(booking_dict[key], (date, datetime)):
                booking_dict[key] = booking_dict[key].isoformat()
        
        booking_dict['nights'] = nights
        
        email_html = create_booking_email_html(booking_dict, lang)
        send_email(guest_email, 
                   "Брон таҳия шуд" if lang == 'tg' else ("Бронирование подтверждено" if lang == 'ru' else "Booking Confirmed"),
                   email_html)
    
    redirect_url = f"/booking-success/{booking_id}?lang={lang}"
    return RedirectResponse(url=redirect_url, status_code=303)


@app.get("/booking-success/{booking_id}", response_class=HTMLResponse)
async def booking_success(request: Request, booking_id: int, lang: str = 'tg'):
    booking = get_booking_by_id(booking_id)
    if not booking:
        raise HTTPException(status_code=404, detail="Бронирование не найдено")
    template_name = get_template_with_lang("booking_success.html", lang)
    return templates.TemplateResponse(template_name, {"request": request, "booking": booking, "current_lang": lang})


# ==================== JSON API ====================

@app.get("/api/rooms")
async def api_get_rooms():
    conn = get_db_connection()
    try:
        rooms = conn.execute('SELECT * FROM rooms WHERE is_available = 1').fetchall()
        conn.close()
        rooms_list = []
        for room in rooms:
            room_dict = dict(room)
            for key, value in room_dict.items():
                if isinstance(value, (date, datetime)):
                    room_dict[key] = value.isoformat()
            rooms_list.append(room_dict)
        return {"status": "success", "rooms": rooms_list}
    except Exception as e:
        conn.close()
        return {"status": "error", "message": str(e)}


@app.get("/api/rooms/{room_id}")
async def api_get_room(room_id: int):
    conn = get_db_connection()
    try:
        room = conn.execute('SELECT * FROM rooms WHERE id = ?', (room_id,)).fetchone()
        conn.close()
        if not room:
            raise HTTPException(status_code=404, detail="Room not found")
        room_dict = dict(room)
        for key, value in room_dict.items():
            if isinstance(value, (date, datetime)):
                room_dict[key] = value.isoformat()
        return {"status": "success", "room": room_dict}
    except Exception as e:
        conn.close()
        return {"status": "error", "message": str(e)}


@app.post("/api/book")
async def api_create_booking(
    room_id: int = Form(...),
    guest_name: str = Form(...),
    guest_email: str = Form(...),
    guest_phone: str = Form(...),
    check_in: str = Form(...),
    check_out: str = Form(...),
    lang: str = Form('tg')
):
    conn = get_db_connection()
    
    try:
        room = conn.execute('SELECT * FROM rooms WHERE id = ?', (room_id,)).fetchone()
        if not room:
            conn.close()
            return {"status": "error", "message": "Room not found"}
        
        conflicting_bookings = conn.execute('''
            SELECT * FROM bookings 
            WHERE room_id = ? AND status = "confirmed"
            AND ((check_in < ? AND check_out > ?) OR (check_in < ? AND check_out > ?))
        ''', (room_id, check_out, check_in, check_in, check_out)).fetchone()
        
        if conflicting_bookings:
            conn.close()
            return {"status": "error", "message": "Комната уже забронирована на эти даты"}
        
        check_in_date = date.fromisoformat(check_in)
        check_out_date = date.fromisoformat(check_out)
        nights = (check_out_date - check_in_date).days
        total_price = room['price'] * nights
        
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO bookings (room_id, guest_name, guest_email, guest_phone, check_in, check_out, total_price)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (room_id, guest_name, guest_email, guest_phone, check_in, check_out, total_price))
        
        booking_id = cursor.lastrowid
        
        new_booking = conn.execute('''
            SELECT b.*, r.number as room_number, r.type as room_type 
            FROM bookings b 
            JOIN rooms r ON b.room_id = r.id 
            WHERE b.id = ?
        ''', (booking_id,)).fetchone()
        
        conn.commit()
        conn.close()
        
        if new_booking:
            booking_dict = dict(new_booking)
            for key in ['check_in', 'check_out', 'created_at']:
                if booking_dict.get(key) and isinstance(booking_dict[key], (date, datetime)):
                    booking_dict[key] = booking_dict[key].isoformat()
            
            booking_dict['nights'] = nights
            
            email_html = create_booking_email_html(booking_dict, lang)
            send_email(guest_email,
                       "Брон таҳия шуд" if lang == 'tg' else ("Бронирование подтверждено" if lang == 'ru' else "Booking Confirmed"),
                       email_html)
        
        return {"status": "success", "booking_id": booking_id, "message": "Бронирование успешно создано", "lang": lang}
        
    except Exception as e:
        conn.rollback()
        conn.close()
        return {"status": "error", "message": f"Ошибка: {str(e)}"}


# ==================== АДМИНСКИЕ МАРШРУТЫ ====================

@app.get("/admin/login", response_class=HTMLResponse)
async def admin_login_page(request: Request):
    return templates.TemplateResponse("admin_login.html", {"request": request})


@app.post("/admin/login")
async def admin_login(
    username: str = Form(...),
    password: str = Form(...)
):
    admin = verify_admin_login(username, password)
    if admin:
        return RedirectResponse(url="/admin", status_code=303)
    else:
        raise HTTPException(status_code=401, detail="Неверные учетные данные")


@app.get("/admin", response_class=HTMLResponse)
async def admin_dashboard(request: Request, admin: dict = Depends(get_current_admin)):
    complete_expired_bookings()
    
    stats = get_admin_stats()
    recent_bookings = get_recent_bookings(5)
    
    return templates.TemplateResponse("admin.html", {
        "request": request,
        "admin": admin,
        "total_rooms": stats['total_rooms'],
        "active_bookings": stats['active_bookings'],
        "total_revenue": stats['total_revenue'],
        "occupancy_rate": stats['occupancy_rate'],
        "recent_bookings": recent_bookings,
        "current_lang": 'tj'
    })


@app.get("/admin/rooms", response_class=HTMLResponse)
async def admin_rooms(request: Request, admin: dict = Depends(get_current_admin)):
    rooms = get_rooms_with_translations()
    return templates.TemplateResponse("admin_rooms.html", {
        "request": request,
        "admin": admin,
        "rooms": rooms
    })


@app.get("/admin/bookings", response_class=HTMLResponse)
async def admin_bookings(request: Request, admin: dict = Depends(get_current_admin)):
    all_bookings = get_all_bookings()
    return templates.TemplateResponse("admin_bookings.html", {
        "request": request,
        "admin": admin,
        "all_bookings": all_bookings
    })


@app.post("/admin/rooms")
async def admin_create_room(
    number: str = Form(...),
    room_type: str = Form(...),
    price: float = Form(...),
    capacity: int = Form(...),
    description_tg: str = Form(...),
    description_ru: str = Form(...),
    description_en: str = Form(...),
    image: UploadFile = File(None),
    admin: dict = Depends(get_current_admin)
):
    conn = get_db_connection()
    
    image_url = "/static/images/room-default.jpg"
    
    if image and image.filename:
        try:
            file_extension = os.path.splitext(image.filename)[1].lower()
            if file_extension in ['.jpg', '.jpeg', '.png', '.webp']:
                filename = f"room-{number}{file_extension}"
                file_path = f"static/uploads/rooms/{filename}"
                with open(file_path, "wb") as buffer:
                    content = await image.read()
                    buffer.write(content)
                image_url = f"/static/uploads/rooms/{filename}"
        except Exception as e:
            print(f"Ошибка загрузки: {e}")
    
    try:
        conn.execute('''
            INSERT INTO rooms (number, type, price, capacity, description_tg, description_ru, description_en, image_url)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (number, room_type, price, capacity, description_tg, description_ru, description_en, image_url))
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()
    
    return RedirectResponse(url="/admin/rooms", status_code=303)


@app.post("/admin/rooms/{room_id}/update")
async def admin_update_room(
    room_id: int,
    number: str = Form(...),
    room_type: str = Form(...),
    price: float = Form(...),
    capacity: int = Form(...),
    description_tg: str = Form(...),
    description_ru: str = Form(...),
    description_en: str = Form(...),
    admin: dict = Depends(get_current_admin)
):
    success, message = update_room(room_id, {
        'number': number, 'type': room_type, 'price': price, 'capacity': capacity,
        'description_tg': description_tg, 'description_ru': description_ru, 'description_en': description_en
    })
    
    if not success:
        raise HTTPException(status_code=500, detail=message)
    
    return RedirectResponse(url="/admin/rooms", status_code=303)


@app.get("/admin/api/room/{room_id}")
async def admin_get_room(room_id: int, admin: dict = Depends(get_current_admin)):
    conn = get_db_connection()
    room = conn.execute('SELECT * FROM rooms WHERE id = ?', (room_id,)).fetchone()
    conn.close()
    
    if not room:
        return {"success": False, "message": "Room not found"}
    
    return {"success": True, "room": dict(room)}


@app.post("/admin/api/cancel-booking/{booking_id}")
async def admin_cancel_booking_api(booking_id: int, admin: dict = Depends(get_current_admin)):
    success, message = cancel_booking_by_admin(booking_id)
    return {"success": success, "message": message}


@app.post("/admin/api/complete-booking/{booking_id}")
async def admin_complete_booking_api(booking_id: int, admin: dict = Depends(get_current_admin)):
    success, message = complete_booking_by_admin(booking_id)
    return {"success": success, "message": message}


@app.post("/admin/api/send-booking-email/{booking_id}")
async def admin_send_booking_email(booking_id: int, admin: dict = Depends(get_current_admin)):
    booking = get_booking_by_id(booking_id)
    if not booking:
        return {"success": False, "message": "Booking not found"}
    
    email_html = create_booking_email_html(booking, 'ru')
    success = send_email(booking['guest_email'], "Подтверждение бронирования - СУГДДЕЛЮКС", email_html)
    
    return {"success": success, "message": "Email отправлен" if success else "Ошибка отправки"}


@app.post("/admin/rooms/{room_id}/update-image")
async def admin_update_room_image(
    room_id: int,
    image: UploadFile = File(...),
    admin: dict = Depends(get_current_admin)
):
    conn = get_db_connection()
    room = conn.execute('SELECT * FROM rooms WHERE id = ?', (room_id,)).fetchone()
    
    if not room:
        conn.close()
        raise HTTPException(status_code=404, detail="Room not found")
    
    try:
        file_extension = os.path.splitext(image.filename)[1].lower()
        filename = f"room-{room['number']}{file_extension}"
        file_path = f"static/uploads/rooms/{filename}"
        
        with open(file_path, "wb") as buffer:
            content = await image.read()
            buffer.write(content)
        
        image_url = f"/static/uploads/rooms/{filename}"
        conn.execute('UPDATE rooms SET image_url = ? WHERE id = ?', (image_url, room_id))
        conn.commit()
        conn.close()
        
    except Exception as e:
        conn.rollback()
        conn.close()
        raise HTTPException(status_code=500, detail=str(e))
    
    return RedirectResponse(url="/admin/rooms", status_code=303)


@app.post("/admin/rooms/{room_id}/delete")
async def admin_delete_room(room_id: int, admin: dict = Depends(get_current_admin)):
    conn = get_db_connection()
    
    try:
        room = conn.execute('SELECT * FROM rooms WHERE id = ?', (room_id,)).fetchone()
        
        if room and room['image_url'] and not room['image_url'].startswith('/static/images/room-default.jpg'):
            file_path = room['image_url'].replace('/static/uploads/rooms/', 'static/uploads/rooms/')
            if os.path.exists(file_path):
                os.remove(file_path)
        
        conn.execute('DELETE FROM rooms WHERE id = ?', (room_id,))
        conn.execute('DELETE FROM bookings WHERE room_id = ?', (room_id,))
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()
    
    return RedirectResponse(url="/admin/rooms", status_code=303)


@app.get("/admin/logout")
async def admin_logout():
    return RedirectResponse(url="/admin/login", status_code=303)


@app.get("/api/status")
async def api_status():
    return {
        "status": "working",
        "deepseek_api": "configured",
        "database": "connected",
        "websocket": "available",
        "email_service": "configured",
        "languages": ["tg", "ru", "en"]
    }


# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

def get_rooms_with_translations():
    conn = get_db_connection()
    rooms = conn.execute('SELECT * FROM rooms').fetchall()
    conn.close()
    
    rooms_list = []
    for room in rooms:
        room_dict = dict(room)
        if not room_dict.get('description_tg'):
            room_dict['description_tg'] = room_dict.get('description', '')
        if not room_dict.get('description_ru'):
            room_dict['description_ru'] = room_dict.get('description', '')
        if not room_dict.get('description_en'):
            room_dict['description_en'] = room_dict.get('description', '')
        rooms_list.append(room_dict)
    
    return rooms_list


def complete_expired_bookings():
    conn = get_db_connection()
    today = date.today().isoformat()
    
    expired = conn.execute('''
        UPDATE bookings 
        SET status = 'completed' 
        WHERE status = 'confirmed' AND check_out <= ?
    ''', (today,))
    
    conn.commit()
    count = expired.rowcount
    conn.close()
    
    if count > 0:
        print(f"✅ Автоматически завершено {count} просроченных бронирований")
    return count


def get_admin_stats():
    conn = get_db_connection()
    
    total_rooms = conn.execute('SELECT COUNT(*) FROM rooms').fetchone()[0]
    active_bookings = conn.execute('SELECT COUNT(*) FROM bookings WHERE status = "confirmed"').fetchone()[0]
    
    total_revenue = conn.execute('SELECT SUM(total_price) FROM bookings WHERE status = "confirmed" OR status = "completed"').fetchone()[0]
    if total_revenue is None:
        total_revenue = 0
    
    occupied_rooms = conn.execute('''
        SELECT COUNT(DISTINCT room_id) FROM bookings 
        WHERE status = "confirmed" AND check_in <= date("now") AND check_out >= date("now")
    ''').fetchone()[0]
    
    occupancy_rate = int((occupied_rooms / total_rooms) * 100) if total_rooms > 0 else 0
    
    conn.close()
    
    return {
        'total_rooms': total_rooms,
        'active_bookings': active_bookings,
        'total_revenue': total_revenue,
        'occupancy_rate': occupancy_rate
    }


def get_recent_bookings(limit=5):
    conn = get_db_connection()
    bookings = conn.execute('''
        SELECT b.*, r.number as room_number, r.type as room_type
        FROM bookings b
        JOIN rooms r ON b.room_id = r.id
        ORDER BY b.created_at DESC
        LIMIT ?
    ''', (limit,)).fetchall()
    conn.close()
    
    return [dict(booking) for booking in bookings]


def get_all_bookings():
    conn = get_db_connection()
    bookings = conn.execute('''
        SELECT b.*, r.number as room_number, r.type as room_type
        FROM bookings b
        JOIN rooms r ON b.room_id = r.id
        ORDER BY b.created_at DESC
    ''',).fetchall()
    conn.close()
    
    return [dict(booking) for booking in bookings]


def cancel_booking_by_admin(booking_id: int):
    conn = get_db_connection()
    
    try:
        booking = conn.execute('SELECT * FROM bookings WHERE id = ?', (booking_id,)).fetchone()
        
        if not booking:
            return False, "Бронирование не найдено"
        
        if booking['status'] != 'confirmed':
            return False, f"Бронирование уже {booking['status']}"
        
        full_booking = conn.execute('''
            SELECT b.*, r.number as room_number, r.type as room_type 
            FROM bookings b 
            JOIN rooms r ON b.room_id = r.id 
            WHERE b.id = ?
        ''', (booking_id,)).fetchone()
        
        conn.execute('UPDATE bookings SET status = "cancelled" WHERE id = ?', (booking_id,))
        conn.commit()
        
        if full_booking:
            booking_dict = dict(full_booking)
            for key in ['check_in', 'check_out', 'created_at']:
                if booking_dict.get(key) and isinstance(booking_dict[key], (date, datetime)):
                    booking_dict[key] = booking_dict[key].isoformat()
            
            if 'check_in' in booking_dict and 'check_out' in booking_dict:
                try:
                    check_in = datetime.fromisoformat(booking_dict['check_in'])
                    check_out = datetime.fromisoformat(booking_dict['check_out'])
                    booking_dict['nights'] = (check_out - check_in).days
                except:
                    booking_dict['nights'] = 1
            
            client_lang = detect_language(full_booking['guest_name'])
            cancellation_html = create_cancellation_email_html(booking_dict, client_lang)
            send_email(
                full_booking['guest_email'],
                "Брон бекор карда шуд" if client_lang == 'tg' else ("Бронирование отменено" if client_lang == 'ru' else "Booking Cancelled"),
                cancellation_html
            )
        
        conn.close()
        return True, f"Бронирование #{booking_id} успешно отменено, клиент уведомлён"
        
    except Exception as e:
        conn.rollback()
        conn.close()
        return False, f"Ошибка: {str(e)}"


def complete_booking_by_admin(booking_id: int):
    conn = get_db_connection()
    
    try:
        booking = conn.execute('SELECT * FROM bookings WHERE id = ?', (booking_id,)).fetchone()
        
        if not booking:
            return False, "Бронирование не найдено"
        
        if booking['status'] != 'confirmed':
            return False, f"Бронирование уже {booking['status']}"
        
        conn.execute('UPDATE bookings SET status = "completed" WHERE id = ?', (booking_id,))
        conn.commit()
        conn.close()
        
        return True, f"Бронирование #{booking_id} отмечено как завершённое"
        
    except Exception as e:
        conn.rollback()
        conn.close()
        return False, f"Ошибка: {str(e)}"


def update_room(room_id: int, room_data: dict):
    conn = get_db_connection()
    
    try:
        conn.execute('''
            UPDATE rooms 
            SET number = ?, type = ?, price = ?, capacity = ?,
                description_tg = ?, description_ru = ?, description_en = ?
            WHERE id = ?
        ''', (
            room_data['number'], room_data['type'], room_data['price'], room_data['capacity'],
            room_data.get('description_tg', ''), room_data.get('description_ru', ''),
            room_data.get('description_en', ''), room_id
        ))
        conn.commit()
        conn.close()
        return True, "Номер успешно обновлён"
    except Exception as e:
        conn.rollback()
        conn.close()
        return False, f"Ошибка: {str(e)}"


def update_db_for_translations():
    conn = sqlite3.connect('hotel.db')
    cursor = conn.cursor()
    
    try:
        cursor.execute('ALTER TABLE rooms ADD COLUMN description_tg TEXT')
    except sqlite3.OperationalError:
        pass
    
    try:
        cursor.execute('ALTER TABLE rooms ADD COLUMN description_ru TEXT')
    except sqlite3.OperationalError:
        pass
    
    try:
        cursor.execute('ALTER TABLE rooms ADD COLUMN description_en TEXT')
    except sqlite3.OperationalError:
        pass
    
    cursor.execute('UPDATE rooms SET description_tg = description WHERE description_tg IS NULL')
    cursor.execute('UPDATE rooms SET description_ru = description WHERE description_ru IS NULL')
    cursor.execute('UPDATE rooms SET description_en = description WHERE description_en IS NULL')
    
    conn.commit()
    conn.close()
    print("✅ База данных обновлена для поддержки языков")


# Обновляем БД
update_db_for_translations()


if __name__ == "__main__":
    import uvicorn
    print("🚀 Запуск сервера СУҒДДЕЛЮКС с поддержкой 3 языков (TJ/RU/EN)...")
    print("💻 Локальный доступ: http://127.0.0.1:8000")
    print("🔑 Админка: http://127.0.0.1:8000/admin/login")
    print("👤 Логин: admin")
    print("🔒 Пароль: admin123")
    print("🌍 Языки: Таджикский (tg), Русский (ru), English (en)")
    print("🎤 Голосовой ввод работает в Chrome, Edge, Safari")
    print("🤖 AI отвечает на любые вопросы, не только про отель")
    
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
