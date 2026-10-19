"""Inspect captured Shenzhen day report offline, without supplier imports."""
from pathlib import Path
from collections import Counter
import io
import json

ROOT = Path(__file__).resolve().parent

if __name__ == "__main__":
    import pandas as pd
    rows = pd.read_excel(io.BytesIO((ROOT / "020-szse-stock-D-export.bin").read_bytes()),
                         dtype=str, keep_default_na=False).to_dict(orient="records")
    (ROOT / "szse-stock-D.rows.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"count": len(rows), "columns": list(rows[0]), "first": rows[:2],
                      "last": rows[-2:], "suspension_text": [r for r in rows if "停" in str(r)],
                      "known": [r for r in rows if any(c in str(r) for c in
                                 ("000016", "002717", "301314", "300773", "002388", "002731"))]},
                     ensure_ascii=True))
