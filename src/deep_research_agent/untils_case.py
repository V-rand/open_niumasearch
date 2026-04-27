import os
import json
import time
import requests
import trafilatura


## 得理案例调用接口
# ===============================
# 配置部分
# ===============================
APP_ID = "GHIEnCuVXykbuwrp"
APP_SECRET = "0AA2FAC17FF94B7A961736F2CA445432"
BASE_URL = "https://openapi.delilegal.com"
TOKEN_FILE = "token_cache.json"


# ===============================
# 内部函数
# ===============================
def _load_token_from_file():
    """从本地读取 token"""
    if not os.path.exists(TOKEN_FILE):
        return None
    try:
        with open(TOKEN_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if "access_token" in data and "expires_at" in data:
                return data
    except Exception:
        return None
    return None


def _save_token_to_file(token_data):
    """保存 token 到本地"""
    with open(TOKEN_FILE, "w", encoding="utf-8") as f:
        json.dump(token_data, f, indent=2, ensure_ascii=False)


def _fetch_new_token():
    """调用接口获取新的 token"""
    url = f"{BASE_URL}/oauth/authorize"
    params = {
        "appid": APP_ID,
        "secret": APP_SECRET,
        "grant_type": "client_credential"
    }

    resp = requests.get(url, params=params, timeout=10)
    data = resp.json()

    if not data.get("success"):
        raise Exception(f"获取 access_token 失败: {data.get('msg')}")

    body = data.get("body", {})
    token = body.get("accessToken")
    expires_in = body.get("expiresIn", 7200)
    if not token:
        raise Exception("返回数据中未找到 accessToken 字段")

    expires_at = time.time() + int(expires_in)
    token_data = {"access_token": token, "expires_at": expires_at}

    _save_token_to_file(token_data)
    print("✅ 已成功获取新 token 并写入缓存。")
    return token


def get_access_token():
    """自动获取有效 token（缓存 + 自动刷新）"""
    data = _load_token_from_file()

    if data:
        token = data["access_token"]
        expires_at = data["expires_at"]
        # 提前5分钟刷新
        if time.time() < expires_at - 300:
            return token
        else:
            print("⚠️ token 即将过期，正在刷新...")
    else:
        print("ℹ️ 未找到本地缓存，正在请求新 token...")

    return _fetch_new_token()


# ===============================
# 对外接口函数
# ===============================
def get_case_results(question: str, size: int = 5, debug = False):
    """调用案例接口"""
    token = get_access_token()
    url = f"{BASE_URL}/api/v1/rag/case"
    headers = {
        "Content-Type": "application/json",
        "authorization": token
    }
    params = {"question": question, "size": size}

    resp = requests.get(url, headers=headers, params=params, timeout=10)
    data = resp.json()

    if not data.get("success"):
        raise Exception(f"调用案例接口失败: {data.get('msg')}")

    results = data["body"]
    if debug:
        print(f"✅ 成功获取 {len(results)} 条案例结果\n")
        for i, case in enumerate(results, 1):
            print(f"📄 {i}. {case['title']}")
            print(case['content'][:200].replace("\n", " ") + "...\n")

    return results