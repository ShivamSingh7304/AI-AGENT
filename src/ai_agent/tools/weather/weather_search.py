
import logging

import requests
from langchain.tools import tool

from ai_agent.core.logging_config import setup_logging

# Initialize shared logging configuration
setup_logging()
logger = logging.getLogger(__name__)

GEO_URL = "https://geocoding-api.open-meteo.com/v1/search"
WEATHER_URL = "https://api.open-meteo.com/v1/forecast"

WEATHER_CODES = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    71: "Slight snowfall",
    73: "Moderate snowfall",
    75: "Heavy snowfall",
    80: "Rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    95: "Thunderstorm",
    96: "Thunderstorm with hail",
    99: "Thunderstorm with heavy hail",
}


@tool
def get_weather(city: str) -> str:
    """Get current weather conditions for a city.

    Use this tool when the user asks about temperature,
    humidity, wind, precipitation, or weather conditions.

    Args:
        city: City name, such as Delhi, Mumbai, or Dehradun.
    """
    city = city.strip()

    if not city:
        return "Please provide a valid city name."

    logger.info("Weather lookup started for city: %s", city)

    try:
        # Step 1: Get city coordinates
        geo_response = requests.get(
            GEO_URL,
            params={
                "name": city,
                "count": 1,
                "language": "en",
                "format": "json",
            },
            timeout=10,
        )
        geo_response.raise_for_status()

        places = geo_response.json().get("results", [])

        if not places:
            logger.warning("City not found: %s", city)
            return f"City not found: {city}"

        place = places[0]
        latitude = place["latitude"]
        longitude = place["longitude"]

        # Step 2: Fetch current weather
        weather_response = requests.get(
            WEATHER_URL,
            params={
                "latitude": latitude,
                "longitude": longitude,
                "current": (
                    "temperature_2m,"
                    "relative_humidity_2m,"
                    "apparent_temperature,"
                    "is_day,"
                    "precipitation,"
                    "weather_code,"
                    "wind_speed_10m"
                ),
                "timezone": "auto",
            },
            timeout=10,
        )
        weather_response.raise_for_status()

        data = weather_response.json()
        current = data["current"]

        code = current["weather_code"]
        condition = WEATHER_CODES.get(
            code, "Unknown conditions"
        )

        logger.info(
            "Weather lookup successful for %s",
            place["name"],
        )

        return (
            f"Weather for {place['name']}, "
            f"{place.get('country', 'Unknown country')}\n"
            f"Condition: {condition}\n"
            f"Temperature: {current['temperature_2m']} °C\n"
            f"Feels like: {current['apparent_temperature']} °C\n"
            f"Humidity: {current['relative_humidity_2m']}%\n"
            f"Wind speed: {current['wind_speed_10m']} km/h\n"
            f"Precipitation: {current['precipitation']} mm\n"
            f"Local time: {current['time']}"
        )

    except requests.RequestException:
        logger.exception("Weather API request failed for %s", city)
        return "Weather service is temporarily unavailable. Please try again."

    except (KeyError, TypeError, ValueError):
        logger.exception("Invalid weather data received for %s", city)
        return "Unable to process the weather data."


if __name__ == "__main__":
    print(get_weather.invoke({"city": "Dehradun"}))
