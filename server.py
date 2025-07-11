from typing import Any

from mcp.server import FastMCP
import aiohttp

mcp = FastMCP("Tehran Stock Exchange MCP Server")

STOCKS = {}

def return_message(is_success: bool, data: Any):

    return {"isSuccess": is_success,
            "data": data}
async def call_tse_api(url: str) -> dict:
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
    url = f"https://cdn.tsetmc.com/api/Instrument/GetInstrumentSearch/{query}"

    search_result = await call_tse_api(url)
    instruments = search_result.get("instrumentSearch")
    if not instruments:
        return return_message(False, "No Tickers found. Make sure you used a correct query")
    top_five_tickers = instruments[:5]

    final_result = []
    for ticker in top_five_tickers:
        final_result.append({
            "Name": ticker.get("lVal30"),
            "symbol": ticker.get("lVal18AFC"),
            "market_name": ticker.get("flowTitle")
        })

        STOCKS[ticker["lVal18AFC"]] = ticker["insCode"]
    return return_message(True, final_result)

@mcp.tool()
async def get_stock_info(symbol: str):
    """
    Retrieve stock information for the given ticker symbol.
    Returns the latest closing price and optionally historical data.
    args:
    symbol (string): Ticker symbol in Persian (e.g. خودرو)
    """
    # include_history (bool): Whether to include historical data.
    # from_date (str): Start date for historical data in YYYY-MM-DD format.
    # to_date (str): End date for historical data in YYYY-MM-DD format.
    instrument_code = STOCKS.get(symbol)
    if not instrument_code:
        return return_message(False, "No ticker found with this name. Make sure you used a correct name.")

    url = f"https://cdn.tsetmc.com/api/ClosingPrice/GetClosingPriceInfo/{instrument_code}"


    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status != 200:
                return {"error": "Failed to fetch stock data"}
            data = await response.json()
            closing_price = data['closingPriceInfo']
    result = await call_tse_api(url)
    closing_price = result.get('closingPriceInfo')
    if not closing_price:
        return return_message(False, "No data found for this ticker" )

    stock_info = {"symbol": symbol,
                  "open": closing_price.get("price_first", None),
                  "close": closing_price.get("pDrCotVal", None),
                  "high": closing_price.get("priceMax", None),
                  "low": closing_price.get("priceMin", None),
                  "last": closing_price.get("last", None),
                  "price_yesterday": closing_price.get("priceYesterday", None),
                  "total_transaction_count": closing_price.get("zTotTran"),
                  "total_transaction_volume": closing_price.get("qTotTran5J"),
                  "total_transaction_value_rial": closing_price.get("qTotCap"),
                  }

    return return_message(True, {"data": stock_info})