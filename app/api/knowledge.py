from __future__ import annotations

import asyncio
import logging
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.configs.settings import settings
from app.database.models.document import Document
from app.database.repositories.category_repo import CategoryRepo
from app.database.repositories.document_repo import DocumentRepo
from app.database.session import async_session_factory, get_db
from app.llm.embedding.embedding_service import EmbeddingService
from app.llm.providers.openai import OpenAIProvider
from app.rag.chunk.finance_chunker import chunk_finance
from app.rag.chunk.legal_chunker import chunk_legal
from app.rag.chunk.semantic_chunker import chunk_semantic
from app.rag.indexing.pipeline import IndexingPipeline
from app.rag.parser import detect_file_type, parse_bytes
from app.rag.retrieval.vector import VectorRetriever
from app.rag.service import RAGService
from app.schemas.knowledge import (
    CategoryCreate,
    CategoryInfo,
    CategoryStats,
    ChunkResult,
    ConfirmRequest,
    ConfirmResponse,
    DocumentInfo,
    DocumentUpload,
    FilePreview,
    ImportJobStatus,
    PreviewSession,
    SearchResponse,
)
from app.services.import_job_store import import_job_store
from app.services.preview_store import preview_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


# ===========================================================================
# 兼容旧接口：POST /knowledge/index（文本直接导入）
# ===========================================================================


@router.post("/index")
async def index_document(request: DocumentUpload, db: AsyncSession = Depends(get_db)):
    llm = OpenAIProvider()
    embedder = EmbeddingService(llm=llm)
    pipeline = IndexingPipeline(db=db, embedder=embedder)
    result = await pipeline.index_text(
        domain=request.domain,
        title=request.title,
        source=request.source,
        content=request.content,
        chunk_strategy=_strategy_for_domain(request.domain),
    )
    await db.commit()
    return {"document_id": str(result.document_id), "chunks": result.chunk_count}


# ===========================================================================
# 类别管理
# ===========================================================================


@router.get("/categories", response_model=list[CategoryStats])
async def list_categories(db: AsyncSession = Depends(get_db)):
    """列出所有类别 + 文件/字数/最近更新统计。"""
    cat_repo = CategoryRepo(db)
    doc_repo = DocumentRepo(db)
    categories = await cat_repo.list_all()
    stats = await doc_repo.get_stats_by_domain()
    stats_map = {s["domain"]: s for s in stats}
    out: list[CategoryStats] = []
    for c in categories:
        s = stats_map.get(c.name, {})
        out.append(
            CategoryStats(
                name=c.name,
                is_builtin=c.is_builtin,
                file_count=int(s.get("file_count", 0) or 0),
                word_count=int(s.get("word_count", 0) or 0),
                last_updated=s.get("last_updated"),
            )
        )
    return out


@router.post("/categories", response_model=CategoryInfo)
async def create_category(req: CategoryCreate, db: AsyncSession = Depends(get_db)):
    name = req.name.strip().lower()
    if not name:
        raise HTTPException(status_code=400, detail="name required")
    repo = CategoryRepo(db)
    existing = await repo.get_by_name(name)
    if existing is not None:
        raise HTTPException(status_code=409, detail=f"category exists: {name}")
    try:
        cat = await repo.create(name=name, is_builtin=False)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    await db.commit()
    return CategoryInfo(id=cat.id, name=cat.name, is_builtin=cat.is_builtin)


@router.get("/categories/{domain}/documents", response_model=list[DocumentInfo])
async def list_documents(domain: str, db: AsyncSession = Depends(get_db)):
    repo = DocumentRepo(db)
    docs = await repo.list_by_domain(domain)
    return [_doc_to_info(d) for d in docs]


# ===========================================================================
# 两阶段导入：upload（解析+切块，不 embed） → confirm（embed+持久化）
# ===========================================================================


