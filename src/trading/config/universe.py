NIFTY_50_NSE = [
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS",
    "BHARTIARTL.NS", "SBIN.NS", "LT.NS", "HINDUNILVR.NS", "ITC.NS",
    "KOTAKBANK.NS", "BAJFINANCE.NS", "ASIANPAINT.NS", "AXISBANK.NS", "MARUTI.NS",
    "M&M.NS", "SUNPHARMA.NS", "TITAN.NS", "ULTRACEMCO.NS", "NTPC.NS",
    "NESTLEIND.NS", "POWERGRID.NS", "ONGC.NS", "COALINDIA.NS", "BAJAJFINSV.NS",
    "TATAMOTORS.NS", "JSWSTEEL.NS", "GRASIM.NS", "HINDALCO.NS", "ADANIENT.NS",
    "TATASTEEL.NS", "WIPRO.NS", "TECHM.NS", "HCLTECH.NS", "DRREDDY.NS",
    "CIPLA.NS", "DIVISLAB.NS", "EICHERMOT.NS", "BAJAJ-AUTO.NS", "BRITANNIA.NS",
    "HDFCLIFE.NS", "SBILIFE.NS", "BPCL.NS", "INDUSINDBK.NS", "APOLLOHOSP.NS",
    "HEROMOTOCO.NS", "ADANIPORTS.NS", "TATACONSUM.NS", "LTIM.NS", "SHRIRAMFIN.NS",
]

NIFTY_NEXT_50_NSE = [
    "ABB.NS", "ADANIENSOL.NS", "ADANIGREEN.NS", "ADANIPOWER.NS", "AMBUJACEM.NS",
    "BAJAJHLDNG.NS", "BANKBARODA.NS", "BEL.NS", "BERGEPAINT.NS", "BOSCHLTD.NS",
    "CANBK.NS", "CGPOWER.NS", "CHOLAFIN.NS", "COLPAL.NS", "DABUR.NS",
    "DLF.NS", "DMART.NS", "GAIL.NS", "GODREJCP.NS", "HAL.NS",
    "HAVELLS.NS", "HDFCAMC.NS", "ICICIGI.NS", "ICICIPRULI.NS", "IOC.NS",
    "IRCTC.NS", "IRFC.NS", "INDHOTEL.NS", "JINDALSTEL.NS", "LICI.NS",
    "LODHA.NS", "MARICO.NS", "MOTHERSON.NS", "NAUKRI.NS", "NMDC.NS",
    "PFC.NS", "PIDILITIND.NS", "PNB.NS", "POLYCAB.NS", "RECLTD.NS",
    "SHREECEM.NS", "SIEMENS.NS", "SRF.NS", "TATAPOWER.NS", "TORNTPHARM.NS",
    "TRENT.NS", "TVSMOTOR.NS", "UNITDSPR.NS", "VBL.NS", "VEDL.NS", "ZYDUSLIFE.NS",
]


SP_100_US = [
    "AAPL", "ABBV", "ABT", "ACN", "ADBE", "AIG", "AMD", "AMGN", "AMT", "AMZN",
    "AVGO", "AXP", "BA", "BAC", "BIIB", "BK", "BKNG", "BLK", "BMY", "BRK-B",
    "C", "CAT", "CHTR", "CL", "CMCSA", "COF", "COP", "COST", "CRM", "CSCO",
    "CVS", "CVX", "DD", "DHR", "DIS", "DOW", "DUK", "EMR", "EXC", "F",
    "FDX", "GD", "GE", "GILD", "GM", "GOOG", "GOOGL", "GS", "HD", "HON",
    "IBM", "INTC", "JNJ", "JPM", "KHC", "KMI", "KO", "LIN", "LLY", "LMT",
    "LOW", "MA", "MCD", "MDLZ", "MDT", "MET", "META", "MMM", "MO", "MRK",
    "MS", "MSFT", "NEE", "NFLX", "NKE", "NVDA", "ORCL", "PEP", "PFE", "PG",
    "PM", "PYPL", "QCOM", "RTX", "SBUX", "SCHW", "SO", "SPG", "T", "TGT",
    "TMO", "TMUS", "TSLA", "TXN", "UNH", "UNP", "UPS", "USB", "V", "VZ",
    "WBA", "WFC", "WMT", "XOM",
]


def get_universe(name: str = "nifty50") -> list[str]:
    if name == "nifty50":
        return list(NIFTY_50_NSE)
    if name == "nifty_next_50":
        return list(NIFTY_NEXT_50_NSE)
    if name == "nifty100":
        return list(NIFTY_50_NSE) + list(NIFTY_NEXT_50_NSE)
    if name == "sp100":
        return list(SP_100_US)
    raise ValueError(f"Unknown universe: {name}")
