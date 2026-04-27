import requests
import yfinance as yf
import trafilatura
import json
import os

def test_serper():
    print("--- Testing Serper ---")
    url = "https://google.serper.dev/search"
    payload = json.dumps({"q": "Deep Learning"})
    headers = {
        'X-API-KEY': 'cc1361280fd7656b11cd5826b37faa171f82e2a0',
        'Content-Type': 'application/json'
    }
    response = requests.request("POST", url, headers=headers, data=payload)
    if response.status_code == 200:
        print("Serper OK: ", response.json().get("searchParameters", {}))
    else:
        print(f"Serper Failed: {response.status_code} {response.text}")

def test_semantic_scholar():
    print("--- Testing Semantic Scholar ---")
    url = "https://api.semanticscholar.org/graph/v1/paper/search"
    params = {"query": "Transformer models", "limit": 2}
    r = requests.get(url, params=params, timeout=10)
    if r.status_code == 200:
        print("Semantic Scholar OK")
    else:
        print(f"Semantic Scholar Failed: {r.status_code}")

def test_crossref():
    print("--- Testing Crossref ---")
    url = "https://api.crossref.org/works"
    params = {"query": "Attention is all you need", "rows": 1}
    r = requests.get(url, params=params, timeout=10)
    if r.status_code == 200:
        print("Crossref OK")
    else:
        print(f"Crossref Failed: {r.status_code}")

def test_yfinance():
    print("--- Testing yfinance ---")
    try:
        msft = yf.Ticker("MSFT")
        hist = msft.history(period="1d")
        print(f"yfinance OK: MSFT last close {hist['Close'].iloc[-1]}")
    except Exception as e:
        print(f"yfinance Failed: {e}")

def test_trafilatura():
    print("--- Testing Trafilatura ---")
    downloaded = trafilatura.fetch_url("https://www.google.com")
    result = trafilatura.extract(downloaded)
    if result:
        print("Trafilatura OK (Length: ", len(result), ")")
    else:
        print("Trafilatura Failed")

if __name__ == "__main__":
    test_serper()
    test_semantic_scholar()
    test_crossref()
    test_yfinance()
    test_trafilatura()
