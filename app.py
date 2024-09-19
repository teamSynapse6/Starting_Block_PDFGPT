from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from typing import List
from werkzeug.utils import secure_filename
import requests, fitz, os, shutil, olefile, zlib, struct, json, re, asyncio
import httpx, aiofiles
import openai
from openai import OpenAI
import functions
from dotenv import load_dotenv
import uvicorn

app = FastAPI(
    title="PDFGPT_StartingBlock_Server",
)

load_dotenv(dotenv_path=".env")

# 애플리케이션의 루트 디렉토리 기반으로 절대 경로 생성
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FILE_DIR = os.path.join(BASE_DIR, 'file')
PROCESSED_FILE_DIR = os.path.join(BASE_DIR, 'processed_file')

# 모델 정의
class DeleteRequest(BaseModel):
    id: List[int]

class UploadRequest(BaseModel):
    url: str
    id: int
    format: str

# 저장된 파일 리스트 get 메소드
@app.get("/validation", tags=["PDF"], summary='저장된 파일 리스트 반환')
def validate_files():
    filenames = os.listdir(PROCESSED_FILE_DIR)
    file_ids_numeric = [int(filename[:-4]) for filename in filenames if filename.endswith('.txt')]
    file_ids_numeric_sorted = sorted(file_ids_numeric)
    file_ids_sorted = [str(file_id) for file_id in file_ids_numeric_sorted]
    return {"file_ids": file_ids_sorted}

# 저장된 특정 공고 정보 가져오기
@app.get("/announcement", tags=["PDF"], summary='특정 공고 정보 가져오기')
async def get_announcement(id: str):
    if not id:
        raise HTTPException(status_code=400, detail="file_id가 없습니다")

    filename = secure_filename(id) + '.txt'
    filepath = os.path.join(PROCESSED_FILE_DIR, filename)

    if os.path.exists(filepath):
        return FileResponse(filepath, media_type='text/plain', filename=filename)
    else:
        raise HTTPException(status_code=404, detail="파일이 없습니다")

# 아이템 삭제 메소드
@app.delete("/announcement/delete", tags=["PDF"], summary='저장된 파일 삭제')
async def delete_files(data: DeleteRequest):
    if not data.id:
        return {"error": "No file ids provided"}

    for file_id in data.id:
        filename = f"{file_id}.txt"
        filepath = os.path.join(PROCESSED_FILE_DIR, filename)
        if os.path.exists(filepath):
            try:
                os.remove(filepath)
            except Exception as e:
                return ({"error": f"Failed to delete file {file_id}"})
    return {"status": "finished"}

# processed_file 디렉토리가 없으면 생성
if not os.path.exists(PROCESSED_FILE_DIR):
    os.makedirs(PROCESSED_FILE_DIR)

# pdf, hwp id 반환후 다운 처리 프로세스
@app.post("/announcement/upload", tags=["PDF"], summary='파일 업로드')
async def upload_files(data: List[UploadRequest], background_tasks: BackgroundTasks):
    success_items = []
    failed_items = []

    async with httpx.AsyncClient() as client:
        for item in data:
            file_url = item.url
            file_id = item.id
            file_format = item.format
            temp_path = os.path.join(BASE_DIR, f"{file_id}.{file_format}")  # 원본 파일 확장자로 저장

            # 지원되는 파일 형식만 처리
            if file_format in ['hwp', 'pdf', 'txt']:
                try:
                    # 파일 다운로드
                    response = await client.get(file_url)
                    async with aiofiles.open(temp_path, 'wb') as f:
                        await f.write(response.content)

                    # 파일 형식 확인 후 처리
                    actual_format = await detect_file_format(temp_path)
                    if actual_format != file_format:
                        raise ValueError(f"Incorrect file format for file_id {file_id}: expected {file_format}, got {actual_format}")

                    try:
                        if actual_format == 'pdf':
                            # PDF 파일을 TXT로 변환
                            background_tasks.add_task(asyncio.to_thread, convert_pdf_to_txt, temp_path, file_id)
                        elif actual_format == 'hwp':
                            # HWP 파일을 TXT로 변환
                            background_tasks.add_task(asyncio.to_thread, convert_hwp_to_txt, temp_path, PROCESSED_FILE_DIR)
                        elif actual_format == 'txt':
                            # TXT 파일은 바로 저장
                            async with aiofiles.open(os.path.join(PROCESSED_FILE_DIR, f"{file_id}.txt"), 'wb') as f:
                                async with aiofiles.open(temp_path, 'rb') as src:
                                    await f.write(await src.read())
                            os.remove(temp_path)  # 처리 완료 후 원본 TXT 파일 삭제

                        success_items.append(file_id)
                    except Exception as e:
                        failed_items.append(file_id)
                        if os.path.exists(temp_path):
                            os.remove(temp_path)  # 실패 시 임시 파일 삭제
                except Exception as e:
                    failed_items.append(file_id)
                    if os.path.exists(temp_path):
                        os.remove(temp_path)  # 실패 시 임시 파일 삭제
            else:
                failed_items.append(file_id)

    return {"status": "finished", "success_items": success_items, "failed_items": failed_items}

