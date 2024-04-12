from flask import Flask, request, jsonify, abort, Response
import requests
import fitz 
import os
from werkzeug.utils import secure_filename
import shutil
import olefile
import zlib
import struct
import json
import openai
from openai import OpenAI
import functions
import time


app = Flask(__name__)

# 애플리케이션의 루트 디렉토리 기반으로 절대 경로 생성
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FILE_DIR = os.path.join(BASE_DIR, 'file')
PROCESSED_FILE_DIR = os.path.join(BASE_DIR, 'processed_file')


# 저장된 파일 리스트 get 메소드
@app.route('/validation', methods=['GET'])
def validate_files():
    filenames = os.listdir(PROCESSED_FILE_DIR)
    file_ids_numeric = [int(filename[:-4]) for filename in filenames if filename.endswith('.txt')]
    file_ids_numeric_sorted = sorted(file_ids_numeric)
    file_ids_sorted = [str(file_id) for file_id in file_ids_numeric_sorted]
    return jsonify({"file_ids": file_ids_sorted}), 200

# 저장된 특정 공고 정보 가져오기
@app.route('/announcement')
def get_announcement():
    file_id = request.args.get('id')
    if not file_id:
        abort(400)  # file_id가 없으면 400 Bad Request 오류 반환

    filename = secure_filename(file_id) + '.txt'
    filepath = os.path.join(PROCESSED_FILE_DIR, filename)

    if os.path.exists(filepath):
        # 파일이 존재하면 해당 파일의 내용을 읽어서 반환
        with open(filepath, 'r', encoding='utf-8') as file:
            content = file.read()
        return Response(content, mimetype='text/plain; charset=utf-8')
    else:
        abort(404)  # 파일이 없으면 404 오류 반환

# 아이템 삭제 메소드
@app.route('/announcement/delete', methods=['DELETE'])
def delete_files():
    data = request.get_json()
    file_ids = data.get('id')
    if not file_ids:
        return jsonify({"error": "No file ids provided"}), 400

    for file_id in file_ids:
        filename = f"{file_id}.txt"
        filepath = os.path.join(PROCESSED_FILE_DIR, filename)
        if os.path.exists(filepath):
            try:
                os.remove(filepath)
            except Exception as e:
                print(f"Error deleting file {file_id}: {e}")
    return jsonify({"status": "finished"}), 200


# processed_file 디렉토리가 없으면 생성
if not os.path.exists(PROCESSED_FILE_DIR):
    os.makedirs(PROCESSED_FILE_DIR)

# pdf, hwp id 반환후 다운 처리 프로세스
@app.route('/announcement/upload', methods=['POST'])
def upload_files():
    data = request.json
    success_items = []
    failed_items = []

    for item in data:
        file_url = item['url']
        file_id = item['id']
        file_format = item['format']
        temp_path = os.path.join(BASE_DIR, f"{file_id}.{file_format}")  # 원본 파일 확장자로 저장

        # 지원되는 파일 형식만 처리
        if file_format in ['hwp', 'pdf', 'txt']:
            try:
                # 파일 다운로드
                response = requests.get(file_url, stream=True)
                with open(temp_path, 'wb') as f:
                    shutil.copyfileobj(response.raw, f)

                # 파일 형식에 따른 처리
                if file_format == 'pdf':
                    # PDF 파일을 TXT로 변환
                    convert_pdf_to_txt(temp_path, file_id)
                elif file_format == 'hwp':
                    # HWP 파일을 TXT로 변환
                    convert_hwp_to_txt(temp_path, PROCESSED_FILE_DIR)
                elif file_format == 'txt':
                    # TXT 파일은 바로 저장
                    shutil.move(temp_path, os.path.join(PROCESSED_FILE_DIR, f"{file_id}.txt"))

                success_items.append(file_id)

            except Exception as e:
                print(f"Error processing file {file_id}: {e}")
                failed_items.append(file_id)
                if os.path.exists(temp_path):
                    os.remove(temp_path)  # 실패 시 임시 파일 삭제
        else:
            failed_items.append(file_id)

    return jsonify({"status": "finished", "success_items": success_items, "failed_items": failed_items}), 200

def convert_pdf_to_txt(temp_path, file_id):
    try:
        # 다운로드한 PDF 파일 열기
        doc = fitz.open(temp_path)
        text = ''
        for page in doc:
            text += page.get_text()

        txt_path = os.path.join(PROCESSED_FILE_DIR, f"{file_id}.txt")
        with open(txt_path, 'w', encoding='utf-8') as txt_file:
            txt_file.write(text)

        doc.close()  # PDF 파일 사용 후 닫기
        os.remove(temp_path)  # 처리 완료 후 원본 PDF 파일 삭제
    except Exception as e:
        raise e
    
