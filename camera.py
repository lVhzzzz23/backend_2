import cv2
import os

# Đường dẫn tới thư mục dataset
DATASET_DIR = "dataset"

# Nhập tên người dùng
name = input("Nhập tên để đăng ký khuôn mặt: ")

# Tạo thư mục nếu chưa tồn tại
user_folder = os.path.join(DATASET_DIR, name)
if not os.path.exists(user_folder):
    os.makedirs(user_folder)
    print(f"[INFO] Đã tạo thư mục cho {name}.")
else:
    print(f"[INFO] Thư mục cho {name} đã tồn tại.")

# Mở webcam
video = cv2.VideoCapture(0)
print("[INFO] Nhấn 'k' để chụp ảnh, 'q' để thoát.")

total = 0
while True:
    ret, frame = video.read()
    if not ret:
        break

    cv2.imshow("Webcam", frame)
    key = cv2.waitKey(1) & 0xFF

    if key == ord("k"):
        # Lưu ảnh vào thư mục của người dùng
        file_name = f"{str(total).zfill(5)}.png"  # Định dạng 00000.png
        file_path = os.path.join(user_folder, file_name)
        cv2.imwrite(file_path, frame)
        total += 1
        print(f"[INFO] Đã lưu ảnh {file_name}.")

    elif key == ord("q"):
        break

video.release()
cv2.destroyAllWindows()

print(f"[INFO] Đã lưu {total} ảnh cho {name}.")
