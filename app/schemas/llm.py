from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    thread_id: str = Field(..., min_length=1, description="대화 세션 UUID")
    message: str = Field(..., min_length=1, description="사용자 질문")
    announcement_id: int = Field(..., description="질의 대상 공고 ID")
