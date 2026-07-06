import requests

def test_sina():
    url = "https://suggest3.sinajs.cn/suggest/type=11,12,13,14,15&key=gdyt"
    res = requests.get(url)
    res.encoding = 'gbk'
    print(res.text)

    url2 = "https://suggest3.sinajs.cn/suggest/type=11,12,13,14,15&key=002152"
    res2 = requests.get(url2)
    res2.encoding = 'gbk'
    print(res2.text)
    
if __name__ == "__main__":
    test_sina()
