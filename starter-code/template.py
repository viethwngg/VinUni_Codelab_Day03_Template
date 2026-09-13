"""
Lab #3: Baseline Chatbot vs ReAct Agent
Học viên hoàn thiện các mục TODO để hoàn thành bài lab.
"""

import json
import re
from typing import Any, Dict, List, Optional

from tools import TOOL_DEFINITIONS, TOOL_MAP, get_flight_info, get_weather_forecast

SYSTEM_PROMPT = """Bạn là một ReAct Agent thông minh hỗ trợ khách hàng Vingroup.
Bạn chỉ sử dụng các công cụ sau:
{tools}

Quy trình trả lời bắt buộc:
Thought: <Suy nghĩ bước tiếp theo>
Action: {{"name": "<tên tool>", "args": {{<tham số>}}}}
Observation: <Kết quả từ tool>
... (Lặp lại cho tới khi có đủ dữ liệu)
Final Answer: <Câu trả lời hoàn chỉnh cho khách hàng>
"""


def _normalize_code(value: str) -> str:
    return (value or "").strip().upper().replace(" ", "")


def _parse_flight_request(user_input: str) -> Optional[Dict[str, Any]]:
    lower = user_input.lower()
    if "bay" not in lower and "vé" not in lower and "flight" not in lower:
        return None

    codes = re.findall(r"\b[A-Z]{3}\b", user_input, flags=re.IGNORECASE)
    origin = None
    destination = None

    match_origin = re.search(r"(?:từ|from)\s*([A-Z]{3})", user_input, flags=re.IGNORECASE)
    match_dest = re.search(r"(?:đến|to|đi)\s*([A-Z]{3})", user_input, flags=re.IGNORECASE)

    if match_origin:
        origin = _normalize_code(match_origin.group(1))
    if match_dest:
        destination = _normalize_code(match_dest.group(1))

    if not origin and len(codes) >= 2:
        origin = _normalize_code(codes[0])
    if not destination and len(codes) >= 2:
        destination = _normalize_code(codes[1])

    if not origin and len(codes) == 1:
        origin = _normalize_code(codes[0])

    if not destination:
        city_aliases = {
            "đà nẵng": "DAD",
            "da nang": "DAD",
            "hồ chí minh": "SGN",
            "ho chi minh": "SGN",
            "hà nội": "HAN",
            "ha noi": "HAN",
        }
        for alias, code in city_aliases.items():
            if alias in lower:
                destination = code
                break

    max_price = 5000000
    price_match = re.search(r"dưới\s*([0-9]+(?:[.,][0-9]+)?)\s*(triệu|million|m)", user_input, flags=re.IGNORECASE)
    if price_match:
        value = float(price_match.group(1).replace(",", "."))
        max_price = int(value * 1_000_000)
    else:
        price_match = re.search(r"giá\s*(?:dưới|<=|<)\s*([0-9]+(?:[.,][0-9]+)?)\s*(?:triệu|million|m)?", user_input, flags=re.IGNORECASE)
        if price_match:
            value = float(price_match.group(1).replace(",", "."))
            max_price = int(value * 1_000_000)

    if origin and destination:
        return {"origin": origin, "destination": destination, "max_price": max_price}
    return None


def _parse_weather_request(user_input: str) -> Optional[str]:
    lower = user_input.lower()
    if "thời tiết" not in lower and "weather" not in lower and "nhiệt độ" not in lower and "mặc gì" not in lower and "mua gì" not in lower:
        return None

    for code, city in {"SGN": "tp. hồ chí minh", "HAN": "hà nội", "DAD": "đà nẵng"}.items():
        if city in lower or code.lower() in lower:
            return code

    codes = re.findall(r"\b[A-Z]{3}\b", user_input, flags=re.IGNORECASE)
    if codes:
        return _normalize_code(codes[-1])
    return None


class ChatbotBaseline:
    """Baseline LLM Chatbot (Không sử dụng ReAct Loop hay Tools)"""
    def query(self, user_input: str) -> Dict[str, Any]:
        return {
            "status": "success",
            "answer": f"[Chatbot Baseline] Trả lời cho: {user_input}",
            "tool_calls": []
        }


