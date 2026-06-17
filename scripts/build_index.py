#!/usr/bin/env python
"""批量构建知识库索引。

用法:
    python scripts/build_index.py --dir data/raw_documents/legal --domain legal
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# 让脚本可以直接运行
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database.session import async_session_factory  # noqa: E402
from app.llm.embedding.embedding_service import EmbeddingService  # noqa: E402
from app.llm.providers.openai import OpenAIProvider  # noqa: E402
from app.rag.indexing.pipeline import IndexingPipeline  # noqa: E402


async def main(args: argparse.Namespace) -> int:
    root = Path(args.dir)
    if not root.exists():
        print(f"[error] 目录不存在: {root}")
        return 1

    files = sorted(p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in {
        ".txt", ".md", ".markdown", ".html", ".htm", ".pdf", ".docx",
    })
    if not files:
        print(f"[warn] 目录中无支持的文档: {root}")
        return 0

    llm = OpenAIProvider()
    embedder = EmbeddingService(llm=llm)

    async with async_session_factory() as db:
        pipeline = IndexingPipeline(db=db, embedder=embedder)
        total_chunks = 0
        for f in files:
            try:
                res = await pipeline.index_file(
                    domain=args.domain,
                    path=f,
                    chunk_strategy=args.strategy,
                )
                total_chunks += res.chunk_count
                print(f"[ok] {f.name}: {res.chunk_count} chunks (doc={res.document_id})")
            except Exception as e:
                print(f"[fail] {f.name}: {e}")
        await db.commit()

    print(f"\n[done] {len(files)} 文档, {total_chunks} chunks 已索引")
    return 0


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="批量构建知识库索引")
    p.add_argument("--dir", required=True, help="待索引的文档目录")
    p.add_argument("--domain", required=True, help="领域标识 (legal/finance/...)")
    p.add_argument("--strategy", default="semantic", choices=["semantic", "legal", "finance"],
                   help="分块策略 (默认 semantic，按 domain 可选 legal/finance)")
    return p.parse_args()


if __name__ == "__main__":
    sys.exit(asyncio.run(main(parse_args())))
