#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
retrieval_untils.py - 得理开放平台法规检索工具模块

提供法规增强检索接口的调用功能，包含 access_token 自动管理
注意：文件名保持 untils 拼写以兼容现有项目
"""

import os
import json
import time
import requests
from typing import Optional, List, Dict, Any


# ===============================
# 配置部分
# ===============================
BASE_URL = os.getenv("DELI_BASE_URL", "https://openapi.delilegal.com")
APP_ID = os.getenv("DELI_APP_ID", "GHIEnCuVXykbuwrp")
APP_SECRET = os.getenv("DELI_APP_SECRET", "0AA2FAC17FF94B7A961736F2CA445432")
TOKEN_FILE = os.getenv("DELI_TOKEN_FILE", "token_cache.json")


# ===============================
# Token 管理函数
# ===============================
def _load_token_from_file() -> Optional[Dict[str, Any]]:
    """从本地文件读取缓存的 token"""
    if not os.path.exists(TOKEN_FILE):
        return None
    try:
        with open(TOKEN_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            # ✅ 修复：补全 "in data"
            if "access_token" in data and "expires_at" in data:
                return data
    except Exception as e:
        print(f"⚠️ 读取 token 缓存文件失败: {e}")
        return None
    return None


def _save_token_to_file(token_data: Dict[str, Any]) -> None:
    """保存 token 到本地文件"""
    try:
        with open(TOKEN_FILE, "w", encoding="utf-8") as f:
            json.dump(token_data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"⚠️ 保存 token 缓存文件失败: {e}")


def _fetch_new_token() -> str:
    """调用授权接口获取新的 access_token"""
    url = f"{BASE_URL}/oauth/authorize"
    params = {
        "appid": APP_ID,
        "secret": APP_SECRET,
        "grant_type": "client_credential"
    }
    
    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        raise Exception(f"请求 access_token 接口失败: {e}")
    
    if not data.get("success"):
        error_code = data.get("code")
        error_msg = data.get("msg", "未知错误")
        error_map = {
            10001: "appid 错误",
            10002: "secret 密钥错误", 
            9998: "调用次数超过默认阈值",
            9997: "参数错误",
            9999: "系统繁忙"
        }
        raise Exception(f"获取 access_token 失败 [{error_code}]: {error_map.get(error_code, error_msg)}")
    
    body = data.get("body", {})
    token = body.get("accessToken")
    expires_in = body.get("expiresIn", 7200)
    
    if not token:
        raise Exception("返回数据中未找到 accessToken 字段")
    
    # 提前5分钟刷新，利用平台缓冲期
    expires_at = time.time() + int(expires_in) - 300
    token_data = {
        "access_token": token,
        "expires_at": expires_at,
        "original_expires_in": expires_in
    }
    
    _save_token_to_file(token_data)
    print("✅ 已成功获取新 access_token 并写入缓存")
    return token


def get_access_token() -> str:
    """获取有效的 access_token（支持缓存 + 自动刷新）"""
    data = _load_token_from_file()
    
    if data:
        token = data["access_token"]
        expires_at = data["expires_at"]
        if time.time() < expires_at:
            return token
        else:
            print("⚠️ access_token 即将过期，正在刷新...")
    else:
        print("ℹ️ 未找到本地缓存，正在请求新 access_token...")
    
    return _fetch_new_token()


# ===============================
# 法规检索接口
# ===============================
def retrieve(
    query: str,
    top_k_embedding: int = 30,
    top_k_rerank: int = 10,
    dataset_name: str = "Deli",
    timeout: int = 120,
    instruct: str = "Given a legal query, retrieve relevant passages.",
    size: Optional[int] = None
) -> List[Dict[str, Any]]:
    """
    调用法规增强检索接口，获取相关法律条文
    """
    token = get_access_token()
    
    url = f"{BASE_URL}/api/v1/rag/article_v2"
    headers = {
        "Content-Type": "application/json",
        "authorization": token
    }
    
    result_size = size if size is not None else min(top_k_rerank, 10) if top_k_rerank else 3
    
    params = {
        "question": query,
        "size": result_size
    }
    
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        raise Exception(f"请求法规检索接口失败: {e}")
    
    if not data.get("success"):
        error_code = data.get("code")
        error_msg = data.get("msg", "未知错误")
        raise Exception(f"法规检索接口调用失败 [{error_code}]: {error_msg}")
    
    results = data.get("body", [])
    
    # 格式化返回结果
    formatted_results = []
    for item in results:
        formatted_results.append({
            "laws_name": item.get("lawsName", ""),
            "article_tag": item.get("articleTag", ""),
            "article_content": item.get("articleContent", ""),
            "timeliness_name": item.get("timelinessName", ""),
            "active_date": item.get("activeDate", ""),
            # 保留原始字段兼容旧代码
            "lawsName": item.get("lawsName", ""),
            "articleTag": item.get("articleTag", ""),
            "articleContent": item.get("articleContent", ""),
            "timelinessName": item.get("timelinessName", ""),
            "activeDate": item.get("activeDate", ""),
        })
    
    return formatted_results


# ===============================
# 辅助函数
# ===============================
def clear_token_cache() -> bool:
    """清除本地 token 缓存"""
    try:
        if os.path.exists(TOKEN_FILE):
            os.remove(TOKEN_FILE)
            print("✅ 已清除 token 缓存")
            return True
        return False
    except Exception as e:
        print(f"⚠️ 清除 token 缓存失败: {e}")
        return False


def get_token_info() -> Optional[Dict[str, Any]]:
    """获取当前 token 信息（不刷新）"""
    data = _load_token_from_file()
    if data:
        remaining = data["expires_at"] - time.time()
        return {
            "has_token": True,
            "expires_at": data["expires_at"],
            "remaining_seconds": max(0, int(remaining)),
            "is_valid": remaining > 0
        }
    return {"has_token": False}


# ===============================
# 测试入口
# ===============================
if __name__ == "__main__":
    test_query = "劳动合同解除的法律依据"
    try:
        results = retrieve(test_query, size=3)
        print(f"✅ 检索成功，返回 {len(results)} 条结果:\n")
        for i, item in enumerate(results, 1):
            print(f"{i}. 【{item['laws_name']}】{item['article_tag']}")
            print(f"   内容: {item['article_content'][:100]}...")
            print(f"   时效: {item['timeliness_name']} | 实施: {item['active_date']}\n")
    except Exception as e:
        print(f"❌ 测试失败: {e}")