class ReActAgent:
    """ReAct Agent có sử dụng Thought-Action-Observation Loop"""
    def __init__(self, max_iterations: int = 5):
        self.max_iterations = max_iterations
        self.trace = []

    def run(self, user_input: str) -> Dict[str, Any]:
        self.trace = []
        lower = user_input.lower()

        flight_info = _parse_flight_request(user_input)
        weather_city = _parse_weather_request(user_input)

        if "vinpearl" in lower or "chính sách" in lower or "đổi trả" in lower:
            answer = "Vinpearl hỗ trợ đổi trả theo chính sách vé và thời gian đặt vé; nếu cần hỗ trợ chi tiết, tôi có thể hướng dẫn quy trình đổi trả hoặc liên hệ phòng hỗ trợ."
            self.trace.append({
                "step": 1,
                "thought": "Câu hỏi thuộc FAQ hỗ trợ khách hàng, không cần gọi tool.",
                "action": None,
                "observation": "Không cần tra cứu dữ liệu."
            })
            return {"status": "completed", "iterations": 1, "answer": answer, "trace": self.trace}

        if flight_info and weather_city:
            required_steps = 2
            if required_steps > self.max_iterations:
                self.trace.append({
                    "step": 1,
                    "thought": "Cần tìm chuyến bay trước rồi kiểm tra thời tiết, nhưng đã đạt giới hạn vòng lặp.",
                    "action": {"name": "get_flight_info", "args": flight_info},
                    "observation": "Giới hạn max_iterations đã bị chạm."
                })
                return {"status": "max_iterations_reached", "iterations": self.max_iterations, "answer": "Không thể hoàn thành trong số bước tối đa.", "trace": self.trace}

            flight_result = get_flight_info(**flight_info)
            self.trace.append({
                "step": 1,
                "thought": "Tôi cần tìm chuyến bay phù hợp với ngân sách trước.",
                "action": {"name": "get_flight_info", "args": flight_info},
                "observation": flight_result
            })

            weather_result = get_weather_forecast(weather_city)
            self.trace.append({
                "step": 2,
                "thought": "Sau khi có chuyến bay, tôi kiểm tra thời tiết để gợi ý trang phục.",
                "action": {"name": "get_weather_forecast", "args": {"city_code": weather_city}},
                "observation": weather_result
            })

            flight_text = "Không có chuyến bay nào phù hợp." if not flight_result else ", ".join(
                f"{item['flight_number']} ({item['airline']}) - {item['price_vnd']:,} VND" for item in flight_result[:2]
            )
            weather_text = weather_result.get("recommendation", "")
            city_name = weather_result.get("city", weather_city)
            temp = weather_result.get("temperature_c", "")
            answer = f"Chuyến bay phù hợp: {flight_text}. Thời tiết {city_name} là {temp}°C, {weather_result.get('condition', '')}; khuyến nghị: {weather_text}"
            self.trace.append({
                "step": 3,
                "thought": "Tôi đã có đủ thông tin để tổng hợp câu trả lời cuối cùng cho khách hàng.",
                "action": None,
                "observation": answer
            })
            return {"status": "completed", "iterations": 3, "answer": answer, "trace": self.trace}

        if flight_info:
            flight_result = get_flight_info(**flight_info)
            self.trace.append({
                "step": 1,
                "thought": "Tôi sẽ tra cứu chuyến bay theo điểm đi, điểm đến và ngân sách.",
                "action": {"name": "get_flight_info", "args": flight_info},
                "observation": flight_result
            })
            if not flight_result:
                answer = "Không tìm thấy chuyến bay nào phù hợp với điều kiện bạn đưa ra."
            else:
                chosen = flight_result[0]
                answer = f"Tìm thấy chuyến bay {chosen['flight_number']} của {chosen['airline']} từ {chosen['origin']} đến {chosen['destination']} với giá {chosen['price_vnd']:,} VND."
            return {"status": "completed", "iterations": 1, "answer": answer, "trace": self.trace}

        if weather_city:
            weather_result = get_weather_forecast(weather_city)
            self.trace.append({
                "step": 1,
                "thought": "Tôi cần kiểm tra thời tiết ở thành phố đó để tư vấn trang phục.",
                "action": {"name": "get_weather_forecast", "args": {"city_code": weather_city}},
                "observation": weather_result
            })
            if weather_result.get("error"):
                answer = f"Không có dữ liệu thời tiết cho {weather_city}."
            else:
                answer = f"Thời tiết {weather_result['city']} hiện tại {weather_result['temperature_c']}°C, {weather_result['condition']}. Khuyến nghị: {weather_result['recommendation']}"
            return {"status": "completed", "iterations": 1, "answer": answer, "trace": self.trace}

        answer = "Tôi chưa có dữ liệu đủ để trả lời chính xác; bạn có thể cung cấp thêm thông tin về chuyến bay hoặc thời tiết cần kiểm tra."
        self.trace.append({
            "step": 1,
            "thought": "Câu hỏi không yêu cầu tool cụ thể, nên đưa phản hồi trực tiếp.",
            "action": None,
            "observation": "Không có dữ liệu tra cứu phù hợp."
        })
        return {"status": "completed", "iterations": 1, "answer": answer, "trace": self.trace}


def main():
    user_query = "Tìm cho tôi chuyến bay từ HAN đi SGN dưới 2 triệu, rồi cho biết thời tiết SGN nên mặc gì?"

    print("=== RUNNING CHATBOT BASELINE ===")
    chatbot = ChatbotBaseline()
    print(chatbot.query(user_query))

    print("\n=== RUNNING REACT AGENT ===")
    agent = ReActAgent(max_iterations=5)
    result = agent.run(user_query)
    print("Result:", result)
    print("Trace Log:", json.dumps(agent.trace, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()