from imutils import paths
import argparse
import pickle
import cv2
import os
import face_recognition
from sklearn.model_selection import train_test_split  # Thêm thư viện này

# Khởi tạo đối số dòng lệnh
ap = argparse.ArgumentParser()
ap.add_argument("-i", "--dataset", required=True, help="path to the directory of faces and images")
ap.add_argument("-e", "--encodings", required=True, help="path to the serialized db of facial encoding")
ap.add_argument("-d", "--detection_method", type=str, default="cnn", help="face detector to use: cnn or hog")
args = vars(ap.parse_args())

# Lấy danh sách image paths từ dataset
print("[INFO] quantifying faces...")
imagePaths = list(paths.list_images(args["dataset"]))

# Khởi tạo lists chứa encodings và names
knownEncodings = []
knownNames = []

# Duyệt qua từng image path
for (i, imagePath) in enumerate(imagePaths):
    print("[INFO] processing image {}/{}".format(i + 1, len(imagePaths)))
    name = imagePath.split(os.path.sep)[-2]

    # Load ảnh và chuyển từ BGR sang RGB
    image = cv2.imread(imagePath)
    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

    # Phát hiện khuôn mặt trong ảnh
    boxes = face_recognition.face_locations(rgb, model=args["detection_method"])

    # Tính toán embeddings
    encodings = face_recognition.face_encodings(rgb, boxes)

    # Lưu encodings và tên vào danh sách
    for encoding in encodings:
        knownEncodings.append(encoding)
        knownNames.append(name)

# Chia dữ liệu thành 80% training và 20% testing
print("[INFO] splitting data into training and testing sets...")
trainEncodings, testEncodings, trainNames, testNames = train_test_split(
    knownEncodings, knownNames, test_size=0.2, random_state=42
)

# Lưu dữ liệu training và testing vào file
print("[INFO] serializing training and testing encodings...")
trainData = {"encodings": trainEncodings, "names": trainNames}
testData = {"encodings": testEncodings, "names": testNames}

# Lưu dữ liệu training
with open("train_" + args["encodings"], "wb") as f:
    f.write(pickle.dumps(trainData))

# Lưu dữ liệu testing
with open("test_" + args["encodings"], "wb") as f:
    f.write(pickle.dumps(testData))

print("[INFO] Encoding process completed.")
