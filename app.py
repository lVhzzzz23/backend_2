import base64
import datetime
import random
import string
import traceback
import uuid
from venv import logger
from flask import Flask, Response, jsonify, logging, request, render_template
from flask_cors import CORS
import cv2
import os
import pickle
import face_recognition
from pymongo import MongoClient
import requests
import cloudinary
import cloudinary.api
import cloudinary.uploader
from io import BytesIO
from PIL import Image
import numpy as np
from flask_mail import Mail, Message
from uuid import UUID
from flask import jsonify
from bson import ObjectId 

app = Flask(__name__)

CORS(app)

client = MongoClient('mongodb://localhost:27017/') 
db = client['conference_db'] 
conference_collection = db['conferences']  
questions_collection = db['questions'] 
users_collection=db['users']
people_collection = db['people'] 
attendance_collection = db["attendance"]
room_collection=db["room_data"] 
cloudinary.config(
    cloud_name="dljfjfjv9", 
    api_key="874823522898532", 
    api_secret="ygL4htfkUhfhOpdB7BcEhi6y8Ac"  
)

app.config['MAIL_SERVER'] = 'smtp.gmail.com' 
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'levanhoang040504@gmail.com' 
app.config['MAIL_PASSWORD'] = 'uuec ugau rwpk xtju'  
app.config['MAIL_DEFAULT_SENDER'] = 'levanhoang040504@gmail.com'

mail = Mail(app)
encodings_file = "encodings.pickle"
knownEncodings = []
knownNames = []

def download_image_from_url(url):
    response = requests.get(url)
    image = Image.open(BytesIO(response.content))
    return cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)


def get_statistics_for_conference_by_day(conference_id):
    try:
        pipeline = [
            {
                "$match": {
                    "conference_id": conference_id 
                }
            },
            {
                "$group": {
                    "_id": "$date",  
                    "userCount": {"$sum": 1}  
                }
            },
            {
                "$sort": {"_id": 1}
            }
        ]
        statistics = list(attendance_collection.aggregate(pipeline))
        if not statistics:
            return None
        return [{"date": stat["_id"].strftime("%Y-%m-%d"), "userCount": stat["userCount"]} for stat in statistics]

    except Exception as e:
        return None
    
def get_images_from_cloudinary():
    resources = []
    try:
        result = cloudinary.api.resources(type="upload", prefix="user_photos/", max_results=500)
        resources = result['resources']
    except Exception as e:
        print(f"Error fetching resources: {e}")
    return resources

from base64 import b64encode
import qrcode


@app.route('/api/add-participant', methods=['POST'])
def add_participant():
    data = request.get_json()
    email = data.get('email')
    conference_id = data.get('conferenceId')

    if not email:
        return jsonify({"error": "Thiếu thông tin email"}), 400

    if not conference_id:
        user = users_collection.find_one({"email": email})
        if user and "conferenceId" in user:
            conference_id = user["conferenceId"]
        else:
            return jsonify({"error": "Thiếu thông tin conferenceId"}), 400

    try:
        existing_participant = users_collection.find_one({"conferenceId": conference_id, "email": email})
        if existing_participant:
            return jsonify({"error": "Email này đã tồn tại trong danh sách người tham gia."}), 409

        participant_id = str(uuid.uuid4())
        participant_data = {
            '_id': participant_id,
            'conferenceId': conference_id,
            'email': email,
            'isRegistered': False  
        }
        users_collection.insert_one(participant_data)

        invitation_link = f"http://localhost:3000/join-conference/{conference_id}?participantId={participant_id}"
        msg = Message(
            'Lời mời tham gia hội nghị',
            recipients=[email],
            html=f"""
                <p>Chào bạn,</p>
                <p>Bạn được mời tham gia hội nghị. Nhấn vào <a href="{invitation_link}">liên kết</a> để đăng ký tham gia.</p>
            """
        )
        mail.send(msg)

        return jsonify({
            "message": "Thêm người tham gia thành công và đã gửi lời mời.",
            "invitationLink": invitation_link,
            "conferenceId": conference_id  
        }), 200

    except Exception as e:
        app.logger.error(f"Lỗi khi thêm người tham gia: {str(e)}")
        return jsonify({"error": f"Không thể thực hiện hành động: {str(e)}"}), 500


@app.route('/api/participant/<participant_id>', methods=['GET'])
def get_participant(participant_id):
    try:
        # Tìm kiếm người tham gia theo participant_id trong cơ sở dữ liệu
        participant = users_collection.find_one({"_id": participant_id})

        if not participant:
            return jsonify({"error": "Không tìm thấy người tham gia với participantId này."}), 404

        # Chỉ trả về thông tin cần thiết
        participant_info = {
            "participantId": participant["_id"],
            "conferenceId": participant["conferenceId"],
            "email": participant["email"],
            "isRegistered": participant.get("isRegistered", False)
        }

        return jsonify({"participant": participant_info}), 200

    except Exception as e:
        app.logger.error(f"Lỗi khi lấy thông tin người tham gia: {str(e)}")
        return jsonify({"error": f"Không thể lấy thông tin người tham gia: {str(e)}"}), 500


@app.route('/api/count-participants', methods=['GET'])
def count_participants():
    conference_id = request.args.get('conferenceId')
    
    if not conference_id:
        return jsonify({"error": "Thiếu thông tin conferenceId"}), 400
    
    try:
        # Tìm tất cả người tham gia với conferenceId cụ thể, không cần kiểm tra trạng thái đăng ký
        count = users_collection.count_documents({"conferenceId": conference_id})
        
        return jsonify({
            "message": "Đếm số người tham gia thành công",
            "count": count
        }), 200
    
    except Exception as e:
        app.logger.error(f"Lỗi khi đếm số người tham gia: {str(e)}")
        return jsonify({"error": f"Không thể thực hiện hành động: {str(e)}"}), 500

def send_confirmation_email(to_email, confirmation_code):
    try:
        subject = "Hội nghị đã được phê duyệt"
        body = f"Chúc mừng! Hội nghị của bạn đã được phê duyệt.\n\nMã xác nhận của bạn: {confirmation_code}"
        msg = Message(subject,
                      sender=app.config['MAIL_USERNAME'],
                      recipients=[to_email])
        msg.body = body
        mail.send(msg)
    except Exception as e:
        print(f"Đã xảy ra lỗi khi gửi email: {e}")
@app.route('/api/participants/<conference_id>', methods=['GET'])
def list_participants(conference_id):
    try:
        participants = list(users_collection.find({"conferenceId": conference_id}, {"conferenceId": 0})) 
        if not participants:
            return jsonify({"message": "Không có người tham gia trong hội nghị này."}), 404
        return jsonify({
            "message": "Danh sách người tham gia hội nghị.",
            "data": participants
        }), 200
    except Exception as e:
        app.logger.error(f"Lỗi khi lấy danh sách người tham gia: {str(e)}")
        return jsonify({"error": f"Không thể thực hiện hành động: {str(e)}"}), 500
    
