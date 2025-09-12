import warnings
from datetime import date, datetime, timezone

from langchain.docstore.document import Document

from config import Config
from utils.enum import ReportSource, ReportType, Tone
from utils.enum import PromptFamily as PromptFamilyEnum
from typing import Callable, List, Dict, Any


## Prompt Families #############################################################

class PromptFamily:

    def __init__(self, config: Config):
        self.cfg = config

    # MCP-specific prompts
    @staticmethod
    def generate_mcp_tool_selection_prompt(query: str, tools_info: List[Dict], max_tools: int = 3) -> str:
        import json

        return f"""你是一名研究助理，任务是为研究问题挑选最相关的工具。

        研究问题（RESEARCH QUERY）: "{query}"

        可用工具（AVAILABLE TOOLS）:
        {json.dumps(tools_info, indent=2)}

        任务（TASK）: 分析这些工具，并从中精确选择 {max_tools} 个最相关的工具，用于研究给定的问题。

        选择标准（SELECTION CRITERIA）:
        - 选择能够提供与研究问题相关的信息、数据或见解的工具
        - 优先选择能够搜索、检索或访问相关内容的工具
        - 考虑能够互补的工具（例如，不同数据来源）
        - 排除明显与研究主题无关的工具

        请返回一个 JSON 对象，格式严格如下:
        {{
          "selected_tools": [
            {{
              "index": 0,
              "name": "工具名称",
              "relevance_score": 9,
              "reason": "详细解释该工具为何相关"
            }}
          ],
          "selection_reasoning": "整体说明选择策略"
        }}

        必须精确选择 {max_tools} 个工具，并按与研究问题的相关性排序。
        """

    @staticmethod
    def generate_mcp_research_prompt(query: str, selected_tools: List) -> str:
        # Handle cases where selected_tools might be strings or objects with .name attribute
        tool_names = []
        for tool in selected_tools:
            if hasattr(tool, 'name'):
                tool_names.append(tool.name)
            else:
                tool_names.append(str(tool))

        return f"""您是一位可以访问专业工具的研究助手。您的任务是研究以下查询并提供全面、准确的信息。

        研究查询："{query}"

        操作说明：
        1. 使用可用工具收集与查询相关的信息
        2. 如需全面覆盖，可调用多个工具
        3. 若工具调用失败或返回空结果，请尝试替代方案
        4. 尽可能综合多来源信息
        5. 重点关注直接回应查询的事实性相关信息

        可用工具：{tool_names}

        请执行深入研究并提供您的发现。请策略性地使用工具以获取最相关、最全面的信息。"""

    @staticmethod
    def generate_search_queries_prompt(
        question: str,
        parent_query: str,
        report_type: str,
        max_iterations: int = 3,
        context: List[Dict[str, Any]] = [],
    ):

        if (
            report_type == ReportType.DetailedReport.value
            or report_type == ReportType.SubtopicReport.value
        ):
            task = f"{parent_query} - {question}"
        else:
            task = question

        context_prompt = f"""
        你是一名经验丰富的研究助理，任务是为以下任务生成搜索查询，以找到相关信息: "{task}"。
        上下文（Context）: {context}

        请利用该上下文来指导和优化你的搜索查询。上下文提供了实时的网络信息，可以帮助你生成更具体和更相关的查询。请考虑上下文中提到的任何时事、最新进展或具体细节，以提升搜索查询的相关性。
        """ if context else ""

        dynamic_example = ", ".join([f'"查询 {i + 1}"' for i in range(max_iterations)])

        return f"""请编写 {max_iterations} 条 Google 搜索查询，用于在线搜索，以便针对以下任务形成客观观点: "{task}"

        如果需要，请假设当前日期为 {datetime.now(timezone.utc).strftime('%B %d, %Y')}。

        {context_prompt}
        你必须以字符串列表的形式作答，格式如下: [{dynamic_example}]。
        回答中只能包含该列表。
        """

    @staticmethod
    def generate_report_prompt(
        question: str,
        context,
        report_source: str,
        report_format="apa",
        total_words=1000,
        tone=None,
        language="english",
    ):
        reference_prompt = ""
        if report_source == ReportSource.Web.value:
            reference_prompt = f"""
        你必须在报告末尾写出所有使用过的来源网址作为参考文献，并确保不要重复添加来源，每个来源只保留一个。
        每个网址都需要超链接格式: [网站名称](url)
        此外，你必须在正文中引用到相关网址的地方加入超链接：

        例如: Author, A. A. (Year, Month Date). Title of web page. Website Name. [网站名称](url)
        """
        else:
            reference_prompt = f"""
        你必须在报告末尾写出所有使用过的来源文档名称作为参考文献，并确保不要重复添加来源，每个文档只保留一个。
        """

        tone_prompt = f"请用{tone.value}的语气撰写报告。" if tone else ""

        return f"""
        报告应聚焦于任务的回答，结构清晰、信息丰富、深入全面，如有可用的事实与数据请务必引用，且不少于 {total_words} 字。
        你应尽可能充分利用提供的所有相关信息，撰写内容详尽的报告。

        请严格遵循以下要求：
        - 你必须基于给定信息形成具体且有效的观点，不得使用笼统或空洞的结论。
        - 报告必须使用 markdown 语法，并采用 {report_format} 格式。
        - 在展示结构化数据或对比时，请使用 markdown 表格以增强可读性。
        - 你必须优先考虑所使用来源的相关性、可靠性和重要性。选择可信来源而非低质量来源。
        - 如果可信来源有新文章，必须优先于旧文章。
        - 报告中不得包含目录，必须直接从正文开始。
        - 在正文中引用参考文献时，必须使用 {report_format} 格式的文本内引用，并以 markdown 超链接形式附在句子或段落末尾，例如: ([文内引用](url))。
        - 请在报告末尾添加参考文献列表，使用 {report_format} 格式，并且必须包含完整的 url 链接（不加超链接）。
        - {reference_prompt}
        - {tone_prompt}

        你必须使用以下语言撰写报告: {language}。
        请尽最大努力完成，这是对我的职业生涯非常重要的事情。
        假设当前日期为 {date.today()}。
        请基于问题："{question}"，为以下信息撰写一份详细的报告: 。\n\n"{context}"
        """

    @staticmethod
    def curate_sources(query, sources, max_results=10):
        return f"""你的目标是针对研究任务 "{query}" 评估并整理所提供的爬取内容，重点优先保留相关且高质量的信息，尤其是包含统计数据、数字或具体数据的来源。

        最终整理出的列表将作为撰写研究报告的上下文，因此请优先考虑：
        - 尽可能保留原始信息，特别强调包含定量数据或独特见解的来源
        - 包括广泛的观点和见解
        - 仅过滤掉明显无关或不可用的内容

        评估指南 (EVALUATION GUIDELINES):
        1. 逐一评估每个来源，依据以下标准：
           - 相关性: 包括与研究任务直接或部分相关的来源。倾向于保留。
           - 可信度: 优先保留权威来源，但除非明显不可信，否则不要排除其他来源。
           - 时效性: 优先保留最新信息，除非旧数据仍然重要或有价值。
           - 客观性: 即便来源存在偏见，只要其提供了独特或互补的观点也要保留。
           - 定量价值: 更高优先级保留包含统计数据、数字或其他具体数据的来源。
        2. 来源选择 (Source Selection):
           - 尽可能包括相关来源，最多保留 {max_results} 个，重点在于覆盖面广和多样性。
           - 优先包含含有统计数据、数值或可验证事实的来源。
           - 内容重叠可以接受，只要其增加了深度，特别是涉及数据时。
           - 仅排除完全无关、严重过时或因内容质量太差而无法使用的来源。
        3. 内容保留 (Content Retention):
           - 不得改写、总结或压缩任何来源内容。
           - 保留所有可用信息，仅清理明显的垃圾或格式问题。
           - 即便内容仅部分相关或不完整，只要包含有价值的数据或见解，也要保留。

        需要评估的来源列表 (SOURCES LIST TO EVALUATE):
        {sources}

        你必须严格按照原始 sources JSON 列表的格式返回结果。
        返回结果中不得包含任何 markdown 格式或附加文本（如 ```json），只允许输出 JSON 列表！
        """

    @staticmethod
    def generate_resource_report_prompt(
        question, context, report_source: str, report_format="apa", tone=None, total_words=1000, language="english"
    ):

        reference_prompt = ""
        if report_source == ReportSource.Web.value:
            reference_prompt = f"""
            你必须包含所有相关的来源网址。
            每个网址都需要使用超链接格式: [网站名称](url)
            """
        else:
            reference_prompt = f"""
            你必须在报告末尾写出所有使用过的来源文档名称作为参考文献，并确保不要重复，每个文档只保留一个。
            """

        return (
            "报告应对每个推荐资源进行详细分析，解释该资源如何有助于回答研究问题。\n"
            "重点关注每个资源的相关性、可靠性和重要性。\n"
            "报告必须结构清晰、信息丰富、深入全面，并遵循 Markdown 语法。\n"
            "在合适的情况下，请使用 markdown 表格和其他格式化功能来组织和展示信息。\n"
            "在可用时请包含相关的事实、数据和数字。\n"
            f"报告的最少长度为 {total_words} 字。\n"
            f"你必须使用以下语言撰写报告: {language}。\n"
            "你必须包含所有相关的来源网址。\n"
            "每个网址都需要使用超链接格式: [网站名称](url)\n"
            f"{reference_prompt}"
            f'请基于以上问题，为以下信息或主题生成一份参考文献推荐报告: "{question}"。\n\n"""{context}"""'
        )

    @staticmethod
    def generate_custom_report_prompt(
        query_prompt, context, report_source: str, report_format="apa", tone=None, total_words=1000, language: str = "english"
    ):
        return f'"{context}"\n\n{query_prompt}'

    @staticmethod
    def generate_outline_report_prompt(
        question, context, report_source: str, report_format="apa", tone=None,  total_words=1000, language: str = "chinese"
    ):
    #
    #     return (
    #         f'"""{context}""" 基于以上信息，请为以下问题或主题生成一份研究报告的大纲（使用 Markdown 语法）: "{question}"。'
    #         f' 该大纲应提供一个结构良好的研究报告框架，包括主要部分、小节，以及需要涵盖的关键要点。'
    #         f' 研究报告应当详细、信息丰富、深入，且不少于 {total_words} 字。'
    #         ' 请使用合适的 Markdown 语法来格式化大纲，以确保可读性。'
    #         ' 在适当的地方考虑使用 Markdown 表格和其他格式化特性，以增强信息的呈现效果。'
    #     )

        return (
            f'### 具体要求：\n'
            f'- 输出语言：{language}\n'
            f'- 格式：严格使用 **Markdown** 语法（例如 `#` 一级标题，`##` 二级标题，`###` 三级标题）。\n'
            f'- 大纲必须包含：\n'
            f'  * 报告的主要部分（一级标题）\n'
            f'  * 各部分下的子章节（二级/三级标题）\n'
            f'  * 每个子章节需要覆盖的关键要点（列表或简短说明）\n'
            f'- 字数：整体不少于 {total_words} 字（包括大纲和各部分的简要说明）。\n'
            f'- 风格：详细、信息丰富、逻辑清晰，体现深入的分析。\n'
            f'- 在适当位置可使用 **Markdown 表格或项目符号列表**，以增强清晰度和可读性。\n\n'
            f'请输出完整的、符合 Markdown 规范的研究报告大纲。'
            f'请基于围绕主题或问题："{question}"，为以下信息生成一份**研究报告大纲**: 。\n\n"{context}"'

        )

    @staticmethod
    def generate_deep_research_prompt(
        question: str,
        context: str,
        report_source: str,
        report_format="apa",
        tone=None,
        total_words=2000,
        language: str = "english"
    ):
        reference_prompt = ""
        if report_source == ReportSource.Web.value:
            reference_prompt = f"""
        你必须在报告末尾写出所有使用过的来源网址作为参考文献，并确保不要重复，每个来源仅保留一次。
        每个网址都应使用超链接格式：[网站名称](url)
        此外，你必须在报告正文中凡是引用相关网址的地方加入超链接：

        示例：Author, A. A. (Year, Month Date). Title of web page. Website Name. [网站名称](url)
        """
        else:
            reference_prompt = f"""
        你必须在报告末尾写出所有使用过的来源文档名称作为参考文献，并确保不要重复，每个文档仅保留一次。
        """

        tone_prompt = f"请用{tone.value}的语气撰写报告。" if tone else ""

        return f"""
        请基于以下分层研究得到的信息与引文, 字数不少于 {total_words}：
        撰写一份全面的研究报告来回答问题：“{question}”
         报告应当：
        1. 综合多个研究深度层级的信息
        2. 融合不同研究分支的发现
        3. 以连贯叙事从基础见解推进到高级洞见
        4. 全文保持正确的来源引用
        5. 结构清晰，包含明确的章节与小节
        6. 最低字数为 {total_words}
        7. 遵循 {report_format} 格式并使用 Markdown 语法
        8. 在呈现比较数据、统计或结构化信息时，使用 Markdown 表格、列表等格式化方式

        附加要求：
        - 优先呈现来自更深研究层级的洞见
        - 突出不同研究分支之间的关联
        - 包含相关统计、数据与具体示例
        - 你必须基于给定信息形成明确且有效的观点，不得使用笼统或空洞的结论
        - 必须优先考虑来源的相关性、可靠性与重要性；可信来源优先于低质量来源
        - 在可信前提下，优先采用较新的文章
        - 文内引用须符合 {report_format} 要求，并在引用的句子或段落末尾以 Markdown 超链接形式标注，例如：([文内引用](url))
        - {tone_prompt}
        - 使用 {language} 写作

        {reference_prompt}

        请撰写一份深入、充分论证的报告，将所有收集到的信息整合为一致的整体。
        假设当前日期为 {datetime.now(timezone.utc).strftime('%B %d, %Y')}。
        信息与引文：
        \"{context}\"
        """

    @staticmethod
    def auto_agent_instructions():
        return """
        这个任务涉及对给定主题进行研究，无论其复杂性如何，或者是否存在明确答案。研究由特定的服务器执行，该服务器由其类型和角色定义，每种服务器需要不同的指令。
        代理 (Agent)
        服务器的选择取决于主题的领域以及可以用于研究该主题的具体服务器名称。代理根据其专业领域进行分类，每种服务器类型都与一个对应的表情符号关联。
        无论给出什么问题，都要按以下格式进行回答，这一点是最重要的

        示例:
        任务: "我应该投资苹果公司的股票吗？"
        回答:
        {
            "server": "💰 金融代理",
            "agent_role_prompt": "你是一名经验丰富的金融分析 AI 助手。你的主要目标是基于所提供的数据和趋势，撰写全面、敏锐、公正、条理清晰的金融报告。"
        }
        任务: "转售球鞋会成为一种盈利方式吗？"
        回答:
        {
            "server": "📈 商业分析代理",
            "agent_role_prompt": "你是一名资深的商业分析 AI 助手。你的主要目标是基于提供的商业数据、市场趋势和战略分析，撰写全面、深刻、公正、系统化的商业报告。"
        }
        任务: "特拉维夫最有趣的景点有哪些？"
        回答:
        {
            "server": "🌍 旅行代理",
            "agent_role_prompt": "你是一名见多识广的 AI 导游助手。你的主要目标是根据给定的地点，撰写引人入胜、深刻、公正且结构良好的旅行报告，包括历史、景点和文化见解。"
        }
        """

    @staticmethod
    def generate_summary_prompt(query, data):
        """Generates the summary prompt for the given question and text.
        Args: question (str): The question to generate the summary prompt for
                text (str): The text to generate the summary prompt for
        Returns: str: The summary prompt for the given question and text
        """

        return (
            f'{data}\n 请根据以上文本，围绕以下任务或问题进行总结: "{query}"。\n '
            f"如果文本无法回答该问题，必须对文本进行简要总结。\n "
            f"在总结中请包含所有事实性信息，如数字、统计数据、引文等（如果有）。 "
        )

    @staticmethod
    def pretty_print_docs(docs: list[Document], top_n: int | None = None) -> str:
        """Compress the list of documents into a context string"""
        return "\n".join(
            f"来源: {d.metadata.get('source')}\n"
            f"标题: {d.metadata.get('title')}\n"
            f"内容: {d.page_content}\n"
            for i, d in enumerate(docs)
            if top_n is None or i < top_n
        )

    @staticmethod
    def join_local_web_documents(docs_context: str, web_context: str) -> str:
        """Joins local web documents with context scraped from the internet"""
        return f"来自本地文档的上下文: {docs_context}\n\n来自网络来源的上下文: {web_context}"


    ################################################################################################

    # DETAILED REPORT PROMPTS

    @staticmethod
    def generate_subtopics_prompt() -> str:
        return """
        给定内容:

        {task}

        - 构建一个子主题列表，这些子主题将作为生成该主题报告文档的标题。
        - 若给定内容已经是大纲，请重点、主要参考这些内容形成主题与子主题列表
        - 若给定内容只是一个主题，请参考研究数据形成主题与子主题列表
        - 这些是可能的子主题列表: {subtopics}。
        - 子主题中不得有重复项。
        - 子主题数量最多限制为 {max_subtopics} 个。
        - 最后，请根据其任务相关性，对子主题进行排序，使其以合理且有意义的顺序呈现，适合用于详细报告。

        "重要提醒!":
        - 每个子主题必须仅与主要主题和提供的研究数据相关！
        
        研究数据:

        {data}

        {format_instructions}
        """

    @staticmethod
    def generate_subtopic_report_prompt(
        current_subtopic,
        existing_headers: list,
        relevant_written_contents: list,
        main_topic: str,
        context,
        report_format: str = "apa",
        max_subsections=5,
        total_words=800,
        tone: Tone = Tone.Objective,
        language: str = "english",
    ) -> str:
        return f"""
        主要主题与子主题 (Main Topic and Subtopic):
        基于最新可用信息，撰写一份关于子主题 {current_subtopic} 的详细报告，该子主题属于主要主题 {main_topic}。
        你必须将子章节数量限制在最多 {max_subsections} 个。
        - 报告长度不得少于 {total_words} 字
        - 报告长度不得少于 {total_words} 字
        - 报告长度不得少于 {total_words} 字
        内容聚焦 (Content Focus):
        - 报告应当围绕问题展开，结构清晰、信息丰富、深入，并在可能时包含事实和数字。
        - 使用 Markdown 语法，并遵循 {report_format.upper()} 格式。
        - 在呈现数据、比较或结构化信息时，使用 Markdown 表格以增强可读性。

        重要提示：内容与章节唯一性 (IMPORTANT: Content and Sections Uniqueness):
        - 本部分要求至关重要，必须确保生成的内容独特，且不与已有报告重叠。
        - 在撰写新的子章节之前，请仔细审阅下方提供的已有标题和已写内容。
        - 避免撰写已经在现有内容中涵盖的主题。
        - 不得使用已有标题作为新的子章节标题。
        - 不得重复任何已写过的信息或其近似变体，以避免重复。
        - 若包含嵌套子章节，必须确保其内容独特，且不与现有内容重复。
        - 确保你的内容完全新颖，不与之前子主题报告中的任何信息重叠。

        "已有子主题报告 (Existing Subtopic Reports)":
        - 已有子主题报告及其章节标题:

            {existing_headers}

        - 来自之前子主题报告的已写内容:

            {relevant_written_contents}

        "结构与格式 (Structure and Formatting)":
        - 由于此子报告将作为更大报告的一部分，请仅包含正文，按适当子主题划分，不要包含引言或结论部分。
        - 在正文中引用来源时，必须添加 Markdown 超链接。例如：

            ### Section Header

            示例文本 ([文内引用](url))。

        - 使用 H2 作为子主题标题 (##)，使用 H3 作为子章节 (###)。
        - 使用较小的 Markdown 标题（如 H2 或 H3）来组织内容，不要使用最大标题 (H1)，因为 H1 将用于整体报告标题。
        - 将你的内容组织成与已有报告互补但不重叠的独立章节。
        - 如果你的报告中新增的子章节与现有子章节相似或相同，必须明确指出新内容与现有内容的差异。例如：

            ### 新标题 (类似于现有标题)

            虽然之前的章节讨论了 [主题A]，本节将探讨 [主题B]。

        "日期 (Date)":
        如有需要，请假设当前日期为 {datetime.now(timezone.utc).strftime('%B %d, %Y')}。

        "重要提醒 (IMPORTANT!)":
        - 你必须使用以下语言撰写报告: {language}。
        - 内容必须聚焦于主要主题！你必须排除所有无关信息！
        - 报告中不得包含引言、结论、摘要或参考文献部分。
        - 你必须使用 {report_format.upper()} 格式的文内引用，并在句子或段落末尾添加 Markdown 超链接，如下所示: ([文内引用](url))。
        - 如果新增子章节与已有子章节类似或相同，必须在报告中明确指出两者的差异。
        - 报告长度不得少于 {total_words} 字。
        - 报告整体必须保持 {tone.value} 的语气。

        禁止添加结论部分。
        
        上下文 (Context):
        "{context}"
        """

    @staticmethod
    def generate_draft_titles_prompt(
        current_subtopic: str,
        main_topic: str,
        context: str,
        max_subsections: int = 5
    ) -> str:
        return f"""
        "上下文 (Context)":
        "{context}"

        "主要主题与子主题 (Main Topic and Subtopic)":
        基于最新可用信息，为主要主题 {main_topic} 下的子主题 {current_subtopic} 构建一份详细报告的草稿章节标题。

        "任务 (Task)":
        1. 为子主题报告创建一个草稿章节标题列表。
        2. 每个标题应简洁明了，并与子主题相关。
        3. 标题不能过于宏观，需足够具体以涵盖子主题的主要方面。
        4. 使用 Markdown 语法书写标题，采用 H3 (###)，因为 H1 和 H2 将用于更大报告的标题。
        5. 确保标题涵盖子主题的主要方面。

        "结构与格式 (Structure and Formatting)":
        请以列表形式提供草稿标题，使用 Markdown 语法，例如：

        ### 标题1
        ### 标题2
        ### 标题3

        "重要提醒 (IMPORTANT!)":
        - 内容必须聚焦于主要主题！必须排除所有无关信息！
        - 不得包含引言、结论、摘要或参考文献部分。
        - 仅专注于创建标题，而不是撰写正文内容。
        """

    @staticmethod
    def generate_report_introduction(question: str, research_summary: str = "", language: str = "english", report_format: str = "apa") -> str:
        return f"""{research_summary}\n
Using the above latest information, Prepare a detailed report introduction on the topic -- {question}.
- The introduction should be succinct, well-structured, informative with markdown syntax.
- As this introduction will be part of a larger report, do NOT include any other sections, which are generally present in a report.
- The introduction should be preceded by an H1 heading with a suitable topic for the entire report.
- You must use in-text citation references in {report_format.upper()} format and make it with markdown hyperlink placed at the end of the sentence or paragraph that references them like this: ([in-text citation](url)).
Assume that the current date is {datetime.now(timezone.utc).strftime('%B %d, %Y')} if required.
- The output must be in {language} language.
"""


    @staticmethod
    def generate_report_conclusion(query: str, report_content: str, language: str = "english", report_format: str = "apa") -> str:
        prompt = f"""
            请根据以下研究报告和研究任务，撰写一个简明的结论，总结主要发现及其意义：

            研究任务: {query}

            研究报告: {report_content}

            你的结论应当：
            1. 回顾研究的主要观点
            2. 突出最重要的发现
            3. 讨论这些发现的意义或后续步骤
            4. 长度大约为 2-3 段

            如果报告末尾没有写“## Conclusion”章节标题，请在你的结论开头添加该标题。
            你必须使用 {report_format.upper()} 格式的文内引用，并在句子或段落末尾以 Markdown 超链接的形式添加引用，例如: ([文内引用](url))。

            重要提示: 整个结论必须用 {language} 语言撰写。

            请撰写结论:
            """

        return prompt

    @staticmethod
    def generate_pipeline_plan_prompt() -> str:
        return r"""
    你是资深数据与可视化工程师。给你一份“需求说明”，请输出一份**完整的分析流水线计划**（从数据加载→预处理→建模/评估→可视化/表格导出），
    用于后续自动生成 Jupyter Notebook 代码。注意：本次只做“规划”，**不输出任何代码**。

    【输入】
    - 需求说明与数据样例（user_requirement）：{user_requirement}
    - 数据路径（data_path）：{data_path}
    - 允许使用的库（allowed_libs）：{allowed_libs}   # 只能使用这些库；禁止网络访问与 pip 安装
    - 输出根目录（output_dir）：{output_dir}         # e.g. /.../artifacts
    - 图表规范（figure_standards）：{figure_standards} # 可为空；若为空用合理默认
    - 表格规范（table_standards）：{table_standards}   # 可为空；若为空用合理默认

    【总体要求】
    1) 产出一个**有序的代码流水线**（pipeline）。每个步骤必须清晰说明：做什么、输入/输出是什么、将生成哪些**图/表/指标**。
    2) 只做规划，不生成代码；后续会按步骤逐一生成并执行代码。
    3) 每个步骤必须：
       - 具名 `id`（如 step_01）与 `name`
       - `objective`：这一小步要完成的目标
       - `inputs`：期望的数据输入（文件路径/列名/依赖上一步的中间结果名）
       - `ops`：要执行的操作（算法/统计检验/特征工程/可视化类型）
       - `artifacts`：明确列出要生成的**文件清单**（带**规范化文件名**）
           - 图像：{output_dir}/figures/id__<slug>.png
           - 表格：{output_dir}/tables/id__<slug>.csv（utf-8-sig）
           - 指标：以 JSON 行或 CSV 形式写入 {output_dir}/metrics/id__metrics.jsonl 或 .csv
       - `checks`：基本验证/健壮性检查（列名检测、缺失值策略、随机种子设定等）
       - `notes`：任何假设/默认值/潜在风险
    4) 规划中**统一约束**：
       - 仅使用 {allowed_libs}；不得引用未列出的第三方库；不得网络访问；不得删除或改写 {output_dir} 外的文件。
       - 统一设定随机种子保证可复现（如 numpy.random.seed(42) / torch.manual_seed(42)）。
       - 图表遵循：{figure_standards}；表格遵循：{table_standards}（若为空请给出合理默认并在 notes 里声明）。
       - 文件命名必须**确定且可预测**，严禁临时随机名；统一使用小写、短横线或下划线。
    5) 若需求信息不全，请做**最小必要假设**，并在 `notes` 中清晰标注。

    【输出格式（严格 JSON，不要多余解释；遵守 format_instructions）】
    {format_instructions}

    # Schema（仅示例，真实格式以 format_instructions 为准）:
    # {{
    #   "settings": {{
    #     "random_seed": 42,
    #     "data_sources": ["./data/train.csv", "./data/test.csv"],
    #     "key_columns": ["id","group","label","feature_1","feature_2"]
    #   }},
    #   "pipeline": [
    #     {{
    #       "id": "step_01",
    #       "name": "数据加载与基本检查",
    #       "objective": "加载数据并做列名/缺失情况检查，输出清洗后的数据文件与缺失统计表",
    #       "inputs": ["./data/train.csv"],
    #       "ops": ["read_csv","basic_profile","missing_stats","type_casting"],
    #       "artifacts": {{
    #         "tables": [
    #           "{{output_dir}}/tables/step_01__missing_summary.csv"
    #         ],
    #         "figures": [
    #           "{{output_dir}}/figures/step_01__missing_heatmap.png"
    #         ],
    #         "metrics": [
    #           "{{output_dir}}/metrics/step_01__profile.jsonl"
    #         ]
    #       }},
    #       "checks": ["ensure columns exist","handle missing with strategy=median/most_frequent","seed=42"],
    #       "notes": "如果某列不存在，则跳过并在 metrics 中记录"
    #     }},
    #     {{
    #       "id": "step_02",
    #       "name": "建模与评估（示例：二分类）",
    #       "objective": "训练模型并计算 AUC/ROC/PR，输出 ROC/PR 图与指标表",
    #       "inputs": ["cleaned dataframe from step_01"],
    #       "ops": ["train_test_split","standardize","logistic_regression","roc_curve","pr_curve","auc"],
    #       "artifacts": {{
    #         "tables": ["{{output_dir}}/tables/step_02__metrics.csv"],
    #         "figures": [
    #           "{{output_dir}}/figures/step_02__roc.png",
    #           "{{output_dir}}/figures/step_02__pr.png"
    #         ],
    #         "metrics": ["{{output_dir}}/metrics/step_02__metrics.jsonl"]
    #       }},
    #       "checks": ["stratify by label","fix random_state=42","robust scaler if heavy tails"],
    #       "notes": "若样本不平衡，补充 PR 曲线与 class_weight"
    #     }}
    #   ]
    # }}
    """

    @staticmethod
    def generate_code_prompt() -> str:
        # 仅返回“单个 Jupyter Cell 的 Python 代码” —— 禁止解释性文字
        # 注意：模板中出现的 { 和 } 都是 PromptTemplate 的变量占位符；示例 JSON/代码块中的花括号需用双花括号转义。
        return r"""
    你是资深 Python 数据与可视化工程师。请为下面这个“步骤计划（step）”生成**一段可直接放入 Jupyter Notebook 单元格执行的 Python 代码**。
    
    【目标模式】
    - 只返回**代码本体**（不要任何解释/标注/Markdown），保证这一个 cell 可独立运行。
    
    【上下文输入】
    - step（JSON）：{step_json}
    - plan 概要：{plan_outline}
    - 允许使用的库（只能用这些；严禁网络与 pip 安装）：{allowed_libs}
    - 输出目录：{output_dir}
    - 随机种子：{seed}
    
    【硬性要求】
    1) 代码必须：
       - 顶部导入所有需要的库（仅限 {allowed_libs}），设置随机种子。
       - 读取数据：若 step.inputs 中存在 csv 路径则尝试多编码读取；否则合成小样本数据以不中断。
       - **严格落盘**：
         - 表格：{output_dir}/tables/{{step_id}}__*.csv（UTF-8-SIG）
         - 图像：{output_dir}/figures/{{step_id}}__*.png（savefig 后 plt.close()）
         - 指标：{output_dir}/metrics/{{step_id}}__*.jsonl 或 .csv
       - 健壮性：对缺列/空数据/绘图失败/编码错误等使用 try/except 记录到 metrics 文件，但不中断。
       - 末尾打印一行 SUMMARY（JSON 字符串），内容包含：step_id、生成文件清单、关键统计数字。
    
    2) 禁止：
       - 使用未列出的库、网络请求、pip 安装；
       - 写 {output_dir} 以外的路径；
       - 删除已有产物。
    
    【参考】
    - step.artifacts 给出期望产物名式样；如信息不足，可合理命名但必须以“{{step_id}}__”为前缀。
    
    【仅返回代码】
        """.strip()

    @staticmethod
    def fix_code_prompt() -> str:
        return r"""
    你是资深 Python 工程师。下面是一段上次生成但执行失败的 Jupyter 单元代码，以及错误日志。请在**最小改动**的前提下修补，并返回一段**完整可运行**的单元代码（仅代码，不要解释）。

    【上下文】
    - step（JSON）：{step_json}
    - plan 概要：{plan_outline}
    - 允许使用的库：{allowed_libs}
    - 输出目录：{output_dir}
    - 随机种子：{seed}
    - 上一次代码：{prev_code}
    - 错误日志：{error_text}
    【硬性要求】
    1) 仅用 {allowed_libs}，禁止网络 & pip 安装。
    2) 路径限制：所有产物写入 {output_dir}/{{tables|figures|metrics}}，文件名以“{{step_id}}__”为前缀。
    3) 健壮性：对缺列/空数据/导入失败/编码问题/绘图失败等用 try/except 兜底，并把错误 append 写入 metrics（jsonl）。
    4) 成功执行后 `print` 一行 SUMMARY（JSON 字符串），包含 step_id、产物清单、关键指标。
    5) 返回**完整代码**（单 cell），不要解释性文字。
    
    【提示】
    - 若错误为“缺少第三方库/算法不被允许”，请替换为被允许的等价实现（如 Prophet→ARIMA，XGBoost→RandomForest）。
    - 若 CSV 读取失败，尝试多编码；仍失败则造小样本以不中断。
    
    【仅返回代码】
        """.strip()

    @staticmethod
    def revise_plan_prompt() -> str:
        return r"""
    你是高级数据工程负责人。当前步骤经过多次修补仍失败，请审视“步骤/整体计划”并给出**结构化修订方案**。

    【上下文】
    - 当前 step（JSON）：{step_json}
    - 计划概要：{plan_outline}
    - 允许使用的库（不可越界）：{allowed_libs}
    - 输出目录：{output_dir}
    - 随机种子：{seed}
    - 最新错误日志：{error_text}
    - 最近一次失败的代码（供参考；可不使用）：{prev_code}
    
    【修订原则】
    1) 若失败因“库不允许/不可用”，用被允许方案替换（如 Prophet→ARIMA；XGBoost→RandomForest；LSTM→跳过或改传统模型）。
    2) 若目标产物不合理或无法保证，允许**收紧 artifacts**（例如减少绘图种类、表格字段），但需保留最小可验证产物。
    3) 保持下游步骤可衔接；如必要，更新后续步骤的 inputs/ops/产物前缀。
    
    【输出格式（严格 JSON；不要代码、不要多余文本）】
    - 修订当前步骤：  
      {{
        "kind": "step",
        "step": {{ ... 新的 step JSON ... }}
      }}
    - 或修订整体计划：  
      {{
        "kind": "plan",
        "plan": {{ ... 新的 plan JSON ... }}
      }}
    - （可选）若直接给出稳定可运行的替代代码：  
      {{
        "kind": "code",
        "code": "<单 cell 代码>"
      }}
    
    （注意：三种返回三选一；严格 JSON，不能混合或添加解释）
        """.strip()


