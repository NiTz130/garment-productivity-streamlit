from pathlib import Path

ROOT = Path(__file__).resolve().parent

def dataset_path(root: Path) -> Path:
    original = root.parent / "Bộ dữ liệu - Nhóm 6.xlsx"
    return original if original.exists() else root / "dataset" / original.name


SOURCE = dataset_path(ROOT)
MODEL = ROOT / "runtime" / "model.joblib"
DB = ROOT / "runtime" / "logs.sqlite"
FEATURES = ["target", "smv", "workers", "overtime", "bonus", "idle"]
LABELS = {"target": "Năng suất mục tiêu", "smv": "Định mức (phút/sản phẩm)",
          "workers": "Số công nhân (người)", "overtime": "Tăng ca cả tổ (phút)",
          "bonus": "Tiền thưởng (BDT)", "idle": "Máy dừng (phút)", "actual": "Năng suất thực tế"}
RANGES = {"target": (0., 1.), "smv": (0.01, 1000.), "workers": (2., 89.),
          "overtime": (0., 25920.), "bonus": (0., 3600.), "idle": (0., 300.), "actual": (0., 2.)}
SLIDER_WORKERS = (2., 60.)
SLIDER_QUANTILE = .95
DRIFT_THRESHOLD = 1.
MIN_NEW_LOGS = 30
LOW_R2 = .5
SEED = 42


def slider_limits(df):
    return {"workers": SLIDER_WORKERS,
            **{k: (0., float(df[k].quantile(SLIDER_QUANTILE))) for k in ("overtime", "bonus")}}