@app.route('/approve_conference/<conference_id>', methods=['POST'])
def approve_conference(conference_id):
    try:
        conference = conference_collection.find_one({'_id': ObjectId(conference_id)})
        if not conference:
            return jsonify({"message": "Hội nghị không tồn tại"}), 404
        if conference['status'] != 'pending':
            return jsonify({"message": "Hội nghị này đã được duyệt hoặc từ chối"}), 400
        confirmation_code = generate_confirmation_code()
        conference_collection.update_one(
            {'_id': ObjectId(conference_id)},
            {'$set': {'status': 'approved', 'confirmation_code': confirmation_code}}
        )
        creator_email = conference['creator_email']
        send_confirmation_email(creator_email, confirmation_code)

        return jsonify({
            "message": "Hội nghị đã được phê duyệt.",
            "confirmation_code": confirmation_code
        })
    except Exception as e:
        return jsonify({"message": "Đã xảy ra lỗi!", "error": str(e)}), 500  
def train_face_recognition():
    global knownEncodings, knownNames
    images = get_images_from_cloudinary()
    if os.path.exists(encodings_file):
        with open(encodings_file, 'rb') as f:
            data = pickle.load(f)
            knownEncodings = data['encodings']
            knownNames = data['names']
    knownNamesSet = set(knownNames)
    for image in images:
        name = image['public_id'].split("/")[1] 

        if name in knownNamesSet:
            continue  
        img = download_image_from_url(image['secure_url'])
        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        boxes = face_recognition.face_locations(rgb, model="cnn")
        encodings = face_recognition.face_encodings(rgb, boxes)
        for encoding in encodings:
            knownEncodings.append(encoding)
            knownNames.append(name)
    data = {"encodings": knownEncodings, "names": knownNames}
    with open(encodings_file, "wb") as f:
        f.write(pickle.dumps(data))


@app.route('/capture/<user_name>', methods=['POST'])
def capture_photo(user_name):
    try:
        data = request.get_json()
        images = data.get('images', [])
        if not images or len(images) == 0:
            return jsonify({"message": "Không có dữ liệu ảnh gửi lên."}), 400
        uploaded_images = []
        user_name = user_name.strip()
        for image_data in images:
            if "," in image_data:
                base64_data = image_data.split(",")[1]
            else:
                base64_data = image_data
            upload_result = cloudinary.uploader.upload(
                f"data:image/png;base64,{base64_data}",
                folder=f"user_photos/{user_name}"
            )
            uploaded_images.append(upload_result.get("secure_url"))
        all_images = get_images_from_cloudinary()
        user_images = [img for img in all_images if img['public_id'].startswith(f"user_photos/{user_name}/")]
        if len(user_images) >= 5:
            avatar_url = uploaded_images[0] 
            train_face_recognition()
            return jsonify({
                "message": "Ảnh đã được tải lên và huấn luyện thành công!",
                "avatar_url": avatar_url, 
                "urls": uploaded_images
            })
        else:
            remaining = 5 - len(user_images)
            return jsonify({
                "message": f"Ảnh đã được tải lên. Cần thêm {remaining} ảnh nữa để hoàn tất.",
                "urls": uploaded_images
            })
    except Exception as e:
        return jsonify({"message": "Đã xảy ra lỗi!", "error": str(e)}), 500
with open('encodings.pickle', 'rb') as f:
    data = pickle.load(f)
def generate_confirmation_code(length=6):
    characters = string.ascii_uppercase + string.digits
    return ''.join(random.choice(characters) for _ in range(length))
@app.route('/recognize', methods=['POST'])
def recognize_faces():
    file = request.files['frame']
    npimg = np.frombuffer(file.read(), np.uint8)
    frame = cv2.imdecode(npimg, cv2.IMREAD_COLOR)
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    boxes = face_recognition.face_locations(rgb)
    encodings = face_recognition.face_encodings(rgb, boxes)
    names = []
    face_images = []
    for box, encoding in zip(boxes, encodings):
        matches = face_recognition.compare_faces(data['encodings'], encoding, 0.4)
        name = "Unknown"
        if True in matches:
            matched_idxs = [i for (i, b) in enumerate(matches) if b]
            counts = {}
            for i in matched_idxs:
                name = data['names'][i]
                counts[name] = counts.get(name, 0) + 1
            name = max(counts, key=counts.get)
        names.append(name)
        top, right, bottom, left = box
        face_image = frame[top:bottom, left:right]
        _, buffer = cv2.imencode('.jpg', face_image)
        face_images.append(buffer.tobytes()) 
    return jsonify({
        "boxes": boxes,
        "names": names,
        "faces": [base64.b64encode(img).decode('utf-8') for img in face_images]
    })
@app.route('/attendance', methods=['POST'])
def attendance():
    try:
        data = request.get_json()
        if not data or 'name' not in data or 'email' not in data or 'status' not in data or 'conferenceId' not in data:
            return jsonify({"message": "Dữ liệu không hợp lệ"}), 400
        name = data['name']
        email = data['email']
        status = data['status']
        conference_id = data['conferenceId']
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        attendance_record = {
            'name': name,
            'email': email,
            'status': status,
            'conferenceId': conference_id,
            'timestamp': timestamp
        }
        attendance_collection.insert_one(attendance_record)
        return jsonify({"message": "Thông tin điểm danh đã được lưu thành công"}), 201
    except Exception as e:
        return jsonify({"message": "Đã xảy ra lỗi!", "error": str(e)}), 500
@app.route('/attendance/<conferenceId>', methods=['GET'])
def get_attendance_by_conference(conferenceId):
    try:
        records = list(attendance_collection.find({"conferenceId": conferenceId}))
        for record in records:
            record['_id'] = str(record['_id'])
        return jsonify(records), 200
    except Exception as e:
        return jsonify({"message": "Đã xảy ra lỗi!", "error": str(e)}), 500
@app.route('/attendance', methods=['GET'])
def get_attendance():
    try:
        attendance_records = list(attendance_collection.find())  
        for record in attendance_records:
            record['_id'] = str(record['_id'])
        return jsonify(attendance_records), 200
    except Exception as e:
        return jsonify({"message": "Đã xảy ra lỗi!", "error": str(e)}), 500