async def detect_file_format(temp_path):
    # 파일의 실제 형식을 확인하는 로직을 추가
    try:
        async with aiofiles.open(temp_path, 'rb') as f:
            header = await f.read(4)
        if header.startswith(b'%PDF'):
            return 'pdf'
        elif header.startswith(b'\xd0\xcf\x11\xe0'):  # OLE header for HWP
            return 'hwp'
        else:
            return 'unknown'
    except Exception as e:
        return 'unknown'

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
    with open(filename, 'rb') as file:
        f = olefile.OleFileIO(file)
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
        sections = ["BodyText/Section" + str(x) for x in sorted(nums)]

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
                    rec_data = unpacked_data[i + 4:i + 4 + rec_len]
                    try:
                        section_text += rec_data.decode('utf-16', errors='ignore')  # 오류 무시
                    except UnicodeDecodeError:
                        section_text += rec_data.decode('utf-16', errors='replace')  # 대체 문자를 사용
                    section_text += "\n"

                i += 4 + rec_len

            text += section_text
            text += "\n"

        return text


def convert_hwp_to_txt(hwp_path, output_folder):
    try:
        extracted_text = get_hwp_text(hwp_path)

        # 출력 가능한 문자 및 일부 특수 문자만 유지
        clean_text = re.sub(r'[^\w\s,.!?;:()가-힣]', '', extracted_text)

        file_id = os.path.basename(hwp_path).split('.')[0]
        output_file_name = f"{file_id}.txt"
        output_file_path = os.path.join(output_folder, output_file_name)

        with open(output_file_path, 'w', encoding='utf-8') as output_file:
            output_file.write(clean_text)

    except Exception as e:
        raise
    finally:
        # 변환 작업이 완료된 후 원본 HWP 파일 삭제
        if os.path.exists(hwp_path):
            os.remove(hwp_path)

# GPT 서버 코드 부분

# 환경 변수에서 OpenAI API 키 로드
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

# OpenAI 클라이언트 초기화
client = OpenAI(api_key=OPENAI_API_KEY, default_headers={"OpenAI-Beta": "assistants=v2"})

# 보조자(Assistant) 생성 또는 로드
assistant_id = functions.create_assistant(client)  # 이 기능은 funcionts.py에서 사용

# 대화 만들기
@app.get("/gpt/start", tags=["GPT"], summary='쓰레드 생성')
async def start_conversation():
    thread = await asyncio.to_thread(client.beta.threads.create)
    return {"thread_id": thread.id}

# 채팅 시작하기
@app.post("/gpt/chat", tags=["GPT"], summary='채팅 시작')
async def chat(request: Request): 
    data = await request.json()
    thread_id = data.get('thread_id')
    message = data.get('message')

    if not thread_id:
        raise HTTPException(status_code=400, detail="thread_id가 없습니다")

    await asyncio.to_thread(client.beta.threads.messages.create, thread_id=thread_id, role="user", content=message)    
    run = await asyncio.to_thread(client.beta.threads.runs.create, thread_id=thread_id, assistant_id=assistant_id)
    
    while True:
        run_status = await asyncio.to_thread(client.beta.threads.runs.retrieve, thread_id=thread_id, run_id=run.id)
        if run_status.status == "completed":
            break
        elif run_status.status == "in_progress":
            await asyncio.sleep(0.1) # 완료 후 0.1초간 대기
        elif run_status.status == "requires_action":
            for tool_call in run_status.required_action.submit_tool_outputs.tool_calls: #이 부분의 레퍼런스를 확인 못함!
                if tool_call.function.name == "information_from_pdf_server":
                    arguments = json.loads(tool_call.function.arguments)
                    output = functions.information_from_pdf_server(arguments["announcement_id"])
                    await asyncio.to_thread(client.beta.threads.runs.submit_tool_outputs,
                                            thread_id=thread_id,
                                            run_id=run.id,
                                            tool_outputs=[{
                                                "tool_call_id": tool_call.id,
                                                "output": json.dumps(output)
                                            }])
            await asyncio.sleep(0.1) # 완료 후 0.1초간 대기
        elif run_status.status in ["failed", "expired"]:
            raise HTTPException(status_code=500, detail="어시스턴트 처리 중 오류가 발생했습니다.")
    
    messages = await asyncio.to_thread(client.beta.threads.messages.list, thread_id=thread_id)
    response = messages.data[0].content[0].text.value
    return JSONResponse(content={"response": response}, media_type="application/json; charset=utf-8")

@app.delete("/gpt/end", tags=["GPT"], summary='쓰레드 삭제')
async def delete_thread(thread_id: str):
    if not thread_id:
        raise HTTPException(status_code=400, detail="thread_id 파라미터가 필요합니다.")
    
    try:
        response = await asyncio.to_thread(client.beta.threads.delete, thread_id)
        return {"id": thread_id, "object": "thread.deleted", "deleted": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail="스레드를 삭제하는 동안 오류가 발생했습니다.")
    
# API 상태 확인
@app.get("/gpt/api_status", tags=["GPT"], summary='API 상태 확인')
async def api_status():
    try:
        # OpenAI 상태 API 호출
        async with httpx.AsyncClient() as client:
            response = await client.get('https://status.openai.com/api/v2/status.json')
            if response.status_code == 200:
                status_data = response.json()
                indicator = status_data.get('status', {}).get('indicator', 'unknown')
    
                # 상태에 따라 메시지 반환
                if indicator in ['major', 'critical']:
                    return {"status": "caution", "message": "OpenAI API에 문제가 있습니다. 현재 사용을 주의하세요."}
                elif indicator in ['minor', 'none']:
                    return {"status": "good", "message": "OpenAI API가 정상적으로 동작하고 있습니다."}
                else:
                    return {"status": "unknown", "message": "상태를 확인할 수 없습니다."}
            else:
                raise HTTPException(status_code=500, detail="OpenAI 상태 API를 불러올 수 없습니다.")
    except Exception as e:
        raise HTTPException(status_code=500, detail="API 호출 중 오류가 발생했습니다.")

if __name__ == '__main__':
    uvicorn.run(app, host="0.0.0.0", port=5001, timeout_keep_alive=60)
