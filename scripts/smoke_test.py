import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.services.profiler import profile_file

sample = Path("tests/data/sample_sales.csv")
profile = profile_file(sample, "test-id", "sample_sales.csv")

assert profile.row_count == 8
assert profile.column_count == 4
assert [c.name for c in profile.columns] == [
    "product_name",
    "sales_amount",
    "order_date",
    "region",
]
print("profiler OK:", profile.row_count, "rows,", profile.column_count, "cols")