@app.route('/register_conference', methods=['POST'])
def register_conference():
    required_fields = ['conference_name', 'date', 'creator_email', 'creator_phone', 'event_date', 'event_time', 'location']

    if 'file' not in request.files:
        return jsonify({"message": "Ảnh hội nghị là bắt buộc."}), 400
    file = request.files['file']
    
    data = request.form
    
    for field in required_fields:
        if field not in data:
            return jsonify({"message": f"Thiếu trường bắt buộc: {field}"}), 400
    
    conference_name = data['conference_name']
    date = data['date']
    creator_email = data['creator_email']
    creator_phone = data['creator_phone']
    event_date = data['event_date']
    event_time = data['event_time']
    location = data['location']
    
    try:
        upload_result = cloudinary.uploader.upload(file)
        image_url = upload_result['secure_url']
    except Exception as e:
        return jsonify({"message": f"Đã xảy ra lỗi khi tải ảnh lên: {str(e)}"}), 500
    
    conference_info = {
        'conference_name': conference_name,
        'date': date,
        'creator_email': creator_email,
        'creator_phone': creator_phone,
        'event_date': event_date,
        'event_time': event_time,
        'location': location,
        'status': 'pending',
        'confirmation_code': None,
        'image_url': image_url
    }
    
    result = conference_collection.insert_one(conference_info)
    conference_info['_id'] = str(result.inserted_id)
    
    return jsonify({
        "message": "Đã nhận đăng ký hội nghị. Đang chờ duyệt từ quản trị viên.",
        "conference_info": conference_info,
        "conference_id": conference_info['_id']
    }), 201
@app.route('/get_meetings_by_month', methods=['GET'])
def get_meetings_by_month():
    pipeline = [
        {
            "$project": {
                "month": {
                    "$month": {
                        "$dateFromString": {
                            "dateString": "$event_date", 
                            "format": "%Y-%m-%d"  
                        }
                    }
                },
                "year": {
                    "$year": {
                        "$dateFromString": {
                            "dateString": "$event_date",  
                            "format": "%Y-%m-%d" 
                        }
                    }
                }
            }
        },
        {
            "$group": {
                "_id": {"month": "$month", "year": "$year"},
                "count": {"$sum": 1}
            }
        },
        {
            "$sort": {"_id.year": 1, "_id.month": 1}
        }
    ]
    result = conference_collection.aggregate(pipeline)
    meetings_by_month = [["Tháng", "Số cuộc họp"]]  
    for entry in result:
        month = entry["_id"]["month"]
        count = entry["count"]
        meetings_by_month.append([f"{month}", count]) 

    return jsonify(meetings_by_month)
