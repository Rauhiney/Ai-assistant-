from flask import Flask, render_template, request, jsonify, send_from_directory, session, redirect, url_for
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import inspect, text, or_
from sqlalchemy.exc import IntegrityError, OperationalError
from datetime import datetime
from functools import wraps
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import logging
import math
import random
import secrets
import smtplib
import requests
import os
import pytz
import threading
import time
import re
import difflib
import socket
import uuid
from email.message import EmailMessage
from urllib.parse import quote
from duckduckgo_search import DDGS
from services.ai_service import AIServiceError, ai_service


# ============================================================================
# LOCAL ENV LOADING
# ============================================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def load_local_env(path=None, override=True):
    """Load KEY=value pairs from .env before app/config constants are read."""
    env_path = path or os.path.join(BASE_DIR, ".env")
    if not os.path.exists(env_path):
        return []

    loaded_keys = []
    with open(env_path, "r", encoding="utf-8") as env_file:
        for line in env_file:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            if override or key not in os.environ:
                os.environ[key] = value.strip().strip('"').strip("'")
            loaded_keys.append(key)
    return loaded_keys

LOAD_DOTENV_OVERRIDE = os.getenv("LOAD_DOTENV_OVERRIDE", "false").strip().lower() in {"1", "true", "yes", "on"}
LOADED_ENV_KEYS = load_local_env(override=LOAD_DOTENV_OVERRIDE)

# ============================================================================
# FLASK APP SETUP
# ============================================================================

app = Flask(__name__, template_folder='templates', static_folder='static')
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1, x_prefix=1)
CORS(app)

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///denz_chat.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['JSON_SORT_KEYS'] = False
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'denz-dev-secret-change-me')
app.config['MAX_CONTENT_LENGTH'] = int(os.getenv('MAX_UPLOAD_MB', '16')) * 1024 * 1024
app.config['UPLOAD_FOLDER'] = os.path.join(app.instance_path, 'uploads')

db = SQLAlchemy(app)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def env_bool(name, default=False):
    """Parse boolean env flags consistently."""
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_int(name, default):
    """Parse integer env values with a safe fallback and log bad values."""
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    try:
        return int(value)
    except ValueError:
        logger.warning(f"Invalid integer for {name}; using {default}")
        return default


def mask_secret(value, visible=3):
    """Show whether a secret is configured without leaking it."""
    if not value:
        return "<missing>"
    if len(value) <= visible:
        return "***"
    return f"{value[:visible]}***"


class OTPDeliveryError(RuntimeError):
    """Raised when OTP delivery is configured but the provider rejects/fails it."""


app.config['SESSION_COOKIE_SECURE'] = env_bool('SESSION_COOKIE_SECURE', env_bool('PRODUCTION', False))
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = os.getenv('SESSION_COOKIE_SAMESITE', 'Lax')
app.config['PREFERRED_URL_SCHEME'] = os.getenv('PREFERRED_URL_SCHEME', 'https' if app.config['SESSION_COOKIE_SECURE'] else 'http')


# ============================================================================
# CONFIGURATION
# ============================================================================

ASSISTANT_NAME = "DENZ"
ASSISTANT_VERSION = "3D-ULTRA-AI-FASTEST"
SYSTEM_PROMPT = """
You are DENZ, an advanced AI assistant created by Rauhiney Kashyap.

You provide accurate, detailed and helpful answers.

You can use tool results supplied by the backend for live weather, location/maps,
and web search. Treat tool results as the freshest available context.

If the question is technical, explain clearly.

If the user asks for code, provide complete code.

Maintain a friendly and intelligent personality.

Do not reveal hidden reasoning or thinking text. Give only the final answer.
"""
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:8b")  # Upgraded to qwen3:8b for better performance and speed
OLLAMA_VISION_MODEL = os.getenv("OLLAMA_VISION_MODEL", OLLAMA_MODEL)
OLLAMA_TIMEOUT = float(os.getenv("OLLAMA_TIMEOUT", "15"))  # Increased from 4s to 15s for better responses
AI_PROVIDER = ai_service.provider_name
AI_MODEL = ai_service.model_name
FLASK_HOST = os.getenv("FLASK_HOST", "0.0.0.0")
FLASK_PORT = int(os.getenv("PORT", os.getenv("FLASK_PORT", "5000")))
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "").strip()
ADMIN_PHONE = os.getenv("ADMIN_PHONE", "").strip()
OTP_EXPIRY_SECONDS = env_int("OTP_EXPIRY_SECONDS", 300)
OTP_RETURN_CODE = env_bool("OTP_RETURN_CODE", False)
SMTP_HOST = os.getenv("SMTP_HOST", "").strip()
SMTP_PORT = env_int("SMTP_PORT", 587)
SMTP_USERNAME = os.getenv("SMTP_USERNAME", "").strip()
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "").strip()
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USERNAME or "no-reply@denz.local").strip()
SMTP_USE_TLS = env_bool("SMTP_USE_TLS", True)
SMTP_USE_SSL = env_bool("SMTP_USE_SSL", False)
SMTP_TIMEOUT = env_int("SMTP_TIMEOUT", 15)
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "").strip()
RESEND_FROM = os.getenv("RESEND_FROM", SMTP_FROM).strip()
SMS_PROVIDER = os.getenv("SMS_PROVIDER", "").strip().lower()
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "").strip()
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "").strip()
TWILIO_FROM_NUMBER = os.getenv("TWILIO_FROM_NUMBER", "").strip()
ALLOWED_DOCUMENT_EXTENSIONS = {"pdf", "docx", "txt", "md"}
ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "gif"}

# Weather API
WEATHER_API_KEY = os.getenv("WEATHER_API_KEY", "").strip()
WEATHER_API_URL = "https://api.openweathermap.org/data/2.5/weather"
FORECAST_API_URL = "https://api.openweathermap.org/data/2.5/forecast"

# IP Geolocation API (free, no key needed)
IP_GEOLOCATION_URL = "https://ipapi.co"

# ============================================================================
# IN-MEMORY CACHE FOR ULTRA SPEED
# ============================================================================

location_cache = {}
weather_cache = {}
response_cache = {}
pending_weather_requests = {}
conversation_memory = {}
geolocation_backoff_until = {}
ai_backoff_until = 0
GEOLOCATION_RATE_LIMIT_BACKOFF_SECONDS = 15 * 60
OLLAMA_FAILURE_BACKOFF_SECONDS = 60

WEATHER_KEYWORDS = [
    "weather",
    "temperature",
    "forecast",
    "rain",
    "humidity",
    "climate",
]
CAPITAL_KEYWORDS = [
    "capital of",
    "captial of",
    "state capital",
    "capital city",
    "captial",
]
CAPITAL_LOOKUP = {
    "india": ("India", "New Delhi"),
    "himachal": ("Himachal Pradesh", "Shimla"),
    "himachal pradesh": ("Himachal Pradesh", "Shimla"),
    "hp": ("Himachal Pradesh", "Shimla"),
    "punjab": ("Punjab", "Chandigarh"),
    "haryana": ("Haryana", "Chandigarh"),
    "uttarakhand": ("Uttarakhand", "Dehradun"),
    "uttar pradesh": ("Uttar Pradesh", "Lucknow"),
    "rajasthan": ("Rajasthan", "Jaipur"),
    "delhi": ("Delhi", "New Delhi"),
    "maharashtra": ("Maharashtra", "Mumbai"),
    "gujarat": ("Gujarat", "Gandhinagar"),
    "karnataka": ("Karnataka", "Bengaluru"),
    "tamil nadu": ("Tamil Nadu", "Chennai"),
    "kerala": ("Kerala", "Thiruvananthapuram"),
    "west bengal": ("West Bengal", "Kolkata"),
    "bihar": ("Bihar", "Patna"),
    "jharkhand": ("Jharkhand", "Ranchi"),
    "odisha": ("Odisha", "Bhubaneswar"),
    "assam": ("Assam", "Dispur"),
    "goa": ("Goa", "Panaji"),
}
NON_LOCATION_WORDS = {
    'what', 'whats', 'what is', 'current', 'the current', 'today', 'now',
    'right now', 'currently', 'please', 'pls', 'weather', 'temperature',
    's', 'hat', 'todays', "today's",
}
WEATHER_FILLER_WORDS = (
    'what', 'whats', 'is', 'the', 'current', 'today', 'now', 'right', 'currently',
    'please', 'pls', 'tell', 'me', 'show', 'check', 'weather', 'temperature',
    'forecast', 'rain', 'humidity', 'climate', 'in', 'at', 'for', 'of',
    's', 'hat', 'todays',
)
FOLLOWUP_REFERENCE_TERMS = {
    'next', 'more', 'again', 'same', 'continue', 'go on', 'what about it',
    'what about that', 'that', 'this', 'it', 'also', 'and', 'explain more',
    'tell me more',
}
LOCATION_ALIASES = {
    'dharamshala': 'Dharamsala',
    'dharamshal': 'Dharamsala',
    'dharsmahala': 'Dharamsala',
    'dharmsala': 'Dharamsala',
    'dharamsala': 'Dharamsala',
    'chandigrah': 'Chandigarh',
    'chandigarh': 'Chandigarh',
}


def normalize_weather_terms(message):
    """Convert common weather misspellings into canonical weather terms."""
    normalized_words = []
    for word in re.findall(r'[a-zA-Z]+', message.lower()):
        if word in WEATHER_KEYWORDS:
            normalized_words.append(word)
            continue

        matches = difflib.get_close_matches(word, WEATHER_KEYWORDS, n=1, cutoff=0.78)
        if matches:
            normalized_words.append(matches[0])
        else:
            normalized_words.append(word)

    return ' '.join(normalized_words)


def normalize_conversation_text(text):
    return re.sub(r'\s+', ' ', text.strip().lower())


def get_session_context(session_id):
    if not session_id:
        return {}
    if session_id not in conversation_memory:
        conversation_memory[session_id] = {
            'last_intent': None,
            'last_entity': None,
            'last_topic': None,
            'last_message': None,
            'last_ai_response': None,
        }
    return conversation_memory[session_id]


def infer_user_intent(message):
    text = normalize_conversation_text(normalize_weather_terms(message))
    if any(keyword in text for keyword in WEATHER_KEYWORDS):
        return 'weather'
    if is_capital_query(message):
        return 'capital'
    if any(keyword in text for keyword in ('news', 'headline', 'breaking', 'latest update', 'latest')):
        return 'news'
    if any(keyword in text for keyword in ('what', 'why', 'how', 'who', 'which', 'where', 'when', 'tell me', 'explain', 'define')):
        return 'question'
    return 'general'


def normalize_entity_from_text(message):
    text = normalize_conversation_text(message)
    if not text:
        return None
    if text in {'next', 'more', 'again', 'same', 'what about it', 'what about', 'that', 'this', 'it', 'also', 'and'}:
        return None

    of_match = re.search(r'\bof\s+the?\s+([a-zA-Z][a-zA-Z\s-]{1,40})$', text, flags=re.IGNORECASE)
    if of_match:
        return of_match.group(1).strip().title()

    in_match = re.search(r'\bin\s+([a-zA-Z][a-zA-Z\s-]{1,40})$', text, flags=re.IGNORECASE)
    if in_match:
        return in_match.group(1).strip().title()

    cleaned = re.sub(r'[^a-zA-Z\s,-]', ' ', text)
    cleaned = re.sub(
        r'\b(what|about|tell|me|more|show|check|please|pls|the|current|today|now|right now|currently|this|that|it|and|also|next|again|same)\b',
        ' ',
        cleaned,
        flags=re.IGNORECASE,
    )
    tokens = [token for token in cleaned.split() if token and token not in WEATHER_KEYWORDS]
    if not tokens:
        return None
    if len(tokens) <= 3:
        return ' '.join(tokens).title()
    return None


def is_short_followup(message, context):
    text = normalize_conversation_text(message)
    if not context or not context.get('last_intent'):
        return False
    if is_capital_query(text) and extract_capital_subject(text):
        return False
    if context.get('last_intent') == 'capital' and text in {'capital', 'captial', 'what is capital', 'what is captial', 'what is the capital'}:
        return True
    if context.get('last_intent') == 'capital' and normalize_entity_from_text(text):
        return True
    if text in FOLLOWUP_REFERENCE_TERMS:
        return True

    if re.match(r'^(what about|how about|and)\s+[a-z0-9][a-z0-9\s-]{1,60}$', text):
        return True

    return False


def build_context_guidance(context, current_message):
    context = context or {}
    if not any(context.values()):
        return ''
    lines = []
    if context.get('last_intent'):
        lines.append(f"Last user intent: {context['last_intent']}")
    if context.get('last_entity'):
        lines.append(f"Last entity/topic: {context['last_entity']}")
    if context.get('last_topic'):
        lines.append(f"Last topic: {context['last_topic']}")
    if is_short_followup(current_message, context):
        lines.append('Current input is a short follow-up. Continue the previous topic or location unless the user clearly changes it.')
    return '\n'.join(lines)


def resolve_followup_message(message, session_id):
    context = get_session_context(session_id)
    normalized = normalize_conversation_text(message)
    if not is_short_followup(normalized, context):
        return message
    last_intent = context.get('last_intent')
    last_entity = context.get('last_entity')
    last_topic = context.get('last_topic')
    if last_intent == 'capital' and normalized in {'capital', 'captial', 'what is capital', 'what is captial', 'what is the capital'}:
        target = last_entity or last_topic
        if target:
            return f'capital of {target}'
    if last_intent == 'capital':
        target = extract_capital_subject(normalized) or normalize_entity_from_text(normalized) or last_entity or last_topic
        if target:
            return f'capital of {target}'
    if normalized == 'capital' and last_entity and 'india' in last_entity.lower():
        return 'capital of india'
    if last_intent == 'weather':
        if normalized in {'next', 'more', 'again', 'same', 'what about it'}:
            target = last_entity or last_topic or 'the same place'
        elif normalized in {'that', 'this', 'it'}:
            target = last_entity or last_topic or 'that place'
        else:
            target = normalize_entity_from_text(normalized) or last_entity or last_topic or normalized
        return f'weather in {target}'
    if normalized in {'next', 'more', 'again', 'what about it', 'what about that', 'that', 'this', 'it', 'continue', 'go on', 'explain more', 'tell me more'}:
        target = last_entity or last_topic or 'the previous topic'
        return f'Tell me more about {target}'
    what_about_match = re.match(r'^(?:what about|how about|and)\s+(.+)$', normalized)
    if what_about_match:
        target = what_about_match.group(1).strip()
        if last_entity or last_topic:
            return f'Tell me about {target} in the context of {last_entity or last_topic}'
        return f'Tell me about {target}'
    if last_entity or last_topic:
        return f'Tell me about {normalized} in the context of {last_entity or last_topic}'
    return message


def update_conversation_memory(session_id, user_message, ai_response, effective_message, weather_question=False, requested_weather_location=None):
    context = get_session_context(session_id)
    intent = infer_user_intent(effective_message)
    capital_subject = extract_capital_subject(effective_message) if intent == 'capital' else None
    entity = capital_subject or requested_weather_location or extract_weather_location(effective_message) or guess_weather_location(effective_message) or normalize_entity_from_text(effective_message)
    topic = entity or normalize_entity_from_text(user_message)
    is_followup = is_short_followup(user_message, context)
    if not entity and is_followup:
        entity = context.get('last_entity')
    if not topic and is_followup:
        topic = context.get('last_topic')
    context.update({
        'last_intent': intent,
        'last_entity': entity,
        'last_topic': topic,
        'last_message': user_message,
        'last_ai_response': ai_response,
        'last_weather_question': weather_question,
    })


def cached_location(ip_address):
    """In-memory cache for locations"""
    return location_cache.get(ip_address)

def cached_weather(location_key):
    """In-memory cache for weather"""
    return weather_cache.get(location_key)

def cached_response(message_key):
    """In-memory cache for AI responses"""
    return response_cache.get(message_key)

# ============================================================================
# DATABASE MODELS
# ============================================================================

