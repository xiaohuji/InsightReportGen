from typing import List, Literal, Optional
from pydantic import BaseModel, Field, conlist

class Subtopic(BaseModel):
    task: str = Field(description="Task name", min_length=1)

class Subtopics(BaseModel):
    subtopics: List[Subtopic] = []

class Section(BaseModel):
    id: str
    title: str
    goal: str
    expected_outputs: List[Literal["table","figure","metric"]]
    code: str

class SectionsResponse(BaseModel):
    sections: List[Section] = Field(default_factory=list)

class Settings(BaseModel):
    random_seed: Optional[int] = Field(default=42, description="随机种子")
    data_sources: List[str] = Field(default_factory=list, description="数据源文件路径")
    key_columns: List[str] = Field(default_factory=list, description="关键列名")

class Artifacts(BaseModel):
    tables: List[str]   = Field(default_factory=list, description="要写出的CSV路径（相对/绝对）")
    figures: List[str]  = Field(default_factory=list, description="要写出的PNG路径（相对/绝对）")
    metrics: List[str]  = Field(default_factory=list, description="要写出的metrics路径（json/jsonl/csv）")

class Step(BaseModel):
    id: str
    name: str
    objective: str
    inputs: List[str] = Field(default_factory=list)
    ops: List[str]    = Field(default_factory=list)
    artifacts: Artifacts = Field(default_factory=Artifacts)
    checks: List[str] = Field(default_factory=list)
    notes: Optional[str] = ""

class PipelinePlanResponse(BaseModel):
    settings: Settings = Field(default_factory=Settings)
    # ✅ pipeline 必须是列表（用 conlist 可顺便限制步数上限）
    pipeline: List[Step] = Field(..., min_length=1, max_length=50)
    class Config:
        extra = "ignore"   # 返回里多给的字段直接忽略