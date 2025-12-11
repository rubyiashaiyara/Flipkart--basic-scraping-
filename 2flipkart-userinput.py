import requests
import json

# Take user input
keyword = input("Enter the product keyword: ")
product_id = input("Enter the product ID: ")  

url = "https://1.rome.api.flipkart.com/api/4/product/swatch"

headers = {
    "Accept": "*/*",
    "Accept-Language": "en-GB,en-US;q=0.9,en;q=0.8,bn;q=0.7",
    "Connection": "keep-alive",
    "Content-Type": "application/json",
    "Origin": "https://www.flipkart.com",
    "Referer": "https://www.flipkart.com/",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36",
    "X-User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 FKUA/website/42/website/Desktop",
    "Cookie": "T=...; ..."  # keep your actual cookie here
}

payload = {
    "pidLidMap": {product_id: product_id + "XVXTX8"},  # dynamic
    "pincode": "",
    "snippetContext": {
        "facetMap": {},
        "layout": "grid",
        "query": keyword,           # dynamic keyword
        "queryType": "null",
        "storePath": "clo/ash/axc/mmk/bk1",
        "viewType": "QUICK_VIEW"
    },
    "showSuperTitle": True
}

response = requests.post(url, headers=headers, json=payload)

print("Status Code:", response.status_code)
print("Response:", response.text)  
