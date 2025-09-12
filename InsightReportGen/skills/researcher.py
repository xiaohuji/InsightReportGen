# import asyncio
# import random
# import logging
# import os
# from ..actions.utils import stream_output
# from ..actions.query_processing import plan_research_outline, get_search_results
# from ..document import DocumentLoader, OnlineDocumentLoader, LangChainDocumentLoader
# from ..utils.enum import ReportSource, ReportType
# from ..utils.logging_config import get_json_handler
# from ..actions.agent_creator import choose_agent
#
#
# class ResearchConductor:
#     """Manages and coordinates the research process."""
#
#     def __init__(self, researcher):
#         self.researcher = researcher
#         self.logger = logging.getLogger('research')
#         self.json_handler = get_json_handler()
#         # Add cache for MCP results to avoid redundant calls
#         self._mcp_results_cache = None
#         # Track MCP query count for balanced mode
#         self._mcp_query_count = 0
#
#     async def plan_research(self, query, query_domains=None):
#         """Gets the sub-queries from the query
#         Args:
#             query: original query
#         Returns:
#             List of queries
#         """
#         await stream_output(
#             "logs",
#             "planning_research",
#             f"🌐 Browsing the web to learn more about the task: {query}...",
#             self.researcher.websocket,
#         )
#
#         search_results = await get_search_results(query, self.researcher.retrievers[0], query_domains, researcher=self.researcher)
#         self.logger.info(f"Initial search results obtained: {len(search_results)} results")
#
#         await stream_output(
#             "logs",
#             "planning_research",
#             f"🤔 Planning the research strategy and subtasks...",
#             self.researcher.websocket,
#         )
#
#         retriever_names = [r.__name__ for r in self.researcher.retrievers]
#         # Remove duplicate logging - this will be logged once in conduct_research instead
#
#         outline = await plan_research_outline(
#             query=query,
#             search_results=search_results,
#             agent_role_prompt=self.researcher.role,
#             cfg=self.researcher.cfg,
#             parent_query=self.researcher.parent_query,
#             report_type=self.researcher.report_type,
#             cost_callback=self.researcher.add_costs,
#             retriever_names=retriever_names,  # Pass retriever names for MCP optimization
#             **self.researcher.kwargs
#         )
#         self.logger.info(f"Research outline planned: {outline}")
#         return outline
#
#     async def conduct_research(self):
#         """Runs the GPT Researcher to conduct research"""
#         if self.json_handler:
#             self.json_handler.update_content("query", self.researcher.query)
#
#         self.logger.info(f"Starting research for query: {self.researcher.query}")
#
#         # Log active retrievers once at the start of research
#         retriever_names = [r.__name__ for r in self.researcher.retrievers]
#         self.logger.info(f"Active retrievers: {retriever_names}")
#
#         # Reset visited_urls and source_urls at the start of each research task
#         self.researcher.visited_urls.clear()
#         research_data = []
#
#         if self.researcher.verbose:
#             await stream_output(
#                 "logs",
#                 "starting_research",
#                 f"🔍 Starting the research task for '{self.researcher.query}'...",
#                 self.researcher.websocket,
#             )
#             await stream_output(
#                 "logs",
#                 "agent_generated",
#                 self.researcher.agent,
#                 self.researcher.websocket
#             )
#
#         # Choose agent and role if not already defined
#         if not (self.researcher.agent and self.researcher.role):
#             self.researcher.agent, self.researcher.role = await choose_agent(
#                 query=self.researcher.query,
#                 cfg=self.researcher.cfg,
#                 parent_query=self.researcher.parent_query,
#                 cost_callback=self.researcher.add_costs,
#                 headers=self.researcher.headers,
#                 prompt_family=self.researcher.prompt_family
#             )
#
#         # Check if MCP retrievers are configured
#         has_mcp_retriever = any("mcpretriever" in r.__name__.lower() for r in self.researcher.retrievers)
#         if has_mcp_retriever:
#             self.logger.info("MCP retrievers configured and will be used with standard research flow")
#
#         # Conduct research based on the source type
#         if self.researcher.source_urls:
#             self.logger.info("Using provided source URLs")
#             research_data = await self._get_context_by_urls(self.researcher.source_urls)
#             if research_data and len(research_data) == 0 and self.researcher.verbose:
#                 await stream_output(
#                     "logs",
#                     "answering_from_memory",
#                     f"🧐 I was unable to find relevant context in the provided sources...",
#                     self.researcher.websocket,
#                 )
#             if self.researcher.complement_source_urls:
#                 self.logger.info("Complementing with web search")
#                 additional_research = await self._get_context_by_web_search(self.researcher.query, [], self.researcher.query_domains)
#                 research_data += ' '.join(additional_research)
#         elif self.researcher.report_source == ReportSource.Web.value:
#             self.logger.info("Using web search with all configured retrievers")
#             research_data = await self._get_context_by_web_search(self.researcher.query, [], self.researcher.query_domains)
#         elif self.researcher.report_source == ReportSource.Local.value:
#             self.logger.info("Using local search")
#             document_data = await DocumentLoader(self.researcher.cfg.doc_path).load()
#             self.logger.info(f"Loaded {len(document_data)} documents")
#             if self.researcher.vector_store:
#                 self.researcher.vector_store.load(document_data)
#
#             research_data = await self._get_context_by_web_search(self.researcher.query, document_data, self.researcher.query_domains)
#         # Hybrid search including both local documents and web sources
#         elif self.researcher.report_source == ReportSource.Hybrid.value:
#             if self.researcher.document_urls:
#                 document_data = await OnlineDocumentLoader(self.researcher.document_urls).load()
#             else:
#                 document_data = await DocumentLoader(self.researcher.cfg.doc_path).load()
#             if self.researcher.vector_store:
#                 self.researcher.vector_store.load(document_data)
#             docs_context = await self._get_context_by_web_search(self.researcher.query, document_data, self.researcher.query_domains)
#             web_context = await self._get_context_by_web_search(self.researcher.query, [], self.researcher.query_domains)
#             research_data = self.researcher.prompt_family.join_local_web_documents(docs_context, web_context)
#         elif self.researcher.report_source == ReportSource.Azure.value:
#             from ..document.azure_document_loader import AzureDocumentLoader
#             azure_loader = AzureDocumentLoader(
#                 container_name=os.getenv("AZURE_CONTAINER_NAME"),
#                 connection_string=os.getenv("AZURE_CONNECTION_STRING")
#             )
#             azure_files = await azure_loader.load()
#             document_data = await DocumentLoader(azure_files).load()  # Reuse existing loader
#             research_data = await self._get_context_by_web_search(self.researcher.query, document_data)
#
#         elif self.researcher.report_source == ReportSource.LangChainDocuments.value:
#             langchain_documents_data = await LangChainDocumentLoader(
#                 self.researcher.documents
#             ).load()
#             if self.researcher.vector_store:
#                 self.researcher.vector_store.load(langchain_documents_data)
#             research_data = await self._get_context_by_web_search(
#                 self.researcher.query, langchain_documents_data, self.researcher.query_domains
#             )
#         elif self.researcher.report_source == ReportSource.LangChainVectorStore.value:
#             research_data = await self._get_context_by_vectorstore(self.researcher.query, self.researcher.vector_store_filter)
#
#         # Rank and curate the sources
#         self.researcher.context = research_data
#         if self.researcher.cfg.curate_sources:
#             self.logger.info("Curating sources")
#             self.researcher.context = await self.researcher.source_curator.curate_sources(research_data)
#
#         if self.researcher.verbose:
#             await stream_output(
#                 "logs",
#                 "research_step_finalized",
#                 f"Finalized research step.\n💸 Total Research Costs: ${self.researcher.get_costs()}",
#                 self.researcher.websocket,
#             )
#             if self.json_handler:
#                 self.json_handler.update_content("costs", self.researcher.get_costs())
#                 self.json_handler.update_content("context", self.researcher.context)
#
#         self.logger.info(f"Research completed. Context size: {len(str(self.researcher.context))}")
#         return self.researcher.context
#
#     # async def _get_context_by_urls(self, urls):
#     #     """Scrapes and compresses the context from the given urls"""
#     #     self.logger.info(f"Getting context from URLs: {urls}")
#     #
#     #     new_search_urls = await self._get_new_urls(urls)
#     #     self.logger.info(f"New URLs to process: {new_search_urls}")
#     #
#     #     scraped_content = await self.researcher.scraper_manager.browse_urls(new_search_urls)
#     #     self.logger.info(f"Scraped content from {len(scraped_content)} URLs")
#     #
#     #     if self.researcher.vector_store:
#     #         self.researcher.vector_store.load(scraped_content)
#     #
#     #     context = await self.researcher.context_manager.get_similar_content_by_query(
#     #         self.researcher.query, scraped_content
#     #     )
#     #     return context
#
#     async def _get_context_by_urls(
#             self,
#             urls,
#             *,
#             web_max_chars: int | None = 5000,  # ✅ 仅网页内容长度上限；None 不启用
#             clip_oversize: bool = True,  # ✅ 超长时是丢弃(False)还是截断(True)
#             drop_empty: bool = True  # ✅ 空文本是否丢弃
#     ):
#         """Scrapes and compresses the context from the given urls (web-only path)."""
#         self.logger.info(f"Getting context from URLs: {urls}")
#
#         new_search_urls = await self._get_new_urls(urls)
#         self.logger.info(f"New URLs to process: {new_search_urls}")
#
#         scraped_content = await self.researcher.scraper_manager.browse_urls(new_search_urls)
#         self.logger.info(f"Scraped content from {len(scraped_content)} URLs")
#
#         # ---- 仅对网页抓取到的内容做文本抽取与长度控制 ----
#         def _page_text(p):
#             # 统一抽文本字段；没有就给空
#             return p.get("raw_content") or p.get("content") or p.get("text") or ""
#
#         filtered = []
#         kept, dropped, clipped = 0, 0, 0
#         for p in scraped_content:
#             txt = _page_text(p)
#             if drop_empty and not txt.strip():
#                 dropped += 1
#                 continue
#             if web_max_chars is not None and len(txt) > web_max_chars:
#                 if clip_oversize:
#                     # 截断保留
#                     p = dict(p)  # 复制一份，避免原对象被外部引用
#                     # 回写到常用字段，保持后续流程一致
#                     if "raw_content" in p and p["raw_content"]:
#                         p["raw_content"] = p["raw_content"][:web_max_chars]
#                     elif "content" in p and p["content"]:
#                         p["content"] = p["content"][:web_max_chars]
#                     else:
#                         p["text"] = txt[:web_max_chars]
#                     clipped += 1
#                     kept += 1
#                     filtered.append(p)
#                 else:
#                     # 直接丢弃
#                     dropped += 1
#             else:
#                 kept += 1
#                 filtered.append(p)
#
#         self.logger.info(
#             f"[URL WebLenControl] max_chars={web_max_chars}, kept={kept}, "
#             f"dropped={dropped}, clipped={clipped}, total_in={len(scraped_content)}"
#         )
#
#         # （可选）向量库：只加载经过长度控制后的网页内容
#         if self.researcher.vector_store and filtered:
#             self.researcher.vector_store.load(filtered)
#
#         # 相似度检索只基于过滤后的网页内容
#         context = await self.researcher.context_manager.get_similar_content_by_query(
#             self.researcher.query, filtered
#         )
#         return context
#
#     # Add logging to other methods similarly...
#
#     async def _get_context_by_vectorstore(self, query, filter: dict | None = None):
#         """
#         Generates the context for the research task by searching the vectorstore
#         Returns:
#             context: List of context
#         """
#         self.logger.info(f"Starting vectorstore search for query: {query}")
#         context = []
#         # Generate Sub-Queries including original query
#         sub_queries = await self.plan_research(query)
#         # If this is not part of a sub researcher, add original query to research for better results
#         if self.researcher.report_type != "subtopic_report":
#             sub_queries.append(query)
#
#         if self.researcher.verbose:
#             await stream_output(
#                 "logs",
#                 "subqueries",
#                 f"🗂️  I will conduct my research based on the following queries: {sub_queries}...",
#                 self.researcher.websocket,
#                 True,
#                 sub_queries,
#             )
#
#         # Using asyncio.gather to process the sub_queries asynchronously
#         context = await asyncio.gather(
#             *[
#                 self._process_sub_query_with_vectorstore(sub_query, filter)
#                 for sub_query in sub_queries
#             ]
#         )
#         return context
#
#
#     # async def _get_context_by_web_search(self, query, scraped_data: list | None = None, query_domains: list | None = None):
#     #     """
#     #     Generates the context for the research task by searching the query and scraping the results
#     #     Returns:
#     #         context: List of context
#     #     """
#     #     self.logger.info(f"Starting web search for query: {query}")
#     #
#     #     if scraped_data is None:
#     #         scraped_data = []
#     #     if query_domains is None:
#     #         query_domains = []
#     #
#     #     # **CONFIGURABLE MCP OPTIMIZATION: Control MCP strategy**
#     #     mcp_retrievers = [r for r in self.researcher.retrievers if "mcpretriever" in r.__name__.lower()]
#     #
#     #     # Get MCP strategy configuration
#     #     mcp_strategy = self._get_mcp_strategy()
#     #
#     #     if mcp_retrievers and self._mcp_results_cache is None:
#     #         if mcp_strategy == "disabled":
#     #             # MCP disabled - skip MCP research entirely
#     #             self.logger.info("MCP disabled by strategy, skipping MCP research")
#     #             if self.researcher.verbose:
#     #                 await stream_output(
#     #                     "logs",
#     #                     "mcp_disabled",
#     #                     f"⚡ MCP research disabled by configuration",
#     #                     self.researcher.websocket,
#     #                 )
#     #         elif mcp_strategy == "fast":
#     #             # Fast: Run MCP once with original query
#     #             self.logger.info("MCP fast strategy: Running once with original query")
#     #             if self.researcher.verbose:
#     #                 await stream_output(
#     #                     "logs",
#     #                     "mcp_optimization",
#     #                     f"🚀 MCP Fast: Running once for main query (performance mode)",
#     #                     self.researcher.websocket,
#     #                 )
#     #
#     #             # Execute MCP research once with the original query
#     #             mcp_context = await self._execute_mcp_research_for_queries([query], mcp_retrievers)
#     #             self._mcp_results_cache = mcp_context
#     #             self.logger.info(f"MCP results cached: {len(mcp_context)} total context entries")
#     #         elif mcp_strategy == "deep":
#     #             # Deep: Will run MCP for all queries (original behavior) - defer to per-query execution
#     #             self.logger.info("MCP deep strategy: Will run for all queries")
#     #             if self.researcher.verbose:
#     #                 await stream_output(
#     #                     "logs",
#     #                     "mcp_comprehensive",
#     #                     f"🔍 MCP Deep: Will run for each sub-query (thorough mode)",
#     #                     self.researcher.websocket,
#     #                 )
#     #             # Don't cache - let each sub-query run MCP individually
#     #         else:
#     #             # Unknown strategy - default to fast
#     #             self.logger.warning(f"Unknown MCP strategy '{mcp_strategy}', defaulting to fast")
#     #             mcp_context = await self._execute_mcp_research_for_queries([query], mcp_retrievers)
#     #             self._mcp_results_cache = mcp_context
#     #             self.logger.info(f"MCP results cached: {len(mcp_context)} total context entries")
#     #
#     #     # Generate Sub-Queries including original query
#     #     sub_queries = await self.plan_research(query, query_domains)
#     #     self.logger.info(f"Generated sub-queries: {sub_queries}")
#     #
#     #     # If this is not part of a sub researcher, add original query to research for better results
#     #     if self.researcher.report_type != "subtopic_report":
#     #         sub_queries.append(query)
#     #
#     #     if self.researcher.verbose:
#     #         await stream_output(
#     #             "logs",
#     #             "subqueries",
#     #             f"🗂️ I will conduct my research based on the following queries: {sub_queries}...",
#     #             self.researcher.websocket,
#     #             True,
#     #             sub_queries,
#     #         )
#     #
#     #     # Using asyncio.gather to process the sub_queries asynchronously
#     #     try:
#     #         context = await asyncio.gather(
#     #             *[
#     #                 self._process_sub_query(sub_query, scraped_data, query_domains)
#     #                 for sub_query in sub_queries
#     #             ]
#     #         )
#     #         self.logger.info(f"Gathered context from {len(context)} sub-queries")
#     #         # Filter out empty results and join the context
#     #         context = [c for c in context if c]
#     #         if context:
#     #             combined_context = " ".join(context)
#     #             self.logger.info(f"Combined context size: {len(combined_context)}")
#     #             return combined_context
#     #         return []
#     #     except Exception as e:
#     #         self.logger.error(f"Error during web search: {e}", exc_info=True)
#     #         return []
#
#     async def _get_context_by_web_search(
#             self,
#             query,
#             scraped_data: list | None = None,
#             query_domains: list | None = None,
#             *,
#             web_max_chars: int | None = 5000,  # ✅ 仅对“网页抓取的数据”限长；None 表示不启用
#             max_combined_chars: int | None = 15000  # ✅ 合并后的总长度保险丝；None 表示不启用
#     ):
#         """
#         Generates the context for the research task by searching the query and scraping the results
#
#         Returns:
#             context: str (combined context)
#         """
#         self.logger.info(f"Starting web search for query: {query}")
#
#         if scraped_data is None:
#             scraped_data = []
#         if query_domains is None:
#             query_domains = []
#
#         # ========== 仅对“网页侧 scraped_data”做长度过滤 ==========
#         # 说明：如果你在其它路径传入了本地文档，请不要从这里传，避免被网页限长波及。
#         def _page_text(p):
#             return p.get("raw_content") or p.get("content") or p.get("text") or ""
#
#         if web_max_chars is not None:
#             before = len(scraped_data)
#             scraped_data = [p for p in scraped_data if _page_text(p) and len(_page_text(p)) <= web_max_chars]
#             after = len(scraped_data)
#             self.logger.info(f"[WebLenFilter] web_max_chars={web_max_chars}, kept={after}/{before}")
#
#         # **CONFIGURABLE MCP OPTIMIZATION: Control MCP strategy**
#         mcp_retrievers = [r for r in self.researcher.retrievers if "mcpretriever" in r.__name__.lower()]
#         mcp_strategy = self._get_mcp_strategy()
#
#         if mcp_retrievers and self._mcp_results_cache is None:
#             if mcp_strategy == "disabled":
#                 self.logger.info("MCP disabled by strategy, skipping MCP research")
#                 if self.researcher.verbose:
#                     await stream_output(
#                         "logs", "mcp_disabled",
#                         f"⚡ MCP research disabled by configuration",
#                         self.researcher.websocket,
#                     )
#             elif mcp_strategy == "fast":
#                 self.logger.info("MCP fast strategy: Running once with original query")
#                 if self.researcher.verbose:
#                     await stream_output(
#                         "logs", "mcp_optimization",
#                         f"🚀 MCP Fast: Running once for main query (performance mode)",
#                         self.researcher.websocket,
#                     )
#                 mcp_context = await self._execute_mcp_research_for_queries([query], mcp_retrievers)
#                 self._mcp_results_cache = mcp_context
#                 self.logger.info(f"MCP results cached: {len(mcp_context)} total context entries")
#             elif mcp_strategy == "deep":
#                 self.logger.info("MCP deep strategy: Will run for all queries")
#                 if self.researcher.verbose:
#                     await stream_output(
#                         "logs", "mcp_comprehensive",
#                         f"🔍 MCP Deep: Will run for each sub-query (thorough mode)",
#                         self.researcher.websocket,
#                     )
#             else:
#                 self.logger.warning(f"Unknown MCP strategy '{mcp_strategy}', defaulting to fast")
#                 mcp_context = await self._execute_mcp_research_for_queries([query], mcp_retrievers)
#                 self._mcp_results_cache = mcp_context
#                 self.logger.info(f"MCP results cached: {len(mcp_context)} total context entries")
#
#         # Generate Sub-Queries including original query
#         sub_queries = await self.plan_research(query, query_domains)
#         self.logger.info(f"Generated sub-queries: {sub_queries}")
#
#         if self.researcher.report_type != "subtopic_report":
#             sub_queries.append(query)
#
#         if self.researcher.verbose:
#             await stream_output(
#                 "logs", "subqueries",
#                 f"🗂️ I will conduct my research based on the following queries: {sub_queries}...",
#                 self.researcher.websocket, True, sub_queries,
#             )
#
#         # ========== 并发处理子查询 ==========
#         try:
#             contexts = await asyncio.gather(
#                 *[self._process_sub_query(sub_query, scraped_data, query_domains) for sub_query in sub_queries]
#             )
#             self.logger.info(f"Gathered context from {len(contexts)} sub-queries")
#
#             # 过滤空字符串
#             contexts = [c for c in contexts if c]
#
#             # 保险：对子查询返回文本做轻量截断（仅网页路径）
#             if web_max_chars is not None:
#                 clipped = []
#                 dropped = 0
#                 for c in contexts:
#                     if len(c) > web_max_chars:
#                         clipped.append(c[:web_max_chars])
#                         dropped += (len(c) - web_max_chars)
#                     else:
#                         clipped.append(c)
#                 contexts = clipped
#                 if dropped > 0:
#                     self.logger.info(f"[WebLenClip] Per-subquery clip applied, total dropped chars={dropped}")
#
#             if not contexts:
#                 return []
#
#             combined_context = " ".join(contexts)
#
#             # 合并后再加一道全局保险丝
#             if max_combined_chars is not None and len(combined_context) > max_combined_chars:
#                 self.logger.info(
#                     f"[WebLenFuse] max_combined_chars={max_combined_chars}, "
#                     f"truncating combined from {len(combined_context)}"
#                 )
#                 combined_context = combined_context[:max_combined_chars]
#
#             self.logger.info(f"Combined context size: {len(combined_context)}")
#             return combined_context
#
#         except Exception as e:
#             self.logger.error(f"Error during web search: {e}", exc_info=True)
#             return []
#
#     def _get_mcp_strategy(self) -> str:
#         """
#         Get the MCP strategy configuration.
#
#         Priority:
#         1. Instance-level setting (self.researcher.mcp_strategy)
#         2. Config file setting (self.researcher.cfg.mcp_strategy)
#         3. Default value ("fast")
#
#         Returns:
#             str: MCP strategy
#                 "disabled" = Skip MCP entirely
#                 "fast" = Run MCP once with original query (default)
#                 "deep" = Run MCP for all sub-queries
#         """
#         # Check instance-level setting first
#         if hasattr(self.researcher, 'mcp_strategy') and self.researcher.mcp_strategy is not None:
#             return self.researcher.mcp_strategy
#
#         # Check config setting
#         if hasattr(self.researcher.cfg, 'mcp_strategy'):
#             return self.researcher.cfg.mcp_strategy
#
#         # Default to fast mode
#         return "fast"
#
#     async def _execute_mcp_research_for_queries(self, queries: list, mcp_retrievers: list) -> list:
#         """
#         Execute MCP research for a list of queries.
#
#         Args:
#             queries: List of queries to research
#             mcp_retrievers: List of MCP retriever classes
#
#         Returns:
#             list: Combined MCP context entries from all queries
#         """
#         all_mcp_context = []
#
#         for i, query in enumerate(queries, 1):
#             self.logger.info(f"Executing MCP research for query {i}/{len(queries)}: {query}")
#
#             for retriever in mcp_retrievers:
#                 try:
#                     mcp_results = await self._execute_mcp_research(retriever, query)
#                     if mcp_results:
#                         for result in mcp_results:
#                             content = result.get("body", "")
#                             url = result.get("href", "")
#                             title = result.get("title", "")
#
#                             if content:
#                                 context_entry = {
#                                     "content": content,
#                                     "url": url,
#                                     "title": title,
#                                     "query": query,
#                                     "source_type": "mcp"
#                                 }
#                                 all_mcp_context.append(context_entry)
#
#                         self.logger.info(f"Added {len(mcp_results)} MCP results for query: {query}")
#
#                         if self.researcher.verbose:
#                             await stream_output(
#                                 "logs",
#                                 "mcp_results_cached",
#                                 f"✅ Cached {len(mcp_results)} MCP results from query {i}/{len(queries)}",
#                                 self.researcher.websocket,
#                             )
#                 except Exception as e:
#                     self.logger.error(f"Error in MCP research for query '{query}': {e}")
#                     if self.researcher.verbose:
#                         await stream_output(
#                             "logs",
#                             "mcp_cache_error",
#                             f"⚠️ MCP research error for query {i}, continuing with other sources",
#                             self.researcher.websocket,
#                         )
#
#         return all_mcp_context
#
#     async def _process_sub_query(self, sub_query: str, scraped_data: list = [], query_domains: list = []):
#         """Takes in a sub query and scrapes urls based on it and gathers context."""
#         if self.json_handler:
#             self.json_handler.log_event("sub_query", {
#                 "query": sub_query,
#                 "scraped_data_size": len(scraped_data)
#             })
#
#         if self.researcher.verbose:
#             await stream_output(
#                 "logs",
#                 "running_subquery_research",
#                 f"\n🔍 Running research for '{sub_query}'...",
#                 self.researcher.websocket,
#             )
#
#         try:
#             # Identify MCP retrievers
#             mcp_retrievers = [r for r in self.researcher.retrievers if "mcpretriever" in r.__name__.lower()]
#             non_mcp_retrievers = [r for r in self.researcher.retrievers if "mcpretriever" not in r.__name__.lower()]
#
#             # Initialize context components
#             mcp_context = []
#             web_context = ""
#
#             # Get MCP strategy configuration
#             mcp_strategy = self._get_mcp_strategy()
#
#             # **CONFIGURABLE MCP PROCESSING**
#             if mcp_retrievers:
#                 if mcp_strategy == "disabled":
#                     # MCP disabled - skip entirely
#                     self.logger.info(f"MCP disabled for sub-query: {sub_query}")
#                 elif mcp_strategy == "fast" and self._mcp_results_cache is not None:
#                     # Fast: Use cached results
#                     mcp_context = self._mcp_results_cache.copy()
#
#                     if self.researcher.verbose:
#                         await stream_output(
#                             "logs",
#                             "mcp_cache_reuse",
#                             f"♻️ Reusing cached MCP results ({len(mcp_context)} sources) for: {sub_query}",
#                             self.researcher.websocket,
#                         )
#
#                     self.logger.info(f"Reused {len(mcp_context)} cached MCP results for sub-query: {sub_query}")
#                 elif mcp_strategy == "deep":
#                     # Deep: Run MCP for every sub-query
#                     self.logger.info(f"Running deep MCP research for: {sub_query}")
#                     if self.researcher.verbose:
#                         await stream_output(
#                             "logs",
#                             "mcp_comprehensive_run",
#                             f"🔍 Running deep MCP research for: {sub_query}",
#                             self.researcher.websocket,
#                         )
#
#                     mcp_context = await self._execute_mcp_research_for_queries([sub_query], mcp_retrievers)
#                 else:
#                     # Fallback: if no cache and not deep mode, run MCP for this query
#                     self.logger.warning("MCP cache not available, falling back to per-sub-query execution")
#                     if self.researcher.verbose:
#                         await stream_output(
#                             "logs",
#                             "mcp_fallback",
#                             f"🔌 MCP cache unavailable, running MCP research for: {sub_query}",
#                             self.researcher.websocket,
#                         )
#
#                     mcp_context = await self._execute_mcp_research_for_queries([sub_query], mcp_retrievers)
#
#             # Get web search context using non-MCP retrievers (if no scraped data provided)
#             if not scraped_data:
#                 scraped_data = await self._scrape_data_by_urls(sub_query, query_domains)
#                 self.logger.info(f"Scraped data size: {len(scraped_data)}")
#
#             # Get similar content based on scraped data
#             if scraped_data:
#                 web_context = await self.researcher.context_manager.get_similar_content_by_query(sub_query, scraped_data)
#                 self.logger.info(f"Web content found for sub-query: {len(str(web_context)) if web_context else 0} chars")
#
#             # Combine MCP context with web context intelligently
#             combined_context = self._combine_mcp_and_web_context(mcp_context, web_context, sub_query)
#
#             # Log context combination results
#             if combined_context:
#                 context_length = len(str(combined_context))
#                 self.logger.info(f"Combined context for '{sub_query}': {context_length} chars")
#
#                 if self.researcher.verbose:
#                     mcp_count = len(mcp_context)
#                     web_available = bool(web_context)
#                     cache_used = self._mcp_results_cache is not None and mcp_retrievers and mcp_strategy != "deep"
#                     cache_status = " (cached)" if cache_used else ""
#                     await stream_output(
#                         "logs",
#                         "context_combined",
#                         f"📚 Combined research context: {mcp_count} MCP sources{cache_status}, {'web content' if web_available else 'no web content'}",
#                         self.researcher.websocket,
#                     )
#             else:
#                 self.logger.warning(f"No combined context found for sub-query: {sub_query}")
#                 if self.researcher.verbose:
#                     await stream_output(
#                         "logs",
#                         "subquery_context_not_found",
#                         f"🤷 No content found for '{sub_query}'...",
#                         self.researcher.websocket,
#                     )
#
#             if combined_context and self.json_handler:
#                 self.json_handler.log_event("content_found", {
#                     "sub_query": sub_query,
#                     "content_size": len(str(combined_context)),
#                     "mcp_sources": len(mcp_context),
#                     "web_content": bool(web_context)
#                 })
#
#             return combined_context
#
#         except Exception as e:
#             self.logger.error(f"Error processing sub-query {sub_query}: {e}", exc_info=True)
#             if self.researcher.verbose:
#                 await stream_output(
#                     "logs",
#                     "subquery_error",
#                     f"❌ Error processing '{sub_query}': {str(e)}",
#                     self.researcher.websocket,
#                 )
#             return ""
#
#     async def _execute_mcp_research(self, retriever, query):
#         """
#         Execute MCP research using the new two-stage approach.
#
#         Args:
#             retriever: The MCP retriever class
#             query: The search query
#
#         Returns:
#             list: MCP research results
#         """
#         retriever_name = retriever.__name__
#
#         self.logger.info(f"Executing MCP research with {retriever_name} for query: {query}")
#
#         try:
#             # Instantiate the MCP retriever with proper parameters
#             # Pass the researcher instance (self.researcher) which contains both cfg and mcp_configs
#             retriever_instance = retriever(
#                 query=query,
#                 headers=self.researcher.headers,
#                 query_domains=self.researcher.query_domains,
#                 websocket=self.researcher.websocket,
#                 researcher=self.researcher  # Pass the entire researcher instance
#             )
#
#             if self.researcher.verbose:
#                 await stream_output(
#                     "logs",
#                     "mcp_retrieval_stage1",
#                     f"🧠 Stage 1: Selecting optimal MCP tools for: {query}",
#                     self.researcher.websocket,
#                 )
#
#             # Execute the two-stage MCP search
#             results = retriever_instance.search(
#                 max_results=self.researcher.cfg.max_search_results_per_query
#             )
#
#             if results:
#                 result_count = len(results)
#                 self.logger.info(f"MCP research completed: {result_count} results from {retriever_name}")
#
#                 if self.researcher.verbose:
#                     await stream_output(
#                         "logs",
#                         "mcp_research_complete",
#                         f"🎯 MCP research completed: {result_count} intelligent results obtained",
#                         self.researcher.websocket,
#                     )
#
#                 return results
#             else:
#                 self.logger.info(f"No results returned from MCP research with {retriever_name}")
#                 if self.researcher.verbose:
#                     await stream_output(
#                         "logs",
#                         "mcp_no_results",
#                         f"ℹ️ No relevant information found via MCP for: {query}",
#                         self.researcher.websocket,
#                     )
#                 return []
#
#         except Exception as e:
#             self.logger.error(f"Error in MCP research with {retriever_name}: {str(e)}")
#             if self.researcher.verbose:
#                 await stream_output(
#                     "logs",
#                     "mcp_research_error",
#                     f"⚠️ MCP research error: {str(e)} - continuing with other sources",
#                     self.researcher.websocket,
#                 )
#             return []
#
#     def _combine_mcp_and_web_context(self, mcp_context: list, web_context: str, sub_query: str) -> str:
#         """
#         Intelligently combine MCP and web research context.
#
#         Args:
#             mcp_context: List of MCP context entries
#             web_context: Web research context string
#             sub_query: The sub-query being processed
#
#         Returns:
#             str: Combined context string
#         """
#         combined_parts = []
#
#         # Add web context first if available
#         if web_context and web_context.strip():
#             combined_parts.append(web_context.strip())
#             self.logger.debug(f"Added web context: {len(web_context)} chars")
#
#         # Add MCP context with proper formatting
#         if mcp_context:
#             mcp_formatted = []
#
#             for i, item in enumerate(mcp_context):
#                 content = item.get("content", "")
#                 url = item.get("url", "")
#                 title = item.get("title", f"MCP Result {i+1}")
#
#                 if content and content.strip():
#                     # Create a well-formatted context entry
#                     if url and url != f"mcp://llm_analysis":
#                         citation = f"\n\n*Source: {title} ({url})*"
#                     else:
#                         citation = f"\n\n*Source: {title}*"
#
#                     formatted_content = f"{content.strip()}{citation}"
#                     mcp_formatted.append(formatted_content)
#
#             if mcp_formatted:
#                 # Join MCP results with clear separation
#                 mcp_section = "\n\n---\n\n".join(mcp_formatted)
#                 combined_parts.append(mcp_section)
#                 self.logger.debug(f"Added {len(mcp_context)} MCP context entries")
#
#         # Combine all parts
#         if combined_parts:
#             final_context = "\n\n".join(combined_parts)
#             self.logger.info(f"Combined context for '{sub_query}': {len(final_context)} total chars")
#             return final_context
#         else:
#             self.logger.warning(f"No context to combine for sub-query: {sub_query}")
#             return ""
#
#     async def _process_sub_query_with_vectorstore(self, sub_query: str, filter: dict | None = None):
#         """Takes in a sub query and gathers context from the user provided vector store
#
#         Args:
#             sub_query (str): The sub-query generated from the original query
#
#         Returns:
#             str: The context gathered from search
#         """
#         if self.researcher.verbose:
#             await stream_output(
#                 "logs",
#                 "running_subquery_with_vectorstore_research",
#                 f"\n🔍 Running research for '{sub_query}'...",
#                 self.researcher.websocket,
#             )
#
#         context = await self.researcher.context_manager.get_similar_content_by_query_with_vectorstore(sub_query, filter)
#
#         return context
#
#     async def _get_new_urls(self, url_set_input):
#         """Gets the new urls from the given url set.
#         Args: url_set_input (set[str]): The url set to get the new urls from
#         Returns: list[str]: The new urls from the given url set
#         """
#
#         new_urls = []
#         for url in url_set_input:
#             if url not in self.researcher.visited_urls:
#                 self.researcher.visited_urls.add(url)
#                 new_urls.append(url)
#                 if self.researcher.verbose:
#                     await stream_output(
#                         "logs",
#                         "added_source_url",
#                         f"✅ Added source url to research: {url}\n",
#                         self.researcher.websocket,
#                         True,
#                         url,
#                     )
#
#         return new_urls
#
#     async def _search_relevant_source_urls(self, query, query_domains: list | None = None):
#         new_search_urls = []
#         if query_domains is None:
#             query_domains = []
#
#         # Iterate through the currently set retrievers
#         # This allows the method to work when retrievers are temporarily modified
#         for retriever_class in self.researcher.retrievers:
#             # Skip MCP retrievers as they don't provide URLs for scraping
#             if "mcpretriever" in retriever_class.__name__.lower():
#                 continue
#
#             try:
#                 # Instantiate the retriever with the sub-query
#                 retriever = retriever_class(query, query_domains=query_domains)
#
#                 # Perform the search using the current retriever
#                 search_results = await asyncio.to_thread(
#                     retriever.search, max_results=self.researcher.cfg.max_search_results_per_query
#                 )
#
#                 # Collect new URLs from search results
#                 search_urls = [url.get("href") for url in search_results if url.get("href")]
#                 new_search_urls.extend(search_urls)
#             except Exception as e:
#                 self.logger.error(f"Error searching with {retriever_class.__name__}: {e}")
#
#         # Get unique URLs
#         new_search_urls = await self._get_new_urls(new_search_urls)
#         random.shuffle(new_search_urls)
#
#         return new_search_urls
#
#     async def _scrape_data_by_urls(self, sub_query, query_domains: list | None = None):
#         """
#         Runs a sub-query across multiple retrievers and scrapes the resulting URLs.
#
#         Args:
#             sub_query (str): The sub-query to search for.
#
#         Returns:
#             list: A list of scraped content results.
#         """
#         if query_domains is None:
#             query_domains = []
#
#         new_search_urls = await self._search_relevant_source_urls(sub_query, query_domains)
#
#         # Log the research process if verbose mode is on
#         if self.researcher.verbose:
#             await stream_output(
#                 "logs",
#                 "researching",
#                 f"🤔 Researching for relevant information across multiple sources...\n",
#                 self.researcher.websocket,
#             )
#
#         # Scrape the new URLs
#         scraped_content = await self.researcher.scraper_manager.browse_urls(new_search_urls)
#
#         if self.researcher.vector_store:
#             self.researcher.vector_store.load(scraped_content)
#
#         return scraped_content
#
#     async def _search(self, retriever, query):
#         """
#         Perform a search using the specified retriever.
#
#         Args:
#             retriever: The retriever class to use
#             query: The search query
#
#         Returns:
#             list: Search results
#         """
#         retriever_name = retriever.__name__
#         is_mcp_retriever = "mcpretriever" in retriever_name.lower()
#
#         self.logger.info(f"Searching with {retriever_name} for query: {query}")
#
#         try:
#             # Instantiate the retriever
#             retriever_instance = retriever(
#                 query=query,
#                 headers=self.researcher.headers,
#                 query_domains=self.researcher.query_domains,
#                 websocket=self.researcher.websocket if is_mcp_retriever else None,
#                 researcher=self.researcher if is_mcp_retriever else None
#             )
#
#             # Log MCP server configurations if using MCP retriever
#             if is_mcp_retriever and self.researcher.verbose:
#                 await stream_output(
#                     "logs",
#                     "mcp_retrieval",
#                     f"🔌 Consulting MCP server(s) for information on: {query}",
#                     self.researcher.websocket,
#                 )
#
#             # Perform the search
#             if hasattr(retriever_instance, 'search'):
#                 results = retriever_instance.search(
#                     max_results=self.researcher.cfg.max_search_results_per_query
#                 )
#
#                 # Log result information
#                 if results:
#                     result_count = len(results)
#                     self.logger.info(f"Received {result_count} results from {retriever_name}")
#
#                     # Special logging for MCP retriever
#                     if is_mcp_retriever:
#                         if self.researcher.verbose:
#                             await stream_output(
#                                 "logs",
#                                 "mcp_results",
#                                 f"✓ Retrieved {result_count} results from MCP server",
#                                 self.researcher.websocket,
#                             )
#
#                         # Log result details
#                         for i, result in enumerate(results[:3]):  # Log first 3 results
#                             title = result.get("title", "No title")
#                             url = result.get("href", "No URL")
#                             content_length = len(result.get("body", "")) if result.get("body") else 0
#                             self.logger.info(f"MCP result {i+1}: '{title}' from {url} ({content_length} chars)")
#
#                         if result_count > 3:
#                             self.logger.info(f"... and {result_count - 3} more MCP results")
#                 else:
#                     self.logger.info(f"No results returned from {retriever_name}")
#                     if is_mcp_retriever and self.researcher.verbose:
#                         await stream_output(
#                             "logs",
#                             "mcp_no_results",
#                             f"ℹ️ No relevant information found from MCP server for: {query}",
#                             self.researcher.websocket,
#                         )
#
#                 return results
#             else:
#                 self.logger.error(f"Retriever {retriever_name} does not have a search method")
#                 return []
#         except Exception as e:
#             self.logger.error(f"Error searching with {retriever_name}: {str(e)}")
#             if is_mcp_retriever and self.researcher.verbose:
#                 await stream_output(
#                     "logs",
#                     "mcp_error",
#                     f"❌ Error retrieving information from MCP server: {str(e)}",
#                     self.researcher.websocket,
#                 )
#             return []
#
#     async def _extract_content(self, results):
#         """
#         Extract content from search results using the browser manager.
#
#         Args:
#             results: Search results
#
#         Returns:
#             list: Extracted content
#         """
#         self.logger.info(f"Extracting content from {len(results)} search results")
#
#         # Get the URLs from the search results
#         urls = []
#         for result in results:
#             if isinstance(result, dict) and "href" in result:
#                 urls.append(result["href"])
#
#         # Skip if no URLs found
#         if not urls:
#             return []
#
#         # Make sure we don't visit URLs we've already visited
#         new_urls = [url for url in urls if url not in self.researcher.visited_urls]
#
#         # Return empty if no new URLs
#         if not new_urls:
#             return []
#
#         # Scrape the content from the URLs
#         scraped_content = await self.researcher.scraper_manager.browse_urls(new_urls)
#
#         # Add the URLs to visited_urls
#         self.researcher.visited_urls.update(new_urls)
#
#         return scraped_content
#
#     async def _summarize_content(self, query, content):
#         """
#         Summarize the extracted content.
#
#         Args:
#             query: The search query
#             content: The extracted content
#
#         Returns:
#             str: Summarized content
#         """
#         self.logger.info(f"Summarizing content for query: {query}")
#
#         # Skip if no content
#         if not content:
#             return ""
#
#         # Summarize the content using the context manager
#         summary = await self.researcher.context_manager.get_similar_content_by_query(
#             query, content
#         )
#
#         return summary
#
#     async def _update_search_progress(self, current, total):
#         """
#         Update the search progress.
#
#         Args:
#             current: Current number of sub-queries processed
#             total: Total number of sub-queries
#         """
#         if self.researcher.verbose and self.researcher.websocket:
#             progress = int((current / total) * 100)
#             await stream_output(
#                 "logs",
#                 "research_progress",
#                 f"📊 Research Progress: {progress}%",
#                 self.researcher.websocket,
#                 True,
#                 {
#                     "current": current,
#                     "total": total,
#                     "progress": progress
#                 }
#             )
#
