@router.post("/upload", response_model=PreviewSession)
async def upload_files(
    files: list[UploadFile] = File(...),
    domain: str = Form(...),
    chunk_strategy: str = Form("semantic"),
    chunk_size: int = Form(500),
    chunk_overlap: int = Form(50),
    db: AsyncSession = Depends(get_db),
):
    """Phase 1: 接收多文件，解析 + 切块，返回预览，不写库不 embed。"""
    if not files:
        raise HTTPException(status_code=400, detail="no files uploaded")
    if len(files) > settings.MAX_UPLOAD_FILES:
        raise HTTPException(
            status_code=400,
            detail=f"too many files: max {settings.MAX_UPLOAD_FILES} per batch",
        )

    cat_repo = CategoryRepo(db)
    cat = await cat_repo.get_by_name(domain.strip().lower())
    if cat is None:
        raise HTTPException(status_code=404, detail=f"category not found: {domain}")

    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    file_payloads: list[dict] = []
    for f in files:
        data = await f.read()
        if len(data) > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"file too large: {f.filename} (max {settings.MAX_UPLOAD_SIZE_MB}MB)",
            )
        parsed_text = parse_bytes(f.filename or "unknown.txt", data)
        chunks = _chunk_text(parsed_text, chunk_strategy, chunk_size, chunk_overlap)
        word_count = len(parsed_text)
        file_payloads.append(
            {
                "filename": f.filename or "unknown",
                "file_type": detect_file_type(f.filename or ""),
                "file_size_bytes": len(data),
                "parsed_text": parsed_text,
                "chunks": [c.text for c in chunks],
                "chunk_metas": [c.metadata for c in chunks],
                "word_count": word_count,
            }
        )

    session_id = uuid.uuid4()
    await preview_store.put(
        session_id,
        {
            "domain": cat.name,
            "chunk_strategy": chunk_strategy,
            "chunk_size": chunk_size,
            "chunk_overlap": chunk_overlap,
            "files": file_payloads,
        },
    )

    return PreviewSession(
        session_id=session_id,
        domain=cat.name,
        chunk_strategy=chunk_strategy,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        embedding_dimension=settings.EMBEDDING_DIMENSION,
        expires_in=settings.PREVIEW_SESSION_TTL,
        files=[
            FilePreview(
                filename=p["filename"],
                file_type=p["file_type"],
                file_size_bytes=p["file_size_bytes"],
                char_count=len(p["parsed_text"]),
                word_count=p["word_count"],
                chunk_count=len(p["chunks"]),
                sample_chunks=p["chunks"][:3],
            )
            for p in file_payloads
        ],
    )


@router.post("/confirm", response_model=ConfirmResponse, status_code=202)
async def confirm_import(req: ConfirmRequest):
    """Phase 2: 用户确认后，排队执行 embed + 持久化。
    立即返回 job_id，前端轮询 GET /knowledge/import/{job_id}/status。
    同步校验 preview session 有效性，失败立即 410。
    """
    data = await preview_store.get(req.session_id)
    if data is None:
        raise HTTPException(status_code=410, detail="preview session expired or not found")
    # 原子消费：立即 remove，避免并发/重复 confirm 在 import 进行中读到同一 session
    # 而创建第二个 job、重复插入 chunks。后台任务拿数据副本即可，不再依赖 session。
    await preview_store.remove(req.session_id)

    total_files = len(data["files"])
    total_chunks = sum(len(p["chunks"]) for p in data["files"])
    job = await import_job_store.create(total_files=total_files, total_chunks=total_chunks)

    payload = {
        "domain": data["domain"],
        "chunk_strategy": data["chunk_strategy"],
        "files": data["files"],
    }
    asyncio.create_task(_run_import(job.job_id, payload))
    return ConfirmResponse(job_id=job.job_id, status="pending")