@app.route('/get_stats', methods=['GET'])
def get_stats():
    try:
        total_meetings = conference_collection.count_documents({})
        total_forms_created = conference_collection.count_documents({"status": "approved"})
        total_registered_people = users_collection.count_documents({"isRegistered": True})
      
        return jsonify({
            "total_meetings": total_meetings,
            "total_forms_created": total_forms_created,
            "total_registered_people": total_registered_people
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
@app.route('/conference/<conference_id>', methods=['GET'])
def get_conference(conference_id):
    try:
        conference_object_id = ObjectId(conference_id)
        conference = conference_collection.find_one({'_id': conference_object_id})
        if not conference:
            return jsonify({"message": "Hội nghị không tồn tại"}), 404
        conference['_id'] = str(conference['_id'])
        return jsonify(conference), 200
    except Exception as e:
        return jsonify({"message": str(e)}), 500
@app.route('/cancel_conference/<conference_id>', methods=['POST'])
def cancel_conference(conference_id):
    try:
        conference = conference_collection.find_one({'_id': ObjectId(conference_id)})
        if not conference:
            return jsonify({"message": "Hội nghị không tồn tại"}), 404
        if conference['status'] == 'pending' or conference['status'] == 'approved':
            conference_collection.update_one(
                {'_id': ObjectId(conference_id)},
                {'$set': {'status': 'pending'}}
            )
            return jsonify({"message": "Hội nghị đã bị hủy."}), 200
        else:
            return jsonify({"message": "Không thể hủy hội nghị với trạng thái này."}), 400

    except Exception as e:
        return jsonify({"message": str(e)}), 500
@app.route('/update_conference/<conference_id>', methods=['PUT'])
def update_conference(conference_id):
    data = request.get_json()
    if not data:
        return jsonify({"message": "Không có dữ liệu để cập nhật"}), 400
    
    try:
        conference_object_id = ObjectId(conference_id)
    except Exception:
        return jsonify({"message": "conference_id không hợp lệ"}), 400
    conference = conference_collection.find_one({"_id": conference_object_id})
    if not conference:
        return jsonify({"message": "Không tìm thấy hội nghị với ID đã cung cấp"}), 404
    update_fields = [
        'conference_name', 'date', 'creator_email', 'creator_phone',
        'event_date', 'event_time', 'location', 'status', 'confirmation_code'
    ]
    update_data = {field: data[field] for field in update_fields if field in data}
    for date_field in ['date', 'event_date']:
        if date_field in update_data:
            try:
                datetime.strptime(update_data[date_field], '%Y-%m-%d')
            except ValueError:
                return jsonify({"message": f"Định dạng ngày của {date_field} không hợp lệ, phải là YYYY-MM-DD"}), 400

    if not update_data:
        return jsonify({"message": "Không có trường hợp lệ để cập nhật"}), 400
    try:
        result = conference_collection.update_one(
            {"_id": conference_object_id},
            {"$set": update_data}
        )
        if result.matched_count == 0:
            return jsonify({"message": "Không tìm thấy hội nghị để cập nhật"}), 404
    except Exception as e:
        return jsonify({"message": "Lỗi khi cập nhật dữ liệu", "error": str(e)}), 500
    updated_conference = conference_collection.find_one({"_id": conference_object_id})
    updated_conference['_id'] = str(updated_conference['_id'])
    return jsonify({
        "message": "Cập nhật hội nghị thành công",
        "updated_conference": updated_conference
    }), 200
@app.route('/conference/registrations/<conference_id>', methods=['GET'])
def get_conference_registrations(conference_id):
    try:
        conference = conference_collection.find_one({'_id': ObjectId(conference_id)})
        if not conference:
            return jsonify({"message": "Hội nghị không tồn tại"}), 404

        registrations = conference.get('registrations', [])
        return jsonify(registrations), 200
    except Exception as e:
        return jsonify({"message": str(e)}), 500
@app.route('/api/conference/details/<conference_id>', methods=['GET'])
def get_conference_details(conference_id):
    try:
        conference = conference_collection.find_one({'_id': ObjectId(conference_id)})
        if not conference:
            return jsonify({"message": "Hội nghị không tồn tại"}), 404
        # Convert ObjectId fields to strings
        conference = convert_objectid_to_str(conference)
        return jsonify(conference), 200
    except Exception as e:
        return jsonify({"message": str(e)}), 500
@app.route('/approved_conferences', methods=['GET'])
def get_approved_conferences():
    try:
        conferences = conference_collection.find({'status': 'approved'})
        result = []
        for conference in conferences:
            conference['_id'] = str(conference['_id'])
            result.append(conference)
        return jsonify(result), 200
    except Exception as e:
        return jsonify({"message": str(e)}), 500

def convert_objectid_to_str(data):
    if isinstance(data, list):
        return [convert_objectid_to_str(item) for item in data]
    elif isinstance(data, dict):
        return {key: convert_objectid_to_str(value) for key, value in data.items()}
    elif isinstance(data, ObjectId):
        return str(data)
    else:
        return data


@app.route('/list_conferences', methods=['GET'])
def list_conferences():
    try:
        conferences = conference_collection.find()
        conference_list = convert_objectid_to_str(list(conferences))  # Chuyển đổi toàn bộ danh sách

        return jsonify({
            "message": "Danh sách hội nghị",
            "conferences": conference_list
        }), 200

    except Exception as e:
        return jsonify({
            "message": "Đã xảy ra lỗi khi lấy danh sách hội nghị.",
            "error": str(e)
        }), 500

@app.route('/delete_conference/<conference_id>', methods=['DELETE'])
def delete_conference(conference_id):
    try:
        conference = conference_collection.find_one({'_id': ObjectId(conference_id)})
        if not conference:
            return jsonify({"message": "Hội nghị không tồn tại"}), 404
        conference_collection.delete_one({'_id': ObjectId(conference_id)})        
        return jsonify({
            "message": "Hội nghị đã được xóa thành công.",
            "conference_id": conference_id
        }), 200

    except Exception as e:
        return jsonify({"message": "Đã xảy ra lỗi khi xóa hội nghị.", "error": str(e)}), 500


@app.route('/conference/login', methods=['POST'])
def login_conference():
    data = request.get_json()
    confirmation_code = data.get('confirmation_code')
    if not confirmation_code:
        return jsonify({"message": "Vui lòng nhập mã xác nhận"}), 400
    conference = conference_collection.find_one({'confirmation_code': confirmation_code})
    if not conference:
        return jsonify({"message": "Mã xác nhận không hợp lệ"}), 404

    return jsonify({
        "message": "Đăng nhập hội nghị thành công.",
        "conference_info": {
            "id": str(conference['_id']),
            "conference_name": conference['conference_name'],
            "event_date": conference['event_date'],
            "event_time": conference['event_time'],
            "location": conference['location']
        }
    }), 200


from datetime import datetime  # Thêm dòng này

@app.route('/add_questions', methods=['POST'])
def add_questions():
    try:
        data = request.get_json()

        if not data or 'conference_id' not in data or 'conference_description' not in data or 'questions' not in data or not isinstance(data['questions'], list):
            return jsonify({"message": "Dữ liệu không hợp lệ. Cần có 'conference_id', 'conference_description' và 'questions'."}), 400
        
        conference_id = data['conference_id']
        conference_description = data['conference_description']
        questions = data['questions']

        if len(questions) == 0:
            return jsonify({"message": "Vui lòng cung cấp ít nhất một câu hỏi."}), 400
        
        for question in questions:
            print(f"Processing question: {question}")  
            
            if 'question' not in question or not question['question'].strip():
                return jsonify({"message": "Thiếu thông tin hoặc nội dung câu hỏi không hợp lệ."}), 400
            
            if question['question_type'] not in ["text", "date", "time"] and ('options' not in question or not isinstance(question['options'], list)):
                return jsonify({"message": f"Câu hỏi '{question['question']}' yêu cầu danh sách lựa chọn hợp lệ."}), 400
            
            if 'description' not in question or not question['description'].strip():
                return jsonify({"message": f"Câu hỏi '{question['question']}' thiếu mô tả."}), 400

            # Handle conference image upload
            conference_image_url = None
            if 'conference_image' in data and data['conference_image']:
                conference_image = data['conference_image']
                try:
                    print(f"Uploading conference image: {conference_image}") 
                    upload_result = cloudinary.uploader.upload(conference_image, folder=f"conference_{conference_id}/title/")
                    conference_image_url = upload_result['secure_url']
                    print(f"Uploaded conference image URL: {conference_image_url}")  # Debugging: Log the uploaded image URL
                except Exception as e:
                    return jsonify({"message": "Lỗi khi tải ảnh tiêu đề lên Cloudinary.", "error": str(e)}), 400

            question_image_url = None
            if 'image' in question and question['image']:
                question_image = question['image']
                try:
                    print(f"Uploading question image for: {question['question']}")  # Debugging: Log the image upload attempt
                    upload_result = cloudinary.uploader.upload(question_image, folder=f"conference_{conference_id}/questions/")
                    question_image_url = upload_result['secure_url']
                    print(f"Uploaded question image URL: {question_image_url}")  # Debugging: Log the uploaded image URL
                except Exception as e:
                    return jsonify({"message": f"Lỗi khi tải ảnh câu hỏi '{question['question']}' lên Cloudinary.", "error": str(e)}), 400

        inserted_ids = []
        for question in questions:
            question_data = {
                "conference_id": ObjectId(conference_id),
                "conference_description": conference_description,
                "question_text": question['question'],
                "question_type": question['question_type'],
                "options": question.get('options', []),
                "description": question['description'],
                "conference_image_url": conference_image_url, 
                "question_image_url": question_image_url,  
                "created_at": datetime.now()  # Cập nhật tại đây
            }
            try:
                print(f"Inserting question data into database: {question_data}")  # Debugging: Log the data being inserted
                question_id = questions_collection.insert_one(question_data).inserted_id
                inserted_ids.append(str(question_id))
                print(f"Inserted question ID: {question_id}")  
            except Exception as e:
                return jsonify({"message": "Lỗi khi thêm câu hỏi vào cơ sở dữ liệu.", "error": str(e)}), 500

        return jsonify({
            "message": "Câu hỏi đã được thêm thành công.",
            "inserted_ids": inserted_ids
        }), 201
    except Exception as e:
        return jsonify({"message": "Đã xảy ra lỗi!", "error": str(e)}), 500


from bson import ObjectId

@app.route('/get_question/<question_id>', methods=['GET'])
def get_question(question_id):
    try:
        # Tìm câu hỏi theo question_id
        question = questions_collection.find_one({"_id": ObjectId(question_id)})
        
        if not question:
            return jsonify({"message": "Câu hỏi không tồn tại!"}), 404
        
        # Chuyển đổi tất cả ObjectId thành chuỗi
        def convert_objectid(obj):
            if isinstance(obj, ObjectId):
                return str(obj)
            elif isinstance(obj, dict):
                return {k: convert_objectid(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [convert_objectid(item) for item in obj]
            return obj
        
        question = convert_objectid(question)
        
        return jsonify({
            "message": "Lấy câu hỏi thành công.",
            "question": question
        }), 200

    except Exception as e:
        return jsonify({"message": "Đã xảy ra lỗi khi lấy câu hỏi!", "error": str(e)}), 500



@app.route('/get_questions/<conference_id>', methods=['GET'])
def get_questions(conference_id):
    try:
        # Kiểm tra tính hợp lệ của conference_id
        if not ObjectId.is_valid(conference_id):
            return jsonify({"message": "ID hội nghị không hợp lệ."}), 400
        
        # Lấy thông tin hội nghị từ collection conferences
        conference = conference_collection.find_one({"_id": ObjectId(conference_id)})
        if not conference:
            return jsonify({"message": "Không tìm thấy hội nghị."}), 404

        # Lấy tất cả câu hỏi của hội nghị từ collection questions
        questions = questions_collection.find({"conference_id": ObjectId(conference_id)})
        result = []

        # Lấy các chi tiết hội nghị từ conference collection
        conference_name = conference.get("conference_name", "")
        event_date = conference.get("event_date", "")
        event_time = conference.get("event_time", "")
        location = conference.get("location", "")
        
        # Biến để lưu một lần duy nhất conference_image_url và conference_description
        conference_image_url = None
        conference_description = None
        
        # Duyệt qua các câu hỏi và tạo danh sách câu hỏi
        for question in questions:
            # Lấy thông tin conference_image_url và conference_description từ mỗi câu hỏi (chỉ lấy giá trị đầu tiên)
            if conference_image_url is None:
                conference_image_url = question.get("conference_image_url", "")
            if conference_description is None:
                conference_description = question.get("conference_description", "")
            
            question_data = {
                "question_id": str(question["_id"]),
                "conference_id": str(question["conference_id"]),
                "question_text": question["question_text"],
                "question_type": question["question_type"],
                "options": question.get("options", []),
                "description": question.get("description", ""),  # Mô tả câu hỏi
                "created_at": question["created_at"].strftime("%Y-%m-%d %H:%M:%S")  # Chuyển thời gian sang định dạng chuỗi
            }
            result.append(question_data)

        if not result:
            return jsonify({"message": "Không tìm thấy câu hỏi cho hội nghị này."}), 404

        return jsonify({
            "message": "Lấy danh sách câu hỏi thành công.",
            "questions": result,
            "conference_name": conference_name,  # Trả riêng conference_name
            "event_date": event_date,            # Trả riêng event_date
            "event_time": event_time,            # Trả riêng event_time
            "location": location,                # Trả riêng location
            "conference_image_url": conference_image_url,  # Trả riêng conference_image_url
            "conference_description": conference_description  # Trả riêng conference_description
        }), 200

    except Exception as e:
        return jsonify({"message": "Đã xảy ra lỗi!", "error": str(e)}), 500


@app.route('/delete_question/<question_id>', methods=['DELETE'])
def delete_question(question_id):
    try:
        # Kiểm tra xem `question_id` có hợp lệ không
        if not ObjectId.is_valid(question_id):
            return jsonify({"message": "ID câu hỏi không hợp lệ."}), 400

        # Tìm và xóa câu hỏi trong cơ sở dữ liệu
        result = questions_collection.delete_one({"_id": ObjectId(question_id)})

        # Kiểm tra xem có câu hỏi nào bị xóa không
        if result.deleted_count == 0:
            return jsonify({"message": "Không tìm thấy câu hỏi để xóa."}), 404

        return jsonify({"message": "Xóa câu hỏi thành công."}), 200
    except Exception as e:
        return jsonify({"message": "Đã xảy ra lỗi!", "error": str(e)}), 500


@app.route('/update_question/<question_id>', methods=['PUT'])
def update_question(question_id):
    try:
        # Kiểm tra xem `question_id` có hợp lệ không
        if not ObjectId.is_valid(question_id):
            return jsonify({"message": "ID câu hỏi không hợp lệ."}), 400

        # Lấy dữ liệu từ body request
        data = request.get_json()

        # Kiểm tra xem dữ liệu cần sửa có đầy đủ không
        if not data.get("question_text") or not data.get("question_type"):
            return jsonify({"message": "Thiếu thông tin câu hỏi hoặc loại câu hỏi."}), 400

        # Tạo từ điển cập nhật với các trường cần thiết
        update_data = {
            "question_text": data["question_text"],
            "question_type": data["question_type"],
            "description": data.get("description", ""),  # Mô tả là tùy chọn
            "options": data.get("options", []),  # Tùy chọn là một danh sách
        }

        # Cập nhật câu hỏi trong cơ sở dữ liệu
        result = questions_collection.update_one(
            {"_id": ObjectId(question_id)}, 
            {"$set": update_data}
        )

        # Kiểm tra nếu không có câu hỏi nào bị cập nhật
        if result.matched_count == 0:
            return jsonify({"message": "Không tìm thấy câu hỏi để sửa."}), 404

        return jsonify({"message": "Sửa câu hỏi thành công."}), 200

    except Exception as e:
        return jsonify({"message": "Đã xảy ra lỗi!", "error": str(e)}), 500
from pymongo import UpdateOne
from bson import ObjectId
from bson.errors import InvalidId

@app.route('/submit_answers', methods=['POST'])
def submit_answers():
    data = request.json
    if not data:
        return jsonify({"error": "Dữ liệu không hợp lệ"}), 400

    conference_id = data.get("conferenceId")
    user_info = data.get("userInfo")
    answers = data.get("answers")

    if not conference_id or not user_info or not answers:
        return jsonify({"error": "Thiếu thông tin bắt buộc"}), 400

    user_name = user_info.get("fullName")
    user_email = user_info.get("email")
    user_phone=user_info.get("phone")
    if not user_name or not user_email:
        return jsonify({"error": "Thông tin người dùng không đầy đủ"}), 400

    try:
        # Danh sách các thao tác cập nhật
        update_operations = []
        for question_id, answer_text in answers.items():
            try:
                update_operations.append(UpdateOne(
                    {
                        "conference_id": conference_id,
                        "question_id": ObjectId(question_id),
                        "user_email": user_email,
                        "phone":user_phone
                    },
                    {
                        "$set": {
                            "user_name": user_name,
                            "answer_text": answer_text
                        }
                    },
                    upsert=True  
                ))
            except InvalidId:
                return jsonify({"error": f"Invalid question_id: {question_id}"}), 400
        if update_operations:
            answers_collection.bulk_write(update_operations)

        return jsonify({"message": "Câu trả lời đã được lưu/cập nhật thành công"}), 200

    except Exception as e:
        return jsonify({"error": f"Lỗi khi lưu dữ liệu: {str(e)}"}), 500


@app.route('/get_answers', methods=['GET'])
def get_answer():
    # Get conference_id from query parameters
    conference_id = request.args.get('conferenceId')
    if not conference_id:
        return jsonify({"error": "Thiếu mã phòng"}), 400

    try:
        # Query to get all answers for the given conference_id
        answers = answers_collection.find({"conference_id": conference_id})
        
        # Check if there are any answers
        if answers_collection.count_documents({"conference_id": conference_id}) == 0:
            return jsonify({"message": "Không có câu trả lời nào cho mã phòng này"}), 404

        # Group answers by user_name
        grouped_answers = {}
        for answer in answers:
            user_name = answer.get("user_name")
            question_id = answer.get("question_id")
            
            # Fetch question_text based on question_id
            question = questions_collection.find_one({"_id": question_id})
            question_text = question.get("question_text") if question else "Câu hỏi không xác định"
            
            if user_name not in grouped_answers:
                grouped_answers[user_name] = {
                    "user_email": answer.get("user_email"),
                    "answers": []
                }
            grouped_answers[user_name]["answers"].append({
                "question_id": str(question_id),
                "question_text": question_text,
                "answer_text": answer.get("answer_text")
            })

        # Convert grouped_answers to a list for the response
        result = []
        for user_name, data in grouped_answers.items():
            result.append({
                "user_name": user_name,
                "user_email": data["user_email"],
                "answers": data["answers"]
            })

        return jsonify({"answers_by_user": result}), 200

    except Exception as e:
        return jsonify({"error": f"Lỗi khi lấy dữ liệu: {str(e)}"}), 500

@app.route('/login', methods=['POST'])
def login_user():
    try:
        data = request.get_json()
        if not data or 'email' not in data or 'phone' not in data:
            return jsonify({"message": "Dữ liệu không hợp lệ. Cần có 'email' và 'phone'."}), 400
        email = data['email']
        phone = data['phone']
        if not email.strip() or not phone.strip():
            return jsonify({"message": "Tất cả các trường đều là bắt buộc."}), 400
        user = users_collection.find_one({"email": email})
        if not user:
            return jsonify({"message": "Email này chưa được đăng ký."}), 400
        if user.get('phone') != phone:
            return jsonify({"message": "Số điện thoại không đúng."}), 400
        return jsonify({"message": "Đăng nhập thành công.", "user_id": str(user['_id'])}), 200
    except Exception as e:
        return jsonify({"message": "Đã xảy ra lỗi!", "error": str(e)}), 500
@app.route('/register', methods=['POST'])
def register_user():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"message": "Dữ liệu không hợp lệ."}), 400

        email = data.get('email')
        if not email:
            return jsonify({"message": "Cần có trường 'email'."}), 400

        # Kiểm tra nếu người dùng đã tồn tại trong hệ thống
        existing_user = users_collection.find_one({"email": email})

        if existing_user:
            # Kiểm tra xem người dùng đã đăng ký chưa (isRegistered)
            if existing_user.get("isRegistered"):
                return jsonify({"message": "Người dùng đã đăng ký thành công trước đó."}), 200

            # Nếu người dùng chưa đăng ký, kiểm tra các thông tin cần thiết
            conference_id = existing_user.get("conferenceId")
            full_name = data.get('fullName')
            phone = data.get('phone')

            if not full_name or not phone:
                return jsonify({"message": "Cần có 'fullName' và 'phone'."}), 400

            update_data = {
                "fullName": full_name,
                "phone": phone,
                "created_at": datetime.now(),
                "isRegistered": True  
            }

            # Cập nhật lại conferenceId nếu có
            if conference_id:
                update_data["conferenceId"] = conference_id

            # Cập nhật thông tin người dùng trong cơ sở dữ liệu
            users_collection.update_one({"email": email}, {"$set": update_data})

            return jsonify({"message": "Thông tin đã được cập nhật thành công và người dùng đã đăng ký.", "conferenceId": conference_id}), 200
        else:
            return jsonify({"message": "Người dùng chưa tồn tại. Không thể đăng ký mới."}), 403

    except Exception as e:
        return jsonify({"message": "Đã xảy ra lỗi!", "error": str(e)}), 500


@app.route('/statistics', methods=['GET'])
def get_statistics():
    try:
        pipeline = [
            {"$group": {"_id": "$conferenceId", "userCount": {"$sum": 1}}},
            {"$sort": {"userCount": -1}}  # Sắp xếp giảm dần theo số lượng người dùng
        ]

        results = list(users_collection.aggregate(pipeline))

        statistics = [{"conferenceId": res["_id"], "userCount": res["userCount"]} for res in results]

        return jsonify({"statistics": statistics}), 200

    except Exception as e:
        return jsonify({"message": "Đã xảy ra lỗi!", "error": str(e)}), 500

@app.route('/statistics/<conferenceId>', methods=['GET'])
def get_statistics_by_conference(conferenceId):
    try:
        pipeline = [
            {"$match": {"conferenceId": conferenceId, "isRegistered": True}},  
            {"$group": {"_id": "$conferenceId", "userCount": {"$sum": 1}}} 
        ]
        results = list(users_collection.aggregate(pipeline))        
        if results:
            statistics = [{"conferenceId": str(res["_id"]), "userCount": res["userCount"]} for res in results]
            return jsonify({"statistics": statistics}), 200
        else:
            return jsonify({"message": "Không tìm thấy dữ liệu cho conferenceId này."}), 404
    except Exception as e:
        return jsonify({"message": "Đã xảy ra lỗi!", "error": str(e)}), 500
@app.route('/input', methods=['POST'])
def input():
    try:
        data = request.get_json()
        if not data or ('email' not in data and 'phone' not in data):
            return jsonify({"message": "Dữ liệu không hợp lệ. Vui lòng cung cấp email hoặc số điện thoại."}), 400
        
        email = data.get('email')
        phone = data.get('phone')
        query = {}
        if email:
            query['email'] = email
        if phone:
            query['phone'] = phone
        user = users_collection.find_one(query)
        
        if user:
            full_name = user.get('fullName', 'Người dùng')
            email_ctl = user.get('email', 'Email')
            phone_ctl = user.get('phone', 'Số điện thoại')
            conference_id = user.get('conferenceId', 'Không có thông tin hội nghị')  # Assuming conferenceId is stored in the user data
            
            return jsonify({
                "message": f"Mời {full_name} vào hội nghị!",
                "full_name": full_name,
                "email": email_ctl if email_ctl else "Không có email",
                "phone": phone_ctl if phone_ctl else "Không có số điện thoại",
                "conferenceId": conference_id  # Include conferenceId in the response
            }), 200
        else:
            return jsonify({"message": "Thông tin đăng nhập không đúng. Vui lòng kiểm tra lại."}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
    
@app.route('/api/registered-people', methods=['GET'])
def get_registered_people():
    try:
        total_registered = users_collection.count_documents({})
        return jsonify({"total_registered": total_registered}), 200
    except Exception as e:
        return jsonify({"message": "Đã xảy ra lỗi!", "error": str(e)}), 500
@app.route('/admin/users', methods=['GET'])
def list_users():
    try:
        users = list(users_collection.find({}, {"password": 0})) 
        for user in users:
            user["_id"] = str(user["_id"])
        return jsonify({"message": "Danh sách người dùng.", "data": users}), 200
    except Exception as e:
        return jsonify({"message": "Đã xảy ra lỗi!", "error": str(e)}), 500
@app.route('/admin/statistics', methods=['GET'])
def get_statistics_users():
    try:
        # Truy vấn số lượng người mời và người đã đăng ký
        invited_count = users_collection.count_documents({"isRegistered": False})  # Người mời
        registered_count = users_collection.count_documents({"isRegistered": True})  # Người đã đăng ký
        
        # Dữ liệu trả về cho PieChart
        pie_chart_data = [
            ["Category", "Total"],
            ["Số người mời", invited_count],  # Tổng số người mời
            ["Số người đã đăng ký", registered_count]  # Tổng số người đã đăng ký
        ]
        
        # Trả về kết quả
        return jsonify({"message": "Dữ liệu thống kê", "data": pie_chart_data}), 200
    except Exception as e:
        return jsonify({"message": "Đã xảy ra lỗi!", "error": str(e)}), 500

@app.route('/users/<user_id>', methods=['DELETE'])
def delete_user(user_id):
    try:
        try:
            UUID(user_id) 
        except ValueError:
            return jsonify({"message": "Dữ liệu không hợp lệ. 'user_id' phải là UUID hợp lệ."}), 400
        
        existing_user = users_collection.find_one({"_id": user_id}) 

        if not existing_user:
            return jsonify({"message": "Người dùng không tồn tại."}), 404
        result = users_collection.delete_one({"_id": user_id})

        if result.deleted_count == 0:
            return jsonify({"message": "Không thể xóa người dùng."}), 500
        return jsonify({"message": "Xóa người dùng thành công."}), 200
    except Exception as e:
        return jsonify({"message": "Đã xảy ra lỗi!", "error": str(e)}), 500

@app.route('/users/update/<user_id>', methods=['POST'])
def update_user(user_id):
    try:
        data = request.get_json()
        if not data:
            return jsonify({"message": "Không có dữ liệu để cập nhật."}), 400
        update_data = {}
        if "fullName" in data and data["fullName"].strip():
            update_data["fullName"] = data["fullName"].strip()

        if "email" in data and data["email"].strip():
            update_data["email"] = data["email"].strip()

        if "phone" in data and data["phone"].strip():
            update_data["phone"] = data["phone"].strip()

        if not update_data:
            return jsonify({"message": "Không có trường hợp hợp lệ để cập nhật."}), 400
        result = users_collection.update_one(
            {"_id": user_id},
            {"$set": update_data}
        )
        if result.matched_count == 0:
            return jsonify({"message": "Người dùng không tồn tại."}), 404
        return jsonify({"message": "Cập nhật thông tin người dùng thành công."}), 200
    except Exception as e:
        return jsonify({"message": "Đã xảy ra lỗi!", "error": str(e)}), 500
    
@app.route('/users/<user_id>', methods=['GET'])
def get_user_by_id(user_id):
    try:
        # Truy vấn người dùng theo user_id và loại bỏ trường "password"
        user = users_collection.find_one({"_id": user_id}, {"password": 0})

        # Nếu không tìm thấy người dùng, trả về thông báo 404
        if user is None:
            return jsonify({"message": "Không tìm thấy người dùng với ID này."}), 404
        
        # Trả về thông tin người dùng
        return jsonify({"message": "Thông tin người dùng.", "data": user}), 200
    except Exception as e:
        return jsonify({"message": "Đã xảy ra lỗi!", "error": str(e)}), 500

@app.route('/users/conference/<conference_id>', methods=['GET'])
def get_users_by_conference(conference_id):
    try:
        # Truy vấn người dùng theo conferenceId và loại bỏ trường "password"
        users = list(users_collection.find({"conferenceId": conference_id}, {"password": 0}))
        
        # Chuyển đổi _id thành chuỗi
        for user in users:
            user["_id"] = str(user["_id"])
        
        # Nếu không có người dùng nào, trả về thông báo 404
        if not users:
            return jsonify({"message": "Không tìm thấy người dùng cho conferenceId này."}), 404
        
        return jsonify({"message": "Danh sách người dùng theo conferenceId.", "data": users}), 200
    except Exception as e:
        return jsonify({"message": "Đã xảy ra lỗi!", "error": str(e)}), 500
@app.route('/api/registered-people-by-day', methods=['GET'])
def get_registered_people_by_day():
    try:
        pipeline = [
            {
                "$group": {
                    "_id": {
                        "$dateToString": {"format": "%Y-%m-%d", "date": "$created_at"}
                    },
                    "total_registered": {"$sum": 1}
                }
            },
            {"$sort": {"_id": 1}}  
        ]

        registered_people_by_day = users_collection.aggregate(pipeline)
        result = [{"date": record["_id"], "total_registered": record["total_registered"]} for record in registered_people_by_day]

        return jsonify(result), 200
    except Exception as e:
        return jsonify({"message": "Đã xảy ra lỗi!", "error": str(e)}), 500


answers_collection = db['answers'] 
from datetime import datetime

@app.route('/answer_question', methods=['POST'])
def answer_question():
    data = request.get_json()

    # Kiểm tra dữ liệu đầu vào
    if 'user_id' not in data or 'question_id' not in data or 'answer' not in data:
        return jsonify({"message": "user_id, question_id và answer là bắt buộc!"}), 400

    user_id = data['user_id']
    question_id = data['question_id']
    answer = data['answer']

    # Kiểm tra xem question_id có hợp lệ hay không
    if not ObjectId.is_valid(question_id):
        return jsonify({"message": "ID câu hỏi không hợp lệ!"}), 400

    # Kiểm tra user_id hợp lệ (UUID format)
    if not isinstance(user_id, str) or len(user_id) != 36:  # UUID thường có 36 ký tự
        return jsonify({"message": "ID người dùng không hợp lệ!"}), 400

    # Tạo đối tượng câu trả lời
    answer_data = {
        "user_id": user_id,  # Lưu trực tiếp user_id dạng chuỗi UUID
        "question_id": ObjectId(question_id),  # question_id vẫn là ObjectId
        "answer": answer,
        "created_at": datetime.utcnow()
    }

    try:
        # Lưu câu trả lời vào MongoDB
        answers_collection.insert_one(answer_data)

        return jsonify({"message": "Trả lời câu hỏi thành công!"}), 201
    except Exception as e:
        return jsonify({"message": "Đã xảy ra lỗi!", "error": str(e)}), 500


@app.route('/get_answers/<user_id>', methods=['GET'])
def get_answers(user_id):
    try:
        print(f"Received request for user_id: {user_id}")  # Debug: log user_id

        # Kiểm tra user_id hợp lệ (giả sử là UUID, nên không cần ObjectId)
        if not isinstance(user_id, str) or len(user_id) != 36:  # UUID thường có 36 ký tự
            print("Invalid user_id format!")  # Debug: log invalid ID
            return jsonify({"message": "ID người dùng không hợp lệ!"}), 400

        # Lấy thông tin người dùng
        user = users_collection.find_one({"_id": user_id})  # Không dùng ObjectId
        print(f"User lookup result: {user}")  # Debug: log user lookup result
        if not user:
            return jsonify({"message": "Người dùng không tồn tại!"}), 404

        # Lấy danh sách câu trả lời
        answers = answers_collection.find({"user_id": user_id})  # Không dùng ObjectId
        print("Fetching answers...")  # Debug: log before fetching answers
        result = []
        for answer in answers:
            answer_data = {
                "answer_id": str(answer["_id"]),
                "question_id": str(answer["question_id"]),
                "answer": answer["answer"],
                "created_at": answer["created_at"].strftime("%Y-%m-%d %H:%M:%S")
            }
            result.append(answer_data)
        print(f"Answers fetched: {result}")  # Debug: log answers fetched

        if not result:
            print("User has no answers.")  # Debug: log no answers
            return jsonify({
                "message": "Người dùng chưa trả lời câu hỏi nào.",
                "user": {
                    "user_id": user_id,
                    "name": user.get("fullName", "Không có tên"),
                    "email": user.get("email", "Không có email")
                }
            }), 404

        # Nếu request yêu cầu xuất CSV
        if request.args.get('export') == 'csv':
            import csv
            from io import StringIO

            output = StringIO()
            writer = csv.writer(output)

            # Ghi thông tin người dùng
            writer.writerow(["User ID", "Name", "Email"])
            writer.writerow([user_id, user.get("fullName", "Không có tên"), user.get("email", "Không có email")])

            # Ghi tiêu đề cột
            writer.writerow(["Answer ID", "Question ID", "Answer", "Created At"])

            # Ghi dữ liệu câu trả lời
            for item in result:
                writer.writerow([item["answer_id"], item["question_id"], item["answer"], item["created_at"]])

            output.seek(0)

            # Trả về file CSV
            return Response(
                output,
                mimetype="text/csv",
                headers={"Content-Disposition": f"attachment;filename=answers_{user_id}.csv"}
            )

        print("Returning success response.")  # Debug: log success response
        return jsonify({
            "message": "Lấy danh sách câu trả lời thành công.",
            "user": {
                "user_id": user_id,
                "name": user.get("fullName", "Không có tên"),
                "email": user.get("email", "Không có email")
            },
            "answers": result
        }), 200

    except Exception as e:
        print("An error occurred:", e)  # Debug: log error
        return jsonify({"message": "Đã xảy ra lỗi!", "error": str(e)}), 500
@app.route('/count_unique_answers/<question_id>', methods=['GET'])
def count_unique_answers(question_id):
    try:
        if not ObjectId.is_valid(question_id):
            return jsonify({"message": "ID câu hỏi không hợp lệ!"}), 400
        unique_users = answers_collection.distinct("user_id", {"question_id": ObjectId(question_id)})

        count = len(unique_users)
        return jsonify({
            "message": "Lấy số người đã trả lời câu hỏi thành công.",
            "question_id": question_id,
            "total_unique_answers": count
        }), 200

    except Exception as e:
        return jsonify({"message": "Đã xảy ra lỗi!", "error": str(e)}), 500
from bson import ObjectId

def convert_objectid(obj):
    if isinstance(obj, dict):
        return {key: convert_objectid(value) if isinstance(value, (dict, list)) else str(value) if isinstance(value, ObjectId) else value for key, value in obj.items()}
    elif isinstance(obj, list):
        return [convert_objectid(item) for item in obj]
    elif isinstance(obj, ObjectId):
        return str(obj)
    else:
        return obj

from flask import Flask, request, jsonify
from datetime import datetime
from bson import ObjectId

@app.route('/update-room-data', methods=['POST'])
def update_room_data():
    try:
        # Get data from the request
        data = request.get_json()
        
        # Validate required fields
        if not data or not all(key in data for key in ('conferenceId', 'totalIn', 'totalOut', 'currentPeopleInRoom')):
            return jsonify({"error": "Payload must include 'conferenceId', 'totalIn', 'totalOut', and 'currentPeopleInRoom'"}), 400

        conference_id = data['conferenceId']
        total_in = data['totalIn']
        total_out = data['totalOut']
        current_people = data['currentPeopleInRoom']
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # Validate ObjectId format
        try:
            conference_object_id = ObjectId(conference_id)
        except Exception as e:
            return jsonify({"error": f"Invalid ObjectId format: {str(e)}"}), 400

        # Prepare the room data entry
        room_data_entry = {
            "conferenceId": conference_id,
            "totalIn": total_in,
            "totalOut": total_out,
            "currentPeopleInRoom": current_people,
            "timestamp": timestamp
        }

        # Insert room data into the room collection
        room_collection.insert_one(room_data_entry)

        # Retrieve the conference document from the database
        conference = conference_collection.find_one({"_id": conference_object_id})
        if not conference:
            return jsonify({"error": "Conference not found"}), 404

        # Convert ObjectId to string for serialization
        conference['_id'] = str(conference['_id'])

        # Update the conference document with the new room data
        conference_collection.update_one(
            {"_id": conference_object_id},
            {"$push": {"rooms": room_data_entry}}
        )

        # Return a success response
        return jsonify({
            "message": "Dữ liệu phòng được cập nhật thành công",
            "data": room_data_entry,
            "conferenceId": conference['_id']  # Convert ObjectId to string here
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/get-room-data/<conference_id>', methods=['GET'])
def get_room_data(conference_id):
    try:
        # Convert conference_id to ObjectId
        conference_id_obj = ObjectId(conference_id)
        # Query the database using ObjectId
        conference = conference_collection.find_one({"_id": conference_id_obj})
        if not conference:
            return jsonify({"error": "Conference not found"}), 404
        
        # Chuyển đổi ObjectId thành chuỗi ở mọi nơi trong dữ liệu
        conference_data = convert_objectid(conference)
        
        # Giả sử bạn có một cấu trúc 'rooms' với thời gian cần chuyển đổi thành timestamp
        rooms = conference_data.get("rooms", [])
        
        # Chuyển đổi thời gian thành timestamp
        for room in rooms:
            for stat in room.get("stats", []):
                # Giả sử 'time' là trường chứa thời gian cần chuyển đổi thành timestamp
                stat["time"] = int(datetime.datetime.strptime(stat["time"], "%Y-%m-%d %H:%M:%S").timestamp() * 1000)  # Convert to milliseconds
        
        return jsonify({"conferenceId": conference_id, "rooms": conference_data.get("rooms", [])}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