import asyncio
import random
import logging
import os
from ..actions.utils import stream_output
from ..actions.query_processing import plan_research_outline, get_search_results
from ..document import DocumentLoader, OnlineDocumentLoader, LangChainDocumentLoader
from ..utils.enum import ReportSource, ReportType
from ..utils.logging_config import get_json_handler
from ..actions.agent_creator import choose_agent


# =========================
# 全局网页侧长度控制配置（仅作用于网页抓取结果）
# =========================
WEB_MAX_CHARS_DEFAULT = 5000       # 单条网页文本最大字符数（None 关闭）
MAX_COMBINED_CHARS_DEFAULT = 10000  # 合并后的总长度保险丝（网页路径才用；None 关闭）
CLIP_OVERSIZE_DEFAULT = True         # 超长时截断(True)；丢弃(False)
DROP_EMPTY_DEFAULT = True            # 空白文本丢弃


def _page_text(page: dict) -> str:
    """统一获取网页抓取条目的文本字段"""
    return page.get("raw_content") or page.get("content") or page.get("text") or ""


def _apply_web_len_control(pages: list,
                           logger: logging.Logger,
                           *,
                           web_max_chars: int | None = WEB_MAX_CHARS_DEFAULT,
                           clip_oversize: bool = CLIP_OVERSIZE_DEFAULT,
                           drop_empty: bool = DROP_EMPTY_DEFAULT) -> list:
    """仅对网页抓取数据做长度控制"""
    if not pages:
        return []

    kept, dropped, clipped = 0, 0, 0
    out = []
    for p in pages:
        txt = _page_text(p)
        if drop_empty and not txt.strip():
            dropped += 1
            continue
        if web_max_chars is not None and len(txt) > web_max_chars:
            if clip_oversize:
                q = dict(p)
                if "raw_content" in q and q["raw_content"]:
                    q["raw_content"] = q["raw_content"][:web_max_chars]
                elif "content" in q and q["content"]:
                    q["content"] = q["content"][:web_max_chars]
                else:
                    q["text"] = txt[:web_max_chars]
                out.append(q)
                clipped += 1
                kept += 1
            else:
                dropped += 1
        else:
            out.append(p)
            kept += 1

    logger.info(f"[WebLenControl] max_chars={web_max_chars}, kept={kept}, dropped={dropped}, clipped={clipped}, total_in={len(pages)}")
    return out


