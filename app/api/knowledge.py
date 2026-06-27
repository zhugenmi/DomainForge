from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.configs.settings import settings
from app.database.models.document import Document
from app.database.repositories.category_repo import CategoryRepo
from app.database.repositories.document_repo import DocumentRepo
from app.database.session import get_db
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
    PreviewSession,
    SearchResponse,
)
from app.services.preview_store import preview_store

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


@router.post("/confirm", response_model=ConfirmResponse)
async def confirm_import(req: ConfirmRequest, db: AsyncSession = Depends(get_db)):
    """Phase 2: 用户确认后，对 preview session 执行 embed + 持久化。"""
    data = await preview_store.get(req.session_id)
    if data is None:
        raise HTTPException(status_code=410, detail="preview session expired or not found")

    llm = OpenAIProvider()
    embedder = EmbeddingService(llm=llm)
    repo = DocumentRepo(db)

    document_ids: list[uuid.UUID] = []
    total_chunks = 0
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

        chunks = p["chunks"]
        if chunks:
            embeddings = await embedder.embed(chunks)
            meta_base = {
                "domain": data["domain"],
                "title": p["filename"],
                "source": p["filename"],
                "chunk_strategy": data["chunk_strategy"],
            }
            for i, (text, emb) in enumerate(zip(chunks, embeddings)):
                await repo.create_chunk(
                    document_id=doc.id,
                    content=text,
                    embedding=emb,
                    metadata={**meta_base, "chunk_index": i},
                )
                total_chunks += 1
        await repo.update_document(doc.id, status="indexed")

    await preview_store.remove(req.session_id)
    await db.commit()
    # 知识库变更，清除 chat 与 rag 检索缓存避免脏读
    from app.services.cache import cache_clear_prefix

    await cache_clear_prefix("chat:")
    await cache_clear_prefix("rag:")
    return ConfirmResponse(document_ids=document_ids, total_chunks=total_chunks)


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
