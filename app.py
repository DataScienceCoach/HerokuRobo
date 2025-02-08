import os
import time
import threading
from flask import Flask, request, jsonify, session
import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import streamlit as st
import requests

# Setup Flask
app = Flask(__name__)
app.secret_key = os.urandom(24)  # Secret key for session management

# Initialize MetaTrader5 for a specific user
def connect_mt5(account_id, password, server):
    if not mt5.initialize():
        return jsonify({"status": "error", "message": "MT5 initialization failed."}), 400

    authorized = mt5.login(login=account_id, password=password, server=server)
    if not authorized:
        return jsonify({"status": "error", "message": f"Failed to connect to account #{account_id}."}), 400

    # Save the MT5 session to Flask's session storage for the user
    session['mt5_session'] = {
        'account_id': account_id,
        'server': server
    }
    return jsonify({"status": "success", "message": "Connected to MetaTrader5."}), 200


@app.route("/connect_mt5", methods=["POST"])
def connect_mt5_route():
    data = request.get_json()
    account_id = data.get('account_id')
    password = data.get('password')
    server = data.get('server')

    if not account_id or not password or not server:
        return jsonify({"status": "error", "message": "Missing credentials."}), 400

    connection_response = connect_mt5(account_id, password, server)
    return connection_response


@app.route("/fetch_btc_data", methods=["GET"])
def fetch_btc_data():
    if 'mt5_session' not in session:
        return jsonify({"status": "error", "message": "User not connected to MT5."}), 400

    symbol = request.args.get("symbol", "BTCUSD")
    timeframe = int(request.args.get("timeframe", 5))  # Default M5
    num_bars = int(request.args.get("num_bars", 1000))

    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, num_bars)
    if rates is None:
        return jsonify({"status": "error", "message": "Failed to fetch rates."}), 400

    btc_data = pd.DataFrame(rates)
    btc_data['time'] = pd.to_datetime(btc_data['time'], unit='s')
    btc_data.set_index('time', inplace=True)

    return btc_data.to_json(date_format='iso')


@app.route("/execute_trade", methods=["POST"])
def execute_trade():
    data = request.get_json()
    symbol = data.get('symbol')
    action = data.get('action')
    lot_size = data.get('lot_size')

    if not symbol or not action or not lot_size:
        return jsonify({"status": "error", "message": "Missing required parameters."}), 400

    symbol_info = mt5.symbol_info(symbol)
    if not symbol_info:
        return jsonify({"status": "error", "message": f"Symbol {symbol} not found."}), 400

    price = mt5.symbol_info_tick(symbol).ask if action == 'U' else mt5.symbol_info_tick(symbol).bid
    take_profit = price + 0.00010 if action == 'U' else price - 0.00010

    order_type = 0 if action == 'U' else 1  # 0 for Buy, 1 for Sell

    request_data = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": lot_size,
        "type": order_type,
        "price": price,
        "tp": take_profit,
        "deviation": 20,
        "magic": 234000,
        "comment": f"Trade {action}",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    result = mt5.order_send(request_data)
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        return jsonify({"status": "error", "message": f"Trade failed: {result.retcode}"}), 400

    return jsonify({"status": "success", "message": f"Trade executed at price {price} with TP {take_profit}."}), 200


# Run Flask in a separate thread
def run_flask():
    app.run(debug=True, host="0.0.0.0", port=5000)


# Streamlit app function
def run_streamlit():
    st.title("Live Trading with MetaTrader 5")

    account_id = st.sidebar.number_input("MT5 Account ID", value=123456789)
    password = st.sidebar.text_input("MT5 Password", type="password")
    server = st.sidebar.text_input("MT5 Server", value="MetaQuotes-Demo")

    ticker = st.sidebar.text_input("Ticker", value="EURUSD")
    interval = st.sidebar.selectbox("Data Interval", ["M1", "M5", "M15", "H1", "D1"], index=2)
    num_candles = st.sidebar.number_input("Number of Candles for Prediction", value=10, min_value=5)
    lot_size = st.sidebar.number_input("Lot Size", value=0.1, min_value=0.01, step=0.01)

    # Function to connect to MT5 using the Flask backend
    def connect_to_mt5(account_id, password, server):
        try:
            response = requests.post("http://127.0.0.1:5000/connect_mt5", json={
                "account_id": account_id,
                "password": password,
                "server": server
            })

            if response.status_code == 200:
                return response.json()
            else:
                st.error(f"Error connecting: {response.json()['message']}")
                return None
        except Exception as e:
            st.error(f"An error occurred: {str(e)}")
            return None

    if st.sidebar.button("Connect to MetaTrader 5"):
        connection_status = connect_to_mt5(account_id, password, server)
        if connection_status and connection_status['status'] == 'success':
            st.write("Connected to MetaTrader 5.")
        else:
            st.write("Failed to connect to MetaTrader 5.")

    # Fetch Data and Execute Trade as before...
    def fetch_btc_data():
        try:
            response = requests.get(f"http://127.0.0.1:5000/fetch_btc_data?symbol={ticker}&timeframe=5")
            if response.status_code == 200:
                btc_data = response.json()
                btc_df = pd.read_json(btc_data)
                return btc_df
            else:
                st.error(f"Error fetching data: {response.json()['message']}")
                return pd.DataFrame()
        except Exception as e:
            st.error(f"An error occurred: {str(e)}")
            return pd.DataFrame()

    btc_data = fetch_btc_data()
    if not btc_data.empty:
        st.write("Fetched BTC Data:")
        st.dataframe(btc_data)


# Run Flask and Streamlit in separate threads
flask_thread = threading.Thread(target=run_flask)
streamlit_thread = threading.Thread(target=run_streamlit)

flask_thread.start()
time.sleep(2)  # Give Flask server time to start before running Streamlit
streamlit_thread.start()

