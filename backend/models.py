from pydantic import BaseModel, Field
from typing import List, Optional


class CategoryWeight(BaseModel):
    name: str
    weight: int = Field(ge=1, description="权重，正整数")


class GenerateRequest(BaseModel):
    total_count: int = Field(ge=1, le=50000, description="单文件总条数")
    categories: List[CategoryWeight]
    mode: str = Field(default="auto", description="生成模式: llm / element_pool / auto")
    actor_id: str = Field(default="Skeleton0", description="actor_id 中 Skeleton 后缀")
    provider: str = Field(default="auto", description="LLM 后端: auto / deepseek / ollama")
    task_id: Optional[str] = Field(default=None, description="任务 ID，用于取消生成")


class BatchGenerateRequest(BaseModel):
    total_count: int = Field(ge=1, le=5000, description="每文件条数")
    file_count: int = Field(ge=1, le=50, description="文件个数")
    categories: List[CategoryWeight]
    mode: str = Field(default="auto", description="生成模式: llm / element_pool / auto")
    actor_id: str = Field(default="Skeleton0", description="actor_id 中 Skeleton 后缀")
    provider: str = Field(default="auto", description="LLM 后端: auto / deepseek / ollama")
    task_id: Optional[str] = Field(default=None, description="任务 ID，用于取消生成")


class CancelRequest(BaseModel):
    task_id: Optional[str] = Field(default=None, description="要取消的生成任务 ID；为空时取消所有进行中的任务")


class ActionRecord(BaseModel):
    query: str
    text: str
    motion_description: str
    voice_feedback: str
    category: str
    is_head: bool


class FileStats(BaseModel):
    file_index: int
    record_id: str
    stats: dict


class GenerateResponse(BaseModel):
    success: bool
    mode: str
    data: Optional[List[dict]] = None
    record_id: Optional[str] = None
    stats: Optional[dict] = None
    error: Optional[str] = None


class BatchGenerateResponse(BaseModel):
    success: bool
    mode: str
    files: Optional[List[dict]] = None
    error: Optional[str] = None


class ProviderInfo(BaseModel):
    id: str
    label: str
    model: str
    available: bool
    online: bool


class StatusResponse(BaseModel):
    llm_available: bool
    mode: str
    model: str
    providers: List[ProviderInfo] = []


class HistoryItem(BaseModel):
    id: str
    type: str
    count_per_file: int
    file_count: int
    total_records: int
    categories_json: str
    created_at: str


class ImportResult(BaseModel):
    success: bool
    imported_count: int
    skipped_count: int
    total_count: int
    error: Optional[str] = None


class QueryPoolStats(BaseModel):
    total: int
    by_category: dict
    by_source: dict


class KeywordItem(BaseModel):
    id: int
    keyword: str
    category: str
    source: str
    reviewed: bool
    created_at: str
