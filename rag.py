"""
RAG (Retrieval-Augmented Generation) 系統模塊

功能：
1. 初始化向量數據庫（首次啟動時構建，後續直接加載）
2. 檢索相關知識庫內容
3. 管理向量數據庫（重建、更新）
"""

import asyncio
import logging
from pathlib import Path
from typing import Dict, List, Optional
import time

# LangChain 相關導入
from langchain_community.document_loaders import UnstructuredMarkdownLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma

# 配置
KNOWLEDGE_DIR = Path(__file__).parent / "knowledge"
CHROMA_PERSIST_DIR = Path(__file__).parent / "chroma_db"
EMBEDDING_MODEL = "BAAI/bge-small-zh-v1.5"  # 中文優化模型
CHUNK_SIZE = 800  # 保留完整問題-解決方案對
CHUNK_OVERLAP = 100
TOP_K_RESULTS = 3  # 檢索前3個最相關文檔
SIMILARITY_THRESHOLD = 0.3  # 相似度閾值

# 全局變量
vectorstore: Optional[Chroma] = None
embeddings: Optional[HuggingFaceEmbeddings] = None

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def initialize_rag_system() -> bool:
    """
    初始化 RAG 系統

    Returns:
        bool: 初始化是否成功
    """
    global vectorstore, embeddings

    try:
        logger.info("開始初始化 RAG 系統...")

        # 初始化 Embedding 模型
        embeddings = await asyncio.to_thread(
            HuggingFaceEmbeddings,
            model_name=EMBEDDING_MODEL,
            model_kwargs={'device': 'cpu'},
            encode_kwargs={'normalize_embeddings': True}
        )
        logger.info(f"Embedding 模型加載成功: {EMBEDDING_MODEL}")

        # 檢查是否已存在向量數據庫
        if CHROMA_PERSIST_DIR.exists() and _is_valid_vectorstore():
            logger.info("檢測到已存在的向量數據庫，直接加載...")
            vectorstore = await asyncio.to_thread(
                Chroma,
                persist_directory=str(CHROMA_PERSIST_DIR),
                embedding_function=embeddings
            )
            collection_count = vectorstore._collection.count()
            logger.info(f"向量數據庫加載成功，包含 {collection_count} 個文檔塊")
        else:
            logger.info("首次啟動或數據庫無效，開始構建向量數據庫...")
            success = await _build_vectorstore()
            if not success:
                logger.error("向量數據庫構建失敗")
                return False

        logger.info("RAG 系統初始化成功")
        return True

    except Exception as e:
        logger.error(f"RAG 系統初始化失敗: {e}", exc_info=True)
        return False


def _is_valid_vectorstore() -> bool:
    """
    檢查向量數據庫是否有效

    Returns:
        bool: 數據庫是否有效
    """
    try:
        chroma_db_file = CHROMA_PERSIST_DIR / "chroma.sqlite3"
        return chroma_db_file.exists()
    except Exception:
        return False


async def _build_vectorstore() -> bool:
    """
    構建向量數據庫

    Returns:
        bool: 構建是否成功
    """
    global vectorstore

    try:
        # 檢查知識庫目錄
        if not KNOWLEDGE_DIR.exists():
            logger.error(f"知識庫目錄不存在: {KNOWLEDGE_DIR}")
            return False

        # 加載所有 Markdown 文件
        md_files = list(KNOWLEDGE_DIR.glob("*.md"))
        if not md_files:
            logger.error(f"知識庫目錄中沒有 Markdown 文件: {KNOWLEDGE_DIR}")
            return False

        logger.info(f"找到 {len(md_files)} 個知識庫文件")

        # 加載文檔
        documents = []
        for md_file in md_files:
            logger.info(f"加載知識庫: {md_file.name}")
            loader = UnstructuredMarkdownLoader(str(md_file))
            docs = await asyncio.to_thread(loader.load)
            # 添加元數據
            for doc in docs:
                doc.metadata["source"] = md_file.name
            documents.extend(docs)

        logger.info(f"共加載 {len(documents)} 個文檔")

        # 分割文檔
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=CHUNK_SIZE,
            chunk_overlap=CHUNK_OVERLAP,
            separators=["\n## ", "\n### ", "\n#### ", "\n\n", "\n", " ", ""]
        )
        split_docs = await asyncio.to_thread(text_splitter.split_documents, documents)
        logger.info(f"文檔分割完成，共 {len(split_docs)} 個文檔塊")

        # 創建向量數據庫
        vectorstore = await asyncio.to_thread(
            Chroma.from_documents,
            documents=split_docs,
            embedding=embeddings,
            persist_directory=str(CHROMA_PERSIST_DIR)
        )

        logger.info(f"向量數據庫已持久化到: {CHROMA_PERSIST_DIR}")
        return True

    except Exception as e:
        logger.error(f"構建向量數據庫失敗: {e}", exc_info=True)
        return False


