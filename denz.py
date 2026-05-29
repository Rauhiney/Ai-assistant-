from flask import Flask, render_template, request, jsonify, send_from_directory
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import inspect, text
from datetime import datetime
import logging
import math
import random
import requests
import os
import pytz
import threading
import time
import re
import difflib

# ============================================================================
# FLASK APP SETUP
# ============================================================================

app = Flask(__name__, template_folder='templates', static_folder='static')
CORS(app)

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///denz_chat.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['JSON_SORT_KEYS'] = False

db = SQLAlchemy(app)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================================================
# CONFIGURATION
# ============================================================================

def load_local_env(path=".env"):
    """Load simple KEY=value pairs for local development."""
    if not os.path.exists(path):
        return

    with open(path, "r", encoding="utf-8") as env_file:
        for line in env_file:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_local_env()

ASSISTANT_NAME = "DENZ"
ASSISTANT_VERSION = "3D-ULTRA-AI-FASTEST"
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3:latest")
OLLAMA_TIMEOUT = float(os.getenv("OLLAMA_TIMEOUT", "4"))

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

WEATHER_KEYWORDS = ('weather', 'temperature', 'forecast', 'rain', 'cloud', 'humidity', 'wind')
NON_LOCATION_WORDS = {
    'what', 'whats', 'what is', 'current', 'the current', 'today', 'now',
    'right now', 'currently', 'please', 'pls', 'weather', 'temperature',
    's', 'hat', 'todays', "today's",
}
WEATHER_FILLER_WORDS = (
    'what', 'whats', 'is', 'the', 'current', 'today', 'now', 'right', 'currently',
    'please', 'pls', 'tell', 'me', 'show', 'check', 'weather', 'temperature',
    'forecast', 'rain', 'cloud', 'humidity', 'wind', 'in', 'at', 'for', 'of',
    's', 'hat', 'todays',
)
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
    if any(keyword in text for keyword in ('weather', 'temperature', 'forecast', 'humidity', 'wind', 'rain', 'cloud')):
        return 'weather'
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
    tokens = [token for token in cleaned.split() if token and token not in {'weather', 'temperature', 'forecast', 'rain', 'humidity', 'wind'}]
    if not tokens:
        return None
    if len(tokens) <= 3:
        return ' '.join(tokens).title()
    return None


def is_short_followup(message, context):
    text = normalize_conversation_text(message)
    if not context or not context.get('last_intent'):
        return False
    if text in {'next', 'more', 'again', 'same', 'what about it', 'what about', 'that', 'this', 'it', 'also', 'and'}:
        return True
    if len(text.split()) <= 3 and not any(word in text for word in ('weather', 'temperature', 'forecast', 'news', 'what', 'why', 'how', 'who', 'where', 'when', 'which', 'is', 'are', 'can', 'could', 'should', 'do', 'does')):
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
    if normalized in {'next', 'more', 'again', 'what about it', 'that', 'this', 'it'}:
        target = last_entity or last_topic or 'the previous topic'
        return f'Tell me more about {target}'
    if last_entity or last_topic:
        return f'Tell me about {normalized} in the context of {last_entity or last_topic}'
    return message


def update_conversation_memory(session_id, user_message, ai_response, effective_message, weather_question=False, requested_weather_location=None):
    context = get_session_context(session_id)
    intent = infer_user_intent(effective_message)
    entity = requested_weather_location or extract_weather_location(effective_message) or guess_weather_location(effective_message) or normalize_entity_from_text(effective_message)
    topic = entity or normalize_entity_from_text(user_message)
    if not entity:
        entity = context.get('last_entity')
    if not topic:
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

class ChatMessage(db.Model):
    """Store chat messages with location data"""
    __tablename__ = 'chat_messages'
    
    id = db.Column(db.Integer, primary_key=True)
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


