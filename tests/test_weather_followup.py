import unittest
from unittest.mock import patch

import denz


class WeatherFollowUpTest(unittest.TestCase):
    def setUp(self):
        with denz.app.app_context():
            denz.db.drop_all()
            denz.db.create_all()
        denz.pending_weather_requests.clear()
        denz.conversation_memory.clear()
        denz.location_cache.clear()
        denz.weather_cache.clear()
        denz.response_cache.clear()

    def tearDown(self):
        with denz.app.app_context():
            denz.db.session.remove()
            denz.db.drop_all()
        denz.pending_weather_requests.clear()
        denz.conversation_memory.clear()
        denz.location_cache.clear()
        denz.weather_cache.clear()
        denz.response_cache.clear()

    def post(self, message, session_id="s1"):
        with denz.app.test_client() as client:
            response = client.post(
                "/api/chat",
                json={"message": message, "session_id": session_id},
                headers={"X-Forwarded-For": "1.2.3.4"},
            )
            return response.get_json()

    def post_with_location(self, message, location, session_id="s1"):
        with denz.app.test_client() as client:
            response = client.post(
                "/api/chat",
                json={"message": message, "session_id": session_id, "location": location},
                headers={"X-Forwarded-For": "8.8.8.8"},
            )
            return response.get_json()

    def test_weather_follow_up_reconnects_after_async_save_delay(self):
        fallback_location = {
            "city": "Unknown",
            "country": "Unknown",
            "latitude": 0,
            "longitude": 0,
            "timezone": "UTC",
        }

        weather_payload = {
            "location": "Dharamsala",
            "temperature": 18,
            "feels_like": 17,
            "humidity": 55,
            "description": "clear sky",
            "wind_speed": 3,
            "clouds": 10,
        }

        with patch("denz.get_location_from_ip", return_value=fallback_location), \
             patch("denz.get_ollama_response_ultra_fast", return_value="OLLAMA FALLBACK") as ollama_mock, \
             patch("denz.get_weather_data_by_city", return_value=weather_payload) as weather_mock, \
             patch("denz.threading.Thread") as thread_mock:
            first_reply = self.post("what is the today weather")
            self.assertEqual(
                first_reply["reply"],
                "Please share the city or location you want the current weather for, and I will check it for you.",
            )

            with denz.app.app_context():
                saved_messages = denz.ChatMessage.query.count()
            self.assertEqual(saved_messages, 1)

            denz.pending_weather_requests.clear()
            second_reply = self.post("dharamshala")

        self.assertIn("Dharamsala", second_reply["reply"])
        self.assertEqual(ollama_mock.call_count, 0)
        self.assertEqual(weather_mock.call_count, 1)
        self.assertEqual(thread_mock.call_count, 1)

    def test_misspelled_weather_query_still_uses_weather_flow(self):
        fallback_location = {
            "city": "Unknown",
            "country": "Unknown",
            "latitude": 0,
            "longitude": 0,
            "timezone": "UTC",
        }

        weather_payload = {
            "location": "Dharamsala",
            "temperature": 18,
            "feels_like": 17,
            "humidity": 55,
            "description": "clear sky",
            "wind_speed": 3,
            "clouds": 10,
        }

        with patch("denz.get_location_from_ip", return_value=fallback_location), \
             patch("denz.get_ollama_response_ultra_fast", return_value="Generic chat response") as ollama_mock, \
             patch("denz.get_weather_data_by_city", return_value=weather_payload) as weather_mock:
            reply = self.post("dharamshala weasther")

        self.assertIn("Dharamsala", reply["reply"])
        self.assertEqual(ollama_mock.call_count, 0)
        self.assertEqual(weather_mock.call_count, 1)

    def test_non_weather_follow_up_does_not_reuse_weather_context(self):
        fallback_location = {
            "city": "Unknown",
            "country": "Unknown",
            "latitude": 0,
            "longitude": 0,
            "timezone": "UTC",
        }

        weather_payload = {
            "location": "Dharamsala",
            "temperature": 18,
            "feels_like": 17,
            "humidity": 55,
            "description": "clear sky",
            "wind_speed": 3,
            "clouds": 10,
        }

        with patch("denz.get_location_from_ip", return_value=fallback_location), \
             patch("denz.get_ollama_response_ultra_fast", return_value="Generic chat response") as ollama_mock, \
             patch("denz.get_weather_data_by_city", return_value=weather_payload) as weather_mock:
            self.post("what is weather")
            self.post("dharamshala")
            reply = self.post("capital of india")
            follow_up = self.post("punjab")

        self.assertEqual(reply["reply"], "Generic chat response")
        self.assertEqual(follow_up["reply"], "Generic chat response")
        self.assertEqual(ollama_mock.call_count, 2)
        self.assertEqual(weather_mock.call_count, 1)

    def test_map_query_uses_location_tool_without_ollama(self):
        fallback_location = {
            "city": "Unknown",
            "country": "Unknown",
            "latitude": 0,
            "longitude": 0,
            "timezone": "UTC",
        }

        with patch("denz.get_location_from_ip", return_value=fallback_location), \
             patch("denz.get_ollama_response_ultra_fast", return_value="OLLAMA") as ollama_mock:
            reply = self.post("show map of Delhi")

        self.assertIn("OpenStreetMap", reply["reply"])
        self.assertEqual(reply["routing"]["tool"], "maps")
        self.assertEqual(reply["map"]["query"], "Delhi")
        self.assertEqual(ollama_mock.call_count, 0)

    def test_web_search_query_augments_ollama(self):
        fallback_location = {
            "city": "Unknown",
            "country": "Unknown",
            "latitude": 0,
            "longitude": 0,
            "timezone": "UTC",
        }
        search_results = [
            {
                "rank": 1,
                "title": "Example result",
                "body": "Fresh result body",
                "href": "https://example.com",
            }
        ]

        with patch("denz.get_location_from_ip", return_value=fallback_location), \
             patch("denz.perform_web_search", return_value=search_results) as search_mock, \
             patch("denz.get_ollama_response_ultra_fast", return_value="Search assisted answer") as ollama_mock:
            reply = self.post("latest AI news")

        self.assertEqual(reply["reply"], "Search assisted answer")
        self.assertEqual(reply["routing"]["tool"], "web_search")
        self.assertTrue(reply["web_search"]["performed"])
        self.assertEqual(reply["web_search"]["results_count"], 1)
        search_mock.assert_called_once()
        self.assertEqual(ollama_mock.call_args.args[6], search_results)

    def test_ollama_failure_uses_search_fallback_for_general_questions(self):
        search_results = [
            {
                "rank": 1,
                "title": "Python",
                "body": "Python is a programming language.",
                "href": "https://example.com/python",
            }
        ]

        with patch("denz.perform_web_search", return_value=search_results) as search_mock:
            reply = denz.generate_smart_fallback(
                "what is python",
                {},
                denz.get_neutral_weather(),
                "12:00",
            )

        self.assertIn("web results", reply)
        self.assertIn("Python is a programming language.", reply)
        search_mock.assert_called_once_with("what is python", max_results=3)

    def test_ollama_failure_uses_wikipedia_after_search_failure(self):
        with patch("denz.perform_web_search", return_value=[]), \
             patch("denz.fetch_wikipedia_summary", return_value="Python: Python is a programming language.") as wiki_mock:
            reply = denz.generate_smart_fallback(
                "what is python",
                {},
                denz.get_neutral_weather(),
                "12:00",
            )

        self.assertEqual(reply, "Python: Python is a programming language.")
        wiki_mock.assert_called_once_with("python")

    def test_ollama_failure_uses_basic_answer_without_network(self):
        with patch("denz.perform_web_search", return_value=[]), \
             patch("denz.fetch_wikipedia_summary", return_value=None):
            reply = denz.generate_smart_fallback(
                "what is python",
                {},
                denz.get_neutral_weather(),
                "12:00",
            )

        self.assertIn("high-level programming language", reply)
        self.assertNotIn("local AI model", reply)

    def test_ip_geolocation_429_enters_backoff(self):
        class RateLimitedResponse:
            status_code = 429

        with denz.app.app_context(), \
             patch("denz.requests.get", return_value=RateLimitedResponse()) as request_mock:
            first = denz.get_location_from_ip("8.8.8.8")
            second = denz.get_location_from_ip("8.8.8.8")

        self.assertEqual(first["city"], "Unknown")
        self.assertEqual(second["city"], "Unknown")
        self.assertIn("8.8.8.8", denz.geolocation_backoff_until)
        request_mock.assert_called_once()

    def test_chat_uses_browser_location_before_ip_lookup(self):
        browser_location = {
            "city": "Dharamsala",
            "country": "India",
            "timezone": "Asia/Kolkata",
            "coords": {"lat": 32.219, "lng": 76.323},
        }
        weather_payload = {
            "location": "Dharamsala, India",
            "temperature": 18,
            "feels_like": 17,
            "humidity": 55,
            "description": "clear sky",
            "wind_speed": 3,
            "clouds": 10,
        }

        with patch("denz.get_location_from_ip") as ip_lookup_mock, \
             patch("denz.get_weather_data", return_value=weather_payload) as weather_mock:
            reply = self.post_with_location("weather", browser_location, session_id="browser-location")

        self.assertIn("Dharamsala", reply["reply"])
        ip_lookup_mock.assert_not_called()
        weather_mock.assert_called_once()
        self.assertEqual(reply["location"]["city"], "Dharamsala")


if __name__ == "__main__":
    unittest.main()