class User(db.Model):
    """Application user for login, chat ownership, and admin access."""
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=True, index=True)
    phone_number = db.Column(db.String(20), unique=True, nullable=True, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.now)
    last_login = db.Column(db.DateTime)

    def verify_password(self, password):
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'phone_number': self.phone_number,
            'is_admin': self.is_admin,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'last_login': self.last_login.isoformat() if self.last_login else None,
        }


class ChatMessage(db.Model):
    """Store chat messages with location data"""
    __tablename__ = 'chat_messages'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)
    session_id = db.Column(db.String(100), index=True)
    user_message = db.Column(db.String(1000), nullable=False)
    bot_response = db.Column(db.String(2000), nullable=False)
    effect_triggered = db.Column(db.String(50))
    ai_model = db.Column(db.String(50), default='ollama')
    user_location = db.Column(db.String(200))
    user_timezone = db.Column(db.String(50))
    user_ip = db.Column(db.String(50))
    weather_data = db.Column(db.JSON)
    timestamp = db.Column(db.DateTime, default=datetime.now)
    
    def to_dict(self):
        return {
            'id': self.id,
            'session_id': self.session_id,
            'user': self.user_message,
            'bot': self.bot_response,
            'effect': self.effect_triggered,
            'model': self.ai_model,
            'location': self.user_location,
            'timezone': self.user_timezone,
            'weather': self.weather_data,
            'timestamp': self.timestamp.isoformat()
        }


class LocationData(db.Model):
    """Store user location history"""
    __tablename__ = 'location_data'
    
    id = db.Column(db.Integer, primary_key=True)
    ip_address = db.Column(db.String(50), unique=True)
    country = db.Column(db.String(100))
    city = db.Column(db.String(100))
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    timezone = db.Column(db.String(50))
    isp = db.Column(db.String(200))
    last_seen = db.Column(db.DateTime, default=datetime.now)
    
    def is_expired(self, hours=24):
        return (datetime.now() - self.last_seen).total_seconds() > (hours * 3600)
    
    def to_dict(self):
        return {
            'ip': self.ip_address,
            'country': self.country,
            'city': self.city,
            'coords': {
                'lat': self.latitude,
                'lng': self.longitude
            },
            'timezone': self.timezone,
            'isp': self.isp,
            'last_seen': self.last_seen.isoformat()
        }


class WeatherCache(db.Model):
    """Cache weather data"""
    __tablename__ = 'weather_cache'
    
    id = db.Column(db.Integer, primary_key=True)
    location = db.Column(db.String(100), unique=True)
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    weather_data = db.Column(db.JSON)
    cached_at = db.Column(db.DateTime, default=datetime.now)
    
    def is_expired(self, minutes=10):  # Even shorter cache
        return (datetime.now() - self.cached_at).total_seconds() > (minutes * 60)
    
    def to_dict(self):
        return {
            'location': self.location,
            'weather': self.weather_data,
            'cached_at': self.cached_at.isoformat()
        }


class UserSession(db.Model):
    """Store user sessions"""
    __tablename__ = 'user_sessions'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)
    session_id = db.Column(db.String(100), unique=True)
    ip_address = db.Column(db.String(50))
    country = db.Column(db.String(100))
    city = db.Column(db.String(100))
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    created_at = db.Column(db.DateTime, default=datetime.now)
    last_active = db.Column(db.DateTime, default=datetime.now)
    messages_count = db.Column(db.Integer, default=0)
    
    def to_dict(self):
        return {
            'session_id': self.session_id,
            'location': {
                'city': self.city,
                'country': self.country,
                'coords': {
                    'lat': self.latitude,
                    'lng': self.longitude
                }
            },
            'created_at': self.created_at.isoformat(),
            'last_active': self.last_active.isoformat(),
            'messages_count': self.messages_count
        }


class UploadedFile(db.Model):
    """Track document and image uploads for users and sessions."""
    __tablename__ = 'uploaded_files'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)
    session_id = db.Column(db.String(100), index=True)
    filename = db.Column(db.String(255), nullable=False)
    stored_filename = db.Column(db.String(255), nullable=False)
    file_type = db.Column(db.String(30), nullable=False)
    mime_type = db.Column(db.String(100))
    size_bytes = db.Column(db.Integer, default=0)
    extracted_text = db.Column(db.Text)
    analysis = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.now)

    def to_dict(self):
        return {
            'id': self.id,
            'filename': self.filename,
            'file_type': self.file_type,
            'size_bytes': self.size_bytes,
            'extracted_text': self.extracted_text,
            'analysis': self.analysis,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


def get_current_user():
    user_id = session.get('user_id')
    if not user_id:
        return None
    return db.session.get(User, user_id)


def current_user_id():
    user = get_current_user()
    return user.id if user else None


def generate_otp_code():
    return f"{secrets.randbelow(1000000):06d}"


def normalize_email(email):
    email = (email or '').strip().lower()
    if not email:
        return None
    if not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email):
        return None
    return email


def normalize_phone(phone_number):
    phone_number = (phone_number or '').strip()
    if not phone_number:
        return None
    cleaned = re.sub(r'[\s().-]', '', phone_number)
    if cleaned.startswith('00'):
        cleaned = '+' + cleaned[2:]
    if not cleaned.startswith('+'):
        return None
    if not re.match(r'^\+[1-9]\d{7,14}$', cleaned):
        return None
    return cleaned


def mask_destination(destination, channel):
    if channel == 'phone':
        return f"***{destination[-4:]}" if destination else 'phone'
    if not destination or '@' not in destination:
        return 'email'
    name, domain = destination.split('@', 1)
    masked_name = name[:2] + '***' if len(name) > 2 else '***'
    return f"{masked_name}@{domain}"


def otp_config_status():
    """Return masked OTP configuration details for startup/debug logs."""
    return {
        "env_file_keys": ",".join(LOADED_ENV_KEYS) if LOADED_ENV_KEYS else "<none>",
        "otp_return_code": OTP_RETURN_CODE,
        "smtp_host": SMTP_HOST or "<missing>",
        "smtp_port": SMTP_PORT,
        "smtp_username": mask_destination(SMTP_USERNAME, "email") if SMTP_USERNAME else "<missing>",
        "smtp_password": mask_secret(SMTP_PASSWORD),
        "smtp_from": SMTP_FROM or "<missing>",
        "smtp_tls": SMTP_USE_TLS,
        "smtp_ssl": SMTP_USE_SSL,
        "resend_api_key": mask_secret(RESEND_API_KEY),
        "resend_from": RESEND_FROM or "<missing>",
        "sms_provider": SMS_PROVIDER or "<missing>",
        "twilio_sid": mask_secret(TWILIO_ACCOUNT_SID),
        "twilio_from": TWILIO_FROM_NUMBER or "<missing>",
    }


def log_otp_config_status():
    """Log enough OTP config context to debug delivery without leaking secrets."""
    status = otp_config_status()
    logger.info(
        "OTP config loaded: "
        f"OTP_RETURN_CODE={status['otp_return_code']}, "
        f"SMTP={status['smtp_username']}@{status['smtp_host']}:{status['smtp_port']}, "
        f"SMTP_PASSWORD={status['smtp_password']}, "
        f"Resend={status['resend_api_key']}:{status['resend_from']}, "
        f"Twilio={status['sms_provider']}:{status['twilio_sid']}, "
        f".env keys={status['env_file_keys']}"
    )


def send_resend_email_otp(destination, code):
    """Send OTP through Resend over HTTPS, which works on hosts that block SMTP."""
    missing = []
    if not destination:
        missing.append("destination email")
    if not RESEND_API_KEY:
        missing.append("RESEND_API_KEY")
    if not RESEND_FROM:
        missing.append("RESEND_FROM")

    if missing:
        logger.warning(f"Resend OTP not sent; missing {', '.join(missing)}")
        return False

    try:
        response = requests.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {RESEND_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "from": RESEND_FROM,
                "to": [destination],
                "subject": "Your DENZ login OTP",
                "text": f"Your DENZ login OTP is {code}. It expires in {OTP_EXPIRY_SECONDS // 60} minutes.",
            },
            timeout=15,
        )
        response.raise_for_status()
        logger.info(f"Sent email OTP through Resend to {mask_destination(destination, 'email')}")
        return True
    except requests.RequestException as error:
        response_text = getattr(getattr(error, "response", None), "text", "")
        message = f"Resend OTP delivery failed: {error} {response_text[:300]}"
        logger.error(message)
        if not OTP_RETURN_CODE:
            raise OTPDeliveryError(message) from error
    return False


def send_email_otp(destination, code):
    """Send OTP by HTTPS email provider or Gmail/SMTP."""
    if RESEND_API_KEY:
        return send_resend_email_otp(destination, code)

    missing = []
    if not destination:
        missing.append("destination email")
    if not SMTP_HOST:
        missing.append("SMTP_HOST")
    if not SMTP_USERNAME:
        missing.append("SMTP_USERNAME")
    if not SMTP_PASSWORD:
        missing.append("SMTP_PASSWORD")

    if missing:
        logger.warning(f"Email OTP not sent; missing {', '.join(missing)}")
        return False

    try:
        message = EmailMessage()
        message["Subject"] = "Your DENZ login OTP"
        message["From"] = SMTP_FROM
        message["To"] = destination
        message.set_content(
            f"Your DENZ login OTP is {code}. It expires in {OTP_EXPIRY_SECONDS // 60} minutes."
        )
        smtp_class = smtplib.SMTP_SSL if SMTP_USE_SSL else smtplib.SMTP
        with smtp_class(SMTP_HOST, SMTP_PORT, timeout=SMTP_TIMEOUT) as smtp:
            if SMTP_USE_TLS and not SMTP_USE_SSL:
                smtp.starttls()
            smtp.login(SMTP_USERNAME, SMTP_PASSWORD)
            smtp.send_message(message)
        logger.info(f"Sent email OTP to {mask_destination(destination, 'email')}")
        return True
    except smtplib.SMTPAuthenticationError as error:
        message = (
            "Gmail SMTP authentication failed. Use a fresh 16-character Gmail App Password "
            "for SMTP_PASSWORD, not your normal Gmail password."
        )
        logger.error(f"{message} Server response: {error}")
        if not OTP_RETURN_CODE:
            raise OTPDeliveryError(message) from error
    except (smtplib.SMTPException, OSError) as error:
        message = (
            f"Email OTP delivery failed via {SMTP_HOST}:{SMTP_PORT} "
            f"TLS={SMTP_USE_TLS} SSL={SMTP_USE_SSL}: {error}"
        )
        logger.error(message)
        if not OTP_RETURN_CODE:
            raise OTPDeliveryError(message) from error
    return False


def send_sms_otp(destination, code):
    """Send OTP by Twilio SMS. Return False when config/delivery is unavailable."""
    missing = []
    if SMS_PROVIDER != 'twilio':
        missing.append("SMS_PROVIDER=twilio")
    if not TWILIO_ACCOUNT_SID:
        missing.append("TWILIO_ACCOUNT_SID")
    if not TWILIO_AUTH_TOKEN:
        missing.append("TWILIO_AUTH_TOKEN")
    if not TWILIO_FROM_NUMBER:
        missing.append("TWILIO_FROM_NUMBER")
    if not destination:
        missing.append("destination phone")

    if missing:
        logger.warning(f"SMS OTP not sent; missing {', '.join(missing)}")
        return False

    try:
        response = requests.post(
            f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_ACCOUNT_SID}/Messages.json",
            data={
                'From': TWILIO_FROM_NUMBER,
                'To': destination,
                'Body': f"Your DENZ login OTP is {code}. It expires in {OTP_EXPIRY_SECONDS // 60} minutes.",
            },
            auth=(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN),
            timeout=10,
        )
        response.raise_for_status()
        logger.info(f"Sent login OTP SMS to {mask_destination(destination, 'phone')}")
        return True
    except requests.RequestException as error:
        response_text = getattr(getattr(error, "response", None), "text", "")
        message = f"SMS OTP delivery failed through Twilio: {error} {response_text[:300]}"
        logger.error(message)
        if not OTP_RETURN_CODE:
            raise OTPDeliveryError(message) from error
    return False


def send_otp_code(user, code, channel):
    if channel == 'phone':
        return send_sms_otp(user.phone_number, code), user.phone_number
    return send_email_otp(user.email, code), user.email


def start_login_otp(user, channel='email'):
    channel = 'phone' if channel == 'phone' else 'email'
    if channel == 'email' and not user.email:
        raise ValueError('No email address is registered for this account.')
    if channel == 'phone' and not user.phone_number:
        raise ValueError('No phone number is registered for this account.')

    code = generate_otp_code()
    sent, destination = send_otp_code(user, code, channel)
    if not sent and not OTP_RETURN_CODE:
        log_otp_config_status()
        raise RuntimeError(
            'OTP delivery is not configured. Set Gmail SMTP settings or Twilio SMS settings on the server.'
        )

    session['pending_otp'] = {
        'user_id': user.id,
        'channel': channel,
        'code_hash': generate_password_hash(code),
        'expires_at': time.time() + OTP_EXPIRY_SECONDS,
        'attempts': 0,
    }
    payload = {
        'otp_required': True,
        'message': f"OTP sent to {mask_destination(destination, channel)}.",
        'delivery': channel,
        'success': True,
    }
    if OTP_RETURN_CODE and not sent:
        logger.warning("OTP_RETURN_CODE=true; returning login OTP in API response for local testing.")
        payload['otp'] = code
        payload['message'] = f'Development OTP: {code}'
    return payload


def start_registration_otp(email, phone_number, channel):
    channel = 'phone' if channel == 'phone' else 'email'
    if channel == 'email' and not email:
        raise ValueError('A valid Gmail/email address is required to verify registration.')
    if channel == 'phone' and not phone_number:
        raise ValueError('A valid phone number is required to verify registration.')

    destination = phone_number if channel == 'phone' else email
    code = generate_otp_code()
    sent = send_sms_otp(phone_number, code) if channel == 'phone' else send_email_otp(email, code)
    if not sent and not OTP_RETURN_CODE:
        log_otp_config_status()
        raise RuntimeError('OTP delivery is not configured. Set Gmail SMTP or Twilio SMS settings on the server.')

    session.pop('pending_otp', None)
    session['pending_registration'] = {
        'email': email,
        'phone_number': phone_number,
        'channel': channel,
        'code_hash': generate_password_hash(code),
        'expires_at': time.time() + OTP_EXPIRY_SECONDS,
        'attempts': 0,
    }

    payload = {
        'otp_required': True,
        'registration_pending': True,
        'message': f"Registration OTP sent to {mask_destination(destination, channel)}.",
        'delivery': channel,
        'success': True,
    }
    if OTP_RETURN_CODE and not sent:
        logger.warning("OTP_RETURN_CODE=true; returning registration OTP in API response for local testing.")
        payload['otp'] = code
        payload['message'] = f'Development registration OTP: {code}'
    return payload


def start_recovery_otp(user):
    """Send OTP for username/password recovery using the account's verified contact."""
    channel = 'email' if user.email else 'phone'
    code = generate_otp_code()
    sent, destination = send_otp_code(user, code, channel)
    if not sent and not OTP_RETURN_CODE:
        log_otp_config_status()
        raise RuntimeError('OTP delivery is not configured. Set Gmail SMTP or Twilio SMS settings on the server.')

    session.pop('pending_otp', None)
    session.pop('pending_registration', None)
    session['pending_recovery'] = {
        'user_id': user.id,
        'channel': channel,
        'code_hash': generate_password_hash(code),
        'expires_at': time.time() + OTP_EXPIRY_SECONDS,
        'attempts': 0,
    }

    payload = {
        'otp_required': True,
        'recovery_pending': True,
        'message': f"Recovery OTP sent to {mask_destination(destination, channel)}.",
        'delivery': channel,
        'success': True,
    }
    if OTP_RETURN_CODE and not sent:
        logger.warning("OTP_RETURN_CODE=true; returning recovery OTP in API response for local testing.")
        payload['otp'] = code
        payload['message'] = f'Development recovery OTP: {code}'
    return payload


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not get_current_user():
            return jsonify({'error': 'Login required', 'success': False}), 401
        return view(*args, **kwargs)
    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = get_current_user()
        if not user or not user.is_admin:
            if request.path.startswith('/api/'):
                return jsonify({'error': 'Admin access required', 'success': False}), 403
            return redirect(url_for('chat_page'))
        return view(*args, **kwargs)
    return wrapped


