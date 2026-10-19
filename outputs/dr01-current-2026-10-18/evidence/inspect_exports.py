"""Read captured exports only; no network or supplier import."""
from pathlib import Path
import io
import json

ROOT = Path(__file__).resolve().parent

if __name__ == "__main__":
    import pandas as pd
    data = pd.read_excel(io.BytesIO((ROOT / "015-szse-risk-export.bin").read_bytes()),
                         dtype=str, keep_default_na=False)
    rows = data.to_dict(orient="records")
    (ROOT / "szse-risk.rows.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2),
                                             encoding="utf-8")
    print(json.dumps({"rows": len(rows), "columns": list(data.columns),
                      "first": rows[:4], "last": rows[-4:]}, ensure_ascii=True))
