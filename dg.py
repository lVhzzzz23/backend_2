import pickle
from sklearn.model_selection import train_test_split
from sklearn.neighbors import KNeighborsClassifier
from sklearn.metrics import classification_report, accuracy_score, precision_score, recall_score, f1_score
import csv

# Đường dẫn file encodings
ENCODINGS_FILE = "encodings.pickle"
OUTPUT_CSV = "evaluation_metrics.csv"

# Load encodings
print("[INFO] Loading encodings...")
with open(ENCODINGS_FILE, "rb") as f:
    data = pickle.load(f)

# Lấy encodings và labels
encodings = data["encodings"]
labels = data["names"]

# Chia dữ liệu thành train và test
X_train, X_test, y_train, y_test = train_test_split(encodings, labels, test_size=0.25, random_state=42)

# Khởi tạo mô hình KNN
print("[INFO] Training KNN classifier...")
knn = KNeighborsClassifier(n_neighbors=3, metric="euclidean")
knn.fit(X_train, y_train)

# Dự đoán trên tập test
print("[INFO] Evaluating classifier...")
y_pred = knn.predict(X_test)

# Tính toán các chỉ số
accuracy = accuracy_score(y_test, y_pred)
precision = precision_score(y_test, y_pred, average="weighted")
recall = recall_score(y_test, y_pred, average="weighted")
f1 = f1_score(y_test, y_pred, average="weighted")

# Hiển thị báo cáo chi tiết
print("\nClassification Report:")
print(classification_report(y_test, y_pred))

# Ghi kết quả vào file CSV
print(f"[INFO] Saving evaluation metrics to {OUTPUT_CSV}...")
with open(OUTPUT_CSV, mode="w", newline="") as file:
    writer = csv.writer(file)
    writer.writerow(["Metric", "Value"])
    writer.writerow(["Accuracy", accuracy])
    writer.writerow(["Precision", precision])
    writer.writerow(["Recall", recall])
    writer.writerow(["F1 Score", f1])

print("[INFO] Evaluation metrics saved successfully.")
