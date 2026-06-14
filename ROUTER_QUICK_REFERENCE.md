# DENZ Agent/Router Quick Reference

## What is the Router?

The **ToolRouter** is an intelligent system that automatically decides which tool to use for each user query:
- 🌤️ Weather queries → Weather API
- 📍 Location queries → Location/Geolocation
- 🔍 Information queries → Web Search
- 💬 General queries → Ollama LLM

---

## Query Examples

### Weather Queries ✨
**Intent**: `weather`

```
"What's the weather?"
"Is it going to rain in Shimla?"
"Current temperature in NYC"
"Weather forecast for tomorrow"
"How hot is it in summer?"
```

**Router Decision**: ✅ Use Weather API
**Response Time**: ~500ms (cached)

---

### Location Queries 📍
**Intent**: `location`

```
"What is the capital of Himachal Pradesh?"
"Where is New York?"
"What state is Dharamshala in?"
"Capital of France?"
"Location of the Taj Mahal"
```

**Router Decision**: ✅ Use Location/Capital Knowledge
**Response Time**: <100ms (instant)

---

### Web Search Queries 🔍
**Intent**: `web_search`

```
"Latest tech news"
"What are current trending topics?"
"Recent updates on AI"
"Who won the latest tournament?"
"What's new in machine learning?"
"How do I install Python?"
"Best restaurants near me"
"Current Bitcoin price"
```

**Router Decision**: ✅ Search Web
**Response Time**: 1-3s (web search + Ollama)

---

### General Chat 💬
**Intent**: `chat`

```
"Tell me a joke"
"Explain quantum computing"
"How does photosynthesis work?"
"What's your favorite color?"
"Explain machine learning"
"How to write better code?"
"Tell me about history"
```

**Router Decision**: ✅ Use Ollama (with optional search)
**Response Time**: 2-5s

---

## Decision Flow

```
User Message
    ↓
Router.classify_intent(message)
    ↓
[Check keywords]
    ├─ "weather", "temperature", "forecast", "rain"? 
    │   → weather ☑️
    │
    ├─ "location", "capital", "where", "map"?
    │   → location ☑️
    │
    ├─ "latest", "news", "recent", "current"?
    │   AND not weather/location?
    │   → web_search ☑️
    │
    └─ Other
        → chat ☑️
```

---

## API Response Examples

### Weather Response
```json
{
  "reply": "The weather in Delhi is Clear with...",
  "routing": {
    "intent": "weather",
    "should_search": false,
    "use_weather": true,
    "use_location": false,
    "use_chat": false
  },
  "model": "qwen3:8b",
  "response_time": 0.45
}
```

### Location Response
```json
{
  "reply": "The capital of Himachal Pradesh is Shimla...",
  "routing": {
    "intent": "location",
    "should_search": false,
    "use_weather": false,
    "use_location": true,
    "use_chat": false
  },
  "model": "qwen3:8b",
  "response_time": 0.08
}
```

### Web Search Response
```json
{
  "reply": "Based on latest searches: [web search results]...",
  "routing": {
    "intent": "web_search",
    "should_search": true,
    "use_weather": false,
    "use_location": false,
    "use_chat": true
  },
  "web_search": {
    "performed": true,
    "results_count": 3
  },
  "model": "qwen3:8b",
  "response_time": 2.15
}
```

### Chat Response
```json
{
  "reply": "Machine learning is...",
  "routing": {
    "intent": "chat",
    "should_search": false,
    "use_weather": false,
    "use_location": false,
    "use_chat": true
  },
  "model": "qwen3:8b",
  "response_time": 3.52
}
```

---

## Performance Expectations

| Route | Time | Cache | Example |
|-------|------|-------|---------|
| Weather | 500ms | ✅ Yes (10m) | "Weather in NYC" |
| Location | 50ms | ✅ Yes (24h) | "Capital of India" |
| Web Search | 1-3s | ❌ No | "Latest news" |
| Chat | 2-5s | ✅ Yes | "Explain AI" |

---

## Router Methods

### `ToolRouter.classify_intent(message)`
Determines the user's intent from their message.

```python
intent = ToolRouter.classify_intent("What's the weather today?")
# Returns: "weather"
```

### `ToolRouter.should_use_web_search(message)`
Decides if web search would benefit the response.

```python
needs_search = ToolRouter.should_use_web_search("Latest AI breakthroughs")
# Returns: True
```

### `ToolRouter.route_request(message, location_data)`
Complete routing decision with all flags.

```python
routing = ToolRouter.route_request(
    "What's the capital of France?",
    location_data
)
# Returns: {
#   'intent': 'location',
#   'should_search': False,
#   'use_location': True,
#   'use_weather': False,
#   'use_chat': False
# }
```

---

## Tips & Tricks

### 1️⃣ Force Web Search
Add words like "latest", "current", "recent", "new"
```
"Latest news on AI" → Forces web search
vs
"Tell me about AI" → Regular chat (no search)
```

### 2️⃣ Combine Intents
The router can combine tools:
```
"Weather in London tomorrow" → Weather + Location
"What's the capital and weather?" → Location + Chat
```

### 3️⃣ Follow-ups
System remembers previous context:
```
User: "Weather in Shimla"
User: "Will it rain?" → Understands = "Will it rain in Shimla?"
```

### 4️⃣ Check Routing Info
Use the `routing` field to understand what tool was used:
```json
"routing": {
  "intent": "web_search",  // ← See what tool was used
  "should_search": true
}
```

---

## Extending the Router

### Add New Intent Type

In `denz.py`, in the `ToolRouter.classify_intent()` method:

```python
@staticmethod
def classify_intent(message):
    msg = message.lower()
    
    # Existing code...
    
    # NEW: Add sports intent
    sports_keywords = ['cricket', 'football', 'score', 'match', 'team']
    if any(keyword in msg for keyword in sports_keywords):
        return 'sports'  # ← New intent
    
    return 'chat'  # Fallback
```

Then handle in `/api/chat`:
```python
if routing_info['intent'] == 'sports':
    # Call sports API or search for scores
    ai_response = get_sports_update(user_message)
```

---

## Debugging

### Check Routing Decision
Look at the `routing` field in API response:
```json
"routing": {
  "intent": "???",
  "should_search": boolean,
  "use_weather": boolean,
  "use_location": boolean,
  "use_chat": boolean
}
```

### Enable Debug Logging
Check logs for router decisions:
```
🤖 Router Intent: web_search | Search: True | Weather: False
```

### Test Specific Intent
```bash
# Test weather routing
curl -X POST http://localhost:5000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What is the weather?", "session_id": "debug"}'

# Check response.routing.intent
```

---

## Migration Guide (for existing systems)

### Old System (Manual Routing)
```python
if "weather" in message:
    response = get_weather()
else:
    response = get_ollama()
```

### New System (Automatic Routing)
```python
routing = ToolRouter.route_request(message, location)
# Automatically selects best tool + web search when needed
response = process_with_routing(message, routing)
```

**Benefits**:
- ✅ No hardcoded logic
- ✅ Easier to maintain
- ✅ Can add new tools without changing core logic
- ✅ Transparent (routing info in response)

---

## Summary

- 🤖 **Router** automatically picks the best tool
- ⚡ **Performance** is optimized for each tool type  
- 🔍 **Web Search** is automatic when helpful
- 📊 **Transparent** routing info in responses
- 🎯 **Extensible** system for new tools

---

*For more details, see IMPROVEMENTS_SUMMARY.md*
