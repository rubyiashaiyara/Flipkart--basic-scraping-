import requests
import json

# API URL
url = "https://1.rome.api.flipkart.com/api/4/product/swatch"

# Headers
headers = {
    "Accept": "*/*",
    "Accept-Language":"en-GB,en-US;q=0.9,en;q=0.8,bn;q=0.7",
    "Connection":"keep-alive",
    "Content-Type":"application/json",
    "Origin":"https://www.flipkart.com",
    "Referer":"https://www.flipkart.com/",
    "User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36",
    "X-User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 FKUA/website/42/website/Desktop",
    "Cookie": "T=TI176114163742400191776133846725869996797322707757083100815840723137; ..."  # truncated
}

# JSON payload
payload = {
    "pidLidMap": {"SHTG6BKFG482ZGTJ": "LSTSHTG6BKFG482ZGTJXVXTX8"},
    "pincode": "",
    "snippetContext": {
        "facetMap": {},
        "layout": "grid",
        "query": "null",
        "queryType": "null",
        "storePath": "clo/ash/axc/mmk/bk1",
        "viewType": "QUICK_VIEW"
    },
    "showSuperTitle": True
}

# POST request
response = requests.post(url, headers=headers, data=json.dumps(payload))

# Save JSON response to file
if response.status_code == 200:
    data = response.json()  # Convert response to Python dict
    with open("flipkart_response.json", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)  # Save as pretty JSON
    print("Response saved to flipkart_response.json")
else:
    print(f"Request failed with status code: {response.status_code}")
    print(response.text)
