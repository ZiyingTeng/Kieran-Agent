#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AI companion tool set"""
import logging
from datetime import datetime
from typing import Optional
from agentscope.tool._response import ToolResponse
from agentscope.message import TextBlock

logger = logging.getLogger(__name__)


async def get_current_time(format: str = "%Y-%m-%d %H:%M:%S") -> ToolResponse:
    """Get the current time.

    Args:
        format: Time format string, default "%Y-%m-%d %H:%M:%S"

    Returns:
        ToolResponse containing the current time.
    """
    try:
        current_time = datetime.now().strftime(format)
        logger.info(f"🔧 [ReAct] tool call: get_current_time → {current_time}")
        return ToolResponse(
            content=[
                TextBlock(
                    type="text",
                    text=f"Current time: {current_time}",
                ),
            ],
        )
    except Exception as e:
        return ToolResponse(
            content=[
                TextBlock(
                    type="text",
                    text=f"Failed to get time: {str(e)}",
                ),
            ],
        )


async def get_current_date() -> ToolResponse:
    """Get the current date.

    Returns:
        ToolResponse containing the current date and weekday.
    """
    try:
        current_date = datetime.now().strftime("%Y-%m-%d")
        weekday = datetime.now().strftime("%A")
        logger.info(f"🔧 [ReAct] tool call: get_current_date → {current_date} {weekday}")
        return ToolResponse(
            content=[
                TextBlock(
                    type="text",
                    text=f"Today is {current_date}, {weekday}",
                ),
            ],
        )
    except Exception as e:
        return ToolResponse(
            content=[
                TextBlock(
                    type="text",
                    text=f"Failed to get date: {str(e)}",
                ),
            ],
        )


async def search_weather(location: str, days: int = 1) -> ToolResponse:
    """Look up the weather for a given location.

    Args:
        location: Place name, e.g. "Beijing", "Shanghai"
        days: Number of days to forecast, default 1

    Returns:
        ToolResponse containing weather information.
    """
    try:
        logger.info(f"🔧 [ReAct] tool call: search_weather → {location}, {days} day(s)")
        weather_data = {
            "Beijing":   {"temp": "15°C", "condition": "Sunny",    "humidity": "45%"},
            "Shanghai":  {"temp": "20°C", "condition": "Cloudy",   "humidity": "65%"},
            "Guangzhou": {"temp": "28°C", "condition": "Showers",  "humidity": "80%"},
            "Shenzhen":  {"temp": "27°C", "condition": "Overcast", "humidity": "75%"},
        }
        if location in weather_data:
            info = weather_data[location]
            return ToolResponse(
                content=[
                    TextBlock(
                        type="text",
                        text=(
                            f"Weather in {location}: {info['condition']}, "
                            f"{info['temp']}, humidity {info['humidity']}"
                        ),
                    ),
                ],
            )
        else:
            return ToolResponse(
                content=[
                    TextBlock(
                        type="text",
                        text=(
                            f"Sorry, no weather data for '{location}'. "
                            "Supported cities: Beijing, Shanghai, Guangzhou, Shenzhen"
                        ),
                    ),
                ],
            )
    except Exception as e:
        return ToolResponse(
            content=[
                TextBlock(
                    type="text",
                    text=f"Failed to fetch weather: {str(e)}",
                ),
            ],
        )


async def calculate(expression: str) -> ToolResponse:
    """Evaluate a mathematical expression.

    Args:
        expression: A math expression, e.g. "2+3*4"

    Returns:
        ToolResponse containing the result.
    """
    try:
        logger.info(f"🔧 [ReAct] tool call: calculate → {expression}")
        result = eval(expression, {"__builtins__": {}}, {})
        return ToolResponse(
            content=[
                TextBlock(
                    type="text",
                    text=f"{expression} = {result}",
                ),
            ],
        )
    except Exception as e:
        return ToolResponse(
            content=[
                TextBlock(
                    type="text",
                    text=f"Calculation failed: {str(e)}",
                ),
            ],
        )


async def search_online(query: str, num_results: int = 3) -> ToolResponse:
    """Search the web for the given query.

    Args:
        query: Search keywords
        num_results: Number of results to return, default 3

    Returns:
        ToolResponse containing search results.
    """
    try:
        logger.info(f"🔧 [ReAct] tool call: search_online → {query}")
        mock_results = [
            f"Search result {i+1} for '{query}'"
            for i in range(num_results)
        ]
        results_text = "\n".join(mock_results)
        return ToolResponse(
            content=[
                TextBlock(
                    type="text",
                    text=f"Search results:\n{results_text}",
                ),
            ],
        )
    except Exception as e:
        return ToolResponse(
            content=[
                TextBlock(
                    type="text",
                    text=f"Search failed: {str(e)}",
                ),
            ],
        )


def create_girlfriend_toolkit():
    """Create the AI companion toolkit."""
    from agentscope.tool import Toolkit

    toolkit = Toolkit()
    toolkit.register_tool_function(get_current_time)
    toolkit.register_tool_function(get_current_date)
    toolkit.register_tool_function(search_weather)
    toolkit.register_tool_function(calculate)
    toolkit.register_tool_function(search_online)

    return toolkit


if __name__ == "__main__":
    import asyncio

    async def test_tools():
        print(await get_current_time())
        print(await get_current_date())
        print(await search_weather("Beijing"))
        print(await calculate("2+3*4"))

    asyncio.run(test_tools())
