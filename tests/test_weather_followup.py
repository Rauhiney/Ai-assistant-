import unittest
from unittest.mock import patch

import denzi


class WeatherFollowUpTest(unittest.TestCase):
    def setUp(self):
        with denzi.app.app_context():
            denzi.db.drop_all()
            denzi.db.create_all()
        denzi.pending_weather_requests.clear()

    def tearDown(self):
        with denzi.app.app_context():
            denzi.db.session.remove()
            denzi.db.drop_all()
        denzi.pending_weather_requests.clear()

    def post(self, message, session_id="s1"):
        with denzi.app.test_client() as client:
            response = client.post(
                "/api/chat",
                json={"message": message, "session_id": session_id},
                headers={"X-Forwarded-For": "1.2.3.4"},
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

        with patch("denzi.get_location_from_ip", return_value=fallback_location), \
             patch("denzi.get_ollama_response_ultra_fast", return_value="OLLAMA FALLBACK") as ollama_mock, \
             patch("denzi.get_weather_data_by_city", return_value=weather_payload) as weather_mock, \
             patch("denzi.threading.Thread") as thread_mock:
            first_reply = self.post("what is the today weather")
            self.assertEqual(
                first_reply["reply"],
                "Please share the city or location you want the current weather for, and I will check it for you.",
            )

            with denzi.app.app_context():
                saved_messages = denzi.ChatMessage.query.count()
            self.assertEqual(saved_messages, 1)

            denzi.pending_weather_requests.clear()
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

        with patch("denzi.get_location_from_ip", return_value=fallback_location), \
             patch("denzi.get_ollama_response_ultra_fast", return_value="Generic chat response") as ollama_mock, \
             patch("denzi.get_weather_data_by_city", return_value=weather_payload) as weather_mock:
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

        with patch("denzi.get_location_from_ip", return_value=fallback_location), \
             patch("denzi.get_ollama_response_ultra_fast", return_value="Generic chat response") as ollama_mock, \
             patch("denzi.get_weather_data_by_city", return_value=weather_payload) as weather_mock:
            self.post("what is weather")
            self.post("dharamshala")
            reply = self.post("capital of india")
            follow_up = self.post("punjab")

        self.assertEqual(reply["reply"], "Generic chat response")
        self.assertEqual(follow_up["reply"], "Generic chat response")
        self.assertEqual(ollama_mock.call_count, 2)
        self.assertEqual(weather_mock.call_count, 1)


if __name__ == "__main__":
    unittest.main()
