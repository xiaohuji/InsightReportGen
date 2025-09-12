from .base import BaseConfig

DEFAULT_CONFIG: BaseConfig = {
    "RETRIEVER": "tavily",
    "EMBEDDING": "openai:text-embedding-v4",
    "SIMILARITY_THRESHOLD": 0.42,
    "FAST_LLM": "openai:qwen-plus-latest",
    "SMART_LLM": "openai:qwen-plus-latest",  # Has support for long responses (2k+ words).
    "STRATEGIC_LLM": "openai:qwen-plus-latest",  # Can be used with o1 or o3, please note it will make tasks slower.
    "FAST_TOKEN_LIMIT": 16000,
    "SMART_TOKEN_LIMIT": 16000,
    "STRATEGIC_TOKEN_LIMIT": 16000,
    "BROWSE_CHUNK_MAX_LENGTH": 8192,
    "CURATE_SOURCES": False,
    "SUMMARY_TOKEN_LIMIT": 700,
    "TEMPERATURE": 0.4,
    "USER_AGENT": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 Edg/119.0.0.0",
    "MAX_SEARCH_RESULTS_PER_QUERY": 5,
    "MEMORY_BACKEND": "local",
    "TOTAL_WORDS": 20000,
    "REPORT_FORMAT": "APA",
    "MAX_ITERATIONS": 3,
    "AGENT_ROLE": None,
    "SCRAPER": "bs",
    "MAX_SCRAPER_WORKERS": 15,
    "MAX_SUBTOPICS": 5,
    "MAX_RESEARCH_RESULTS": 5,
    "LANGUAGE": "中文",
    "REPORT_SOURCE": "web",
    "DOC_PATH": "./my-docs",
    "PROMPT_FAMILY": "default",
    "LLM_KWARGS": {},
    "EMBEDDING_KWARGS": {},
    "VERBOSE": False,
    # Deep research specific settings
    "DEEP_RESEARCH_BREADTH": 10,
    "DEEP_RESEARCH_DEPTH": 2,
    "DEEP_RESEARCH_CONCURRENCY": 4,
    
    # MCP retriever specific settings
    "MCP_SERVERS": [],  # List of predefined MCP server configurations
    "MCP_AUTO_TOOL_SELECTION": True,  # Whether to automatically select the best tool for a query
    "MCP_ALLOWED_ROOT_PATHS": [],  # List of allowed root paths for local file access
    "MCP_STRATEGY": "fast",  # MCP execution strategy: "fast", "deep", "disabled"
    "REASONING_EFFORT": "medium",

    # Coder specific settings
    "CODE_LIBS": """
    numpy, pandas, scipy,
    matplotlib, seaborn, plotly,
    scikit-learn, scikit-plot, statsmodels,
    torch, torchvision, tensorflow, keras,
    shap, lime, yellowbrick,
    lifelines,
    opencv-python, Pillow, scikit-image, SimpleITK, monai
    """,
    "FIGURE_STANDARDS": """
    - 图像尺寸 8x6 英寸，分辨率 150dpi。
    - 字体：中文使用 SimHei，英文使用 Arial，防止乱码。
    - 颜色方案使用 seaborn Set2。
    - 标题加粗，字号 14；坐标轴标签字号 12。
    - 保存为 PNG 格式，使用 bbox_inches='tight'。
    """,
    "TABLE_STANDARDS": """
    - CSV 文件统一保存为 utf-8-sig 编码。
    - 列顺序：group → metric → value。
    - 数值保留 2 位小数，缺失值填 NA。
    - 列名统一为英文小写，下划线分隔。
    """,
    "DATA_PATH": r'C:\Users\Lenovo\Desktop\report_gen\prediction_task\PMI.csv',
    "OUTPUT_DIR": r'C:\Users\Lenovo\Desktop\report_gen\prediction_task\result'
}