async def retrieve_relevant_context(query: str, timeout: float = 5.0) -> Dict:
    """
    檢索相關知識庫內容

    Args:
        query: 用戶查詢
        timeout: 檢索超時時間（秒）

    Returns:
        Dict: 包含以下鍵值：
            - has_context: bool, 是否找到相關內容
            - context: str, 格式化的上下文內容
            - sources: List[str], 來源文件列表
            - scores: List[float], 相關度分數列表
    """
    global vectorstore

    # 默認返回值
    default_result = {
        "has_context": False,
        "context": "",
        "sources": [],
        "scores": []
    }

    # 檢查 RAG 系統是否已初始化
    if vectorstore is None:
        logger.warning("RAG 系統未初始化，無法檢索")
        return default_result

    try:
        # 執行相似度搜索（使用 asyncio.to_thread 避免阻塞）
        results = await asyncio.wait_for(
            asyncio.to_thread(
                vectorstore.similarity_search_with_score,
                query,
                k=TOP_K_RESULTS
            ),
            timeout=timeout
        )

        # 過濾低相關度結果
        filtered_results = [
            (doc, score) for doc, score in results
            if score >= SIMILARITY_THRESHOLD
        ]

        if not filtered_results:
            logger.info(f"未找到相關內容（查詢: {query[:50]}...）")
            return default_result

        # 格式化上下文
        context_parts = []
        sources = []
        scores = []

        for idx, (doc, score) in enumerate(filtered_results, 1):
            source = doc.metadata.get("source", "未知來源")
            content = doc.page_content.strip()

            context_parts.append(f"[參考資料 {idx}] (來源: {source}, 相關度: {score:.2f})\n{content}")
            sources.append(source)
            scores.append(float(score))

        context = "\n\n".join(context_parts)

        logger.info(f"檢索成功，找到 {len(filtered_results)} 個相關文檔（查詢: {query[:50]}...）")

        return {
            "has_context": True,
            "context": context,
            "sources": sources,
            "scores": scores
        }

    except asyncio.TimeoutError:
        logger.error(f"檢索超時（查詢: {query[:50]}...）")
        return default_result
    except Exception as e:
        logger.error(f"檢索失敗: {e}", exc_info=True)
        return default_result


async def force_rebuild_vectorstore() -> bool:
    """
    強制重建向量數據庫（管理命令）

    Returns:
        bool: 重建是否成功
    """
    global vectorstore

    try:
        logger.info("開始強制重建向量數據庫...")

        # 刪除現有數據庫
        if CHROMA_PERSIST_DIR.exists():
            import shutil
            await asyncio.to_thread(shutil.rmtree, CHROMA_PERSIST_DIR)
            logger.info("已刪除現有向量數據庫")

        # 重建數據庫
        success = await _build_vectorstore()

        if success:
            logger.info("向量數據庫重建成功")
        else:
            logger.error("向量數據庫重建失敗")

        return success

    except Exception as e:
        logger.error(f"強制重建失敗: {e}", exc_info=True)
        return False


def get_rag_status() -> Dict:
    """
    獲取 RAG 系統狀態

    Returns:
        Dict: 包含系統狀態信息
    """
    global vectorstore

    status = {
        "initialized": vectorstore is not None,
        "vectorstore_exists": CHROMA_PERSIST_DIR.exists(),
        "knowledge_dir": str(KNOWLEDGE_DIR),
        "chroma_dir": str(CHROMA_PERSIST_DIR),
        "embedding_model": EMBEDDING_MODEL,
        "document_count": 0
    }

    if vectorstore is not None:
        try:
            status["document_count"] = vectorstore._collection.count()
        except Exception:
            pass

    return status