def initialize_database():
    """Create database tables and add missing columns for older DB files."""
    with app.app_context():
        db.create_all()
        inspector = inspect(db.engine)

        def add_missing_columns(table_name, migrations):
            existing_columns = {
                column['name']
                for column in inspector.get_columns(table_name)
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
            'session_id': 'VARCHAR(100)',
            'ai_model': 'VARCHAR(50)',
            'user_location': 'VARCHAR(200)',
            'user_timezone': 'VARCHAR(50)',
            'user_ip': 'VARCHAR(50)',
            'weather_data': 'JSON',
        })
        add_missing_columns(UserSession.__tablename__, {
            'ip_address': 'VARCHAR(50)',
            'country': 'VARCHAR(100)',
            'city': 'VARCHAR(100)',
            'latitude': 'FLOAT',
            'longitude': 'FLOAT',
            'messages_count': 'INTEGER DEFAULT 0',
        })


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
        return get_fallback_location()

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
        return get_fallback_location()
    
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
                return get_fallback_location()
        
        else:
            logger.warning(f"⚠️ IP geolocation failed with status {response.status_code}, using fallback")
            return get_fallback_location()
    
    except Exception as e:
        logger.error(f"❌ Location error: {e}, using fallback")
        return get_fallback_location()


def get_fallback_location():
    """Neutral fallback for when location lookup is unavailable."""
    return {
        'ip': 'unknown',
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

def get_timezone_from_coords(latitude, longitude):
    """Get timezone (cached)"""
    if not latitude or not longitude:
        return "UTC"

    try:
        return timezone_finder.timezone_at(lat=latitude, lng=longitude) or "UTC"
    except Exception as e:
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
    msg = normalize_weather_terms(message).lower()
    return any(keyword in msg for keyword in WEATHER_KEYWORDS)


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
    patterns = [
        r'\b(?:weather|temperature|forecast|rain|humidity|wind)\s+(?:in|at|for|of)\s+([a-zA-Z\s,-]+)',
        r'\b(?:in|at|for|of)\s+([a-zA-Z\s,-]+)\s+(?:weather|temperature|forecast|rain|humidity|wind)\b',
        r'^([a-zA-Z\s,-]+)\s+(?:weather|temperature|forecast|rain|humidity|wind)\b',
        r'\b(?:weather|temperature|forecast|rain|humidity|wind)\s+([a-zA-Z\s,-]+)$',
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
    """Detect short question fragments that need the next user message."""
    normalized = re.sub(r'\s+', ' ', message.lower()).strip(" .?!")
    if not normalized:
        return False

    words = normalized.split()
    incomplete_exact = {
        'what is', 'what are', 'who is', 'who are', 'where is', 'where are',
        'why is', 'why are', 'how to', 'how do', 'how can', 'tell me',
        'explain', 'define', 'meaning of', 'difference between',
    }
    incomplete_endings = {
        'what', 'who', 'where', 'why', 'how', 'is', 'are', 'about',
        'of', 'between', 'for', 'to', 'in',
    }

    if normalized in incomplete_exact:
        return True

    if len(words) <= 4 and (
        normalized.startswith(('what is ', 'what are ', 'who is ', 'how to ', 'tell me ', 'explain '))
        or words[-1] in incomplete_endings
    ):
        return True

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
        if is_pending_weather_message(message):
            return message.user_message

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


def build_ultra_fast_prompt(user_message, location_data, weather_data, local_time, chat_history=None, context_state=None):
    """Build a concise prompt that can use previous conversation context."""
    history_text = format_chat_history(chat_history or [])
    history_section = f"\nPrevious conversation:\n{history_text}\n" if history_text else ""
    context_guidance = build_context_guidance(context_state or {}, user_message)
    context_section = f"\nConversation memory:\n{context_guidance}\n" if context_guidance else ""

    return f"""You are DENZ, a concise 3D AI assistant.
Use the previous conversation and conversation memory when they help answer the new question.
If the user gives a short follow-up, treat it as a continuation of the last relevant topic or location unless they clearly change the subject.
Reply in 1-3 short sentences.
Do not mention any city, country, location, weather, or local temperature unless the user explicitly asks for it.
{history_section}{context_section}
New user question: {user_message}

DENZ:"""


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


def get_ollama_response_ultra_fast(user_message, location_data, weather_data, local_time, chat_history=None, session_id=None):
    """Ultra-fast Ollama response"""
    chat_history = chat_history or []

    # Check response cache
    history_key = "|".join(f"{item.user_message}:{item.bot_response}" for item in chat_history[-3:])
    message_key = f"with_history_v1_{history_key}_{user_message}"
    cached_resp = cached_response(message_key)
    if cached_resp:
        logger.info("🚀 Response cache hit")
        return cached_resp
    
    try:
        prompt = build_ultra_fast_prompt(
            user_message,
            location_data,
            weather_data,
            local_time,
            chat_history,
            get_session_context(session_id),
        )
        
        logger.info("📤 Ultra-fast Ollama request")
        
        response = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "keep_alive": "10m",
                "options": {
                    "temperature": 0.3,
                    "num_predict": 96,
                    "num_ctx": 1024,
                },
            },
            timeout=OLLAMA_TIMEOUT
        )
        response.raise_for_status()
        
        data = response.json()
        ai_response = data.get('response', '').strip()
        
        if ai_response:
            if len(ai_response) > 500:
                ai_response = ai_response[:500] + "..."
            
            # Cache response
            response_cache[message_key] = ai_response
            
            logger.info(f"✅ Fast response: {ai_response[:30]}")
            return ai_response
        
        logger.warning("⚠️ Ollama failed, using fallback")
        if has_real_location(location_data):
            return f"Nice weather in {location_data['city']}! {weather_data['description']}, {weather_data['temperature']}C."
        return "Hello! How can I help?"
    
    except Exception as e:
        logger.error(f"❌ Ollama error: {e}")
        if has_real_location(location_data):
            return f"Hello! It's {local_time['time']} in {location_data['city']}."
        return "Hello! How can I help?"


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


