from enum import Enum


class ReportType(Enum):
    ResearchReport = "research_report"
    ResourceReport = "resource_report"
    OutlineReport = "outline_report"
    CustomReport = "custom_report"
    DetailedReport = "detailed_report"
    SubtopicReport = "subtopic_report"
    DeepResearch = "deep"
    CodeReport = "code_report"


class ReportSource(Enum):
    Web = "web"
    Local = "local"
    Azure = "azure"
    LangChainDocuments = "langchain_documents"
    LangChainVectorStore = "langchain_vectorstore"
    Static = "static"
    Hybrid = "hybrid"


class Tone(Enum):
    Objective = "客观（公正且不带偏见地呈现事实和研究结果）"
    Formal = "正式（符合学术规范，使用复杂的语言和结构）"
    Analytical = "分析性（对数据和理论进行批判性评估和详细审查）"
    Persuasive = "说服性（旨在使读者信服某一观点或论点）"
    Informative = "信息性（提供清晰而全面的主题信息）"
    Explanatory = "解释性（阐明复杂概念和过程）"
    Descriptive = "描述性（详细描绘现象、实验或案例研究）"
    Critical = "批判性（判断研究及其结论的有效性和相关性）"
    Comparative = "比较性（对不同理论、数据或方法进行对比以突出差异和相似性）"
    Speculative = "推测性（探索假设及潜在影响或未来研究方向）"
    Reflective = "反思性（思考研究过程及个人见解或经验）"
    Narrative = "叙事性（通过讲述故事来说明研究发现或方法）"
    Humorous = "幽默性（轻松有趣，使内容更易于接受）"
    Optimistic = "乐观性（强调积极发现和潜在益处）"
    Pessimistic = "悲观性（侧重于局限性、挑战或负面结果）"
    Simple = "简明（面向年轻读者，使用基础词汇和清晰解释）"
    Casual = "随意（对话式、轻松的风格，便于日常阅读）"


class PromptFamily(Enum):
    """Supported prompt families by name"""
    Default = "default"
    Granite = "granite"
    Granite3 = "granite3"
    Granite31 = "granite3.1"
    Granite32 = "granite3.2"
    Granite33 = "granite3.3"
