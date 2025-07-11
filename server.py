import logging
from datetime import datetime
from typing import Any, Dict

import aiohttp
from mcp.server import FastMCP

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

mcp = FastMCP("Tehran Stock Exchange MCP Server")

STOCKS_CACHE = {}


def is_cache_valid(symbol: str) -> bool:
    return symbol in STOCKS_CACHE


def update_cache(symbol: str, instrument_code: str) -> None:
    STOCKS_CACHE[symbol] = instrument_code


def return_message(is_success: bool, data: Any, message: str = "") -> Dict[str, Any]:
    """
    Standardized response format

    Args:
        is_success: Whether the operation was successful
        data: The data to return
        message: Optional message for additional context

    Returns:
        Formatted response dictionary
    """
    response = {"isSuccess": is_success, "data": data}
    if message:
        response["message"] = message
    return response


async def make_request(url: str) -> dict:
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status != 200:
                return {"error": "Failed to fetch data"}
            data = await response.json()
    return data


@mcp.tool()
async def search_stock(query: str):
    """
    Search for stock names in Tehran stock market.
    Use this tool first to find the correct stock symbol before fetching data.
    The AI should present the results to the user and ask them to confirm which stock they want.

    Args:
        query (string): Stock name or symbol to search for

    Returns:
        Formatted list of possible stock matches
    """
    try:
        query = query.strip()

        url = f"https://cdn.tsetmc.com/api/Instrument/GetInstrumentSearch/{query}"

        search_result = await make_request(url)
        logger.info(f"Searching for stock: {query}")

        instruments = search_result.get("instrumentSearch")
        if not instruments:
            return return_message(
                False, "No Tickers found. Make sure you used a correct query"
            )
        top_results = instruments[:10]

        formatted_results = []
        for ticker in top_results:
            stock_data = {
                "name": ticker.get("lVal30", "Unknown"),
                "symbol": ticker.get("lVal18AFC", "Unknown"),
                "market_name": ticker.get("flowTitle", "Unknown"),
                "instrument_code": ticker.get("insCode", ""),
            }
            formatted_results.append(stock_data)

            symbol = ticker.get("lVal18AFC")
            instrument_code = ticker.get("insCode")
            if symbol and instrument_code:
                update_cache(symbol, instrument_code)

        return return_message(
            True,
            formatted_results,
            f"Found {len(formatted_results)} stocks matching '{query}'",
        )
    except Exception as e:
        logger.error(f"Unexpected error in search_stock: {str(e)}")
        return return_message(False, [], "An unexpected error occurred while searching")


@mcp.tool()
async def get_stock_info(symbol: str):
    """
    Retrieve latest stock information for the given ticker symbol.
    Returns the latest closing price and optionally historical data.
    args:
    symbol (string): Ticker symbol in Persian (e.g. خودرو)
    """
    symbol = symbol.strip()

    try:
        instrument_code = None
        if is_cache_valid(symbol):
            instrument_code = STOCKS_CACHE.get(symbol)
            logger.info(f"Using cached instrument code for {symbol}")

        if not instrument_code:
            return return_message(False, {},
                                  f"Stock '{symbol}' not found in cache. Please search for the stock first using search_stock tool.")

        url = (
            f"https://cdn.tsetmc.com/api/ClosingPrice/GetClosingPriceInfo/{instrument_code}"
        )

        result = await make_request(url)

        closing_price = result.get("closingPriceInfo")
        if not closing_price:
            return return_message(False, {}, f"No trading data found for '{symbol}'")

        stock_info = {
            "symbol": symbol,
            "instrument_code": instrument_code,
            "date": closing_price.get("dEven"),
            "trading_data": {
                "open": closing_price.get("price_first"),
                "close": closing_price.get("pDrCotVal"),
                "high": closing_price.get("priceMax"),
                "low": closing_price.get("priceMin"),
                "last": closing_price.get("last"),
                "yesterday_price": closing_price.get("priceYesterday"),
                "change": None,
                "change_percent": None
            },
            "volume_data": {
                "total_transactions": closing_price.get("zTotTran"),
                "total_volume": closing_price.get("qTotTran5J"),
                "total_value_rial": closing_price.get("qTotCap"),
                "total_value_millions": None  # Will be calculated
            },
            "timestamp": datetime.now().isoformat()
        }

        current_price = stock_info["trading_data"]["close"]
        yesterday_price = stock_info["trading_data"]["yesterday_price"]

        if current_price and yesterday_price:
            change = current_price - yesterday_price
            change_percent = (change / yesterday_price) * 100 if yesterday_price != 0 else 0
            stock_info["trading_data"]["change"] = change
            stock_info["trading_data"]["change_percent"] = round(change_percent, 2)

        total_value = stock_info["volume_data"]["total_value_rial"]
        if total_value:
            stock_info["volume_data"]["total_value_millions"] = round(total_value / 1_000_000, 2)

        return return_message(True, stock_info, f"Successfully retrieved data for {symbol}")
    except Exception as e:
        logger.error(f"Unexpected error in get_stock_info: {str(e)}")
        return return_message(False, {}, "An unexpected error occurred while fetching stock data")


@mcp.tool()
async def get_stock_history(symbol: str, days: int = 30) -> Dict[str, Any]:
    """
    Retrieve historical stock data for the given ticker symbol.

    Args:
        symbol: Ticker symbol in Persian (e.g. خودرو)
        days: Number of days of historical data to retrieve (default: 30, max: 365)

    Returns:
        Historical stock data with success/failure status
    """
    if not symbol or not symbol.strip():
        return return_message(False, [], "Symbol cannot be empty")

    symbol = symbol.strip()

    if not isinstance(days, int) or days < 1:
        days = 30
    elif days > 365:
        days = 365

    try:
        instrument_code = None
        if is_cache_valid(symbol):
            instrument_code = STOCKS_CACHE.get(symbol)

        if not instrument_code:
            return return_message(
                False,
                [],
                f"Stock '{symbol}' not found in cache. Please search for the stock first using search_stock tool.",
            )

        url = f"https://cdn.tsetmc.com/api/ClosingPrice/GetClosingPriceDailyList/{instrument_code}/0"
        logger.info(f"Fetching historical data for: {symbol}")

        result = await make_request(url)
        daily_data = result.get("closingPriceDaily", [])

        if not daily_data:
            return return_message(False, [], f"No historical data found for '{symbol}'")

        daily_data.sort(key=lambda x: x.get("dEven", ""), reverse=True)
        recent_data = daily_data[:days]

        formatted_history = []
        for day in recent_data:
            formatted_day = {
                "date": day.get("dEven"),
                "open": day.get("price_first"),
                "high": day.get("priceMax"),
                "low": day.get("priceMin"),
                "close": day.get("last"),
                "volume": day.get("qTotTran5J"),
                "value": day.get("qTotCap"),
                "transactions": day.get("zTotTran"),
            }
            formatted_history.append(formatted_day)

        return return_message(
            True,
            formatted_history,
            f"Retrieved {len(formatted_history)} days of historical data for {symbol}",
        )

    except Exception as e:
        logger.error(f"Unexpected error in get_stock_history: {str(e)}")
        return return_message(
            False, [], "An unexpected error occurred while fetching historical data"
        )