@app.route('/about')
def about():
    return render_template('about.html')


@app.route('/static/<path:filename>')
def serve_static(filename):
    return send_from_directory('static', filename)


def save_chat_message_to_db(session_id, user_message, bot_response, effect, location_data, timezone, user_ip, weather_data):
    """Persist a chat turn and keep user-session counters in sync."""
    with app.app_context():
        try:
            chat_msg = ChatMessage(
                session_id=session_id,
                user_message=user_message,
                bot_response=bot_response,
                effect_triggered=effect,
                ai_model=OLLAMA_MODEL,
                user_location=f"{location_data['city']}, {location_data['country']}",
                user_timezone=timezone,
                user_ip=user_ip,
                weather_data=weather_data
            )
            db.session.add(chat_msg)

            session = UserSession.query.filter_by(session_id=session_id).first()
            if session:
                session.messages_count += 1
                session.last_active = datetime.now()
            else:
                session = UserSession(
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
        logger.info("🔄 ULTRA FAST CHAT REQUEST")
        
        data = request.get_json()
        user_ip = get_user_ip(request)
        
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
        pending_question_part = get_pending_question_part(chat_history)
        pending_weather_question = None
        if not pending_question_part:
            pending_weather_question = (
                get_pending_weather_question_from_memory(session_id, user_ip)
                or get_pending_weather_question(chat_history)
            )
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

        user_is_weather_question = is_weather_question(user_message)
        if not pending_question_part and not user_is_weather_question and is_incomplete_question(raw_user_message):
            weather_question = False
            instant_response = None
        else:
            weather_question = is_weather_question(effective_message)
            instant_response = None if weather_question else get_instant_response(effective_message)

        # Normal chats should not wait on public IP geolocation.
        location_data = get_location_from_ip(user_ip, allow_network=weather_question) or {
            'city': 'Unknown', 'country': 'Unknown', 'latitude': 0, 'longitude': 0, 'timezone': 'UTC'
        }
        
        timezone = location_data.get('timezone') or get_timezone_from_coords(location_data['latitude'], location_data['longitude'])
        local_time = get_local_time(timezone)
        
        requested_weather_location = None
        if weather_question:
            requested_weather_location = extract_weather_location(effective_message) or guess_weather_location(effective_message)

        if not pending_question_part and not user_is_weather_question and is_incomplete_question(user_message):
            weather_data = get_neutral_weather()
            ai_response = INCOMPLETE_QUESTION_REPLY
        elif instant_response:
            weather_data = get_neutral_weather()
            ai_response = instant_response
        elif weather_question and not requested_weather_location and not has_real_location(location_data):
            weather_data = get_neutral_weather()
            ai_response = "Please share the city or location you want the current weather for, and I will check it for you."
            remember_pending_weather_question(session_id, user_ip, effective_message)
        elif requested_weather_location:
            weather_data = get_weather_data_by_city(requested_weather_location)
            ai_response = format_professional_weather_reply(weather_data)
            clear_pending_weather_question(session_id, user_ip)
        elif weather_question and has_real_location(location_data):
            weather_data = get_weather_data(
                location_data['latitude'], location_data['longitude'],
                f"{location_data['city']}, {location_data['country']}"
            )
            ai_response = format_professional_weather_reply(weather_data)
            clear_pending_weather_question(session_id, user_ip)
        else:
            weather_data = get_neutral_weather()
            ai_response = get_ollama_response_ultra_fast(
                effective_message,
                location_data,
                weather_data,
                local_time,
                chat_history,
                session_id,
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
            'model': OLLAMA_MODEL,
            'response_time': response_time
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

        query = ChatMessage.query
        if session_id:
            query = query.filter_by(session_id=session_id)

        messages = query.order_by(ChatMessage.timestamp.desc()).limit(limit).all()
        return jsonify({'history': [msg.to_dict() for msg in reversed(messages)], 'total': len(messages), 'success': True}), 200
    except Exception as e:
        return jsonify({'history': [], 'success': False}), 500


@app.route('/api/chat/clear', methods=['POST'])
def clear_chat():
    try:
        count = ChatMessage.query.count()
        ChatMessage.query.delete()
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
            'ollama_url': OLLAMA_URL,
            'ollama_model': OLLAMA_MODEL,
            'capabilities': ['Ultra-fast AI chat', 'Real-time location', 'Live weather', '3D effects', 'In-memory caching'],
            'success': True
        }), 200
    except Exception as e:
        return jsonify({'error': str(e), 'success': False}), 500