def allowed_file(filename, allowed_extensions):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions


def ensure_upload_folder():
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)


def save_uploaded_file(file_storage, prefix):
    ensure_upload_folder()
    original_name = secure_filename(file_storage.filename or f'{prefix}-upload')
    extension = original_name.rsplit('.', 1)[1].lower() if '.' in original_name else 'bin'
    stored_name = f"{prefix}-{uuid.uuid4().hex}.{extension}"
    stored_path = os.path.join(app.config['UPLOAD_FOLDER'], stored_name)
    file_storage.save(stored_path)
    return original_name, stored_name, stored_path


def extract_text_from_document(path, extension):
    extension = extension.lower()
    if extension in {'txt', 'md'}:
        with open(path, 'r', encoding='utf-8', errors='ignore') as text_file:
            return text_file.read()

    if extension == 'pdf':
        try:
            from PyPDF2 import PdfReader
        except Exception:
            return 'PDF uploaded. Install PyPDF2 to enable text extraction.'

        reader = PdfReader(path)
        pages = []
        for page in reader.pages[:20]:
            pages.append(page.extract_text() or '')
        return '\n'.join(pages).strip() or 'No selectable text was found in this PDF.'

    if extension == 'docx':
        try:
            from docx import Document
        except Exception:
            return 'DOCX uploaded. Install python-docx to enable text extraction.'

        document = Document(path)
        return '\n'.join(paragraph.text for paragraph in document.paragraphs).strip() or 'No text was found in this DOCX.'

    return ''


def summarize_uploaded_text(text):
    clean_text = re.sub(r'\s+', ' ', (text or '')).strip()
    if not clean_text:
        return 'I uploaded the file, but I could not extract readable text from it.'

    excerpt = clean_text[:4000]
    prompt = (
        "Summarize this uploaded document in 5 concise bullets, then list any key dates, names, or action items.\n\n"
        f"{excerpt}"
    )
    try:
        return get_ollama_response_ultra_fast(
            prompt,
            {'city': 'Unknown', 'country': 'Unknown', 'latitude': 0, 'longitude': 0, 'timezone': 'UTC'},
            get_neutral_weather(),
            'UTC',
            [],
            None,
            None,
        )
    except Exception as error:
        logger.warning(f"Document summary fallback used: {error}")
        return clean_text[:900]


def analyze_image_file(path, prompt):
    prompt = prompt or 'Describe this image. Mention visible text, objects, scene, and anything notable.'
    try:
        answer = ai_service.analyze_image(path, prompt, timeout=max(OLLAMA_TIMEOUT, 30))
        if answer:
            return clean_ai_response(answer)
    except AIServiceError as error:
        logger.warning(f"Vision model analysis fallback used: {error}")

    try:
        from PIL import Image
        with Image.open(path) as image:
            width, height = image.size
            return (
                f"Image uploaded successfully. Size: {width}x{height}px, format: {image.format}. "
                "Configure a vision-capable AI provider model for detailed visual analysis."
            )
    except Exception:
        return 'Image uploaded successfully. Configure a vision-capable AI provider model for detailed visual analysis.'


def initialize_database():
    """Create database tables and add missing columns for older DB files."""
    with app.app_context():
        try:
            db.create_all()
        except OperationalError as error:
            if "already exists" not in str(error).lower():
                raise
            db.session.rollback()
            logger.warning("Database table already existed during startup; continuing.")
        inspector = inspect(db.engine)

        def add_missing_columns(table_name, migrations):
            current_inspector = inspect(db.engine)
            if not current_inspector.has_table(table_name):
                db.create_all()
                current_inspector = inspect(db.engine)
            if not current_inspector.has_table(table_name):
                logger.warning(f"Skipping migration for missing table: {table_name}")
                return

            existing_columns = {
                column['name']
                for column in current_inspector.get_columns(table_name)
            }
            added_columns = []

            for column_name, column_type in migrations.items():
                if column_name not in existing_columns:
                    db.session.execute(
                        text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")
                    )
                    added_columns.append(column_name)

            if added_columns:
                db.session.commit()
                logger.info(f"Updated {table_name}: {', '.join(added_columns)}")

        add_missing_columns(ChatMessage.__tablename__, {
            'user_id': 'INTEGER',
            'session_id': 'VARCHAR(100)',
            'ai_model': 'VARCHAR(50)',
            'user_location': 'VARCHAR(200)',
            'user_timezone': 'VARCHAR(50)',
            'user_ip': 'VARCHAR(50)',
            'weather_data': 'JSON',
        })
        add_missing_columns(UserSession.__tablename__, {
            'user_id': 'INTEGER',
            'ip_address': 'VARCHAR(50)',
            'country': 'VARCHAR(100)',
            'city': 'VARCHAR(100)',
            'latitude': 'FLOAT',
            'longitude': 'FLOAT',
            'messages_count': 'INTEGER DEFAULT 0',
        })
        add_missing_columns(User.__tablename__, {
            'phone_number': 'VARCHAR(20)',
        })

        admin_email = normalize_email(ADMIN_EMAIL)
        admin_phone = normalize_phone(ADMIN_PHONE)
        admin = User.query.filter_by(username=ADMIN_USERNAME).first()
        if not admin:
            try:
                db.session.add(User(
                    username=ADMIN_USERNAME,
                    email=admin_email,
                    phone_number=admin_phone,
                    password_hash=generate_password_hash(ADMIN_PASSWORD),
                    is_admin=True,
                ))
                db.session.commit()
                logger.info(f"Created default admin user '{ADMIN_USERNAME}'")
            except IntegrityError:
                db.session.rollback()
                logger.info(f"Default admin user '{ADMIN_USERNAME}' already exists")
        else:
            changed = False
            if admin_email and not admin.email:
                admin.email = admin_email
                changed = True
            if admin_phone and not admin.phone_number:
                admin.phone_number = admin_phone
                changed = True
            if changed:
                db.session.commit()
                logger.info(f"Updated admin OTP destination for '{ADMIN_USERNAME}'")


# ============================================================================
# LOCATION & GEOLOCATION FUNCTIONS (ULTRA FAST)
# ============================================================================

def get_user_ip(request):
    """Get user IP address"""
    if request.environ.get('HTTP_X_FORWARDED_FOR'):
        return request.environ.get('HTTP_X_FORWARDED_FOR').split(',')[0]
    return request.environ.get('REMOTE_ADDR')


def get_location_from_ip(ip_address, allow_network=True):
    """Get location with in-memory cache and fallback"""
    if ip_address in ("127.0.0.1", "::1", "localhost") or ip_address.startswith("192.168.") or ip_address.startswith("10."):
        logger.info(f"Local/private IP detected ({ip_address}), using neutral location")
        return get_fallback_location(ip_address)

    # Check in-memory cache first
    cached = cached_location(ip_address)
    if cached:
        logger.info(f"🚀 In-memory location cache hit for {ip_address}")
        return cached
    
    # Check database cache
    db_cached = LocationData.query.filter_by(ip_address=ip_address).first()
    if db_cached and not db_cached.is_expired():
        location_info = {
            'ip': db_cached.ip_address,
            'country': db_cached.country,
            'country_code': '',
            'city': db_cached.city,
            'region': '',
            'latitude': db_cached.latitude,
            'longitude': db_cached.longitude,
            'timezone': db_cached.timezone,
            'isp': db_cached.isp,
            'postal': '',
        }
        location_cache[ip_address] = location_info  # Add to in-memory
        logger.info(f"📦 DB location cache hit for {ip_address}")
        return location_info

    if not allow_network:
        return get_fallback_location(ip_address)

    backoff_until = geolocation_backoff_until.get(ip_address, 0)
    if time.time() < backoff_until:
        logger.info(f"IP geolocation temporarily rate-limited for {ip_address}, using fallback")
        return get_fallback_location(ip_address)
    
    # Fetch from API with fallback
    try:
        logger.info(f"🌍 Fetching location for IP: {ip_address}")
        
        response = requests.get(
            f"{IP_GEOLOCATION_URL}/{ip_address}/json/",
            timeout=5  # Increased timeout
        )
        
        if response.status_code == 200:
            data = response.json()
            
            # Check if data is valid
            if data.get('city') and data.get('country_name'):
                location_info = {
                    'ip': ip_address,
                    'country': data.get('country_name', 'Unknown'),
                    'country_code': data.get('country_code', ''),
                    'city': data.get('city', 'Unknown'),
                    'region': data.get('region', ''),
                    'latitude': float(data.get('latitude', 0)),
                    'longitude': float(data.get('longitude', 0)),
                    'timezone': data.get('timezone', 'UTC'),
                    'isp': data.get('org', 'Unknown'),
                    'postal': data.get('postal', ''),
                }
                
                # Cache in memory and DB
                location_cache[ip_address] = location_info
                
                try:
                    if db_cached:
                        db_cached.country = location_info['country']
                        db_cached.city = location_info['city']
                        db_cached.latitude = location_info['latitude']
                        db_cached.longitude = location_info['longitude']
                        db_cached.timezone = location_info['timezone']
                        db_cached.isp = location_info['isp']
                        db_cached.last_seen = datetime.now()
                    else:
                        db_cached = LocationData(
                            ip_address=ip_address,
                            country=location_info['country'],
                            city=location_info['city'],
                            latitude=location_info['latitude'],
                            longitude=location_info['longitude'],
                            timezone=location_info['timezone'],
                            isp=location_info['isp']
                        )
                        db.session.add(db_cached)
                    
                    db.session.commit()
                except Exception as e:
                    logger.warning(f"⚠️ Could not cache location: {e}")
                    db.session.rollback()
                
                logger.info(f"✅ Location: {location_info['city']}")
                return location_info
            else:
                logger.warning("⚠️ Invalid location data, using fallback")
                return get_fallback_location(ip_address)
        
        else:
            if response.status_code == 429:
                geolocation_backoff_until[ip_address] = time.time() + GEOLOCATION_RATE_LIMIT_BACKOFF_SECONDS
                logger.warning(
                    f"IP geolocation rate limited for {ip_address}; "
                    f"using fallback for {GEOLOCATION_RATE_LIMIT_BACKOFF_SECONDS // 60} minutes"
                )
            else:
                logger.warning(f"⚠️ IP geolocation failed with status {response.status_code}, using fallback")
            return get_fallback_location(ip_address)
    
    except Exception as e:
        logger.error(f"❌ Location error: {e}, using fallback")
        return get_fallback_location(ip_address)


def get_fallback_location(ip_address='unknown'):
    """Neutral fallback for when location lookup is unavailable."""
    return {
        'ip': ip_address or 'unknown',
        'country': 'Unknown',
        'country_code': '',
        'city': 'Unknown',
        'region': '',
        'latitude': 0,
        'longitude': 0,
        'timezone': 'UTC',
        'isp': 'Local Network',
        'postal': '',
    }


def has_real_location(location_data):
    return bool(location_data and location_data.get('city') not in (None, '', 'Unknown'))


def is_valid_coordinate_pair(latitude, longitude):
    try:
        lat = float(latitude)
        lng = float(longitude)
    except (TypeError, ValueError):
        return False
    return math.isfinite(lat) and math.isfinite(lng) and (lat != 0 or lng != 0)


def get_location_from_request_payload(data):
    """Use browser-provided geolocation when the frontend has permission."""
    payload = (data or {}).get('location') or {}
    coords = payload.get('coords') or {}

    try:
        latitude = float(coords.get('lat'))
        longitude = float(coords.get('lng'))
    except (TypeError, ValueError):
        return None

    if not is_valid_coordinate_pair(latitude, longitude):
        return None

    return {
        'ip': 'browser',
        'country': payload.get('country') or 'Current location',
        'country_code': '',
        'city': payload.get('city') or 'Current location',
        'region': payload.get('region') or '',
        'latitude': latitude,
        'longitude': longitude,
        'timezone': payload.get('timezone') or 'UTC',
        'isp': 'Browser geolocation',
        'postal': '',
        'source': 'browser',
    }


def get_timezone_from_coords(latitude, longitude):
    """Get timezone (cached)"""
    if not latitude or not longitude:
        return "UTC"


def get_local_time(timezone):
    """Get local time"""
    try:
        tz = pytz.timezone(timezone)
        local_time = datetime.now(tz)
        return {
            'timezone': timezone,
            'time': local_time.strftime("%H:%M:%S"),
            'date': local_time.strftime("%Y-%m-%d"),
            'day_of_week': local_time.strftime("%A"),
            'iso': local_time.isoformat()
        }
    except Exception as e:
        return {'timezone': 'UTC', 'time': datetime.now().strftime("%H:%M:%S")}


# ============================================================================
# WEATHER FUNCTIONS (ULTRA FAST)
# ============================================================================

def get_weather_data(latitude, longitude, location_name="Unknown"):
    """Get weather with in-memory cache"""
    if not WEATHER_API_KEY or WEATHER_API_KEY == "PASTE_YOUR_NEW_OPENWEATHER_KEY_HERE":
        logger.warning("Weather API key is not configured")
        return get_neutral_weather()

    if not is_valid_coordinate_pair(latitude, longitude) or str(location_name).lower() in {'unknown', 'unknown, unknown'}:
        logger.info("Skipping weather lookup for unknown location")
        return get_neutral_weather()

    location_key = f"{location_name}_{latitude}_{longitude}"
    
    # Check in-memory cache
    cached = cached_weather(location_key)
    if cached:
        logger.info(f"🚀 In-memory weather cache hit for {location_name}")
        return cached
    
    # Check database cache
    db_cached = WeatherCache.query.filter_by(location=location_name).first()
    if db_cached and not db_cached.is_expired():
        weather_cache[location_key] = db_cached.weather_data  # Add to in-memory
        logger.info(f"📦 DB weather cache hit for {location_name}")
        return db_cached.weather_data
    
    # Fetch from API
    try:
        logger.info(f"🌤️ Fetching weather for {location_name}")
        
        response = requests.get(
            WEATHER_API_URL,
            params={
                'lat': latitude,
                'lon': longitude,
                'appid': WEATHER_API_KEY,
                'units': 'metric'
            },
            timeout=2  # Ultra-fast
        )
        
        if response.status_code == 200:
            data = response.json()
            
            weather_info = {
                'location': location_name,
                'temperature': data['main'].get('temp', 'N/A'),
                'feels_like': data['main'].get('feels_like', 'N/A'),
                'humidity': data['main'].get('humidity', 'N/A'),
                'pressure': data['main'].get('pressure', 'N/A'),
                'description': data['weather'][0].get('description', 'Unknown'),
                'wind_speed': data['wind'].get('speed', 'N/A'),
                'clouds': data['clouds'].get('all', 'N/A'),
                'sunrise': datetime.fromtimestamp(data['sys']['sunrise']).strftime("%H:%M:%S"),
                'sunset': datetime.fromtimestamp(data['sys']['sunset']).strftime("%H:%M:%S"),
                'visibility': data.get('visibility', 'N/A'),
                'updated_at': datetime.now().isoformat()
            }
            
            # Cache in memory and DB
            weather_cache[location_key] = weather_info
            
            try:
                if db_cached:
                    db_cached.weather_data = weather_info
                    db_cached.cached_at = datetime.now()
                else:
                    db_cached = WeatherCache(
                        location=location_name,
                        latitude=latitude,
                        longitude=longitude,
                        weather_data=weather_info
                    )
                    db.session.add(db_cached)
                
                db.session.commit()
            except Exception as e:
                logger.warning(f"⚠️ Could not cache weather: {e}")
                db.session.rollback()
            
            logger.info(f"✅ Weather: {weather_info['temperature']}°C")
            return weather_info
        
        else:
            logger.warning(f"⚠️ Weather API failed")
            return get_mock_weather()
    
    except Exception as e:
        logger.error(f"❌ Weather error: {e}")
        return get_mock_weather()


