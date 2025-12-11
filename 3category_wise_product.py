# file: flipkart_search.py
import requests
import json
from urllib.parse import quote_plus

def flipkart_search():
    query = input("Enter search keyword: ").strip()
    encoded_query = quote_plus(query)

    user_url = f"https://www.flipkart.com/search?q={encoded_query}&otracker=AS_Query_HistoryAutoSuggest_5_0&otracker1=AS_Query_HistoryAutoSuggest_5_0&marketplace=FLIPKART&as-show=on&as=off&as-pos=5&as-type=HISTORY"

    headers = {
        "Accept": "*/*",
        "Accept-Language": "en-GB,en;q=0.9",
        "Connection": "keep-alive",
        "Content-Type": "application/json",
        "Origin": "https://www.flipkart.com",
        "Referer": "https://www.flipkart.com/",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-site",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36",
        "X-User-Agent": "Mozilla/5.0 ...",
        "sec-ch-ua": "\"Chromium\";v=\"142\", \"Google Chrome\";v=\"142\", \"Not_A Brand\";v=\"99\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "Cookie": "T=TI176464610512100142815543819410152705989317520624841985171523562625; at=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCIsImtpZCI6IjFkOTYzYzUwLTM0YjctNDA1OC1iMTNmLWY2NDhiODFjYTBkYSJ9.eyJleHAiOjE3NjYzNzQxMDUsImlhdCI6MTc2NDY0NjEwNSwiaXNzIjoia2V2bGFyIiwianRpIjoiMTA5ZjIzMzMtZTI0ZC00YWQwLWI1MjgtOWFmNWUzODQ2MTA1IiwidHlwZSI6IkFUIiwiZElkIjoiVEkxNzY0NjQ2MTA1MTIxMDAxNDI4MTU1NDM4MTk0MTAxNTI3MDU5ODkzMTc1MjA2MjQ4NDE5ODUxNzE1MjM1NjI2MjUiLCJrZXZJZCI6IlZJQUZGNDFBQjk1NjE2NDRBNzk4RTJCNzAwNDYxRDA5MTUiLCJ0SWQiOiJtYXBpIiwidnMiOiJMTyIsInoiOiJIWUQiLCJtIjp0cnVlLCJnZW4iOjR9.JAG18MyQiAtAR0S6S0hV0W1QJVIRcHqTlsEQoxnu_PM; rt=null; K-ACTION=null; ud=0.kg-XnFW5gcfK9f7SstW1IN72H5ij2JFnXkB84-sRkKjeLx8FuK0ArnV4teTZg9SCn08Rp9txeGpCDJeljDGxueq8KJ84IgCIDOt2DYaI77UJMWDmLXpMvSd5QGsa6SWmZcWvDIegQeBi7JMMLQAwbg; AMCVS_17EB401053DAF4840A490D4C%40AdobeOrg=1; vd=VIAFF41AB9561644A798E2B700461D0915-1764646106755-1.1764646106.1764646106.152274686; AMCV_17EB401053DAF4840A490D4C%40AdobeOrg=-227196251%7CMCIDTS%7C20425%7CMCMID%7C87325980907535442201635451903102570408%7CMCAAMLH-1765250906%7C3%7CMCAAMB-1765250906%7C6G1ynYcLPuiQxYZrsz_pkqfLG9yMXBpb2zX5dvJdYQJzPXImdj0y%7CMCOPTOUT-1764653307s%7CNONE%7CMCAID%7CNONE; S=d1t15Pxs/BSIXBj9nPz9DPz8vYSopsQQrYbt1Vdgs8sX1P1yV9QQ2861L63doM2ZiZ5ADRsTx8eAD2iryGGhP8c27uw==; SN=VIAFF41AB9561644A798E2B700461D0915.TOKF13F99E7F5DE4D2888587F304BF5FD8B.1764646134942.LO; s_sq=flipkart-prd%3D%2526pid%253Dwww.flipkart.com%25253Aflyscape-terror-black-bag-25-l-backpack%25253Ap%25253Aitm7419dd3e030c0%2526pidt%253D1%2526oid%253Dhttps%25253A%25252F%25252Fwww.flipkart.com%25252Fsearch%25253Fq%25253Dshoes%252526as%25253Don%252526as-show%25253Don%252526otracker%25253DAS_Query_OrganicAutoSuggest_6_2_na%2526ot%253DA"
    }

    payload = {
        "pageUri": user_url,
        "pageContext": {
            "fetchSeoData": True,
            "paginatedFetch": False,
            "pageNumber": 1
        },
        "requestContext": {
            "type": "BROWSE_PAGE",
            "ssid": "e72a0gdu...",
            "sqid": "plfyx74d..."
        }
    }

    endpoint = "https://1.rome.api.flipkart.com/api/4/product/swatch"

    response = requests.post(
        endpoint,
        headers=headers,
        data=json.dumps(payload)
    )

    print("\n--- RAW RESPONSE ---\n")
    print(response.text)

flipkart_search()
