#!/usr/bin/env python
"""导入单个文档到知识库。

用法:
    python scripts/import_documents.py --file path/to/doc.pdf --domain legal --title "民法典"
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database.session import async_session_factory  # noqa: E402
from app.llm.embedding.embedding_service import EmbeddingService  # noqa: E402
from app.llm.providers.openai import OpenAIProvider  # noqa: E402
from app.rag.indexing.pipeline import IndexingPipeline  # noqa: E402


async def main(args: argparse.Namespace) -> int:
    p = Path(args.file)
    if not p.exists():
        print(f"[error] 文件不存在: {p}")
        return 1

    llm = OpenAIProvider()
    embedder = EmbeddingService(llm=llm)

    async with async_session_factory() as db:
        pipeline = IndexingPipeline(db=db, embedder=embedder)
        res = await pipeline.index_file(
            domain=args.domain,
            path=p,
            title=args.title,
            chunk_strategy=args.strategy,
        )
        await db.commit()

    print(f"[ok] document_id={res.document_id} chunks={res.chunk_count}")
    return 0


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="导入单个文档到知识库")
    p.add_argument("--file", required=True, help="文档路径")
    p.add_argument("--domain", required=True)
    p.add_argument("--title", default=None)
    p.add_argument("--strategy", default="semantic", choices=["semantic", "legal", "finance"])
    return p.parse_args()


if __name__ == "__main__":
    sys.exit(asyncio.run(main(parse_args())))