def is_weather_question(message):
    user_message = normalize_weather_terms(message).lower()
    return any(
        word in user_message
        for word in WEATHER_KEYWORDS
    )


def is_capital_query(message):
    user_message = message.lower().replace('captial', 'capital')
    return any(
        phrase.replace('captial', 'capital') in user_message
        for phrase in CAPITAL_KEYWORDS
    ) or bool(re.search(r'\bwhat\s+is\s+(?:the\s+)?capital\b', user_message))


def normalize_capital_subject(subject):
    if not subject:
        return None
    normalized = normalize_conversation_text(subject)
    normalized = re.sub(r'\b(state|capital|city|of|the|is|what|which|tell|me|please|pls)\b', ' ', normalized)
    normalized = re.sub(r'[^a-z\s-]', ' ', normalized)
    normalized = re.sub(r'\s+', ' ', normalized).strip()
    return normalized or None


def extract_capital_subject(message):
    normalized = normalize_conversation_text(message).replace('captial', 'capital')
    patterns = [
        r'\bcapital\s+(?:city\s+)?(?:of|for)\s+([a-zA-Z\s-]+)$',
        r'\b(?:what|which)\s+is\s+(?:the\s+)?capital\s+(?:city\s+)?(?:of|for)\s+([a-zA-Z\s-]+)$',
        r'\bstate\s+capital\s+(?:of|for)\s+([a-zA-Z\s-]+)$',
    ]
    for pattern in patterns:
        match = re.search(pattern, normalized, flags=re.IGNORECASE)
        if match:
            return normalize_capital_subject(match.group(1))
    return None


def answer_capital_query(message, session_id=None):
    subject = extract_capital_subject(message)
    context = get_session_context(session_id) if session_id else {}
    if not subject and context.get('last_intent') == 'capital':
        subject = normalize_capital_subject(context.get('last_entity') or context.get('last_topic'))
    if not subject:
        return None

    place = CAPITAL_LOOKUP.get(subject)
    if not place:
        return None

    place_name, capital = place
    return f"The capital of {place_name} is {capital}."


def is_valid_weather_location(location):
    """Reject filler fragments that are not real city/location names."""
    if not location:
        return False

    location_key = re.sub(r'\s+', ' ', location.lower()).strip(" ,.-?!")
    if location_key in NON_LOCATION_WORDS:
        return False
    if location_key.startswith(('what ', 'which ', 'how ')):
        return False

    tokens = [token for token in re.split(r'[^a-zA-Z]+', location_key) if token]
    if not tokens:
        return False

    if tokens[0] == 'the' and len(tokens) > 1:
        tokens = tokens[1:]

    if any(token in WEATHER_FILLER_WORDS or token in NON_LOCATION_WORDS for token in tokens):
        return False

    letters = re.sub(r'[^a-zA-Z]', '', location_key)
    return len(letters) >= 2


def extract_weather_location(message):
    """Extract simple locations from weather questions like 'weather of Dharamshala'."""
    normalized_message = normalize_weather_terms(message)
    weather_terms = '|'.join(re.escape(keyword) for keyword in WEATHER_KEYWORDS)
    patterns = [
        rf'\b(?:{weather_terms})\s+(?:in|at|for|of)\s+([a-zA-Z\s,-]+)',
        rf'\b(?:in|at|for|of)\s+([a-zA-Z\s,-]+)\s+(?:{weather_terms})\b',
        rf'^([a-zA-Z\s,-]+)\s+(?:{weather_terms})\b',
        rf'\b(?:{weather_terms})\s+([a-zA-Z\s,-]+)$',
    ]

    for pattern in patterns:
        match = re.search(pattern, normalized_message, re.IGNORECASE)
        if match:
            location = match.group(1)
            location = re.sub(
                r'\b(today|now|right now|currently|please|pls|current|tell me|show me|check|the)\b',
                '',
                location,
                flags=re.IGNORECASE
            )
            location = location.strip(" ,.-?!")
            if is_valid_weather_location(location):
                return location

    return None


def guess_weather_location(message):
    """Last-resort city extractor for natural weather questions."""
    normalized_message = normalize_weather_terms(message)
    cleaned = re.sub(r'[^a-zA-Z\s,-]', ' ', normalized_message.lower())
    words = [
        word for word in re.split(r'[\s,]+', cleaned)
        if word and word not in WEATHER_FILLER_WORDS
    ]
    location = ' '.join(words).strip(" ,.-?!")
    if not location:
        return None

    location_key = re.sub(r'\s+', ' ', location).strip()
    if not is_valid_weather_location(location_key):
        return None

    return location


def get_weather_data_by_city(location_name):
    """Get weather by city/place name from OpenWeather."""
    if not WEATHER_API_KEY or WEATHER_API_KEY == "PASTE_YOUR_NEW_OPENWEATHER_KEY_HERE":
        logger.warning("Weather API key is not configured")
        weather_info = get_neutral_weather()
        weather_info['location'] = location_name
        return weather_info

    location_key = re.sub(r'\s+', ' ', location_name.lower()).strip(" ,.-?!")
    query_location = LOCATION_ALIASES.get(location_key, location_name)
    requested_location = query_location
    cache_key = f"city_{query_location.lower()}"
    cached = cached_weather(cache_key)
    if cached:
        cached['location'] = requested_location
        return cached

    try:
        logger.info(f"Fetching weather by city: {query_location}")
        response = requests.get(
            WEATHER_API_URL,
            params={
                'q': query_location,
                'appid': WEATHER_API_KEY,
                'units': 'metric'
            },
            timeout=5
        )
        response.raise_for_status()
        data = response.json()
        resolved_name = requested_location or data.get('name') or query_location
        country = data.get('sys', {}).get('country')
        display_name = f"{resolved_name}, {country}" if country else resolved_name

        weather_info = {
            'location': display_name,
            'temperature': data['main'].get('temp', 'N/A'),
            'feels_like': data['main'].get('feels_like', 'N/A'),
            'humidity': data['main'].get('humidity', 'N/A'),
            'pressure': data['main'].get('pressure', 'N/A'),
            'description': data['weather'][0].get('description', 'Unknown'),
            'wind_speed': data.get('wind', {}).get('speed', 'N/A'),
            'clouds': data.get('clouds', {}).get('all', 'N/A'),
            'sunrise': datetime.fromtimestamp(data['sys']['sunrise']).strftime("%H:%M:%S"),
            'sunset': datetime.fromtimestamp(data['sys']['sunset']).strftime("%H:%M:%S"),
            'visibility': data.get('visibility', 'N/A'),
            'updated_at': datetime.now().isoformat()
        }
        weather_cache[cache_key] = weather_info
        return weather_info
    except Exception as e:
        logger.error(f"Weather city lookup failed for {location_name}: {e}")
        weather_info = get_neutral_weather()
        weather_info['location'] = location_name
        return weather_info


def format_weather_reply(weather_data):
    if not weather_data or weather_data.get('temperature') is None:
        location = weather_data.get('location', 'that place') if weather_data else 'that place'
        return f"I could not get the current weather for {location} right now. Please try again in a moment."

    return (
        f"The current weather in {weather_data['location']} is {weather_data['description']} "
        f"with a temperature of {weather_data['temperature']}°C. "
        f"It feels like {weather_data['feels_like']}°C, humidity is {weather_data['humidity']}%, "
        f"and wind speed is {weather_data['wind_speed']} m/s."
    )


def format_professional_weather_reply(weather_data):
    """Return a concise, professional weather summary."""
    if not weather_data or weather_data.get('temperature') is None:
        location = weather_data.get('location', 'that location') if weather_data else 'that location'
        return (
            f"I am unable to retrieve live weather for {location} right now. "
            "Please check the city name or try again in a moment."
        )

    location = weather_data.get('location', 'the requested location')
    description = str(weather_data.get('description', 'current conditions')).capitalize()
    temperature = weather_data.get('temperature')
    feels_like = weather_data.get('feels_like')
    humidity = weather_data.get('humidity')
    wind_speed = weather_data.get('wind_speed')
    clouds = weather_data.get('clouds')

    comfort_note = "Conditions look manageable overall."
    try:
        temp_value = float(temperature)
        if temp_value >= 35:
            comfort_note = "It is quite hot, so staying hydrated would be sensible."
        elif temp_value <= 8:
            comfort_note = "It is on the colder side, so a warm layer would help."
        elif "rain" in str(weather_data.get('description', '')).lower():
            comfort_note = "Carrying an umbrella or rain jacket would be a good idea."
        elif clouds not in (None, 'N/A') and float(clouds) >= 70:
            comfort_note = "Expect a mostly cloudy sky."
    except (TypeError, ValueError):
        pass

    return (
        f"Here is the current weather for {location}: {description}, "
        f"{temperature}°C, feeling like {feels_like}°C. "
        f"Humidity is {humidity}%, with wind at {wind_speed} m/s. "
        f"{comfort_note}"
    )


def get_mock_weather():
    """Mock weather for speed"""
    return {
        'location': 'Your Location',
        'temperature': random.uniform(15, 28),
        'feels_like': random.uniform(14, 29),
        'humidity': random.randint(40, 90),
        'pressure': random.randint(1000, 1030),
        'description': random.choice(['Sunny ☀️', 'Cloudy ☁️', 'Rainy 🌧️', 'Clear 🌙']),
        'wind_speed': random.uniform(5, 25),
        'clouds': random.randint(0, 100),
        'sunrise': '06:30:00',
        'sunset': '18:45:00',
        'visibility': 10000,
        'updated_at': datetime.now().isoformat()
    }


def get_neutral_weather():
    """Weather placeholder used when the user's location is unknown."""
    return {
        'location': 'Unknown',
        'temperature': None,
        'feels_like': None,
        'humidity': None,
        'pressure': None,
        'description': 'Unavailable',
        'wind_speed': None,
        'clouds': None,
        'sunrise': None,
        'sunset': None,
        'visibility': None,
        'updated_at': datetime.now().isoformat()
    }


# ============================================================================
# WEB SEARCH FUNCTIONS
# ============================================================================

def perform_web_search(query, max_results=5):
    """Perform web search using DuckDuckGo"""
    try:
        logger.info(f"🔍 Performing web search for: {query}")
        
        ddgs = DDGS(timeout=4)
        results = list(ddgs.text(query, max_results=max_results))
        
        if results:
            formatted_results = []
            for i, result in enumerate(results, 1):
                formatted_results.append({
                    'rank': i,
                    'title': result.get('title', 'N/A'),
                    'body': result.get('body', 'N/A')[:200],  # Truncate for brevity
                    'href': result.get('href', 'N/A')
                })
            
            logger.info(f"✅ Found {len(formatted_results)} web results")
            return formatted_results
        else:
            logger.warning("⚠️ No web search results found")
            return []
    
    except Exception as e:
        logger.error(f"❌ Web search error: {e}")
        return []


def format_web_search_response(results, original_query):
    """Format web search results into a conversational response"""
    if not results:
        return f"I couldn't find relevant web results for '{original_query}'. Please try rephrasing your question."
    
    response = f"Here's what I found online about '{original_query}':\n\n"
    
    for result in results[:3]:  # Show top 3 results
        response += f"• **{result['title']}**: {result['body']}\n"
    
    return response.strip()


def should_try_search_fallback(message):
    """Use web snippets when the local model is unavailable for factual questions."""
    msg = message.lower()
    if is_weather_question(msg) or is_capital_query(msg):
        return False

    factual_markers = (
        'what', 'who', 'where', 'when', 'why', 'how', 'define', 'meaning',
        'explain', 'tell me about', 'information about', 'details about',
        'latest', 'current', 'news', 'search', 'find',
    )
    return any(marker in msg for marker in factual_markers)


def generate_search_fallback_response(user_message, web_search_results=None):
    """Return a useful answer when Ollama is unavailable on a deployed server."""
    results = web_search_results
    if results is None and should_try_search_fallback(user_message):
        results = perform_web_search(user_message, max_results=3)

    if not results:
        return None

    return summarize_search_results(results, user_message)


def extract_knowledge_topic(message):
    """Pull a likely encyclopedia topic from a short factual question."""
    msg = re.sub(r'\s+', ' ', message.lower()).strip(" .?!")
    replacements = (
        'what is ', 'what are ', 'who is ', 'who are ', 'where is ',
        'define ', 'meaning of ', 'explain ', 'tell me about ',
        'information about ', 'details about ',
    )
    for prefix in replacements:
        if msg.startswith(prefix):
            msg = msg[len(prefix):].strip(" .?!")
            break

    msg = re.sub(r'\b(please|pls|short answer|briefly)\b', '', msg)
    msg = re.sub(r'\s+', ' ', msg).strip(" .?!")
    if not msg or len(msg) > 80:
        return None

    words = msg.split()
    if len(words) > 8:
        return None

    return msg


def fetch_wikipedia_summary(topic):
    """Fetch a concise encyclopedia summary without requiring an API key."""
    if not topic:
        return None

    headers = {'User-Agent': 'DENZ assistant educational fallback/1.0'}
    try:
        search_response = requests.get(
            'https://en.wikipedia.org/w/api.php',
            params={
                'action': 'query',
                'list': 'search',
                'srsearch': topic,
                'format': 'json',
                'srlimit': 1,
            },
            headers=headers,
            timeout=4,
        )
        search_response.raise_for_status()
        search_results = search_response.json().get('query', {}).get('search', [])
        if not search_results:
            return None

        title = search_results[0].get('title')
        if not title:
            return None

        summary_response = requests.get(
            f"https://en.wikipedia.org/api/rest_v1/page/summary/{quote(title.replace(' ', '_'))}",
            headers=headers,
            timeout=4,
        )
        summary_response.raise_for_status()
        summary_data = summary_response.json()
        extract = summary_data.get('extract')
        if not extract:
            return None

        page_url = (
            summary_data.get('content_urls', {})
            .get('desktop', {})
            .get('page')
        )
        answer = f"{title}: {extract}"
        if page_url:
            answer += f"\nSource: {page_url}"
        return answer
    except Exception as e:
        logger.warning(f"Wikipedia fallback failed for '{topic}': {e}")
        return None


def get_basic_knowledge_response(topic):
    """Small no-network fallback for common demo and school questions."""
    if not topic:
        return None

    topic_key = topic.lower().strip()
    basics = {
        'python': 'Python is a high-level programming language known for readable syntax. It is used for web development, automation, data science, AI, scripting, and many beginner programming courses.',
        'artificial intelligence': 'Artificial intelligence is the field of building computer systems that can perform tasks usually associated with human intelligence, such as understanding language, recognizing patterns, making predictions, and solving problems.',
        'ai': 'AI, or artificial intelligence, is technology that helps computers perform tasks such as understanding language, recognizing images, making predictions, and assisting with decisions.',
        'machine learning': 'Machine learning is a branch of AI where systems learn patterns from data instead of being programmed with every rule by hand.',
        'flask': 'Flask is a lightweight Python web framework used to build websites, APIs, and backend services.',
        'html': 'HTML is the standard markup language used to structure content on web pages.',
        'css': 'CSS is the language used to style web pages, including layout, colors, fonts, spacing, and responsive design.',
        'javascript': 'JavaScript is a programming language used mainly to make websites interactive, and it can also run on servers through platforms like Node.js.',
        'denz': 'DENZ is your 3D AI assistant project. It combines a Flask backend, chat, weather, maps, and an interactive 3D frontend.',
    }
    return basics.get(topic_key)