@app.route('/api/health', methods=['GET'])
def health_check():
    try:
        ollama = {'connected': False, 'url': OLLAMA_URL, 'model': OLLAMA_MODEL}
        try:
            ollama_response = requests.get(f"{OLLAMA_URL}/api/tags", timeout=3)
            ollama['connected'] = ollama_response.status_code == 200
            if ollama['connected']:
                models = [model.get('name') for model in ollama_response.json().get('models', [])]
                ollama['model_available'] = OLLAMA_MODEL in models
        except Exception as ollama_error:
            ollama['error'] = str(ollama_error)

        return jsonify({
            'status': 'healthy',
            'service': ASSISTANT_NAME,
            'version': ASSISTANT_VERSION,
            'ollama': ollama,
            'timestamp': datetime.now().isoformat(),
            'success': True
        }), 200
    except Exception as e:
        return jsonify({'status': 'unhealthy', 'success': False}), 500


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
# MAIN
# ============================================================================

if __name__ == '__main__':
    logger.info("="*70)
    logger.info(f"🚀 Starting {ASSISTANT_NAME} {ASSISTANT_VERSION}")
    logger.info("="*70)
    logger.info("⚡ ULTRA SPEED OPTIMIZATIONS:")
    logger.info("  ✅ Llama3.2:1B - Fastest model")
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
    
    logger.info(f"🌐 Flask on http://localhost:5000")
    logger.info("="*70 + "\n")
    
    app.run(debug=True, host='localhost', port=5000, use_reloader=False)
