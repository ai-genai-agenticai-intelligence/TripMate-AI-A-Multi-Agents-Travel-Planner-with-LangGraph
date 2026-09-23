import os
import re
from datetime import datetime, timedelta
import requests
from dotenv import load_dotenv
import airportsdata
import pycountry

load_dotenv()

SERPAPI_KEY = os.getenv("SERPAPI_API_KEY")
DEFAULT_ORIGIN_IATA = os.getenv("DEFAULT_ORIGIN_IATA", "DAC")
AIRPORTS = airportsdata.load("IATA")

COUNTRY_ALIASES = {
    "usa": "US",
    "u.s.a": "US",
    "u.s.": "US",
    "america": "US",
    "united states": "US",
    "uk": "GB",
    "u.k.": "GB",
    "britain": "GB",
    "england": "GB",
    "uae": "AE",
    "dubai": "AE",
    "south korea": "KR",
    "korea": "KR",
    "russia": "RU",
    "vietnam": "VN",
    "bangladesh": "BD",
    "india": "IN",
    "japan": "JP",
    "china": "CN",
    "singapore": "SG",
    "malaysia": "MY",
    "thailand": "TH",
    "indonesia": "ID",
    "nepal": "NP",
    "qatar": "QA",
    "saudi arabia": "SA",
    "turkey": "TR",
    "canada": "CA",
    "australia": "AU",
    "germany": "DE",
    "france": "FR",
    "italy": "IT",
    "spain": "ES",
}

COUNTRY_MAIN_AIRPORT = {
    "BD": "DAC",
    "IN": "DEL",
    "JP": "NRT",
    "US": "JFK",
    "GB": "LHR",
    "AE": "DXB",
    "SG": "SIN",
    "MY": "KUL",
    "TH": "BKK",
    "ID": "CGK",
    "CN": "PEK",
    "KR": "ICN",
    "NP": "KTM",
    "QA": "DOH",
    "SA": "JED",
    "TR": "IST",
    "CA": "YYZ",
    "AU": "SYD",
    "DE": "FRA",
    "FR": "CDG",
    "IT": "FCO",
    "ES": "MAD",
}

CITY_MAIN_AIRPORT = {
    "dhaka": "DAC",
    "delhi": "DEL",
    "new delhi": "DEL",
    "mumbai": "BOM",
    "kolkata": "CCU",
    "chennai": "MAA",
    "bangalore": "BLR",
    "bengaluru": "BLR",
    "tokyo": "NRT",
    "osaka": "KIX",
    "kyoto": "KIX",
    "new york": "JFK",
    "london": "LHR",
    "dubai": "DXB",
    "singapore": "SIN",
    "kuala lumpur": "KUL",
    "bangkok": "BKK",
    "doha": "DOH",
    "istanbul": "IST",
    "toronto": "YYZ",
    "sydney": "SYD",
    "paris": "CDG",
    "rome": "FCO",
    "madrid": "MAD",
    "frankfurt": "FRA",
}


def clean_text(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text)
    stop_words = [
        "flight", "flights", "ticket", "tickets", "trip", "travel",
        "plan", "complete", "days", "day", "including", "hotel",
        "hotels", "sightseeing", "under", "budget", "info", "information"
    ]
    words = [w for w in text.split() if w not in stop_words]
    return " ".join(words).strip()


def country_name_to_code(text: str):
    text = clean_text(text)
    if text in COUNTRY_ALIASES:
        return COUNTRY_ALIASES[text]

    try:
        country = pycountry.countries.lookup(text)
        return country.alpha_2
    except LookupError:
        pass

    for country in pycountry.countries:
        if country.name.lower() in text:
            return country.alpha_2

    for alias, code in COUNTRY_ALIASES.items():
        if alias in text:
            return code

    return None


def resolve_location_to_iata(location: str):
    if not location:
        return None
    raw = location.strip()
    if re.fullmatch(r"[A-Za-z]{3}", raw):
        code = raw.upper()
        if code in AIRPORTS:
            return code

    cleaned = clean_text(raw)
    if not cleaned:
        return None

    if cleaned in CITY_MAIN_AIRPORT:
        return CITY_MAIN_AIRPORT[cleaned]

    country_code = country_name_to_code(cleaned)
    if country_code and country_code in COUNTRY_MAIN_AIRPORT:
        return COUNTRY_MAIN_AIRPORT[country_code]

    return None