def safe_eval_math_expression(expression):
    """Evaluate simple arithmetic without executing arbitrary code."""
    import ast
    import operator

    operators = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv,
        ast.Mod: operator.mod,
        ast.Pow: operator.pow,
        ast.USub: operator.neg,
        ast.UAdd: operator.pos,
    }

    def evaluate(node):
        if isinstance(node, ast.Expression):
            return evaluate(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in operators:
            left = evaluate(node.left)
            right = evaluate(node.right)
            if isinstance(node.op, ast.Pow) and abs(right) > 10:
                raise ValueError("Exponent too large")
            return operators[type(node.op)](left, right)
        if isinstance(node, ast.UnaryOp) and type(node.op) in operators:
            return operators[type(node.op)](evaluate(node.operand))
        raise ValueError("Unsupported expression")

    if not expression or not re.fullmatch(r'[\d\s+\-*/().%^]+', expression):
        return None

    normalized = expression.replace('^', '**')
    try:
        return evaluate(ast.parse(normalized, mode='eval'))
    except Exception:
        return None


def extract_math_expression(message):
    """Find a simple arithmetic expression inside a user question."""
    normalized = message.lower()
    normalized = normalized.replace('plus', '+').replace('minus', '-')
    normalized = normalized.replace('times', '*').replace('multiplied by', '*')
    normalized = normalized.replace('divided by', '/').replace('over', '/')
    match = re.search(r'[-+*/().\d\s^%]{3,}', normalized)
    if not match:
        return None
    expression = match.group(0).strip()
    if not re.search(r'\d', expression) or not re.search(r'[+\-*/^%]', expression):
        return None
    return expression


def generate_math_fallback_response(message):
    expression = extract_math_expression(message)
    result = safe_eval_math_expression(expression) if expression else None
    if result is None:
        return None
    if isinstance(result, float) and result.is_integer():
        result = int(result)
    return f"The answer is {result}.\n\nCalculation: {expression} = {result}"


def summarize_search_results(results, original_query):
    """Turn search snippets into a cleaner assistant-style answer."""
    if not results:
        return None

    lines = [f"Here is the best answer I can build from current web results for '{original_query}':"]
    for result in results[:3]:
        title = result.get('title') or 'Result'
        body = (result.get('body') or '').strip()
        href = result.get('href') or ''
        if not body:
            continue
        lines.append(f"- {title}: {body}")
        if href and href != 'N/A':
            lines.append(f"  Source: {href}")

    if len(lines) == 1:
        return None
    return "\n".join(lines)


def generate_structured_fallback_response(user_message):
    """Produce a useful answer shape for complex prompts without pretending to know facts."""
    msg = normalize_conversation_text(user_message)
    topic = extract_knowledge_topic(user_message)

    if any(phrase in msg for phrase in ('write code', 'give code', 'create code', 'python code', 'javascript code', 'html code', 'css code')):
        return (
            "I can help with code, but I need the exact task and language to avoid giving you the wrong solution.\n\n"
            "Send it like this:\n"
            "- Language/framework\n"
            "- What input you have\n"
            "- What output you want\n"
            "- Any error message or current code\n\n"
            "Then I will give you a complete, runnable answer."
        )

    if msg.startswith('how ') or ' how to ' in msg or msg.startswith('how do '):
        subject = topic or user_message.strip(" .?!")
        return (
            f"Here is a practical way to approach {subject}:\n\n"
            "1. Define the exact goal and inputs.\n"
            "2. Break the problem into smaller steps.\n"
            "3. Solve the easiest step first and verify it works.\n"
            "4. Add the next step only after the previous one is correct.\n"
            "5. Test the final result with normal cases and edge cases.\n\n"
            "Send the specific problem details and I will solve it step by step."
        )

    if any(word in msg for word in ('difference between', 'compare', 'vs', 'versus')):
        return (
            "I can compare them, but I need the two exact things you want compared. "
            "Ask like: 'compare Flask and Django' or 'difference between AI and machine learning', "
            "and I will give you a clear table with use cases and recommendation."
        )

    if msg.startswith('why '):
        return (
            "A good way to answer a 'why' question is to identify the cause, the mechanism, and the result. "
            "Please include the exact topic or situation, and I will explain it clearly with examples."
        )

    if is_complex_question(user_message):
        return (
            "I can help with complex problems, but I need the full problem statement to solve it correctly. "
            "Please send the exact question, any data/code/error, and what answer format you need. "
            "I will then work through it step by step."
        )

    return None


def generate_knowledge_fallback_response(user_message):
    """Answer factual questions when both Ollama and search are unavailable."""
    topic = extract_knowledge_topic(user_message)
    if not topic:
        return None

    wiki_summary = fetch_wikipedia_summary(topic)
    if wiki_summary:
        return wiki_summary

    basic_response = get_basic_knowledge_response(topic)
    if basic_response:
        return basic_response

    return None


# ============================================================================
# AGENT/ROUTER SYSTEM
# ============================================================================

def extract_map_query(message):
    """Extract the place the user wants to see on a map, if one is present."""
    msg = re.sub(r'\s+', ' ', message).strip(" .?!")
    patterns = [
        r'\b(?:map|maps|direction|directions|route|navigate|navigation)\s+(?:to|for|of)?\s*([a-zA-Z0-9\s,.-]+)$',
        r'\b(?:show|open|find)\s+(?:me\s+)?(?:a\s+)?map\s+(?:of|for)?\s*([a-zA-Z0-9\s,.-]+)$',
        r'\bwhere\s+is\s+([a-zA-Z0-9\s,.-]+)$',
    ]

    for pattern in patterns:
        match = re.search(pattern, msg, re.IGNORECASE)
        if match:
            place = re.sub(
                r'\b(on map|in map|near me|please|pls|now|today)\b',
                '',
                match.group(1),
                flags=re.IGNORECASE,
            ).strip(" ,.-")
            if place:
                return place
    return None


def build_openstreetmap_search_url(place):
    encoded = requests.utils.quote(place)
    return f"https://www.openstreetmap.org/search?query={encoded}"


def build_openstreetmap_marker_url(latitude, longitude):
    return f"https://www.openstreetmap.org/?mlat={latitude}&mlon={longitude}#map=13/{latitude}/{longitude}"


def run_location_tool(message, location_data):
    """Return a concise map/location answer and structured map metadata."""
    requested_place = extract_map_query(message)
    location_data = location_data or get_fallback_location()
    has_location = has_real_location(location_data)

    if requested_place:
        map_data = {
            'type': 'place_search',
            'query': requested_place,
            'provider': 'OpenStreetMap',
            'url': build_openstreetmap_search_url(requested_place),
        }
        reply = (
            f"I can look up {requested_place} on OpenStreetMap: {map_data['url']}. "
            "Use that map result for the exact pin, nearby places, and directions."
        )
        return reply, map_data

    if has_location:
        lat = location_data.get('latitude')
        lng = location_data.get('longitude')
        city = location_data.get('city', 'your area')
        country = location_data.get('country', '')
        map_data = {
            'type': 'current_location',
            'city': city,
            'country': country,
            'lat': lat,
            'lng': lng,
            'provider': 'OpenStreetMap',
            'url': build_openstreetmap_marker_url(lat, lng),
        }
        reply = (
            f"Your network location appears to be {city}, {country} "
            f"({lat}, {lng}). Map: {map_data['url']}"
        )
        return reply, map_data

    map_data = {
        'type': 'unavailable',
        'provider': 'OpenStreetMap',
        'url': 'https://www.openstreetmap.org',
    }
    return (
        "I could not determine your current location yet. Share a city/place name, "
        "or allow browser location, and I will show the map for it."
    ), map_data

class ToolRouter:
    """Intelligent router to decide which tool to use based on user query"""
    
    @staticmethod
    def classify_intent(message):
        """Classify the user's intent to determine which tool to use"""
        msg = message.lower()
        words = set(re.findall(r'[a-z0-9]+', msg))
        
        # Weather queries
        weather_keywords = ['weather', 'temperature', 'forecast', 'rain', 'humidity', 'climate', 'hot', 'cold', 'snow']
        if any(keyword in msg for keyword in weather_keywords):
            return 'weather'
        
        # Location/maps queries
        map_keywords = {'map', 'maps', 'direction', 'directions', 'route', 'navigate', 'navigation'}
        if words.intersection(map_keywords):
            return 'maps'

        location_phrases = ['my location', 'current location', 'where am i']
        location_words = {'coordinates', 'lat', 'latitude', 'lon', 'lng', 'longitude', 'address'}
        capital_keywords = ['capital of', 'state capital', 'capital city']
        if any(phrase in msg for phrase in location_phrases + capital_keywords) or words.intersection(location_words):
            return 'location'
        
        # Web search queries: explicit search or time-sensitive requests.
        search_keywords = [
            'search', 'find online', 'look up', 'look for', 'latest',
            'news', 'current', 'recent', 'today', 'trending', 'upcoming',
            'price', 'stock', 'score', 'schedule'
        ]
        if any(keyword in msg for keyword in search_keywords):
            # Additional check: if it's a factual question about something not in our tools
            if not any(k in msg for k in ['weather', 'location', 'map', 'capital']):
                return 'web_search'
        
        # General chat
        return 'chat'
    
    @staticmethod
    def should_use_web_search(message):
        """Determine if web search would be beneficial"""
        msg = message.lower()
        
        # Questions that benefit from real-time information
        search_queries = [
            'latest', 'recent', 'new', 'current', 'today', 'news',
            'trending', 'upcoming', 'schedule', 'announce', 'released',
            'price', 'stock', 'election', 'score', 'result',
            'how to', 'tutorial', 'guide', 'best', 'top'
        ]
        
        if any(keyword in msg for keyword in search_queries):
            return True
        
        # Time-sensitive question patterns only.
        question_patterns = [
            r'^who is .* current',
            r'^what is .* latest',
            r'^when is .* upcoming',
        ]
        if any(re.match(pattern, msg) for pattern in question_patterns):
            return True
        
        return False
    
    @staticmethod
    def route_request(message, location_data):
        """Route the request to the appropriate tool"""
        intent = ToolRouter.classify_intent(message)
        
        routing_info = {
            'intent': intent,
            'should_search': False,
            'use_location': False,
            'use_weather': False,
            'use_chat': True,
            'tool': 'chat'
        }
        
        if intent == 'weather':
            routing_info['use_weather'] = True
            routing_info['use_chat'] = False
            routing_info['tool'] = 'weather'
        elif intent in ('location', 'maps'):
            routing_info['use_location'] = True
            routing_info['use_chat'] = False
            routing_info['tool'] = 'maps' if intent == 'maps' else 'location'
        elif intent == 'web_search':
            routing_info['should_search'] = True
            routing_info['use_chat'] = True
            routing_info['tool'] = 'web_search'
        
        return routing_info


# ============================================================================
# OLLAMA FUNCTIONS (ULTRA FAST)
# ============================================================================

def get_recent_chat_history(session_id, limit=6):
    """Fetch recent chat turns for the same browser/session."""
    if not session_id or session_id == 'unknown':
        return []

    messages = (
        ChatMessage.query
        .filter_by(session_id=session_id)
        .order_by(ChatMessage.timestamp.desc())
        .limit(limit)
        .all()
    )
    return list(reversed(messages))


def format_chat_history(messages):
    """Convert previous chat turns into compact prompt context."""
    history_lines = []
    for message in messages:
        history_lines.append(f"User: {message.user_message}")
        history_lines.append(f"DENZ: {message.bot_response}")
    return "\n".join(history_lines)


INCOMPLETE_QUESTION_REPLY = (
    "I did not recognize the full question yet. Please send the remaining part."
)


def is_incomplete_question(message):
    """Detect ONLY truly incomplete question fragments - be very strict."""
    normalized = re.sub(r'\s+', ' ', message.lower()).strip(" .?!")
    if not normalized:
        return False

    # Single words that alone are incomplete
    single_word_incomplete = {'what', 'who', 'where', 'why', 'how', 'tell', 'explain', 'define'}
    
    if normalized in single_word_incomplete:
        return True
    
    # Very short phrases that are obviously incomplete (2-3 words max)
    if len(normalized.split()) <= 3:
        # "tell me" alone is incomplete, but "tell me a joke" is complete
        if normalized in {'tell me', 'tell me about', 'explain to me', 'define', 'meaning'}:
            return True
    
    # Everything else is considered complete and should be answered
    return False


def get_pending_question_part(chat_history):
    """Return the last unfinished question if DENZ asked for the remaining part."""
    if not chat_history:
        return None

    last_message = chat_history[-1]
    if last_message.bot_response == INCOMPLETE_QUESTION_REPLY:
        return last_message.user_message

    return None


def get_pending_weather_question(chat_history):
    """Return the last weather question when DENZ still needs a city."""
    if not chat_history:
        return None

    last_message = chat_history[-1]
    if is_pending_weather_message(last_message):
        return last_message.user_message

    return None


def is_pending_weather_message(message):
    """Check if a stored chat is waiting for a weather city/location."""
    reply = (message.bot_response or '').lower()
    return (
        is_weather_question(message.user_message)
        and (
            'please share the city' in reply
            or 'unable to retrieve live weather' in reply
            or 'check the city name' in reply
        )
    )


def get_pending_weather_question_by_ip(user_ip, limit=12):
    """Fallback for old/cached frontends that did not send the same session id."""
    if not user_ip:
        return None

    recent_messages = (
        ChatMessage.query
        .filter_by(user_ip=user_ip)
        .order_by(ChatMessage.timestamp.desc())
        .limit(limit)
        .all()
    )

    for message in recent_messages:
        if is_weather_question(message.user_message):
            return message.user_message if is_pending_weather_message(message) else None

    return None


def weather_pending_keys(session_id, user_ip):
    return [session_id, f"ip-{user_ip}", "latest"]


def remember_pending_weather_question(session_id, user_ip, question):
    """Remember weather question immediately, before async DB save finishes."""
    for key in weather_pending_keys(session_id, user_ip):
        if key:
            pending_weather_requests[key] = question


def get_pending_weather_question_from_memory(session_id, user_ip):
    for key in weather_pending_keys(session_id, user_ip):
        question = pending_weather_requests.get(key)
        if question:
            return question
    return None


def clear_pending_weather_question(session_id, user_ip):
    for key in weather_pending_keys(session_id, user_ip):
        pending_weather_requests.pop(key, None)


def combine_question_parts(first_part, second_part):
    """Join two user fragments into one complete question."""
    return re.sub(r'\s+', ' ', f"{first_part} {second_part}").strip()


def combine_weather_question_with_location(question, location):
    """Attach a follow-up city/location to the previous weather question."""
    return re.sub(r'\s+', ' ', f"{question} in {location}").strip()


def build_ultra_fast_prompt(user_message, location_data, weather_data, local_time, chat_history=None, context_state=None, web_search_results=None):
    """Build a prompt that adapts to question complexity and ensures helpful responses."""
    history_text = format_chat_history(chat_history or [])
    history_section = f"\nPrevious conversation:\n{history_text}\n" if history_text else ""
    context_guidance = build_context_guidance(context_state or {}, user_message)
    context_section = f"\nConversation memory:\n{context_guidance}\n" if context_guidance else ""
    
    # Add web search context if available
    search_context = ""
    if web_search_results:
        search_context = "\nWeb Search Results:\n"
        for result in web_search_results[:3]:
            search_context += f"- {result['title']}: {result['body']} Source: {result['href']}\n"
        search_context += "When using web search results, mention that the answer is based on current web results and include source links when useful.\n\n"

    # Adjust response length based on question complexity
    if is_complex_question(user_message):
        length_guidance = "Reply in 4-6 sentences with detailed explanations, examples, and actionable insights."
    else:
        length_guidance = "Reply in 1-3 sentences with direct, helpful information."

    prompt = SYSTEM_PROMPT + f"""

RESPONSE STYLE:
{length_guidance}

CRITICAL BEHAVIOR:
- Answer the latest user message first.
- Use previous conversation only when the latest message is clearly a follow-up such as "more", "again", "that", or "what about it".
- If the latest message changes topic, ignore stale weather/location/topic context.
- For complex problems, solve step by step and give the final answer clearly.
- If required details are missing, ask one specific clarifying question instead of guessing.

{history_section}{context_section}{search_context}User: {user_message}
/no_think

DENZ: """
    return prompt


def is_complex_question(message):
    """Detect if a question requires detailed/complex answer."""
    msg = message.lower()
    if any(phrase in msg for phrase in ('one sentence', 'brief', 'short answer', 'quick answer')):
        return False
    
    # Questions that typically need more explanation
    complex_keywords = {
        'explain', 'how does', 'how do', 'what is', 'why', 'difference',
        'compare', 'pros and cons', 'advantages', 'disadvantages', 'benefits',
        'steps', 'process', 'method', 'technique', 'algorithm', 'concept',
        'theory', 'principle', 'definition', 'example', 'use case',
        'best practice', 'guideline', 'tutorial', 'guide', 'overview',
    }
    
    word_count = len(message.split())
    has_complex_keyword = any(keyword in msg for keyword in complex_keywords)
    
    # Questions with multiple parts or longer queries are complex
    if has_complex_keyword or word_count >= 10:
        return True
    
    return False


def get_instant_response(user_message):
    """Return quick local replies for common demo questions."""
    msg = re.sub(r'\s+', ' ', user_message.lower()).strip(" .?!")

    greetings = {'hi', 'hello', 'hey', 'hii', 'hy', 'good morning', 'good afternoon', 'good evening'}
    if msg in greetings:
        return "Hello! I am DENZ, your 3D AI assistant. Ask me anything or try the 3D controls."

    if msg in {'how are you', 'how r u', 'how are you doing'}:
        return "I am running well and ready to help. The 3D scene is active too."

    if any(phrase in msg for phrase in ('who are you', 'what are you', 'your name')):
        return "I am DENZ, a 3D AI virtual assistant with chat, visual effects, map preview, and theme controls."

    if any(word in msg for word in ('feature', 'features', 'project', 'submission')):
        return "DENZ features AI chat, a real-time 3D interface, morphing shapes, particles, map preview, theme switching, and a Flask backend."

    if any(phrase in msg for phrase in ('different', 'difference', 'other assistant', 'why use')):
        return "DENZ is different because it is not only text chat. It combines assistant replies with an interactive 3D visual experience."

    if any(word in msg for word in ('morph', 'shape', 'particle', 'rotate', '3d')):
        return "Sure. Use the 3D controls to morph shapes, rotate the object, emit particles, and switch between sphere, torus, tetrahedron, octahedron, and icosahedron."

    if msg in {'thanks', 'thank you', 'ok', 'okay'}:
        return "You are welcome."

    return None


def clean_ai_response(response_text):
    """Remove provider thinking traces and return only the user-facing answer."""
    if not response_text:
        return ""

    cleaned = re.sub(r'<think>.*?</think>', '', response_text, flags=re.IGNORECASE | re.DOTALL)
    cleaned = re.sub(
        r'^\s*Thinking\.\.\..*?\.\.\.done thinking\.\s*',
        '',
        cleaned,
        flags=re.IGNORECASE | re.DOTALL,
    )
    return cleaned.strip()


def clean_ollama_response(response_text):
    """Backward-compatible alias for older tests/helpers."""
    return clean_ai_response(response_text)


def is_ollama_in_backoff():
    return time.time() < ai_backoff_until


def mark_ollama_unavailable():
    global ai_backoff_until
    ai_backoff_until = time.time() + OLLAMA_FAILURE_BACKOFF_SECONDS


def get_ai_response_ultra_fast(user_message, location_data, weather_data, local_time, chat_history=None, session_id=None, web_search_results=None):
    """AI response with retry mechanism, caching, and provider fallback."""
    chat_history = chat_history or []

    if is_ollama_in_backoff():
        logger.warning("AI provider is in temporary backoff; using fallback response")
        return generate_smart_fallback(user_message, location_data, weather_data, local_time, web_search_results)

    # Check response cache
    history_key = "|".join(f"{item.user_message}:{item.bot_response}" for item in chat_history[-3:])
    message_key = f"{ai_service.provider_name}_{ai_service.model_name}_with_history_v1_{history_key}_{user_message}"
    cached_resp = cached_response(message_key)
    if cached_resp:
        logger.info("🚀 Response cache hit")
        return cached_resp
    
    # Retry mechanism for failed requests
    max_retries = 2
    last_error = None
    
    for attempt in range(max_retries):
        try:
            prompt = build_ultra_fast_prompt(
                user_message,
                location_data,
                weather_data,
                local_time,
                chat_history,
                get_session_context(session_id),
                web_search_results,
            )
            
            # Determine token limit based on question complexity
            is_complex = is_complex_question(user_message)
            num_predict = 300 if is_complex else 96
            max_response_length = 1500 if is_complex else 500
            
            # Adaptive timeout: longer for complex questions
            timeout = min(OLLAMA_TIMEOUT * 2, 120) if is_complex else OLLAMA_TIMEOUT
            
            logger.info(f"📤 Ollama request (attempt {attempt + 1}/{max_retries}, complexity: {'HIGH' if is_complex else 'LOW'}, timeout: {timeout}s)")
            logger.info(f"   Question: {user_message[:60]}")
            
            ai_response = clean_ai_response(
                ai_service.generate_text(
                    prompt,
                    temperature=0.3,
                    max_tokens=num_predict,
                    timeout=timeout,
                )
            )
            
            if ai_response:
                if len(ai_response) > max_response_length:
                    ai_response = ai_response[:max_response_length] + "..."
                
                # Cache response
                response_cache[message_key] = ai_response
                
                logger.info(f"✅ Response: {ai_response[:60]}")
                return ai_response
            
            logger.warning(f"⚠️ Ollama returned empty response (attempt {attempt + 1})")
            last_error = "Empty response"
            
            # Retry if empty response
            if attempt < max_retries - 1:
                import time
                time.sleep(0.5)
                continue
        
        except requests.exceptions.Timeout as e:
            logger.warning(f"⏱️ Timeout on attempt {attempt + 1}/{max_retries}")
            last_error = str(e)
            mark_ollama_unavailable()
            if attempt < max_retries - 1:
                import time
                time.sleep(1)  # Wait before retry
                continue
        except requests.exceptions.ConnectionError as e:
            logger.warning(f"🔌 Connection error on attempt {attempt + 1}/{max_retries}: {e}")
            last_error = str(e)
            mark_ollama_unavailable()
            if attempt < max_retries - 1:
                import time
                time.sleep(1)
                continue
        except Exception as e:
            logger.error(f"❌ Error on attempt {attempt + 1}/{max_retries}: {e}")
            last_error = str(e)
            if attempt < max_retries - 1:
                import time
                time.sleep(0.5)
                continue
    
    logger.error(f"❌ Ollama failed after {max_retries} attempts: {last_error}")
    return generate_smart_fallback(user_message, location_data, weather_data, local_time, web_search_results)


def get_ollama_response_ultra_fast(user_message, location_data, weather_data, local_time, chat_history=None, session_id=None, web_search_results=None):
    """Backward-compatible wrapper for older route/test names."""
    return get_ai_response_ultra_fast(
        user_message,
        location_data,
        weather_data,
        local_time,
        chat_history,
        session_id,
        web_search_results,
    )


def generate_smart_fallback(user_message, location_data, weather_data, local_time, web_search_results=None):
    """Generate intelligent fallback responses when the AI provider fails."""
    msg = user_message.lower()
    math_fallback = generate_math_fallback_response(user_message)
    if math_fallback:
        return math_fallback

    search_fallback = generate_search_fallback_response(user_message, web_search_results)
    if search_fallback:
        return search_fallback

    knowledge_fallback = generate_knowledge_fallback_response(user_message)
    if knowledge_fallback:
        return knowledge_fallback

    structured_fallback = generate_structured_fallback_response(user_message)
    if structured_fallback:
        return structured_fallback
    
    # Location/Place questions
    if any(word in msg for word in ['where', 'location', 'city', 'state', 'country', 'lies', 'situated', 'located', 'capital']):
        # Extract the place name from the question
        place_match = None
        patterns = [
            r'(?:where|location|city|state).*?(?:is|lies|in|of)?\s+([a-zA-Z\s]+)(?:\s+lies|\s+in|\s+located|$)',
            r'([a-zA-Z\s]+)\s+(?:lies|is|located|in)\s+(?:which|what)',
            r'(?:which|what)\s+(?:state|country|location|place).*?([a-zA-Z\s]+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, msg, re.IGNORECASE)
            if match:
                place_match = match.group(1).strip().title()
                break
        
        if place_match and place_match not in {'Which', 'What', 'State', 'Country', 'Location', 'Place'}:
            return f"I apologize - I'm having temporary difficulty retrieving detailed information about {place_match} right now. However, {place_match} is a place in India. For specific state/location details, please try again in a moment."
        
        return "I'm temporarily unable to retrieve location information. Please ask again in a moment, and I'll provide details about the place you're asking about."
    
    # General knowledge questions
    if any(word in msg for word in ['what', 'who', 'define', 'mean', 'meaning', 'explain']):
        # Extract what they're asking about
        question_about = msg.replace('what is', '').replace('what are', '').replace('who is', '').replace('define', '').replace('meaning of', '').replace('explain', '').strip()
        if question_about:
            return f"I could not find enough reliable information about '{question_about}' right now. Try asking it in a simpler way, or include a few more details."
        return "I could not find enough reliable information for that question right now. Try rephrasing it or asking for weather, maps, or a specific topic."
    
    # How/Why questions
    if any(word in msg for word in ['how', 'why', 'describe', 'tell me', 'explain']):
        return "I could not find enough reliable information for that question right now. Try asking it in a simpler or more specific way."
    
    # Acknowledgment that we got their question but have issues
    if user_message.strip():
        return f"I received your question about '{user_message[:50]}...' but I do not have enough information to answer it well right now. Please try asking with more detail."
    
    # Absolute fallback
    return "I'm currently having technical difficulties. Please try your question again in a moment!"


# ============================================================================
# 3D EFFECT DETECTION
# ============================================================================

def get_3d_effect_from_text(user_message):
    """Fast effect detection"""
    msg = user_message.lower()
    
    if any(word in msg for word in ['rotate', 'spin', 'turn', 'twist']):
        return 'rotate'
    elif any(word in msg for word in ['scale', 'grow', 'bigger', 'zoom']):
        return 'scale'
    elif any(word in msg for word in ['morph', 'transform', 'change']):
        return 'morph'
    elif any(word in msg for word in ['particle', 'burst', 'effect']):
        return 'particle'
    
    return None


# ============================================================================
# 3D DATA GENERATION
# ============================================================================

def generate_particles(count=1000):
    """Generate particle data"""
    particles = []
    for i in range(count):
        particles.append({
            'id': i,
            'position': {
                'x': random.uniform(-5, 5),
                'y': random.uniform(-5, 5),
                'z': random.uniform(-5, 5),
            },
            'velocity': {
                'x': random.uniform(-2, 2),
                'y': random.uniform(-2, 2),
                'z': random.uniform(-2, 2),
            },
            'size': random.uniform(0.1, 2.0),
            'lifetime': random.uniform(1, 5),
            'color': {
                'r': random.random(),
                'g': random.random(),
                'b': random.random(),
            }
        })
    return particles


def generate_animation_keyframes(duration=3.0, fps=60):
    """Generate animation keyframes"""
    total_frames = int(duration * fps)
    keyframes = []
    
    for frame in range(total_frames):
        progress = frame / total_frames
        eased = easing_cubic_in_out(progress)
        
        keyframes.append({
            'frame': frame,
            'progress': progress,
            'eased': eased,
            'position': {
                'x': math.sin(progress * math.pi * 2) * 5,
                'y': math.cos(progress * math.pi * 2) * 5,
                'z': progress * 10,
            },
            'rotation': {
                'x': progress * math.pi * 2,
                'y': progress * math.pi * 4,
                'z': progress * math.pi,
            },
            'scale': {
                'x': 1.0 + math.sin(progress * math.pi) * 0.3,
                'y': 1.0 + math.sin(progress * math.pi) * 0.3,
                'z': 1.0 + math.sin(progress * math.pi) * 0.3,
            }
        })
    
    return keyframes


def easing_cubic_in_out(t):
    """Cubic easing"""
    if t < 0.5:
        return 4 * t * t * t
    else:
        return 1 - pow(-2 * t + 2, 3) / 2


# ============================================================================
# FLASK ROUTES - PAGES
# ============================================================================

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/chat')
def chat_page():
    return render_template('chat.html')


@app.route('/admin')
@admin_required
def admin_dashboard_page():
    return render_template('admin.html')


@app.route('/about')
def about():
    return render_template('about.html')


@app.route('/static/<path:filename>')
def serve_static(filename):
    return send_from_directory('static', filename)


# ============================================================================
# AUTH API
# ============================================================================

@app.route('/api/auth/register', methods=['POST'])
def register_user():
    try:
        data = request.get_json() or {}
        email = normalize_email(data.get('email'))
        phone_number = None
        otp_channel = 'email'

        if not email:
            return jsonify({'error': 'Enter a valid email address for OTP.', 'success': False}), 400

        existing_filters = []
        if email:
            existing_filters.append(User.email == email)
        if phone_number:
            existing_filters.append(User.phone_number == phone_number)
        existing = User.query.filter(or_(*existing_filters)).first()
        if existing:
            return jsonify({'error': 'That email or phone is already registered.', 'success': False}), 409

        otp_payload = start_registration_otp(
            email=email,
            phone_number=phone_number,
            channel=otp_channel,
        )
        return jsonify(otp_payload), 201
    except ValueError as error:
        db.session.rollback()
        return jsonify({'error': str(error), 'success': False}), 400
    except OTPDeliveryError as error:
        db.session.rollback()
        return jsonify({'error': str(error), 'success': False}), 502
    except RuntimeError as error:
        db.session.rollback()
        logger.error(f"OTP delivery not configured: {error}")
        return jsonify({'error': str(error), 'success': False}), 503
    except Exception as error:
        db.session.rollback()
        logger.error(f"Register error: {error}")
        return jsonify({'error': 'Registration failed', 'success': False}), 500


@app.route('/api/auth/complete-registration', methods=['POST'])
def complete_registration():
    try:
        data = request.get_json() or {}
        username = (data.get('username') or '').strip()
        password = data.get('password') or ''
        code = re.sub(r'\D', '', data.get('otp') or data.get('code') or '')
        pending = session.get('pending_registration') or {}

        if not pending:
            return jsonify({'error': 'No verified registration is pending. Start registration again.', 'success': False}), 400
        if time.time() > float(pending.get('expires_at', 0)):
            session.pop('pending_registration', None)
            return jsonify({'error': 'OTP expired. Start registration again.', 'success': False}), 400
        if len(code) != 6:
            return jsonify({'error': 'Enter the 6-digit OTP.', 'success': False}), 400
        if len(username) < 3 or len(password) < 6:
            return jsonify({'error': 'Username must be 3+ chars and password 6+ chars.', 'success': False}), 400

        attempts = int(pending.get('attempts', 0)) + 1
        pending['attempts'] = attempts
        session['pending_registration'] = pending
        if attempts > 5:
            session.pop('pending_registration', None)
            return jsonify({'error': 'Too many OTP attempts. Start registration again.', 'success': False}), 429
        if not check_password_hash(pending.get('code_hash', ''), code):
            return jsonify({'error': 'Incorrect OTP.', 'success': False}), 401

        duplicate_filters = [User.username == username]
        if pending.get('email'):
            duplicate_filters.append(User.email == pending['email'])
        if pending.get('phone_number'):
            duplicate_filters.append(User.phone_number == pending['phone_number'])
        if User.query.filter(or_(*duplicate_filters)).first():
            return jsonify({'error': 'That username, email, or phone is already registered.', 'success': False}), 409

        user = User(
            username=username,
            email=pending.get('email'),
            phone_number=pending.get('phone_number'),
            password_hash=generate_password_hash(password),
            is_admin=False,
            last_login=datetime.now(),
        )
        db.session.add(user)
        db.session.commit()
        session.pop('pending_registration', None)
        session['user_id'] = user.id
        return jsonify({'user': user.to_dict(), 'success': True}), 200
    except Exception as error:
        db.session.rollback()
        logger.error(f"Complete registration error: {error}")
        return jsonify({'error': 'Registration completion failed', 'success': False}), 500


@app.route('/api/auth/login', methods=['POST'])
def login_user():
    try:
        data = request.get_json() or {}
        identifier = (data.get('username') or data.get('email') or '').strip()
        password = data.get('password') or ''

        normalized_email = normalize_email(identifier)
        normalized_phone = normalize_phone(identifier)
        filters = [User.username == identifier]
        if normalized_email:
            filters.append(User.email == normalized_email)
        if normalized_phone:
            filters.append(User.phone_number == normalized_phone)
        user = User.query.filter(or_(*filters)).first()
        if not user or not user.verify_password(password):
            return jsonify({'error': 'Invalid username or password', 'success': False}), 401

        otp_channel = 'email' if user.email else 'phone'
        return jsonify(start_login_otp(user, otp_channel)), 200
    except ValueError as error:
        return jsonify({'error': str(error), 'success': False}), 400
    except OTPDeliveryError as error:
        return jsonify({'error': str(error), 'success': False}), 502
    except RuntimeError as error:
        logger.error(f"OTP delivery not configured: {error}")
        return jsonify({'error': str(error), 'success': False}), 503
    except Exception as error:
        logger.error(f"Login error: {error}")
        return jsonify({'error': 'Login failed', 'success': False}), 500


@app.route('/api/auth/recovery/start', methods=['POST'])
def start_account_recovery():
    try:
        data = request.get_json() or {}
        identifier = (data.get('identifier') or data.get('email') or data.get('phone') or '').strip()
        normalized_email = normalize_email(identifier)
        normalized_phone = normalize_phone(identifier)

        filters = []
        if normalized_email:
            filters.append(User.email == normalized_email)
        if normalized_phone:
            filters.append(User.phone_number == normalized_phone)
        if not filters:
            return jsonify({'error': 'Enter a valid registered email or phone number.', 'success': False}), 400

        user = User.query.filter(or_(*filters)).first()
        if not user:
            return jsonify({'error': 'No account found for that email or phone.', 'success': False}), 404

        return jsonify(start_recovery_otp(user)), 200
    except OTPDeliveryError as error:
        return jsonify({'error': str(error), 'success': False}), 502
    except RuntimeError as error:
        logger.error(f"Recovery OTP delivery not configured: {error}")
        return jsonify({'error': str(error), 'success': False}), 503
    except Exception as error:
        logger.error(f"Recovery start error: {error}")
        return jsonify({'error': 'Recovery failed to start', 'success': False}), 500


@app.route('/api/auth/recovery/complete', methods=['POST'])
def complete_account_recovery():
    try:
        data = request.get_json() or {}
        code = re.sub(r'\D', '', data.get('otp') or data.get('code') or '')
        new_password = data.get('new_password') or data.get('password') or ''
        pending = session.get('pending_recovery') or {}

        if not pending:
            return jsonify({'error': 'No recovery is pending. Start recovery again.', 'success': False}), 400
        if time.time() > float(pending.get('expires_at', 0)):
            session.pop('pending_recovery', None)
            return jsonify({'error': 'OTP expired. Start recovery again.', 'success': False}), 400
        if len(code) != 6:
            return jsonify({'error': 'Enter the 6-digit OTP.', 'success': False}), 400

        attempts = int(pending.get('attempts', 0)) + 1
        pending['attempts'] = attempts
        session['pending_recovery'] = pending
        if attempts > 5:
            session.pop('pending_recovery', None)
            return jsonify({'error': 'Too many OTP attempts. Start recovery again.', 'success': False}), 429
        if not check_password_hash(pending.get('code_hash', ''), code):
            return jsonify({'error': 'Incorrect OTP.', 'success': False}), 401

        user = db.session.get(User, pending.get('user_id'))
        if not user:
            session.pop('pending_recovery', None)
            return jsonify({'error': 'Account not found. Start recovery again.', 'success': False}), 400

        password_updated = False
        if new_password:
            if len(new_password) < 6:
                return jsonify({'error': 'New password must be at least 6 characters.', 'success': False}), 400
            user.password_hash = generate_password_hash(new_password)
            password_updated = True
            db.session.commit()

        session.pop('pending_recovery', None)
        return jsonify({
            'username': user.username,
            'password_updated': password_updated,
            'message': 'Recovery complete.',
            'success': True,
        }), 200
    except Exception as error:
        db.session.rollback()
        logger.error(f"Recovery complete error: {error}")
        return jsonify({'error': 'Recovery failed', 'success': False}), 500


@app.route('/api/auth/verify-otp', methods=['POST'])
def verify_login_otp():
    try:
        data = request.get_json() or {}
        code = re.sub(r'\D', '', data.get('otp') or data.get('code') or '')
        pending = session.get('pending_otp') or {}

        if not pending:
            return jsonify({'error': 'No OTP login is pending. Start login again.', 'success': False}), 400
        if time.time() > float(pending.get('expires_at', 0)):
            session.pop('pending_otp', None)
            return jsonify({'error': 'OTP expired. Start login again.', 'success': False}), 400
        if len(code) != 6:
            return jsonify({'error': 'Enter the 6-digit OTP.', 'success': False}), 400

        attempts = int(pending.get('attempts', 0)) + 1
        pending['attempts'] = attempts
        session['pending_otp'] = pending
        if attempts > 5:
            session.pop('pending_otp', None)
            return jsonify({'error': 'Too many OTP attempts. Start login again.', 'success': False}), 429

        if not check_password_hash(pending.get('code_hash', ''), code):
            return jsonify({'error': 'Incorrect OTP.', 'success': False}), 401

        user = db.session.get(User, pending.get('user_id'))
        if not user:
            session.pop('pending_otp', None)
            return jsonify({'error': 'User not found. Start login again.', 'success': False}), 400

        user.last_login = datetime.now()
        db.session.commit()
        session.pop('pending_otp', None)
        session['user_id'] = user.id
        return jsonify({'user': user.to_dict(), 'success': True}), 200
    except Exception as error:
        logger.error(f"OTP verify error: {error}")
        return jsonify({'error': 'OTP verification failed', 'success': False}), 500


@app.route('/api/auth/logout', methods=['POST'])
def logout_user():
    session.pop('user_id', None)
    session.pop('pending_otp', None)
    session.pop('pending_registration', None)
    session.pop('pending_recovery', None)
    return jsonify({'success': True}), 200


@app.route('/api/auth/me', methods=['GET'])
def auth_me():
    user = get_current_user()
    return jsonify({'user': user.to_dict() if user else None, 'authenticated': bool(user), 'success': True}), 200


@app.route('/api/auth/otp/config', methods=['GET'])
def otp_config_check():
    """Expose masked OTP config so local setup problems are easy to diagnose."""
    return jsonify({'config': otp_config_status(), 'success': True}), 200


# ============================================================================
# FILE AND IMAGE API
# ============================================================================

@app.route('/api/files/upload', methods=['POST'])
def upload_document():
    try:
        uploaded = request.files.get('file')
        session_id = request.form.get('session_id') or 'unknown'
        if not uploaded or not uploaded.filename:
            return jsonify({'error': 'No file uploaded', 'success': False}), 400
        if not allowed_file(uploaded.filename, ALLOWED_DOCUMENT_EXTENSIONS):
            return jsonify({'error': 'Only PDF, DOCX, TXT, and MD files are supported.', 'success': False}), 400

        original_name, stored_name, stored_path = save_uploaded_file(uploaded, 'doc')
        extension = original_name.rsplit('.', 1)[1].lower()
        extracted_text = extract_text_from_document(stored_path, extension)
        summary = summarize_uploaded_text(extracted_text)

        record = UploadedFile(
            user_id=current_user_id(),
            session_id=session_id,
            filename=original_name,
            stored_filename=stored_name,
            file_type=extension,
            mime_type=uploaded.mimetype,
            size_bytes=os.path.getsize(stored_path),
            extracted_text=extracted_text[:12000] if extracted_text else '',
            analysis=summary,
        )
        db.session.add(record)
        db.session.commit()

        return jsonify({'file': record.to_dict(), 'summary': summary, 'success': True}), 200
    except Exception as error:
        db.session.rollback()
        logger.error(f"Upload error: {error}")
        return jsonify({'error': 'File upload failed', 'success': False}), 500


@app.route('/api/images/analyze', methods=['POST'])
def analyze_image():
    try:
        uploaded = request.files.get('image') or request.files.get('file')
        session_id = request.form.get('session_id') or 'unknown'
        prompt = (request.form.get('prompt') or '').strip()
        if not uploaded or not uploaded.filename:
            return jsonify({'error': 'No image uploaded', 'success': False}), 400
        if not allowed_file(uploaded.filename, ALLOWED_IMAGE_EXTENSIONS):
            return jsonify({'error': 'Only PNG, JPG, JPEG, WEBP, and GIF images are supported.', 'success': False}), 400

        original_name, stored_name, stored_path = save_uploaded_file(uploaded, 'image')
        analysis = analyze_image_file(stored_path, prompt)
        extension = original_name.rsplit('.', 1)[1].lower()

        record = UploadedFile(
            user_id=current_user_id(),
            session_id=session_id,
            filename=original_name,
            stored_filename=stored_name,
            file_type=extension,
            mime_type=uploaded.mimetype,
            size_bytes=os.path.getsize(stored_path),
            analysis=analysis,
        )
        db.session.add(record)
        db.session.commit()

        return jsonify({'file': record.to_dict(), 'analysis': analysis, 'success': True}), 200
    except Exception as error:
        db.session.rollback()
        logger.error(f"Image analysis error: {error}")
        return jsonify({'error': 'Image analysis failed', 'success': False}), 500


@app.route('/api/uploads', methods=['GET'])
def list_uploads():
    try:
        user_id = current_user_id()
        session_id = request.args.get('session_id', '').strip()
        query = UploadedFile.query
        if user_id:
            query = query.filter_by(user_id=user_id)
        elif session_id:
            query = query.filter_by(session_id=session_id)
        else:
            return jsonify({'uploads': [], 'success': True}), 200
        uploads = query.order_by(UploadedFile.created_at.desc()).limit(50).all()
        return jsonify({'uploads': [item.to_dict() for item in uploads], 'success': True}), 200
    except Exception:
        return jsonify({'uploads': [], 'success': False}), 500


@app.route('/api/admin/dashboard', methods=['GET'])
@admin_required
def admin_dashboard_data():
    try:
        users = User.query.order_by(User.created_at.desc()).limit(20).all()
        recent_messages = ChatMessage.query.order_by(ChatMessage.timestamp.desc()).limit(20).all()
        recent_uploads = UploadedFile.query.order_by(UploadedFile.created_at.desc()).limit(20).all()
        return jsonify({
            'stats': {
                'users': User.query.count(),
                'messages': ChatMessage.query.count(),
                'sessions': UserSession.query.count(),
                'uploads': UploadedFile.query.count(),
            },
            'users': [user.to_dict() for user in users],
            'messages': [message.to_dict() for message in recent_messages],
            'uploads': [upload.to_dict() for upload in recent_uploads],
            'success': True,
        }), 200
    except Exception as error:
        logger.error(f"Admin dashboard error: {error}")
        return jsonify({'error': 'Admin dashboard failed', 'success': False}), 500


def save_chat_message_to_db(session_id, user_message, bot_response, effect, location_data, timezone, user_ip, weather_data, user_id=None):
    """Persist a chat turn and keep user-session counters in sync."""
    with app.app_context():
        try:
            chat_msg = ChatMessage(
                user_id=user_id,
                session_id=session_id,
                user_message=user_message,
                bot_response=bot_response,
                effect_triggered=effect,
                ai_model=AI_MODEL,
                user_location=f"{location_data['city']}, {location_data['country']}",
                user_timezone=timezone,
                user_ip=user_ip,
                weather_data=weather_data
            )
            db.session.add(chat_msg)

            session = UserSession.query.filter_by(session_id=session_id).first()
            if session:
                if user_id and not session.user_id:
                    session.user_id = user_id
                session.messages_count += 1
                session.last_active = datetime.now()
            else:
                session = UserSession(
                    user_id=user_id,
                    session_id=session_id,
                    ip_address=user_ip,
                    country=location_data['country'],
                    city=location_data['city'],
                    latitude=location_data['latitude'],
                    longitude=location_data['longitude'],
                    messages_count=1
                )
                db.session.add(session)

            db.session.commit()
        except Exception as db_error:
            logger.error(f"⚠️ DB error: {db_error}")
            db.session.rollback()


# ============================================================================
# FLASK ROUTES - LOCATION API
# ============================================================================

@app.route('/api/location', methods=['GET'])
def get_location():
    try:
        user_ip = get_user_ip(request)
        logger.info(f"🔍 Location request from IP: {user_ip}")
        
        location = get_location_from_ip(user_ip)
        
        if location:
            timezone = get_timezone_from_coords(location['latitude'], location['longitude'])
            location['timezone'] = timezone
            local_time = get_local_time(timezone)
            weather = get_weather_data(location['latitude'], location['longitude'], f"{location['city']}, {location['country']}")
            
            return jsonify({
                'location': location,
                'timezone': timezone,
                'local_time': local_time,
                'weather': weather,
                'success': True
            }), 200
        
        return jsonify({'error': 'Could not determine location', 'success': False}), 400
    
    except Exception as e:
        logger.error(f"❌ Location error: {e}")
        return jsonify({'error': str(e), 'success': False}), 500


# ============================================================================
# FLASK ROUTES - WEATHER API
# ============================================================================

@app.route('/api/weather', methods=['POST'])
def get_weather():
    try:
        data = request.get_json()
        latitude = data.get('latitude')
        longitude = data.get('longitude')
        location_name = data.get('location', 'Unknown')
        
        if not latitude or not longitude:
            return jsonify({'error': 'Missing coordinates', 'success': False}), 400
        
        weather = get_weather_data(latitude, longitude, location_name)
        
        return jsonify({'weather': weather, 'success': True}), 200
    
    except Exception as e:
        logger.error(f"❌ Weather error: {e}")
        return jsonify({'error': str(e), 'success': False}), 500


# ============================================================================
# FLASK ROUTES - CHAT API (ULTRA FAST)
# ============================================================================

@app.route('/api/chat', methods=['POST'])
def api_chat():
    start_time = time.time()
    
    try:
        logger.info("🔄 ULTRA FAST CHAT REQUEST WITH INTELLIGENT ROUTING")
        
        data = request.get_json()
        user_ip = get_user_ip(request)
        user_id = current_user_id()
        
        if not data:
            return jsonify({'reply': 'No data received', 'success': False}), 400
        
        raw_user_message = data.get('message', '').strip()
        raw_session_id = data.get('session_id')
        session_id = raw_session_id or 'unknown'
        if session_id == 'unknown':
            session_id = f"ip-{user_ip}"
        
        if not raw_user_message:
            return jsonify({'reply': 'Please enter a message', 'success': False}), 400

        user_message = resolve_followup_message(raw_user_message, session_id)
        chat_history = get_recent_chat_history(session_id)
        
        # ===== LOCATION CONTEXT =====
        location_data = get_location_from_request_payload(data)
        if not location_data:
            location_data = get_location_from_ip(user_ip, allow_network=True)
        location_data = location_data or {
            'city': 'Unknown', 'country': 'Unknown', 'latitude': 0, 'longitude': 0, 'timezone': 'UTC'
        }
        
        pending_question_part = get_pending_question_part(chat_history)
        pending_weather_question = None
        if not pending_question_part:
            pending_weather_question = (
                get_pending_weather_question_from_memory(session_id, user_ip)
                or get_pending_weather_question(chat_history)
            )
        context_state = get_session_context(session_id)
        if (
            pending_weather_question
            and context_state.get('last_intent')
            and context_state.get('last_intent') != 'weather'
            and not is_weather_question(user_message)
        ):
            pending_weather_question = None
        if (
            not pending_question_part
            and not pending_weather_question
            and not is_weather_question(user_message)
            and is_valid_weather_location(user_message)
            and not raw_session_id
        ):
            pending_weather_question = get_pending_weather_question_by_ip(user_ip)

        if pending_weather_question and not is_valid_weather_location(user_message):
            clear_pending_weather_question(session_id, user_ip)
            pending_weather_question = None

        effective_message = (
            combine_question_parts(pending_question_part, user_message)
            if pending_question_part
            else combine_weather_question_with_location(pending_weather_question, user_message)
            if (
                pending_weather_question
                and not is_weather_question(user_message)
                and is_valid_weather_location(user_message)
            )
            else user_message
        )

        # ===== INTELLIGENT ROUTING =====
        routing_info = ToolRouter.route_request(effective_message, location_data)
        logger.info(f"Router Intent: {routing_info['intent']} | Tool: {routing_info['tool']} | Search: {routing_info['should_search']} | Weather: {routing_info['use_weather']} | Location: {routing_info['use_location']}")
        
        # ===== GET WEB SEARCH RESULTS IF NEEDED =====
        web_search_results = None
        if routing_info['should_search'] and ToolRouter.should_use_web_search(effective_message):
            logger.info(f"Fetching web search results for: {effective_message}")
            web_search_results = perform_web_search(effective_message, max_results=5)

        user_is_weather_question = is_weather_question(user_message)
        is_capital_query_request = is_capital_query(effective_message)
        if (
            not pending_question_part
            and not user_is_weather_question
            and not is_capital_query_request
            and is_incomplete_question(raw_user_message)
        ):
            is_weather = False
            instant_response = None
        else:
            is_weather = is_weather_question(effective_message)
            instant_response = None if is_weather else get_instant_response(effective_message)
        weather_question = is_weather

        timezone = location_data.get('timezone') or get_timezone_from_coords(location_data['latitude'], location_data['longitude'])
        local_time = get_local_time(timezone)
        
        requested_weather_location = None
        if is_weather:
            requested_weather_location = extract_weather_location(effective_message) or guess_weather_location(effective_message)

        map_data = None
        if (
            not pending_question_part
            and not user_is_weather_question
            and not is_capital_query_request
            and is_incomplete_question(user_message)
        ):
            weather_data = get_neutral_weather()
            ai_response = INCOMPLETE_QUESTION_REPLY
        elif instant_response:
            weather_data = get_neutral_weather()
            ai_response = instant_response
        else:
            if routing_info['use_location'] and not is_capital_query_request:
                weather_data = get_neutral_weather()
                ai_response, map_data = run_location_tool(effective_message, location_data)
            elif is_capital_query_request:
                weather_data = get_neutral_weather()
                ai_response = answer_capital_query(effective_message, session_id)
                if not ai_response:
                    ai_response = get_ollama_response_ultra_fast(
                        effective_message,
                        location_data,
                        weather_data,
                        local_time,
                        chat_history,
                        session_id,
                        web_search_results,
                    )
            elif is_weather:
                # Weather code
                if not requested_weather_location and not has_real_location(location_data):
                    weather_data = get_neutral_weather()
                    ai_response = "Please share the city or location you want the current weather for, and I will check it for you."
                    remember_pending_weather_question(session_id, user_ip, effective_message)
                elif requested_weather_location:
                    weather_data = get_weather_data_by_city(requested_weather_location)
                    ai_response = format_professional_weather_reply(weather_data)
                    clear_pending_weather_question(session_id, user_ip)
                else:
                    weather_data = get_weather_data(
                        location_data['latitude'], location_data['longitude'],
                        f"{location_data['city']}, {location_data['country']}"
                    )
                    ai_response = format_professional_weather_reply(weather_data)
                    clear_pending_weather_question(session_id, user_ip)
            else:
                # General chat with optional web search augmentation
                weather_data = get_neutral_weather()
                ai_response = get_ollama_response_ultra_fast(
                    effective_message,
                    location_data,
                    weather_data,
                    local_time,
                    chat_history,
                    session_id,
                    web_search_results,  # Pass web search results for context
                )

        update_conversation_memory(
            session_id,
            raw_user_message,
            ai_response,
            effective_message,
            weather_question=weather_question,
            requested_weather_location=requested_weather_location,
        )
        
        effect = get_3d_effect_from_text(effective_message)
        should_persist_synchronously = (
            weather_question
            and not requested_weather_location
            and not has_real_location(location_data)
        )

        if should_persist_synchronously:
            save_chat_message_to_db(
                session_id,
                raw_user_message,
                ai_response,
                effect,
                location_data,
                timezone,
                user_ip,
                weather_data,
                user_id,
            )
        else:
            threading.Thread(
                target=save_chat_message_to_db,
                args=(
                    session_id,
                    raw_user_message,
                    ai_response,
                    effect,
                    location_data,
                    timezone,
                    user_ip,
                    weather_data,
                    user_id,
                ),
                daemon=True,
            ).start()

        response_time = round(time.time() - start_time, 2)
        
        response = {
            'reply': ai_response,
            'response': ai_response,
            'effect': effect,
            '3d_effect': effect,
            'location': {
                'city': location_data['city'],
                'country': location_data['country'],
                'coords': {'lat': location_data['latitude'], 'lng': location_data['longitude']}
            },
            'weather': weather_data,
            'local_time': local_time,
            'success': True,
            'provider': AI_PROVIDER,
            'model': AI_MODEL,
            'response_time': response_time,
            'routing': routing_info,  # Include routing info for debugging
            'web_search': {
                'performed': routing_info['should_search'],
                'results_count': len(web_search_results) if web_search_results else 0
            },
            'map': map_data
        }
        
        logger.info(f"⚡ Response time: {response_time}s")
        
        return jsonify(response), 200
    
    except Exception as e:
        logger.error(f"❌ Error: {e}")
        db.session.rollback()
        return jsonify({'reply': f'Error: {str(e)}', 'success': False}), 500


# ============================================================================
# OTHER ROUTES (SHORTENED)
# ============================================================================

@app.route('/api/chat/history', methods=['GET'])
def get_chat_history():
    try:
        limit = request.args.get('limit', 50, type=int)
        session_id = request.args.get('session_id', '').strip()
        user_id = current_user_id()

        query = ChatMessage.query
        if user_id:
            query = query.filter_by(user_id=user_id)
        elif session_id:
            query = query.filter_by(session_id=session_id)

        messages = query.order_by(ChatMessage.timestamp.desc()).limit(limit).all()
        return jsonify({'history': [msg.to_dict() for msg in reversed(messages)], 'total': len(messages), 'success': True}), 200
    except Exception as e:
        return jsonify({'history': [], 'success': False}), 500


@app.route('/api/chat/clear', methods=['POST'])
def clear_chat():
    try:
        data = request.get_json(silent=True) or {}
        session_id = data.get('session_id') or request.args.get('session_id', '').strip()
        user = get_current_user()

        query = ChatMessage.query
        if user and not user.is_admin:
            query = query.filter_by(user_id=user.id)
        elif not user:
            if not session_id:
                return jsonify({'error': 'session_id required', 'success': False}), 400
            query = query.filter_by(session_id=session_id)

        count = query.count()
        query.delete(synchronize_session=False)
        db.session.commit()
        return jsonify({'message': f'Cleared {count} messages', 'success': True}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e), 'success': False}), 500