class GranitePromptFamily(PromptFamily):
    """Prompts for IBM's granite models"""


    def _get_granite_class(self) -> type[PromptFamily]:
        """Get the right granite prompt family based on the version number"""
        if "3.3" in self.cfg.smart_llm:
            return Granite33PromptFamily
        if "3" in self.cfg.smart_llm:
            return Granite3PromptFamily
        # If not a known version, return the default
        return PromptFamily

    def pretty_print_docs(self, *args, **kwargs) -> str:
        return self._get_granite_class().pretty_print_docs(*args, **kwargs)

    def join_local_web_documents(self, *args, **kwargs) -> str:
        return self._get_granite_class().join_local_web_documents(*args, **kwargs)

## Factory ######################################################################

# This is the function signature for the various prompt generator functions
PROMPT_GENERATOR = Callable[
    [
        str,        # question
        str,        # context
        str,        # report_source
        str,        # report_format
        str | None, # tone
        int,        # total_words
        str,        # language
    ],
    str,
]

report_type_mapping = {
    ReportType.ResearchReport.value: "generate_report_prompt",
    ReportType.ResourceReport.value: "generate_resource_report_prompt",
    ReportType.OutlineReport.value: "generate_outline_report_prompt",
    ReportType.CustomReport.value: "generate_custom_report_prompt",
    ReportType.SubtopicReport.value: "generate_subtopic_report_prompt",
    ReportType.DeepResearch.value: "generate_deep_research_prompt",
}


