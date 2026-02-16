from pydantic import BaseModel
from typing import List


class DeleteRequest(BaseModel):
    id: List[int]


class UploadRequest(BaseModel):
    url: str
    id: int
    format: str
