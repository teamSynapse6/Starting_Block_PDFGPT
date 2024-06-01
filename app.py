from fastapi import FastAPI, HTTPException, Request, APIRouter
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from typing import List
from werkzeug.utils import secure_filename
import requests, fitz, os, shutil, olefile, zlib, struct, json, re, asyncio
import openai
from openai import OpenAI
import functions

app = FastAPI(
    title="PDFGPT_StartingBlock_Server",
)

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

# PDF 관련 라우터
pdf_router = APIRouter(prefix="/pdf", tags=["PDF"])

@pdf_router.get("/validation")
async def validate_files():
    filenames = os.listdir(PROCESSED_FILE_DIR)
    file_ids_numeric = [int(filename[:-4]) for filename in filenames if filename.endswith('.txt')]
    file_ids_numeric_sorted = sorted(file_ids_numeric)
    file_ids_sorted = [str(file_id) for file_id in file_ids_numeric_sorted]
    return {"file_ids": file_ids_sorted}

@pdf_router.get("/announcement")
async def get_announcement(id: str):
    if not id:
        raise HTTPException(status_code=400, detail="file_id가 없습니다")

    filename = secure_filename(id) + '.txt'
    filepath = os.path.join(PROCESSED_FILE_DIR, filename)

    if os.path.exists(filepath):
        return FileResponse(filepath, media_type='text/plain', filename=filename)
    else:
        raise HTTPException(status_code=404, detail="파일이 없습니다")

@pdf_router.delete("/announcement/delete")
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
                print(f"Error deleting file {file_id}: {e}")
    return {"status": "finished"}

@pdf_router.post("/announcement/upload")
async def upload_files(data: List[UploadRequest]):
    success_items = []
    failed_items = []

    for item in data:
        file_url = item.url
        file_id = item.id
        file_format = item.format
        temp_path = os.path.join(BASE_DIR, f"{file_id}.{file_format}")  # 원본 파일 확장자로 저장

        if file_format in ['hwp', 'pdf', 'txt']:
            try:
                response = requests.get(file_url, stream=True)
                with open(temp_path, 'wb') as f:
                    shutil.copyfileobj(response.raw, f)

                if file_format == 'pdf':
                    await convert_pdf_to_txt(temp_path, file_id)
                elif file_format == 'hwp':
                    await convert_hwp_to_txt(temp_path, PROCESSED_FILE_DIR)
                elif file_format == 'txt':
                    shutil.move(temp_path, os.path.join(PROCESSED_FILE_DIR, f"{file_id}.txt"))

                success_items.append(file_id)

            except Exception as e:
                failed_items.append(file_id)
                if os.path.exists(temp_path):
                    os.remove(temp_path)
        else:
            failed_items.append(file_id)

    return {"status": "finished", "success_items": success_items, "failed_items": failed_items}

async def convert_pdf_to_txt(temp_path, file_id):
    try:
        doc = fitz.open(temp_path)
        text = ''
        for page in doc:
            text += page.get_text()

        txt_path = os.path.join(PROCESSED_FILE_DIR, f"{file_id}.txt")
        with open(txt_path, 'w', encoding='utf-8') as txt_file:
            txt_file.write(text)

        doc.close()
        os.remove(temp_path)
    except Exception as e:
        raise e

async def get_hwp_text(filename):
    with olefile.OleFileIO(filename) as f:
        dirs = f.listdir()

        header = f.openstream("FileHeader")
        header_data = header.read()
        is_compressed = (header_data[36] & 1) == 1

        nums = []
        for d in dirs:
            if d[0] == "BodyText":
                nums.append(int(d[1][len("Section"):]))
        sections = ["BodyText/Section"+str(x) for x in sorted(nums)]

        text = ""
        for section in sections:
            bodytext = f.openstream(section)
            data = bodytext.read()
            if is_compressed:
                unpacked_data = zlib.decompress(data, -15)
            else:
                unpacked_data = data

            section_text = ""
            i = 0
            size = len(unpacked_data)
            while i < size:
                header = struct.unpack_from("<I", unpacked_data, i)[0]
                rec_type = header & 0x3ff
                rec_len = (header >> 20) & 0xfff

                if rec_type in [67]:
                    rec_data = unpacked_data[i+4:i+4+rec_len]
                    section_text += rec_data.decode('utf-16')
                    section_text += "\n"

                i += 4 + rec_len

            text += section_text
            text += "\n"

        return text

async def convert_hwp_to_txt(hwp_path, output_folder):
    try:
        extracted_text = await get_hwp_text(hwp_path)

        clean_text = re.sub(r'[^\w\s,.!?;:()가-힣]', '', extracted_text)

        file_id = os.path.basename(hwp_path).split('.')[0]
        output_file_name = f"{file_id}.txt"
        output_file_path = os.path.join(output_folder, output_file_name)

        with open(output_file_path, 'w', encoding='utf-8') as output_file:
            output_file.write(clean_text)

    except Exception as e:
        raise
    finally:
        if os.path.exists(hwp_path):
            os.remove(hwp_path)

# GPT 관련 라우터
gpt_router = APIRouter(prefix="/gpt", tags=["GPT"])

@gpt_router.get("/start")
async def start_conversation():
    thread = await asyncio.to_thread(client.beta.threads.create)
    return {"thread_id": thread.id}

@gpt_router.post("/chat", summary="GPT API에 메시지 전송")
async def chat(request: Request):
    data = await request.json()
    thread_id = data.get('thread_id')
    message = data.get('message')

    if not thread_id:
        raise HTTPException(status_code=400, detail="thread_id가 없습니다")

    await asyncio.to_thread(client.beta.threads.messages.create, thread_id=thread_id, role="user", content=message)
    run = await asyncio.to_thread(client.beta.threads.runs.create, thread_id=thread_id, assistant_id=assistant_id)
    print('어시스턴트 실행')

    while True:
        run_status = await asyncio.to_thread(client.beta.threads.runs.retrieve, thread_id=thread_id, run_id=run.id)
        if run_status.status == "completed":
            print('내부처리 완료')
            break
        elif run_status.status == "in_progress":
            print('내부처리 중')
            await asyncio.sleep(0.1)
        elif run_status.status == "requires_action":
            for tool_call in run_status.required_action.submit_tool_outputs.tool_calls:
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
            await asyncio.sleep(0.1)
            print('정보호출 완료')
        elif run_status.status in ["failed", "expired"]:
            raise HTTPException(status_code=500, detail="어시스턴트 처리 중 오류가 발생했습니다.")

    messages = await asyncio.to_thread(client.beta.threads.messages.list, thread_id=thread_id)
    response = messages.data[0].content[0].text.value
    return JSONResponse(content={"response": response}, media_type="application/json; charset=utf-8")

@gpt_router.delete("/end")
async def delete_thread(thread_id: str):
    if not thread_id:
        raise HTTPException(status_code=400, detail="thread_id 파라미터가 필요합니다.")

    try:
        response = await asyncio.to_thread(client.beta.threads.delete, thread_id)
        return {"id": thread_id, "object": "thread.deleted", "deleted": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail="스레드를 삭제하는 동안 오류가 발생했습니다.")

# 라우터 등록
app.include_router(pdf_router)
app.include_router(gpt_router)

# 환경 변수에서 OpenAI API 키 로드
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

# OpenAI 클라이언트 초기화
client = OpenAI(api_key=OPENAI_API_KEY)

# 보조자(Assistant) 생성 또는 로드
assistant_id = functions.create_assistant(client)  # 이 기능은 functions.py에서 사용

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5001, timeout_keep_alive=60)
