import face_recognition
import cv2
import pickle
import os

# Đường dẫn tới file lưu encodings
ENCODINGS_FILE = "encodings.pickle"

# Tên người dùng cần đăng ký
name = input("Nhập tên để đăng ký khuôn mặt: ")

# Mở webcam
video = cv2.VideoCapture(0)
print("[INFO] Nhấn 'k' để chụp ảnh, 'q' để thoát.")

encodings = []
while True:
    ret, frame = video.read()
    if not ret:
        break

    cv2.imshow("Webcam", frame)
    key = cv2.waitKey(1) & 0xFF

    if key == ord("k"):
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        # Phát hiện khuôn mặt
        boxes = face_recognition.face_locations(rgb, model="hog")

        # Tính toán encoding
        face_encodings = face_recognition.face_encodings(rgb, boxes)
        if len(face_encodings) > 0:
            encodings.append(face_encodings[0])
            print("[INFO] Đã chụp và lưu 1 khuôn mặt.")
        else:
            print("[WARNING] Không phát hiện khuôn mặt.")

    elif key == ord("q"):
        break

video.release()
cv2.destroyAllWindows()

if len(encodings) > 0:
    # Kiểm tra nếu file encodings đã tồn tại
    if os.path.exists(ENCODINGS_FILE):
        print("[INFO] Đang tải dữ liệu cũ...")
        with open(ENCODINGS_FILE, "rb") as f:
            data = pickle.load(f)
    else:
        print("[INFO] Không tìm thấy file encodings. Tạo mới.")
        data = {"encodings": [], "names": []}

    # Thêm encoding và tên vào dữ liệu
    data["encodings"].extend(encodings)
    data["names"].extend([name] * len(encodings))

    # Lưu lại file encodings
    with open(ENCODINGS_FILE, "wb") as f:
        f.write(pickle.dumps(data))
    print(f"[INFO] Đăng ký khuôn mặt cho {name} thành công!")
else:
    print("[ERROR] Không có khuôn mặt nào được chụp.")
