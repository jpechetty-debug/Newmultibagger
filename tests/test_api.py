from fastapi.testclient import TestClient
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from main import app

client = TestClient(app)

def test_read_root():
    response = client.get("/")
    assert response.status_code == 200

def test_get_stocks():
    response = client.get("/api/stocks")
    assert response.status_code == 200
    assert isinstance(response.json(), list)

def test_get_microcaps():
    response = client.get("/api/microcaps")
    assert response.status_code == 200
    assert isinstance(response.json(), list)