@app.route('/api/sessions', methods=['GET'])
def get_sessions():
    try:
        sessions = UserSession.query.order_by(UserSession.last_active.desc()).all()
        return jsonify({'sessions': [s.to_dict() for s in sessions], 'total': len(sessions), 'success': True}), 200
    except Exception as e:
        return jsonify({'sessions': [], 'success': False}), 500


@app.route('/api/analytics', methods=['GET'])
def get_analytics():
    try:
        total_messages = ChatMessage.query.count()
        total_sessions = UserSession.query.count()
        total_locations = LocationData.query.count()
        
        top_locations = db.session.query(ChatMessage.user_location, db.func.count(ChatMessage.id).label('count')).group_by(ChatMessage.user_location).order_by(db.desc(db.func.count(ChatMessage.id))).limit(10).all()
        top_effects = db.session.query(ChatMessage.effect_triggered, db.func.count(ChatMessage.id).label('count')).filter(ChatMessage.effect_triggered != None).group_by(ChatMessage.effect_triggered).order_by(db.desc(db.func.count(ChatMessage.id))).all()
        
        return jsonify({
            'stats': {'total_messages': total_messages, 'total_sessions': total_sessions, 'total_locations': total_locations},
            'top_locations': [{'location': loc[0], 'count': loc[1]} for loc in top_locations],
            'top_effects': [{'effect': eff[0], 'count': eff[1]} for eff in top_effects],
            'success': True
        }), 200
    except Exception as e:
        return jsonify({'stats': {}, 'success': False}), 500