def get_prompt_by_report_type(
    report_type: str,
    prompt_family: type[PromptFamily] | PromptFamily,
):
    prompt_by_type = getattr(prompt_family, report_type_mapping.get(report_type, ""), None)
    default_report_type = ReportType.ResearchReport.value
    if not prompt_by_type:
        warnings.warn(
            f"Invalid report type: {report_type}.\n"
            f"Please use one of the following: {', '.join([enum_value for enum_value in report_type_mapping.keys()])}\n"
            f"Using default report type: {default_report_type} prompt.",
            UserWarning,
        )
        prompt_by_type = getattr(prompt_family, report_type_mapping.get(default_report_type))
    return prompt_by_type


prompt_family_mapping = {
    PromptFamilyEnum.Default.value: PromptFamily,
    PromptFamilyEnum.Granite.value: GranitePromptFamily,
    PromptFamilyEnum.Granite3.value: Granite3PromptFamily,
    PromptFamilyEnum.Granite31.value: Granite3PromptFamily,
    PromptFamilyEnum.Granite32.value: Granite3PromptFamily,
    PromptFamilyEnum.Granite33.value: Granite33PromptFamily,
}


def get_prompt_family(
    prompt_family_name: PromptFamilyEnum | str, config: Config,
) -> PromptFamily:
    if isinstance(prompt_family_name, PromptFamilyEnum):
        prompt_family_name = prompt_family_name.value
    if prompt_family := prompt_family_mapping.get(prompt_family_name):
        return prompt_family(config)
    warnings.warn(
        f"Invalid prompt family: {prompt_family_name}.\n"
        f"Please use one of the following: {', '.join([enum_value for enum_value in prompt_family_mapping.keys()])}\n"
        f"Using default prompt family: {PromptFamilyEnum.Default.value} prompt.",
        UserWarning,
    )
    return PromptFamily()
