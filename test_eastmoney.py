import requests
import json

def test():
    url = "http://82.push2.eastmoney.com/api/qt/clist/get?pn=1&pz=10000&po=1&np=1&ut=bd1d9ddb04089700cf9c27f6f7426281&fltt=2&invt=2&fid=f3&fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048"
    try:
        res = requests.get(url).json()
        stocks = res['data']['diff']
        print(f"Total stocks fetched: {len(stocks)}")
        print(f"Sample 1: {stocks[0]['f12']} - {stocks[0]['f14']}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test()
