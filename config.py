from pathlib import Path

ROOT = Path(__file__).resolve().parent

def dataset_path(root: Path) -> Path:
    # Chỉ dùng dataset VNĐ đóng gói; tệp NDT gốc ở thư mục cha chỉ để đối chiếu hash.
    return root / "dataset" / "Bộ dữ liệu - Nhóm 6.xlsx"


SOURCE = dataset_path(ROOT)
MODEL = ROOT / "runtime" / "model.joblib"
FEATURES = ["target", "smv", "workers", "overtime", "bonus", "idle"]
SOURCE_COLUMNS = [
    "Mã SKU (Sản phẩm)",
    "Tên sản phẩm (Đề xuất)",
    "Năng suất mục tiêu(%)",
    "Thời gian tạo sản phẩm (Phút)",
    "Thời gian tăng ca (Phút)",
    "Tiền thưởng năng suất (VNĐ)",
    "Thời gian máy nghỉ(Phút)",
    "Số công nhân(Người)",
    "Năng xuất thực tế (%)",
]
SOURCE_TO_INTERNAL = dict(zip(SOURCE_COLUMNS, [
    "sku", "product", "target", "smv", "overtime", "bonus", "idle", "workers", "actual"
]))
DATA_COLUMNS = list(SOURCE_TO_INTERNAL.values())
NUMERIC_COLUMNS = FEATURES + ["actual"]
MODELS = ("Linear Regression",)
TRAINING_CONFIG = {
    "test_size": 0.2,
    "random_state": 42,
    "cv_splits": 5,
    "group_features": FEATURES.copy(),
    "estimators": {
        "Linear Regression": {"class": "LinearRegression", "params": {}},
    },
}
MODEL_FORMAT_VERSION = 3
SCHEMA_VERSION = 3
BONUS_UNIT = "VND"
LABELS = {"target": "Năng suất mục tiêu", "smv": "Định mức (phút/sản phẩm)",
          "workers": "Số công nhân (người)", "overtime": "Tăng ca cả tổ (phút)",
          "bonus": "Tiền thưởng năng suất (VNĐ)", "idle": "Máy dừng (phút)", "actual": "Năng suất thực tế"}

# Historical records may retain decimal VND values from the user's conversion.
# This domain validates records but does not impose new-shift input increments.
HISTORY_RANGES = {"target": (0., 1.), "smv": (0.01, 1000.), "workers": (0., 1000.),
                  "overtime": (0., 25920.), "bonus": (0., None), "idle": (0., 300.),
                  "actual": (0., 2.)}

# New shift entry rules. The API derives the bonus ceiling from valid VNĐ history.
INPUT_RANGES = {"target": (0., 1.), "smv": (0.01, 1000.), "workers": (2., 89.),
                "overtime": (0., 25920.), "bonus": (0., 1_000_000.), "idle": (0., 300.)}
INTEGER_INPUTS = {"overtime", "bonus", "idle"}
# The form takes overtime minutes per full-shift worker; the model still gets the team total.
# 720 is the largest per-worker value in the history (12 hours).
OVERTIME_PER_WORKER_MAX = 720.
WORKER_STEP = 0.5

# Bounded option search. Recommendation ceilings are derived from the valid
# operational dataset at this quantile, then capped by these configured limits.
RECOMMENDATION_QUANTILE = 0.95
RECOMMENDATION_AXIS_POINTS = 8
MAX_AXIS_CANDIDATES = 256
MAX_COMBINED_CANDIDATES = 8192  # 9^4 = 6561 lưới đầy đủ (4 trục × 8 điểm + giữ nguyên)
