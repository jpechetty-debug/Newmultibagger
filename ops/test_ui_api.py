
import requests
import sys

BASE_URL = "http://127.0.0.1:8000"

def test_slippage_stats():
    print("Testing /api/slippage_stats...")
    try:
        res = requests.get(f"{BASE_URL}/api/slippage_stats", timeout=5)
        if res.status_code == 200:
            data = res.json()
            if isinstance(data, list):
                print(f"✅ Success. Records: {len(data)}")
                if data:
                    print(f"   Sample: {data[0]}")
            else:
                print(f"❌ Failed: Expected list, got {type(data)}")
        else:
            print(f"❌ Failed: Status {res.status_code}")
    except Exception as e:
        print(f"❌ Failed: {e}")

def test_regime_status():
    print("Testing /api/regime_status...")
    try:
        res = requests.get(f"{BASE_URL}/api/regime_status", timeout=5)
        if res.status_code == 200:
            data = res.json()
            if "regime" in data and "vix" in data:
                print(f"✅ Success. Regime: {data['regime']}, VIX: {data['vix']}")
            else:
                print(f"❌ Failed: Missing keys in {data.keys()}")
        else:
            print(f"❌ Failed: Status {res.status_code}")
    except Exception as e:
        print(f"❌ Failed: {e}")

if __name__ == "__main__":
    test_slippage_stats()
    test_regime_status()