@app.route('/api/3d/particles', methods=['GET'])
def get_particles():
    try:
        count = request.args.get('count', 1000, type=int)
        particles = generate_particles(min(count, 10000))
        return jsonify({'particles': particles, 'count': len(particles), 'success': True}), 200
    except Exception as e:
        return jsonify({'error': str(e), 'success': False}), 500


@app.route('/api/3d/animation', methods=['GET'])
def get_animation():
    try:
        duration = request.args.get('duration', 3.0, type=float)
        fps = request.args.get('fps', 60, type=int)
        keyframes = generate_animation_keyframes(duration, fps)
        return jsonify({'keyframes': keyframes, 'total_frames': len(keyframes), 'duration': duration, 'fps': fps, 'success': True}), 200
    except Exception as e:
        return jsonify({'error': str(e), 'success': False}), 500


@app.route('/api/assistant/info', methods=['GET'])
def get_assistant_info():
    try:
        return jsonify({
            'name': ASSISTANT_NAME,
            'version': ASSISTANT_VERSION,
            'ai_provider': AI_PROVIDER,
            'ai_model': AI_MODEL,
            'capabilities': [
                'Provider-based AI chat',
                'Agent/router tool selection',
                'Web search',
                'Live weather',
                'Location lookup',
                'OpenStreetMap links',
                '3D effects',
                'In-memory caching',
            ],
            'success': True
        }), 200
    except Exception as e:
        return jsonify({'error': str(e), 'success': False}), 500