def find_location_mentions(query: str):
    q = query.lower()
    mentions = []
    for alias in COUNTRY_ALIASES:
        if re.search(rf"\b{re.escape(alias)}\b", q):
            mentions.append(alias)

    for country in pycountry.countries:
        name = country.name.lower()
        if len(name) >= 4 and re.search(rf"\b{re.escape(name)}\b", q):
            mentions.append(name)

    for city in CITY_MAIN_AIRPORT:
        if re.search(rf"\b{re.escape(city)}\b", q):
            mentions.append(city)

    unique = []
    for m in mentions:
        if m not in unique:
            unique.append(m)
    return unique


def parse_route(query: str):
    q_lower = query.lower()
    match = re.search(r"\bfrom\s+(.+?)\s+\bto\s+(.+?)(?:\s+(?:on|for|under|including|with|in|at)\b|[.!?]|$)", q_lower)
    if match:
        return resolve_location_to_iata(match.group(1)), resolve_location_to_iata(match.group(2))

    match = re.search(r"\bto\s+(.+?)\s+\bfrom\s+(.+?)(?:\s+(?:on|for|under|including|with|in|at)\b|[.!?]|$)", q_lower)
    if match:
        return resolve_location_to_iata(match.group(2)), resolve_location_to_iata(match.group(1))

    mentions = find_location_mentions(q_lower)
    if len(mentions) >= 2:
        return resolve_location_to_iata(mentions[0]), resolve_location_to_iata(mentions[1])
    if len(mentions) == 1:
        return DEFAULT_ORIGIN_IATA, resolve_location_to_iata(mentions[0])

    return DEFAULT_ORIGIN_IATA, "NRT"


def format_google_flight(flight_option: dict):
    price = flight_option.get("price", "N/A")
    total_duration = flight_option.get("total_duration", "N/A")
    flights = flight_option.get("flights", [])

    flight_details = []
    for f in flights:
        airline = f.get("airline", "Unknown Airline")
        flight_no = f.get("flight_number", "")
        dep = f.get("departure_airport", {})
        arr = f.get("arrival_airport", {})
        dep_time = dep.get("time", "")
        dep_id = dep.get("id", "")
        arr_time = arr.get("time", "")
        arr_id = arr.get("id", "")
        duration = f.get("duration", "")
        airplane = f.get("airplane", "")

        flight_details.append(
            f"  - **{airline} {flight_no}** ({airplane})\n"
            f"    From: {dep_id} ({dep_time}) -> To: {arr_id} ({arr_time}) | Duration: {duration} mins"
        )

    layovers = flight_option.get("layovers", [])
    layover_text = ""
    if layovers:
        layover_text = "\n  Layovers: " + ", ".join([f"{l.get('name', 'Airport')} ({l.get('duration', 0)} mins)" for l in layovers])

    return f"""### Flight - Price: ${price} (Total Duration: {total_duration} mins)
""" + "\n".join(flight_details) + layover_text


def search_flights(query: str, outbound_date: str = None, limit: int = 5):
    if not SERPAPI_KEY:
        return (
            "Flight API error: SERPAPI_API_KEY is missing.\n"
            "Please add SERPAPI_API_KEY in your .env file."
        )

    dep_iata, arr_iata = parse_route(query)
    if not dep_iata:
        dep_iata = DEFAULT_ORIGIN_IATA
    if not arr_iata:
        arr_iata = "NRT"

    if not outbound_date:
        # Default to 30 days from today
        outbound_date = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")

    params = {
        "engine": "google_flights",
        "departure_id": dep_iata,
        "arrival_id": arr_iata,
        "outbound_date": outbound_date,
        "type": "2",  # One-way (or 1 for round-trip)
        "currency": "USD",
        "hl": "en",
        "api_key": SERPAPI_KEY,
    }

    try:
        response = requests.get("https://serpapi.com/search.json", params=params, timeout=30)
        data = response.json()
    except requests.exceptions.RequestException as e:
        return f"Flight API request failed: {e}"
    except ValueError:
        return "Flight API returned invalid response."

    if "error" in data:
        error_msg = data.get("error")
        return (
            f"SerpAPI Google Flights Error:\n{error_msg}\n\n"
            "Tip: If your SerpAPI account was just created, check your email to verify your account."
        )

    all_flights = data.get("best_flights", []) + data.get("other_flights", [])

    if not all_flights:
        return f"No flights found from {dep_iata} to {arr_iata} on {outbound_date}."

    formatted = [format_google_flight(f) for f in all_flights[:limit]]
    header = f"## Live Flight Options from {dep_iata} to {arr_iata} (Date: {outbound_date})\n"
    return header + "\n\n---\n\n".join(formatted)


if __name__ == "__main__":
    print(search_flights("Plan a 7 days Japan trip from Bangladesh"))
