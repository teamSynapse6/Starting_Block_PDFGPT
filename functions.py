import requests
import os
from openai import OpenAI
import json
from prompts import instructions
from dotenv import load_dotenv

# prompts.py에서 정의된 지시문을 사용
from prompts import instructions as assistant_instructions

load_dotenv(dotenv_path=".env")

# 환경 변수에서 OpenAI API 키 로드
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

#assistant 초기화
client = OpenAI(api_key=OPENAI_API_KEY, default_headers={"OpenAI-Beta": "assistants=v2"})

#루트 설정
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

#어시스턴트_파일_패스
assistant_file_path = os.path.join(BASE_DIR, 'assistant.json')

# PDF서버로부터 id의 데이터를 호출하는 메소드
def information_from_pdf_server(announcement_id):
    pdf_url = f"https://pdfgpt.startingblock.co.kr/announcement?id={announcement_id}"
    response = requests.get(pdf_url)
    
    if response.status_code == 200:
        text_data = response.content.decode('utf-8')
        return text_data
    elif response.status_code == 404:
        return "요청하신 정보를 찾을 수 없습니다."
    else:
        return "서버에서 정보를 검색하는 동안 오류가 발생했습니다."


#어시스턴트 API 생성
def create_assistant(client):
    #만약 assistant.json이 이미 있다면 로드.
    if os.path.exists(assistant_file_path):
        with open(assistant_file_path, 'r') as file:
            assistant_data = json.load(file)
            assistant_id = assistant_data['assistant_id']
    
    else:
        #만약 assistant.json이 없다면, 아래의 메소드를 사용하는 새 파일을 생성.
        assistant = client.beta.assistants.create(
            instructions=assistant_instructions,
            name = "Starting_Block_GPT_PDF_Assistant",
            model="gpt-4o",
             tools=[
                {
                    "type": "function",
                    "function": {
                        "name": "information_from_pdf_server",
                        "description": "Retrieve text information from a PDF server using the announcement ID.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "announcement_id": {
                                    "type": "integer",
                                    "description": "The ID of the announcement to retrieve information for."
                                }
                            },
                            "required": ["announcement_id"]
                        }
                    }
                }
            ]
        )

        # 생성된 보조자 ID를 assistant.json 파일에 저장합니다.
        with open(assistant_file_path, 'w') as file:
            json.dump({'assistant_id': assistant.id}, file)
        assistant_id = assistant.id

    return assistant_id