class ResearchConductor:
    """Manages and coordinates the research process."""

    def __init__(self, researcher):
        self.researcher = researcher
        self.logger = logging.getLogger('research')
        self.json_handler = get_json_handler()
        # Add cache for MCP results to avoid redundant calls
        self._mcp_results_cache = None
        # Track MCP query count for balanced mode
        self._mcp_query_count = 0

    async def plan_research(self, query, query_domains=None):
        """Gets the sub-queries from the query
        Args:
            query: original query
        Returns:
            List of queries
        """
        await stream_output(
            "logs",
            "planning_research",
            f"🌐 Browsing the web to learn more about the task: {query}...",
            self.researcher.websocket,
        )

        search_results = await get_search_results(query, self.researcher.retrievers[0], query_domains, researcher=self.researcher)
        self.logger.info(f"Initial search results obtained: {len(search_results)} results")

        await stream_output(
            "logs",
            "planning_research",
            f"🤔 Planning the research strategy and subtasks...",
            self.researcher.websocket,
        )

        retriever_names = [r.__name__ for r in self.researcher.retrievers]

        outline = await plan_research_outline(
            query=query,
            search_results=search_results,
            agent_role_prompt=self.researcher.role,
            cfg=self.researcher.cfg,
            parent_query=self.researcher.parent_query,
            report_type=self.researcher.report_type,
            cost_callback=self.researcher.add_costs,
            retriever_names=retriever_names,  # Pass retriever names for MCP optimization
            **self.researcher.kwargs
        )
        self.logger.info(f"Research outline planned: {outline}")
        return outline

    async def conduct_research(self):
        """Runs the GPT Researcher to conduct research"""
        if self.json_handler:
            self.json_handler.update_content("query", self.researcher.query)

        self.logger.info(f"Starting research for query: {self.researcher.query}")

        # Log active retrievers once at the start of research
        retriever_names = [r.__name__ for r in self.researcher.retrievers]
        self.logger.info(f"Active retrievers: {retriever_names}")

        # Reset visited_urls and source_urls at the start of each research task
        self.researcher.visited_urls.clear()
        research_data = []

        if self.researcher.verbose:
            await stream_output(
                "logs",
                "starting_research",
                f"🔍 Starting the research task for '{self.researcher.query}'...",
                self.researcher.websocket,
            )
            await stream_output(
                "logs",
                "agent_generated",
                self.researcher.agent,
                self.researcher.websocket
            )

        # Choose agent and role if not already defined
        if not (self.researcher.agent and self.researcher.role):
            self.researcher.agent, self.researcher.role = await choose_agent(
                query=self.researcher.query,
                cfg=self.researcher.cfg,
                parent_query=self.researcher.parent_query,
                cost_callback=self.researcher.add_costs,
                headers=self.researcher.headers,
                prompt_family=self.researcher.prompt_family
            )

        # Check if MCP retrievers are configured
        has_mcp_retriever = any("mcpretriever" in r.__name__.lower() for r in self.researcher.retrievers)
        if has_mcp_retriever:
            self.logger.info("MCP retrievers configured and will be used with standard research flow")

        # Conduct research based on the source type
        if self.researcher.source_urls:
            self.logger.info("Using provided source URLs")
            # ✅ 网页内容：开启限长
            research_data = await self._get_context_by_urls(
                self.researcher.source_urls,
                web_max_chars=getattr(self.researcher.cfg, "web_max_chars", WEB_MAX_CHARS_DEFAULT),
                clip_oversize=CLIP_OVERSIZE_DEFAULT,
                drop_empty=DROP_EMPTY_DEFAULT
            )
            if research_data and len(research_data) == 0 and self.researcher.verbose:
                await stream_output(
                    "logs",
                    "answering_from_memory",
                    f"🧐 I was unable to find relevant context in the provided sources...",
                    self.researcher.websocket,
                )
            if self.researcher.complement_source_urls:
                self.logger.info("Complementing with web search")
                additional_research = await self._get_context_by_web_search(
                    self.researcher.query, [], self.researcher.query_domains,
                    web_max_chars=getattr(self.researcher.cfg, "web_max_chars", WEB_MAX_CHARS_DEFAULT),
                    max_combined_chars=getattr(self.researcher.cfg, "max_combined_chars", MAX_COMBINED_CHARS_DEFAULT)
                )
                research_data += ' '.join(additional_research) if isinstance(additional_research, list) else (additional_research or "")
        elif self.researcher.report_source == ReportSource.Web.value:
            self.logger.info("Using web search with all configured retrievers")
            # ✅ 纯网页：开启限长
            research_data = await self._get_context_by_web_search(
                self.researcher.query, [], self.researcher.query_domains,
                web_max_chars=getattr(self.researcher.cfg, "web_max_chars", WEB_MAX_CHARS_DEFAULT),
                max_combined_chars=getattr(self.researcher.cfg, "max_combined_chars", MAX_COMBINED_CHARS_DEFAULT)
            )
        elif self.researcher.report_source == ReportSource.Local.value:
            self.logger.info("Using local search")
            document_data = await DocumentLoader(self.researcher.cfg.doc_path).load()
            self.logger.info(f"Loaded {len(document_data)} documents")
            if self.researcher.vector_store:
                self.researcher.vector_store.load(document_data)
            # ❌ 本地：不传 web_max_chars（不限制本地）
            research_data = await self._get_context_by_web_search(self.researcher.query, document_data, self.researcher.query_domains)
        # Hybrid search including both local documents and web sources
        elif self.researcher.report_source == ReportSource.Hybrid.value:
            if self.researcher.document_urls:
                document_data = await OnlineDocumentLoader(self.researcher.document_urls).load()
            else:
                document_data = await DocumentLoader(self.researcher.cfg.doc_path).load()
            if self.researcher.vector_store:
                self.researcher.vector_store.load(document_data)
            # ❌ 本地：不限制
            docs_context = await self._get_context_by_web_search(self.researcher.query, document_data, self.researcher.query_domains)
            # ✅ 网页：限制
            web_context = await self._get_context_by_web_search(
                self.researcher.query, [], self.researcher.query_domains,
                web_max_chars=getattr(self.researcher.cfg, "web_max_chars", WEB_MAX_CHARS_DEFAULT),
                max_combined_chars=getattr(self.researcher.cfg, "max_combined_chars", MAX_COMBINED_CHARS_DEFAULT)
            )
            research_data = self.researcher.prompt_family.join_local_web_documents(docs_context, web_context)
        elif self.researcher.report_source == ReportSource.Azure.value:
            from ..document.azure_document_loader import AzureDocumentLoader
            azure_loader = AzureDocumentLoader(
                container_name=os.getenv("AZURE_CONTAINER_NAME"),
                connection_string=os.getenv("AZURE_CONNECTION_STRING")
            )
            azure_files = await azure_loader.load()
            document_data = await DocumentLoader(azure_files).load()  # Reuse existing loader
            # ❌ Azure 本地化后走本地链路，不限长
            research_data = await self._get_context_by_web_search(self.researcher.query, document_data)
        elif self.researcher.report_source == ReportSource.LangChainDocuments.value:
            langchain_documents_data = await LangChainDocumentLoader(
                self.researcher.documents
            ).load()
            if self.researcher.vector_store:
                self.researcher.vector_store.load(langchain_documents_data)
            # ❌ LangChain 本地文档：不限制
            research_data = await self._get_context_by_web_search(
                self.researcher.query, langchain_documents_data, self.researcher.query_domains
            )
        elif self.researcher.report_source == ReportSource.LangChainVectorStore.value:
            research_data = await self._get_context_by_vectorstore(self.researcher.query, self.researcher.vector_store_filter)

        # Rank and curate the sources
        self.researcher.context = research_data
        if self.researcher.cfg.curate_sources:
            self.logger.info("Curating sources")
            self.researcher.context = await self.researcher.source_curator.curate_sources(research_data)

        if self.researcher.verbose:
            await stream_output(
                "logs",
                "research_step_finalized",
                f"Finalized research step.\n💸 Total Research Costs: ${self.researcher.get_costs()}",
                self.researcher.websocket,
            )
            if self.json_handler:
                self.json_handler.update_content("costs", self.researcher.get_costs())
                self.json_handler.update_content("context", self.researcher.context)

        self.logger.info(f"Research completed. Context size: {len(str(self.researcher.context))}")
        return self.researcher.context

    async def _get_context_by_urls(self, urls,
                                   *,
                                   web_max_chars: int | None = WEB_MAX_CHARS_DEFAULT,
                                   clip_oversize: bool = CLIP_OVERSIZE_DEFAULT,
                                   drop_empty: bool = DROP_EMPTY_DEFAULT):
        """Scrapes and compresses the context from the given urls (web-only path)"""
        self.logger.info(f"Getting context from URLs: {urls}")

        new_search_urls = await self._get_new_urls(urls)
        self.logger.info(f"New URLs to process: {new_search_urls}")

        scraped_content = await self.researcher.scraper_manager.browse_urls(new_search_urls)
        self.logger.info(f"Scraped content from {len(scraped_content)} URLs")

        # ✅ 网页内容：长度控制
        filtered = _apply_web_len_control(
            scraped_content, self.logger,
            web_max_chars=web_max_chars,
            clip_oversize=clip_oversize,
            drop_empty=drop_empty
        )

        if self.researcher.vector_store and filtered:
            self.researcher.vector_store.load(filtered)

        context = await self.researcher.context_manager.get_similar_content_by_query(
            self.researcher.query, filtered
        )
        return context

    # Add logging to other methods similarly...

    async def _get_context_by_vectorstore(self, query, filter: dict | None = None):
        """
        Generates the context for the research task by searching the vectorstore
        Returns:
            context: List of context
        """
        self.logger.info(f"Starting vectorstore search for query: {query}")
        context = []
        # Generate Sub-Queries including original query
        sub_queries = await self.plan_research(query)
        # If this is not part of a sub researcher, add original query to research for better results
        if self.researcher.report_type != "subtopic_report":
            sub_queries.append(query)

        if self.researcher.verbose:
            await stream_output(
                "logs",
                "subqueries",
                f"🗂️  I will conduct my research based on the following queries: {sub_queries}...",
                self.researcher.websocket,
                True,
                sub_queries,
            )

        # Using asyncio.gather to process the sub_queries asynchronously
        context = await asyncio.gather(
            *[
                self._process_sub_query_with_vectorstore(sub_query, filter)
                for sub_query in sub_queries
            ]
        )
        return context

    async def _get_context_by_web_search(self, query, scraped_data: list | None = None, query_domains: list | None = None,
                                         *,
                                         web_max_chars: int | None = WEB_MAX_CHARS_DEFAULT,
                                         max_combined_chars: int | None = MAX_COMBINED_CHARS_DEFAULT):
        """
        Generates the context for the research task by searching the query and scraping the results
        Returns:
            context: str (combined context)
        """
        self.logger.info(f"Starting web search for query: {query}")

        if scraped_data is None:
            scraped_data = []
        if query_domains is None:
            query_domains = []

        # ✅ 仅对传入的网页 scraped_data 做长度控制（本地文档不应从这里的 scraped_data 传入）
        if scraped_data:
            scraped_data = _apply_web_len_control(
                scraped_data, self.logger,
                web_max_chars=web_max_chars,
                clip_oversize=CLIP_OVERSIZE_DEFAULT,
                drop_empty=DROP_EMPTY_DEFAULT
            )

        # **CONFIGURABLE MCP OPTIMIZATION: Control MCP strategy**
        mcp_retrievers = [r for r in self.researcher.retrievers if "mcpretriever" in r.__name__.lower()]

        # Get MCP strategy configuration
        mcp_strategy = self._get_mcp_strategy()

        if mcp_retrievers and self._mcp_results_cache is None:
            if mcp_strategy == "disabled":
                self.logger.info("MCP disabled by strategy, skipping MCP research")
                if self.researcher.verbose:
                    await stream_output(
                        "logs",
                        "mcp_disabled",
                        f"⚡ MCP research disabled by configuration",
                        self.researcher.websocket,
                    )
            elif mcp_strategy == "fast":
                self.logger.info("MCP fast strategy: Running once with original query")
                if self.researcher.verbose:
                    await stream_output(
                        "logs",
                        "mcp_optimization",
                        f"🚀 MCP Fast: Running once for main query (performance mode)",
                        self.researcher.websocket,
                    )

                # Execute MCP research once with the original query
                mcp_context = await self._execute_mcp_research_for_queries([query], mcp_retrievers)
                self._mcp_results_cache = mcp_context
                self.logger.info(f"MCP results cached: {len(mcp_context)} total context entries")
            elif mcp_strategy == "deep":
                self.logger.info("MCP deep strategy: Will run for all queries")
                if self.researcher.verbose:
                    await stream_output(
                        "logs",
                        "mcp_comprehensive",
                        f"🔍 MCP Deep: Will run for each sub-query (thorough mode)",
                        self.researcher.websocket,
                    )
            else:
                self.logger.warning(f"Unknown MCP strategy '{mcp_strategy}', defaulting to fast")
                mcp_context = await self._execute_mcp_research_for_queries([query], mcp_retrievers)
                self._mcp_results_cache = mcp_context
                self.logger.info(f"MCP results cached: {len(mcp_context)} total context entries")

        # Generate Sub-Queries including original query
        sub_queries = await self.plan_research(query, query_domains)
        self.logger.info(f"Generated sub-queries: {sub_queries}")

        # If this is not part of a sub researcher, add original query to research for better results
        if self.researcher.report_type != "subtopic_report":
            sub_queries.append(query)

        if self.researcher.verbose:
            await stream_output(
                "logs",
                "subqueries",
                f"🗂️ I will conduct my research based on the following queries: {sub_queries}...",
                self.researcher.websocket,
                True,
                sub_queries,
            )

        # Using asyncio.gather to process the sub_queries asynchronously
        try:
            contexts = await asyncio.gather(
                *[
                    self._process_sub_query(sub_query, scraped_data, query_domains)
                    for sub_query in sub_queries
                ]
            )
            self.logger.info(f"Gathered context from {len(contexts)} sub-queries")

            # Filter out empty results
            contexts = [c for c in contexts if c]
            if not contexts:
                return []

            # ✅ 子查询返回文本可能很长：先做每段轻截断（仅网页路径；此处我们用 web_max_chars 作为每段 clip 上限）
            dropped_chars = 0
            if web_max_chars is not None:
                clipped_ctxs = []
                for c in contexts:
                    if len(c) > web_max_chars:
                        clipped_ctxs.append(c[:web_max_chars])
                        dropped_chars += (len(c) - web_max_chars)
                    else:
                        clipped_ctxs.append(c)
                contexts = clipped_ctxs
                if dropped_chars > 0:
                    self.logger.info(f"[WebLenClip] Per-subquery clip applied, total dropped chars={dropped_chars}")

            combined_context = " ".join(contexts)

            # ✅ 合并后的总长度保险丝（仅网页路径）
            if max_combined_chars is not None and len(combined_context) > max_combined_chars:
                self.logger.info(
                    f"[WebLenFuse] max_combined_chars={max_combined_chars}, "
                    f"truncating combined from {len(combined_context)}"
                )
                combined_context = combined_context[:max_combined_chars]

            self.logger.info(f"Combined context size: {len(combined_context)}")
            return combined_context
        except Exception as e:
            self.logger.error(f"Error during web search: {e}", exc_info=True)
            return []

    def _get_mcp_strategy(self) -> str:
        """
        Get the MCP strategy configuration.

        Priority:
        1. Instance-level setting (self.researcher.mcp_strategy)
        2. Config file setting (self.researcher.cfg.mcp_strategy)
        3. Default value ("fast")

        Returns:
            str: MCP strategy
                "disabled" = Skip MCP entirely
                "fast" = Run MCP once with original query (default)
                "deep" = Run MCP for all sub-queries
        """
        # Check instance-level setting first
        if hasattr(self.researcher, 'mcp_strategy') and self.researcher.mcp_strategy is not None:
            return self.researcher.mcp_strategy

        # Check config setting
        if hasattr(self.researcher.cfg, 'mcp_strategy'):
            return self.researcher.cfg.mcp_strategy

        # Default to fast mode
        return "fast"

    async def _execute_mcp_research_for_queries(self, queries: list, mcp_retrievers: list) -> list:
        """
        Execute MCP research for a list of queries.

        Args:
            queries: List of queries to research
            mcp_retrievers: List of MCP retriever classes

        Returns:
            list: Combined MCP context entries from all queries
        """
        all_mcp_context = []

        for i, query in enumerate(queries, 1):
            self.logger.info(f"Executing MCP research for query {i}/{len(queries)}: {query}")

            for retriever in mcp_retrievers:
                try:
                    mcp_results = await self._execute_mcp_research(retriever, query)
                    if mcp_results:
                        for result in mcp_results:
                            content = result.get("body", "")
                            url = result.get("href", "")
                            title = result.get("title", "")

                            if content:
                                context_entry = {
                                    "content": content,
                                    "url": url,
                                    "title": title,
                                    "query": query,
                                    "source_type": "mcp"
                                }
                                all_mcp_context.append(context_entry)

                        self.logger.info(f"Added {len(mcp_results)} MCP results for query: {query}")

                        if self.researcher.verbose:
                            await stream_output(
                                "logs",
                                "mcp_results_cached",
                                f"✅ Cached {len(mcp_results)} MCP results from query {i}/{len(queries)}",
                                self.researcher.websocket,
                            )
                except Exception as e:
                    self.logger.error(f"Error in MCP research for query '{query}': {e}")
                    if self.researcher.verbose:
                        await stream_output(
                            "logs",
                            "mcp_cache_error",
                            f"⚠️ MCP research error for query {i}, continuing with other sources",
                            self.researcher.websocket,
                        )

        return all_mcp_context

    async def _process_sub_query(self, sub_query: str, scraped_data: list = [], query_domains: list = []):
        """Takes in a sub query and scrapes urls based on it and gathers context."""
        if self.json_handler:
            self.json_handler.log_event("sub_query", {
                "query": sub_query,
                "scraped_data_size": len(scraped_data)
            })

        if self.researcher.verbose:
            await stream_output(
                "logs",
                "running_subquery_research",
                f"\n🔍 Running research for '{sub_query}'...",
                self.researcher.websocket,
            )

        try:
            # Identify MCP retrievers
            mcp_retrievers = [r for r in self.researcher.retrievers if "mcpretriever" in r.__name__.lower()]
            non_mcp_retrievers = [r for r in self.researcher.retrievers if "mcpretriever" not in r.__name__.lower()]

            # Initialize context components
            mcp_context = []
            web_context = ""

            # Get MCP strategy configuration
            mcp_strategy = self._get_mcp_strategy()

            # **CONFIGURABLE MCP PROCESSING**
            if mcp_retrievers:
                if mcp_strategy == "disabled":
                    self.logger.info(f"MCP disabled for sub-query: {sub_query}")
                elif mcp_strategy == "fast" and self._mcp_results_cache is not None:
                    mcp_context = self._mcp_results_cache.copy()

                    if self.researcher.verbose:
                        await stream_output(
                            "logs",
                            "mcp_cache_reuse",
                            f"♻️ Reusing cached MCP results ({len(mcp_context)} sources) for: {sub_query}",
                            self.researcher.websocket,
                        )

                    self.logger.info(f"Reused {len(mcp_context)} cached MCP results for sub-query: {sub_query}")
                elif mcp_strategy == "deep":
                    self.logger.info(f"Running deep MCP research for: {sub_query}")
                    if self.researcher.verbose:
                        await stream_output(
                            "logs",
                            "mcp_comprehensive_run",
                            f"🔍 Running deep MCP research for: {sub_query}",
                            self.researcher.websocket,
                        )

                    mcp_context = await self._execute_mcp_research_for_queries([sub_query], mcp_retrievers)
                else:
                    self.logger.warning("MCP cache not available, falling back to per-sub-query execution")
                    if self.researcher.verbose:
                        await stream_output(
                            "logs",
                            "mcp_fallback",
                            f"🔌 MCP cache unavailable, running MCP research for: {sub_query}",
                            self.researcher.websocket,
                        )

                    mcp_context = await self._execute_mcp_research_for_queries([sub_query], mcp_retrievers)

            # Get web search context using non-MCP retrievers (if no scraped data provided)
            if not scraped_data:
                scraped_data = await self._scrape_data_by_urls(sub_query, query_domains)
                self.logger.info(f"Scraped data size: {len(scraped_data)}")

            # Get similar content based on scraped data
            if scraped_data:
                web_context = await self.researcher.context_manager.get_similar_content_by_query(sub_query, scraped_data)
                self.logger.info(f"Web content found for sub-query: {len(str(web_context)) if web_context else 0} chars")

            # Combine MCP context with web context intelligently
            combined_context = self._combine_mcp_and_web_context(mcp_context, web_context, sub_query)

            # Log context combination results
            if combined_context:
                context_length = len(str(combined_context))
                self.logger.info(f"Combined context for '{sub_query}': {context_length} chars")

                if self.researcher.verbose:
                    mcp_count = len(mcp_context)
                    web_available = bool(web_context)
                    cache_used = self._mcp_results_cache is not None and mcp_retrievers and mcp_strategy != "deep"
                    cache_status = " (cached)" if cache_used else ""
                    await stream_output(
                        "logs",
                        "context_combined",
                        f"📚 Combined research context: {mcp_count} MCP sources{cache_status}, {'web content' if web_available else 'no web content'}",
                        self.researcher.websocket,
                    )
            else:
                self.logger.warning(f"No combined context found for sub-query: {sub_query}")
                if self.researcher.verbose:
                    await stream_output(
                        "logs",
                        "subquery_context_not_found",
                        f"🤷 No content found for '{sub_query}'...",
                        self.researcher.websocket,
                    )

            if combined_context and self.json_handler:
                self.json_handler.log_event("content_found", {
                    "sub_query": sub_query,
                    "content_size": len(str(combined_context)),
                    "mcp_sources": len(mcp_context),
                    "web_content": bool(web_context)
                })

            return combined_context

        except Exception as e:
            self.logger.error(f"Error processing sub-query {sub_query}: {e}", exc_info=True)
            if self.researcher.verbose:
                await stream_output(
                    "logs",
                    "subquery_error",
                    f"❌ Error processing '{sub_query}': {str(e)}",
                    self.researcher.websocket,
                )
            return ""

    async def _execute_mcp_research(self, retriever, query):
        """
        Execute MCP research using the new two-stage approach.

        Args:
            retriever: The MCP retriever class
            query: The search query

        Returns:
            list: MCP research results
        """
        retriever_name = retriever.__name__

        self.logger.info(f"Executing MCP research with {retriever_name} for query: {query}")

        try:
            retriever_instance = retriever(
                query=query,
                headers=self.researcher.headers,
                query_domains=self.researcher.query_domains,
                websocket=self.researcher.websocket,
                researcher=self.researcher
            )

            if self.researcher.verbose:
                await stream_output(
                    "logs",
                    "mcp_retrieval_stage1",
                    f"🧠 Stage 1: Selecting optimal MCP tools for: {query}",
                    self.researcher.websocket,
                )

            results = retriever_instance.search(
                max_results=self.researcher.cfg.max_search_results_per_query
            )

            if results:
                result_count = len(results)
                self.logger.info(f"MCP research completed: {result_count} results from {retriever_name}")

                if self.researcher.verbose:
                    await stream_output(
                        "logs",
                        "mcp_research_complete",
                        f"🎯 MCP research completed: {result_count} intelligent results obtained",
                        self.researcher.websocket,
                    )

                return results
            else:
                self.logger.info(f"No results returned from MCP research with {retriever_name}")
                if self.researcher.verbose:
                    await stream_output(
                        "logs",
                        "mcp_no_results",
                        f"ℹ️ No relevant information found via MCP for: {query}",
                        self.researcher.websocket,
                    )
                return []

        except Exception as e:
            self.logger.error(f"Error in MCP research with {retriever_name}: {str(e)}")
            if self.researcher.verbose:
                await stream_output(
                    "logs",
                    "mcp_research_error",
                    f"⚠️ MCP research error: {str(e)} - continuing with other sources",
                    self.researcher.websocket,
                )
            return []

    def _combine_mcp_and_web_context(self, mcp_context: list, web_context: str, sub_query: str) -> str:
        """
        Intelligently combine MCP and web research context.
        """
        combined_parts = []

        if web_context and web_context.strip():
            combined_parts.append(web_context.strip())
            self.logger.debug(f"Added web context: {len(web_context)} chars")

        if mcp_context:
            mcp_formatted = []
            for i, item in enumerate(mcp_context):
                content = item.get("content", "")
                url = item.get("url", "")
                title = item.get("title", f"MCP Result {i+1}")

                if content and content.strip():
                    if url and url != f"mcp://llm_analysis":
                        citation = f"\n\n*Source: {title} ({url})*"
                    else:
                        citation = f"\n\n*Source: {title}*"

                    formatted_content = f"{content.strip()}{citation}"
                    mcp_formatted.append(formatted_content)

            if mcp_formatted:
                mcp_section = "\n\n---\n\n".join(mcp_formatted)
                combined_parts.append(mcp_section)
                self.logger.debug(f"Added {len(mcp_context)} MCP context entries")

        if combined_parts:
            final_context = "\n\n".join(combined_parts)
            self.logger.info(f"Combined context for '{sub_query}': {len(final_context)} total chars")
            return final_context
        else:
            self.logger.warning(f"No context to combine for sub-query: {sub_query}")
            return ""

    async def _process_sub_query_with_vectorstore(self, sub_query: str, filter: dict | None = None):
        """Gather context from user provided vector store"""
        if self.researcher.verbose:
            await stream_output(
                "logs",
                "running_subquery_with_vectorstore_research",
                f"\n🔍 Running research for '{sub_query}'...",
                self.researcher.websocket,
            )

        context = await self.researcher.context_manager.get_similar_content_by_query_with_vectorstore(sub_query, filter)

        return context

    async def _get_new_urls(self, url_set_input):
        """Gets the new urls from the given url set."""
        new_urls = []
        for url in url_set_input:
            if url not in self.researcher.visited_urls:
                self.researcher.visited_urls.add(url)
                new_urls.append(url)
                if self.researcher.verbose:
                    await stream_output(
                        "logs",
                        "added_source_url",
                        f"✅ Added source url to research: {url}\n",
                        self.researcher.websocket,
                        True,
                        url,
                    )

        return new_urls

    async def _search_relevant_source_urls(self, query, query_domains: list | None = None):
        new_search_urls = []
        if query_domains is None:
            query_domains = []

        for retriever_class in self.researcher.retrievers:
            if "mcpretriever" in retriever_class.__name__.lower():
                continue

            try:
                retriever = retriever_class(query, query_domains=query_domains)

                search_results = await asyncio.to_thread(
                    retriever.search, max_results=self.researcher.cfg.max_search_results_per_query
                )

                search_urls = [url.get("href") for url in search_results if url.get("href")]
                new_search_urls.extend(search_urls)
            except Exception as e:
                self.logger.error(f"Error searching with {retriever_class.__name__}: {e}")

        new_search_urls = await self._get_new_urls(new_search_urls)
        random.shuffle(new_search_urls)

        return new_search_urls

    async def _scrape_data_by_urls(self, sub_query, query_domains: list | None = None,
                                   *,
                                   web_max_chars: int | None = WEB_MAX_CHARS_DEFAULT,
                                   clip_oversize: bool = CLIP_OVERSIZE_DEFAULT,
                                   drop_empty: bool = DROP_EMPTY_DEFAULT):
        """
        Runs a sub-query across multiple retrievers and scrapes the resulting URLs.
        """
        if query_domains is None:
            query_domains = []

        new_search_urls = await self._search_relevant_source_urls(sub_query, query_domains)

        if self.researcher.verbose:
            await stream_output(
                "logs",
                "researching",
                f"🤔 Researching for relevant information across multiple sources...\n",
                self.researcher.websocket,
            )

        scraped_content = await self.researcher.scraper_manager.browse_urls(new_search_urls)

        # ✅ 网页内容：长度控制
        scraped_content = _apply_web_len_control(
            scraped_content, self.logger,
            web_max_chars=web_max_chars,
            clip_oversize=clip_oversize,
            drop_empty=drop_empty
        )

        if self.researcher.vector_store and scraped_content:
            self.researcher.vector_store.load(scraped_content)

        return scraped_content

    async def _search(self, retriever, query):
        """
        Perform a search using the specified retriever.
        """
        retriever_name = retriever.__name__
        is_mcp_retriever = "mcpretriever" in retriever_name.lower()

        self.logger.info(f"Searching with {retriever_name} for query: {query}")

        try:
            retriever_instance = retriever(
                query=query,
                headers=self.researcher.headers,
                query_domains=self.researcher.query_domains,
                websocket=self.researcher.websocket if is_mcp_retriever else None,
                researcher=self.researcher if is_mcp_retriever else None
            )

            if is_mcp_retriever and self.researcher.verbose:
                await stream_output(
                    "logs",
                    "mcp_retrieval",
                    f"🔌 Consulting MCP server(s) for information on: {query}",
                    self.researcher.websocket,
                )

            if hasattr(retriever_instance, 'search'):
                results = retriever_instance.search(
                    max_results=self.researcher.cfg.max_search_results_per_query
                )

                if results:
                    result_count = len(results)
                    self.logger.info(f"Received {result_count} results from {retriever_name}")

                    if is_mcp_retriever:
                        if self.researcher.verbose:
                            await stream_output(
                                "logs",
                                "mcp_results",
                                f"✓ Retrieved {result_count} results from MCP server",
                                self.researcher.websocket,
                            )

                        for i, result in enumerate(results[:3]):
                            title = result.get("title", "No title")
                            url = result.get("href", "No URL")
                            content_length = len(result.get("body", "")) if result.get("body") else 0
                            self.logger.info(f"MCP result {i+1}: '{title}' from {url} ({content_length} chars)")

                        if result_count > 3:
                            self.logger.info(f"... and {result_count - 3} more MCP results")
                else:
                    self.logger.info(f"No results returned from {retriever_name}")
                    if is_mcp_retriever and self.researcher.verbose:
                        await stream_output(
                            "logs",
                            "mcp_no_results",
                            f"ℹ️ No relevant information found from MCP server for: {query}",
                            self.researcher.websocket,
                        )

                return results
            else:
                self.logger.error(f"Retriever {retriever_name} does not have a search method")
                return []
        except Exception as e:
            self.logger.error(f"Error searching with {retriever_name}: {str(e)}")
            if is_mcp_retriever and self.researcher.verbose:
                await stream_output(
                    "logs",
                    "mcp_error",
                    f"❌ Error retrieving information from MCP server: {str(e)}",
                    self.researcher.websocket,
                )
            return []

    async def _extract_content(self, results,
                               *,
                               web_max_chars: int | None = WEB_MAX_CHARS_DEFAULT,
                               clip_oversize: bool = CLIP_OVERSIZE_DEFAULT,
                               drop_empty: bool = DROP_EMPTY_DEFAULT):
        """
        Extract content from search results using the browser manager.
        """
        self.logger.info(f"Extracting content from {len(results)} search results")

        urls = []
        for result in results:
            if isinstance(result, dict) and "href" in result:
                urls.append(result["href"])

        if not urls:
            return []

        new_urls = [url for url in urls if url not in self.researcher.visited_urls]
        if not new_urls:
            return []

        scraped_content = await self.researcher.scraper_manager.browse_urls(new_urls)
        self.researcher.visited_urls.update(new_urls)

        # ✅ 网页内容：长度控制
        scraped_content = _apply_web_len_control(
            scraped_content, self.logger,
            web_max_chars=web_max_chars,
            clip_oversize=clip_oversize,
            drop_empty=drop_empty
        )

        return scraped_content

    async def _summarize_content(self, query, content):
        """
        Summarize the extracted content.
        """
        self.logger.info(f"Summarizing content for query: {query}")

        if not content:
            return ""

        summary = await self.researcher.context_manager.get_similar_content_by_query(
            query, content
        )

        return summary

    async def _update_search_progress(self, current, total):
        """
        Update the search progress.
        """
        if self.researcher.verbose and self.researcher.websocket:
            progress = int((current / total) * 100)
            await stream_output(
                "logs",
                "research_progress",
                f"📊 Research Progress: {progress}%",
                self.researcher.websocket,
                True,
                {
                    "current": current,
                    "total": total,
                    "progress": progress
                }
            )
