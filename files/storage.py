import json
import os
from threading import Lock

RESULTS_FILE = os.path.join(os.path.dirname(__file__), "data", "results.json")
_lock = Lock()


def _load():
    if not os.path.exists(RESULTS_FILE):
        return []
    try:
        with open(RESULTS_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return []


def _save(data):
    os.makedirs(os.path.dirname(RESULTS_FILE), exist_ok=True)
    with open(RESULTS_FILE, "w") as f:
        json.dump(data, f, indent=2)


def save_result(result):
    with _lock:
        data = _load()
        for i, r in enumerate(data):
            if r.get("lead") == result.get("lead"):
                data[i] = result
                _save(data)
                return
        data.append(result)
        _save(data)


def load_all_results():
    with _lock:
        return _load()


def clear_results():
    with _lock:
        _save([])