def get_hwp_text(filename):
    with olefile.OleFileIO(filename) as f:
        dirs = f.listdir()

        # 문서 포맷 압축 여부 확인
        header = f.openstream("FileHeader")
        header_data = header.read()
        is_compressed = (header_data[36] & 1) == 1

        # Body Sections 불러오기
        nums = []
        for d in dirs:
            if d[0] == "BodyText":
                nums.append(int(d[1][len("Section"):]))
        sections = ["BodyText/Section"+str(x) for x in sorted(nums)]

        # 전체 text 추출
        text = ""
        for section in sections:
            bodytext = f.openstream(section)
            data = bodytext.read()
            if is_compressed:
                unpacked_data = zlib.decompress(data, -15)
            else:
                unpacked_data = data

            # 각 Section 내 text 추출    
            section_text = ""
            i = 0
            size = len(unpacked_data)
            while i < size:
                header = struct.unpack_from("<I", unpacked_data, i)[0]
                rec_type = header & 0x3ff
                rec_len = (header >> 20) & 0xfff

                if rec_type in [67]:  # 67은 텍스트 블록을 의미
                    rec_data = unpacked_data[i+4:i+4+rec_len]
                    section_text += rec_data.decode('utf-16')
                    section_text += "\n"

                i += 4 + rec_len

            text += section_text
            text += "\n"

        return text
    
def convert_hwp_to_txt(hwp_path, output_folder):
    try:
        extracted_text = get_hwp_text(hwp_path)

        file_id = os.path.basename(hwp_path).split('.')[0]
        output_file_name = f"{file_id}.txt"
        output_file_path = os.path.join(output_folder, output_file_name)

        with open(output_file_path, 'w', encoding='utf-8') as output_file:
            output_file.write(extracted_text)

    except Exception as e:
        raise
    finally:
        # 변환 작업이 완료된 후 원본 HWP 파일 삭제
        if os.path.exists(hwp_path):
            os.remove(hwp_path)


#GPT 서버 코드 부분
            
# 환경 변수에서 OpenAI API 키 로드
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')            
            
# OpenAI 클라이언트 초기화
client = OpenAI(api_key=OPENAI_API_KEY)

# 보조자(Assistant) 생성 또는 로드
assistant_id = functions.create_assistant(client)  # 이 기능은 funcionts.py에서 사용


# 대화 만들기
@app.route('/gpt/start', methods=['GET'])
def start_conversation():
      thread = client.beta.threads.create()
      return jsonify({"thread_id": thread.id})

    
# 채팅 시작하기
@app.route('/gpt/chat', methods=['POST'])
def chat():
    data = request.json
    thread_id = data.get('thread_id')
    announcement_id = data.get('announcement_id')
    message = data.get('message')

    if not thread_id:
        return jsonify({"error": "thread_id가 없습니다"}), 400

    # 유저의 메시지를 쓰레드에 추가
    client.beta.threads.messages.create(thread_id=thread_id, role="user", content=message)
   


    # 어시스턴트 실행과 동시에 스트리밍 시작
    def generate():
        stream = client.beta.threads.runs.create(thread_id=thread_id, assistant_id=assistant_id, stream=True)
        complete_message = ''
        
        for event in stream:
            if event.event == 'thread.message.delta':
                # 실시간 메시지 업데이트 처리
                message_delta = event.data.delta
                for part in message_delta.content:
                    if part.type == 'text':
                        complete_message += part.text.value
                        yield complete_message
                complete_message = ''
            elif event.event == 'thread.run.requires_action':
                tool_call_id = event.data.required_action.submit_tool_outputs.tool_calls[0].id
                # PDF 서버에서 정보 찾기
                output = functions.information_from_pdf_server(announcement_id)
                tool_stream = client.beta.threads.runs.submit_tool_outputs(thread_id=thread_id,
                                                                run_id=event.data.id,
                                                                stream=True,
                                                                tool_outputs=[{
                                                                    "tool_call_id": tool_call_id,
                                                                    "output": json.dumps(output)
                                                                }])
                for event in tool_stream:
                    if event.event == 'thread.message.delta':
                        # 실시간 메시지 업데이트 처리
                        message_delta = event.data.delta
                        for part in message_delta.content:
                            if part.type == 'text':
                                complete_message += part.text.value
                        yield complete_message
                        complete_message = ''
            time.sleep(1)  # 완료 후 1초간 대기

    return Response(generate(), content_type='text/event-stream')

# 대화 종료 후 쓰레드 삭제하기
@app.route('/gpt/end', methods=['DELETE'])
def delete_thread():
    # 쿼리 파라미터에서 thread_id 추출
    thread_id = request.args.get('thread_id')
    
    # thread_id의 유효성 검사
    if not thread_id:
        return jsonify({"error": "thread_id 파라미터가 필요합니다."}), 400
    
    # OpenAI API를 사용하여 스레드 삭제
    try:
        response = client.beta.threads.delete(thread_id)
        return jsonify({"id": thread_id, "object": "thread.deleted", "deleted": True}), 200
    except Exception as e:
        return jsonify({"error": "스레드를 삭제하는 동안 오류가 발생했습니다."}), 500



if __name__ == '__main__':
    app.run(debug=True)