@app.route('/api/health', methods=['GET'])
def health_check():
    """Application health check for deployment platforms.

    AI readiness is reported here, but it does not make the web process
    unhealthy because the app has local fallback responses.
    """
    try:
        ai_status = ai_service.health()

        return jsonify({
            'status': 'healthy',
            'dependencies': {
                'ai': 'ready' if ai_status.get('ready') else 'degraded',
            },
            'service': ASSISTANT_NAME,
            'version': ASSISTANT_VERSION,
            'ai': ai_status,
            'ollama': ai_status if ai_status.get('provider') == 'ollama' else None,
            'timestamp': datetime.now().isoformat(),
            'success': True
        }), 200
    except Exception as e:
        return jsonify({'status': 'unhealthy', 'success': False}), 500


@app.route('/api/ollama/ready', methods=['GET'])
def ollama_ready():
    """Backward-compatible readiness endpoint used by the existing frontend."""
    try:
        status = ai_service.health()
        is_ready = bool(status.get('ready'))
        return jsonify({
            'ready': is_ready,
            'provider': status.get('provider'),
            'model': status.get('model'),
            'status': status,
            'success': True
        }), 200 if is_ready else 503
    except Exception as e:
        return jsonify({
            'ready': False,
            'error': str(e),
            'provider': AI_PROVIDER,
            'success': False
        }), 503


# ============================================================================
# ERROR HANDLERS
# ============================================================================

@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Not found', 'success': False}), 404


@app.errorhandler(500)
def server_error(error):
    return jsonify({'error': 'Server error', 'success': False}), 500


initialize_database()


# ============================================================================
# OLLAMA INITIALIZATION & WARMUP
# ============================================================================

def warmup_ollama():
    """Warm up Ollama on startup by loading the model and making a test request."""
    logger.info("🔥 Warming up Ollama...")
    
    max_attempts = 10
    attempt = 0
    
    while attempt < max_attempts:
        attempt += 1
        try:
            logger.info(f"   Attempt {attempt}/{max_attempts}: Checking Ollama at {OLLAMA_URL}")
            
            # First, check if Ollama is accessible
            tags_response = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
            tags_response.raise_for_status()
            
            models = [model.get('name') for model in tags_response.json().get('models', [])]
            logger.info(f"   ✅ Ollama is running. Available models: {models[:3]}")
            
            if OLLAMA_MODEL not in models:
                logger.warning(f"   ⚠️ Model '{OLLAMA_MODEL}' not in available models. Pulling it...")
                # Try to pull the model
                try:
                    pull_response = requests.post(
                        f"{OLLAMA_URL}/api/pull",
                        json={"name": OLLAMA_MODEL},
                        timeout=120
                    )
                    if pull_response.status_code == 200:
                        logger.info(f"   ✅ Model '{OLLAMA_MODEL}' pulled successfully")
                except Exception as pull_error:
                    logger.error(f"   ❌ Could not pull model: {pull_error}")
                    return False
            
            # Make a warmup request to load the model into memory
            logger.info(f"   🚀 Making warmup request to load model into memory...")
            warmup_prompt = "Hello, respond with 'Ready' only."
            
            warmup_response = requests.post(
                f"{OLLAMA_URL}/api/generate",
                json={
                    "model": OLLAMA_MODEL,
                    "prompt": warmup_prompt,
                    "stream": False,
                    "think": False,
                    "keep_alive": "10m",
                    "options": {
                        "temperature": 0.1,
                        "num_predict": 10,
                    },
                },
                timeout=60
            )
            warmup_response.raise_for_status()
            
            logger.info(f"   ✅ Ollama is ready! Model loaded and warmed up.")
            return True
        
        except requests.exceptions.Timeout:
            logger.warning(f"   ⏱️ Timeout waiting for Ollama (attempt {attempt}/{max_attempts})")
            if attempt < max_attempts:
                import time
                time.sleep(2)
            continue
        except requests.exceptions.ConnectionError:
            logger.warning(f"   🔌 Ollama not responding (attempt {attempt}/{max_attempts})")
            if attempt < max_attempts:
                import time
                time.sleep(2)
            continue
        except Exception as e:
            logger.warning(f"   ⚠️ Warmup error: {e} (attempt {attempt}/{max_attempts})")
            if attempt < max_attempts:
                import time
                time.sleep(2)
            continue
    
    logger.error(f"❌ Could not connect to Ollama after {max_attempts} attempts")
    logger.error(f"   Make sure Ollama is running at {OLLAMA_URL}")
    return False


def get_lan_ip():
    """Best-effort local network IP for opening DENZ from a phone."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
    except Exception:
        return "YOUR_COMPUTER_IP"


# ============================================================================
# MAIN
# ============================================================================

if __name__ == '__main__':
    logger.info("="*70)
    logger.info(f"🚀 Starting {ASSISTANT_NAME} {ASSISTANT_VERSION}")
    logger.info("="*70)
    logger.info("⚡ ULTRA SPEED OPTIMIZATIONS:")
    logger.info(f"  ✅ {OLLAMA_MODEL} - upgraded reasoning model")
    logger.info("  ✅ Agent/router for weather, maps, location, web search, and chat")
    logger.info("  ✅ In-memory LRU caching")
    logger.info("  ✅ Response caching")
    logger.info("  ✅ Async database saves")
    logger.info("  ✅ Ultra-short timeouts (2s API, 15s Ollama)")
    logger.info("  ✅ Minimal prompts and responses")
    logger.info("="*70)
    
    with app.app_context():
        try:
            db.create_all()
            logger.info("✅ Database ready")
        except Exception as e:
            logger.error(f"❌ DB error: {e}")
    
    # Warm up Ollama in the background so web/mobile clients can connect immediately.
    if AI_PROVIDER == "ollama" and env_bool("START_OLLAMA_WARMUP", True):
        threading.Thread(target=warmup_ollama, daemon=True).start()
        logger.info("Ollama warmup started in the background.")
    else:
        logger.info(f"AI warmup skipped for provider={AI_PROVIDER}.")
    lan_ip = get_lan_ip()
    logger.info(f"🌐 Flask local:  http://localhost:{FLASK_PORT}")
    logger.info(f"📱 Mobile/LAN:   http://{lan_ip}:{FLASK_PORT}")
    logger.info("="*70 + "\n")
    
    app.run(
        debug=env_bool("FLASK_DEBUG", False),
        host=FLASK_HOST,
        port=FLASK_PORT,
        use_reloader=False,
    )
