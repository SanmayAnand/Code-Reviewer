import os
import statistics
import tempfile
import time

os.environ["LLM_PROVIDER"] = "none"
os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "timing_check.db")

from fastapi.testclient import TestClient

from app.main import app
from app.metrics import java_metrics, python_metrics

PY_FUNCTION = """def func_{i}(a, b, c):
    total = 0
    for x in range(a):
        if x % 2 == 0 and b > 0:
            total += x * c
        elif x % 3 == 0:
            total -= 1
        else:
            while total > 100:
                total -= 10
    return total

"""

JAVA_METHOD = """    public int m{i}(int a, int b) {{
        int t = 0;
        for (int x = 0; x < a; x++) {{
            if (x % 2 == 0 && b > 0) {{ t += x; }} else {{ t -= 1; }}
        }}
        return t;
    }}
"""


def python_code(lines):
    return "".join(PY_FUNCTION.format(i=i) for i in range(lines // PY_FUNCTION.count("\n")))


def java_code(lines):
    count = (lines - 2) // JAVA_METHOD.count("\n")
    return "public class Big {\n" + "".join(JAVA_METHOD.format(i=i) for i in range(count)) + "}\n"


def median_seconds(action, runs=7):
    times = []
    for _ in range(runs):
        start = time.perf_counter()
        action()
        times.append(time.perf_counter() - start)
    return round(statistics.median(times), 3)


py2000, java2000, py500 = python_code(2000), java_code(2000), python_code(500)
client = TestClient(app)
headers = {"X-Session-Id": "timing-check-01"}


def review_500():
    response = client.post("/api/review", json={"code": py500, "language": "python"}, headers=headers)
    assert response.status_code == 200


print("Python metrics, 2000 lines:", median_seconds(lambda: python_metrics.extract(py2000)), "s")
print("Java metrics, 2000 lines:", median_seconds(lambda: java_metrics.extract(java2000)), "s")
print("Full static review, 500 lines:", median_seconds(review_500), "s")