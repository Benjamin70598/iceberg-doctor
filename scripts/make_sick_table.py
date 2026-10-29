import os
import pyarrow as pa
from pyiceberg.catalog.sql import SqlCatalog

wh = os.path.abspath("warehouse")
os.makedirs(wh, exist_ok=True)
cat = SqlCatalog("local", uri=f"sqlite:///{wh}/catalog.db", warehouse=f"file://{wh}")
cat.create_namespace_if_not_exists("demo")

schema = pa.schema([("id", pa.int64()), ("msg", pa.string())])
tbl = cat.create_table_if_not_exists("demo.logs", schema=schema)

for i in range(500):
    tbl.append(pa.table({"id": [i], "msg": [f"event {i}"]}, schema=schema))
    if i % 100 == 0:
        print(f"appended {i}")

print("done")
