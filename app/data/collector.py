import yfinance as yf


def get_stock_data(stocksTickers: list):
    dailyData = []

    for ticker in stocksTickers:
        dat = yf.Ticker(ticker)

        dailyData.append(dat.history(period="1d"))

    print(dailyData)

    return dailyData


def get_portfolio_ticeckers():
    return None
