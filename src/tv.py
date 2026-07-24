"""External chart links."""


def tradingview_chart_url(stock_code: str) -> str:
    """국내 상장주 TradingView 차트 URL (KRX)."""
    code = str(stock_code).zfill(6)
    return f"https://kr.tradingview.com/chart/?symbol=KRX%3A{code}"