async def _run_import(job_id: uuid.UUID, data: dict) -> None:
    """后台执行 embed + 持久化。使用独立 DB session，逐文件更新进度。"""
    await import_job_store.update(job_id, status="running")
    llm = OpenAIProvider()
    embedder = EmbeddingService(llm=llm)
    document_ids: list[uuid.UUID] = []
    processed_chunks = 0

    try:
        async with async_session_factory() as db:
            repo = DocumentRepo(db)
            for p in data["files"]:
                doc = Document(
                    domain=data["domain"],
                    title=p["filename"],
                    source=p["filename"],
                    file_type=p["file_type"],
                    file_size_bytes=p["file_size_bytes"],
                    word_count=p["word_count"],
                    chunk_count=len(p["chunks"]),
                    status="parsing",
                )
                db.add(doc)
                await db.flush()
                document_ids.append(doc.id)
                await import_job_store.update(
                    job_id, document_ids=list(document_ids)
                )

                chunks = p["chunks"]
                if chunks:

                    async def _on_progress(done: int, total: int) -> None:
                        await import_job_store.update(
                            job_id, processed_chunks=processed_chunks + done
                        )

                    embeddings = await embedder.embed(chunks, on_progress=_on_progress)
                    meta_base = {
                        "domain": data["domain"],
                        "title": p["filename"],
                        "source": p["filename"],
                        "chunk_strategy": data["chunk_strategy"],
                    }
                    chunk_metas = p.get("chunk_metas") or []
                    for i, (text, emb) in enumerate(zip(chunks, embeddings)):
                        per_chunk = chunk_metas[i] if i < len(chunk_metas) else {}
                        await repo.create_chunk(
                            document_id=doc.id,
                            content=text,
                            embedding=emb,
                            metadata={**meta_base, **per_chunk, "chunk_index": i},
                        )
                    processed_chunks += len(chunks)
                await repo.update_document(doc.id, status="indexed")
                await import_job_store.update(
                    job_id,
                    processed_chunks=processed_chunks,
                    processed_files=len(document_ids),
                )
            await db.commit()

        # 知识库变更，清除 chat 与 rag 检索缓存避免脏读
        from app.services.cache import cache_clear_prefix

        await cache_clear_prefix("chat:")
        await cache_clear_prefix("rag:")
        await import_job_store.update(job_id, status="succeeded")
        logger.info("import_job_succeeded job_id=%s docs=%d chunks=%d", job_id, len(document_ids), processed_chunks)
    except Exception as e:
        logger.exception("import_job_failed job_id=%s", job_id)
        # 整个 job 在单事务内，失败回滚 → 无孤儿文档
        await import_job_store.update(job_id, status="failed", error=str(e))


@router.get("/import/{job_id}/status", response_model=ImportJobStatus)
async def get_import_status(job_id: uuid.UUID):
    job = await import_job_store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="import job not found")
    return ImportJobStatus(
        job_id=job.job_id,
        status=job.status,
        total_files=job.total_files,
        processed_files=job.processed_files,
        total_chunks=job.total_chunks,
        processed_chunks=job.processed_chunks,
        document_ids=job.document_ids,
        error=job.error,
    )


# ===========================================================================
# 文档删除
# ===========================================================================


@router.delete("/documents/{document_id}")
async def delete_document(document_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    repo = DocumentRepo(db)
    ok = await repo.delete_with_chunks(document_id)
    if not ok:
        raise HTTPException(status_code=404, detail="document not found")
    await db.commit()
    # 知识库变更，清除 chat 与 rag 检索缓存避免脏读
    from app.services.cache import cache_clear_prefix

    await cache_clear_prefix("chat:")
    await cache_clear_prefix("rag:")
    return {"deleted": str(document_id)}


# ===========================================================================
# 检索（保留）
# ===========================================================================


@router.get("/search", response_model=SearchResponse)
async def search_knowledge(
    query: str,
    top_k: int = 5,
    mode: str = "hybrid",
    domain: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    llm = OpenAIProvider()
    retriever = VectorRetriever(db=db, llm=llm)
    rag_service = RAGService(db=db, retriever=retriever, llm=llm, mode=mode)  # type: ignore[arg-type]
    results = await rag_service.search(query, top_k=top_k, mode=mode, domain=domain)  # type: ignore[arg-type]
    return SearchResponse(
        results=[
            ChunkResult(
                id=chunk.id,
                document_id=chunk.document_id,
                content=chunk.content,
                metadata=chunk.metadata_,
                score=chunk.score,
            )
            for chunk in results
        ]
    )


# ===========================================================================
# 辅助
# ===========================================================================


def _strategy_for_domain(domain: str) -> str:
    d = (domain or "").lower()
    if "legal" in d or "法律" in d:
        return "legal"
    if "finance" in d or "金融" in d:
        return "finance"
    return "semantic"


def _chunk_text(text: str, strategy: str, chunk_size: int, overlap: int) -> list:
    if strategy == "legal":
        return chunk_legal(text, metadata={})
    if strategy == "finance":
        return chunk_finance(text, metadata={})
    return chunk_semantic(text, chunk_size=chunk_size, overlap=overlap, metadata={})


def _doc_to_info(d: Document) -> DocumentInfo:
    return DocumentInfo(
        id=d.id,
        domain=d.domain,
        title=d.title,
        source=d.source or "",
        file_type=d.file_type,
        file_size_bytes=d.file_size_bytes,
        word_count=d.word_count,
        chunk_count=d.chunk_count,
        status=d.status,
        created_at=d.created_at,
        updated_at=d.updated_at,
    )
