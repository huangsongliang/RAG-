"""文档管理服务层 - 处理文档上传、索引、版本管理等"""

import hashlib
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.data_loader.chunker import get_chunker
from backend.data_loader.loader import DocumentLoader
from backend.database.models import Document, DocumentLibrary, DocumentVersion
from backend.database.session import get_db_session
from backend.retrieval import get_vector_store, reload_hybrid_retriever
from backend.utils.logger import get_logger

logger = get_logger(__name__)


class DocumentManager:
    """文档管理器"""

    def __init__(self, upload_dir: str = "data/uploads"):
        self.upload_dir = Path(upload_dir)
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.vector_store = get_vector_store()
        self.document_loader = DocumentLoader()

    async def upload_document(
        self,
        file_content: str,
        file_name: str,
        description: Optional[str] = None,
        chunk_size: int = 512,
        chunk_overlap: int = 100,
    ) -> Dict[str, Any]:
        """
        上传并索引文档

        重复检测规则：
        - 相同内容 + 相同文件名 + 活跃状态 → 跳过，返回已有文档信息
        - 相同文件名 + 不同内容 + 活跃状态 → 自动版本更新

        Args:
            file_content: 文件内容
            file_name: 文件名
            description: 文档描述
            chunk_size: 分块大小
            chunk_overlap: 分块重叠

        Returns:
            上传结果
        """
        file_hash = self._compute_hash(file_content)

        try:
            async with get_db_session() as session:
                # 1. 内容去重：相同 hash + 相同文件名 + 活跃
                exact_duplicate = await session.execute(
                    select(DocumentLibrary).where(
                        DocumentLibrary.file_hash == file_hash,
                        DocumentLibrary.name == file_name,
                        DocumentLibrary.is_active.is_(True),
                    )
                )
                exact_duplicate = exact_duplicate.scalar_one_or_none()

                if exact_duplicate:
                    logger.info(
                        "文档内容未变化，跳过重复上传: %s (doc_id=%s)",
                        file_name,
                        exact_duplicate.document_id,
                    )
                    return {
                        "success": True,
                        "skipped": True,
                        "document_id": exact_duplicate.document_id,
                        "file_name": file_name,
                        "message": f"文档「{file_name}」内容未变化，已跳过重复上传",
                    }

                # 2. 同名文档 → 自动版本更新
                existing_by_name = await session.execute(
                    select(DocumentLibrary).where(
                        DocumentLibrary.name == file_name,
                        DocumentLibrary.is_active.is_(True),
                    )
                )
                existing_by_name = existing_by_name.scalar_one_or_none()

                if existing_by_name:
                    document_id = existing_by_name.document_id
                    file_path = self.upload_dir / f"{document_id}_{file_name}"
                    with open(file_path, "w", encoding="utf-8") as f:
                        f.write(file_content)

                    await self._update_document(
                        session,
                        existing_by_name,
                        file_content,
                        file_name,
                        file_hash,
                        len(file_content),
                        description,
                        chunk_size,
                        chunk_overlap,
                    )
                    await session.commit()

                    reload_hybrid_retriever()

                    logger.info(
                        "文档版本更新成功: %s v%s (doc_id=%s)",
                        file_name,
                        existing_by_name.version,
                        document_id,
                    )

                    return {
                        "success": True,
                        "document_id": document_id,
                        "file_name": file_name,
                        "version": existing_by_name.version,
                        "message": f"文档「{file_name}」已更新至 v{existing_by_name.version}",
                    }

                # 3. 全新文档
                document_id = str(uuid.uuid4())
                file_path = self.upload_dir / f"{document_id}_{file_name}"
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(file_content)

                await self._create_document(
                    session,
                    document_id,
                    file_content,
                    file_name,
                    str(file_path),
                    file_hash,
                    len(file_content),
                    description,
                    chunk_size,
                    chunk_overlap,
                )
                await session.commit()

                reload_hybrid_retriever()

                logger.info("文档上传成功: %s (doc_id=%s)", file_name, document_id)

                return {
                    "success": True,
                    "document_id": document_id,
                    "file_name": file_name,
                }

        except Exception as e:
            logger.error(f"文档上传失败: {e}")
            return {
                "success": False,
                "error": str(e),
            }

    async def _create_document(
        self,
        session: AsyncSession,
        document_id: str,
        file_content: str,
        file_name: str,
        file_path: str,
        file_hash: str,
        file_size: int,
        description: Optional[str],
        chunk_size: int,
        chunk_overlap: int,
    ):
        """创建新文档"""
        mime_type = self._guess_mime_type(file_name)

        doc_lib = DocumentLibrary(
            name=file_name,
            description=description,
            document_id=document_id,
            file_path=file_path,
            file_hash=file_hash,
            file_size=file_size,
            mime_type=mime_type,
            version=1,
            is_active=True,
        )
        session.add(doc_lib)

        version = DocumentVersion(
            document_id=document_id,
            version=1,
            file_path=file_path,
            file_hash=file_hash,
            file_size=file_size,
            change_log="Initial upload",
        )
        session.add(version)

        chunks = self._chunk_document(file_content, file_name, chunk_size, chunk_overlap)
        await self._index_chunks(session, document_id, file_name, chunks)

        doc_lib.chunk_count = len(chunks)

    async def _update_document(
        self,
        session: AsyncSession,
        existing_doc: DocumentLibrary,
        file_content: str,
        file_name: str,
        file_hash: str,
        file_size: int,
        description: Optional[str],
        chunk_size: int,
        chunk_overlap: int,
    ):
        """更新文档"""
        if existing_doc.file_hash == file_hash:
            logger.info("文档未变化，跳过更新")
            return

        old_version = existing_doc.version
        new_version = old_version + 1

        existing_doc.version = new_version
        existing_doc.file_hash = file_hash
        existing_doc.file_size = file_size
        existing_doc.updated_at = datetime.now()
        if description:
            existing_doc.description = description

        version = DocumentVersion(
            document_id=existing_doc.document_id,
            version=new_version,
            file_path=existing_doc.file_path,
            file_hash=file_hash,
            file_size=file_size,
            change_log=f"Updated from v{old_version}",
        )
        session.add(version)

        stmt = select(Document).where(Document.document_id == existing_doc.document_id)
        result = await session.execute(stmt)
        old_chunks = result.scalars().all()

        for chunk in old_chunks:
            await session.delete(chunk)

        chunks = self._chunk_document(file_content, file_name, chunk_size, chunk_overlap)
        await self._index_chunks(
            session,
            existing_doc.document_id,
            file_name,
            chunks,
        )

        existing_doc.chunk_count = len(chunks)

    def _chunk_document(
        self,
        content: str,
        file_name: str,
        chunk_size: int,
        chunk_overlap: int,
    ) -> List[str]:
        """分块文档"""
        chunker = get_chunker(file_name, chunk_size, chunk_overlap)
        chunks = chunker.split_text(content)
        logger.debug(f"文档分块完成: {len(chunks)} chunks")
        return chunks

    async def _index_chunks(
        self,
        session: AsyncSession,
        document_id: str,
        source: str,
        chunks: List[str],
    ):
        """索引文档分块"""
        doc_chunks = []
        for idx, chunk in enumerate(chunks):
            doc = Document(
                content=chunk,
                source=source,
                document_id=document_id,
                chunk_index=idx,
                total_chunks=len(chunks),
                metadata_json=json.dumps(
                    {
                        "source": source,
                        "document_id": document_id,
                        "chunk_index": idx,
                        "total_chunks": len(chunks),
                    }
                ),
            )
            session.add(doc)
            doc_chunks.append(chunk)

        metadatas = [
            {
                "source": source,
                "document_id": document_id,
                "chunk_index": idx,
                "total_chunks": len(chunks),
            }
            for idx in range(len(chunks))
        ]

        ids = [f"{document_id}_chunk_{i}" for i in range(len(chunks))]
        self.vector_store.add_documents(doc_chunks, ids, metadatas)

    async def list_documents(
        self,
        skip: int = 0,
        limit: int = 100,
        include_inactive: bool = False,
    ) -> List[Dict[str, Any]]:
        """列出文档"""
        async with get_db_session() as session:
            stmt = select(DocumentLibrary)

            if not include_inactive:
                stmt = stmt.where(DocumentLibrary.is_active)

            stmt = stmt.order_by(DocumentLibrary.updated_at.desc())
            stmt = stmt.offset(skip).limit(limit)

            result = await session.execute(stmt)
            docs = result.scalars().all()

            return [
                {
                    "id": doc.id,
                    "document_id": doc.document_id,
                    "name": doc.name,
                    "description": doc.description,
                    "chunk_count": doc.chunk_count,
                    "version": doc.version,
                    "is_active": doc.is_active,
                    "created_at": doc.created_at.isoformat(),
                    "updated_at": doc.updated_at.isoformat(),
                }
                for doc in docs
            ]

    async def delete_document(
        self,
        document_id: str,
        soft_delete: bool = True,
    ) -> Dict[str, Any]:
        """删除文档"""
        try:
            async with get_db_session() as session:
                stmt = select(DocumentLibrary).where(DocumentLibrary.document_id == document_id)
                result = await session.execute(stmt)
                doc = result.scalar_one_or_none()

                if not doc:
                    return {
                        "success": False,
                        "error": "Document not found",
                    }

                if soft_delete:
                    doc.is_active = False
                else:
                    await session.delete(doc)

                    chunk_stmt = select(Document).where(Document.document_id == document_id)
                    chunks = (await session.execute(chunk_stmt)).scalars().all()
                    for chunk in chunks:
                        await session.delete(chunk)

                    if doc.file_path and Path(doc.file_path).exists():
                        Path(doc.file_path).unlink()

                await session.commit()

                logger.info(f"文档删除成功: {document_id}")
                return {"success": True}

        except Exception as e:
            logger.error(f"文档删除失败: {e}")
            return {"success": False, "error": str(e)}

    async def get_document_content(
        self,
        document_id: str,
    ) -> Dict[str, Any]:
        """获取文档内容"""
        try:
            async with get_db_session() as session:
                stmt = select(DocumentLibrary).where(DocumentLibrary.document_id == document_id)
                result = await session.execute(stmt)
                doc = result.scalar_one_or_none()

                if not doc:
                    return {"success": False, "error": "Document not found"}

                file_path = Path(doc.file_path)
                if not file_path.exists():
                    return {"success": False, "error": "File not found"}

                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()

                return {
                    "success": True,
                    "content": content,
                    "name": doc.name,
                }

        except Exception as e:
            logger.error(f"获取文档内容失败: {e}")
            return {"success": False, "error": str(e)}

    async def get_document_versions(
        self,
        document_id: str,
    ) -> List[Dict[str, Any]]:
        """获取文档版本历史"""
        async with get_db_session() as session:
            stmt = (
                select(DocumentVersion)
                .where(DocumentVersion.document_id == document_id)
                .order_by(DocumentVersion.version.desc())
            )

            result = await session.execute(stmt)
            versions = result.scalars().all()

            return [
                {
                    "version": v.version,
                    "file_size": v.file_size,
                    "change_log": v.change_log,
                    "created_at": v.created_at.isoformat(),
                }
                for v in versions
            ]

    def _compute_hash(self, content: str) -> str:
        """计算文件哈希"""
        return hashlib.md5(content.encode("utf-8"), usedforsecurity=False).hexdigest()

    def _guess_mime_type(self, file_name: str) -> str:
        """猜测文件类型"""
        ext = Path(file_name).suffix.lower()
        mime_map = {
            ".txt": "text/plain",
            ".md": "text/markdown",
            ".markdown": "text/markdown",
            ".json": "application/json",
            ".csv": "text/csv",
            ".html": "text/html",
        }
        return mime_map.get(ext, "application/octet-stream")


_document_manager: Optional[DocumentManager] = None


def get_document_manager() -> DocumentManager:
    """获取文档管理器实例"""
    global _document_manager
    if _document_manager is None:
        _document_manager = DocumentManager()
        logger.info("文档管理器已初始化")
    return _document_manager
