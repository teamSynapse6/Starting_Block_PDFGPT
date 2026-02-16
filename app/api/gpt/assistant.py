import json
from pathlib import Path
from openai import OpenAI
from app.api.gpt.prompts import instructions as assistant_instructions

BASE_DIR = Path(__file__).resolve().parents[3]
ASSISTANT_FILE_PATH = BASE_DIR / "assistant.json"


def _save_assistant_id(assistant_id: str):
    with open(ASSISTANT_FILE_PATH, "w", encoding="utf-8") as file:
        json.dump({"assistant_id": assistant_id}, file)


def create_or_sync_assistant(client: OpenAI) -> str:
    if ASSISTANT_FILE_PATH.exists():
        with open(ASSISTANT_FILE_PATH, "r", encoding="utf-8") as file:
            assistant_data = json.load(file)
            assistant_id = assistant_data["assistant_id"]
        assistant = client.beta.assistants.update(
            assistant_id=assistant_id,
            instructions=assistant_instructions,
            name="Starting_Block_GPT_PDF_Assistant",
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
                                    "description": "The ID of the announcement to retrieve information for.",
                                }
                            },
                            "required": ["announcement_id"],
                        },
                    },
                }
            ],
        )
        assistant_id = assistant.id
    else:
        assistant = client.beta.assistants.create(
            instructions=assistant_instructions,
            name="Starting_Block_GPT_PDF_Assistant",
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
                                    "description": "The ID of the announcement to retrieve information for.",
                                }
                            },
                            "required": ["announcement_id"],
                        },
                    },
                }
            ],
        )
        assistant_id = assistant.id

    _save_assistant_id(assistant_id)

    return assistant_id
