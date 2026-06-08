"""文档管理 API 路由"""

import tempfile
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from backend.data_loader.manager import get_document_manager
from backend.data_loader.pdf_processor import extract_pdf_text
from backend.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/documents", tags=["documents"])


class DocumentUploadResponse(BaseModel):
    """文档上传响应"""

    success: bool
    document_id: Optional[str] = None
    file_name: Optional[str] = None
    error: Optional[str] = None
    skipped: Optional[bool] = None
    version: Optional[int] = None
    message: Optional[str] = None


class DocumentInfo(BaseModel):
    """文档信息"""

    id: int
    document_id: str
    name: str
    description: Optional[str] = None
    chunk_count: int
    version: int
    is_active: bool
    created_at: str
    updated_at: str


class DocumentListResponse(BaseModel):
    """文档列表响应"""

    documents: List[DocumentInfo]
    total: int


class DocumentVersionInfo(BaseModel):
    """文档版本信息"""

    version: int
    file_size: int
    change_log: Optional[str] = None
    created_at: str


class SimpleResponse(BaseModel):
    """简单响应"""

    success: bool
    error: Optional[str] = None


@router.post("/upload", response_model=DocumentUploadResponse)
async def upload_document(
    file: UploadFile = File(..., description="上传的文件"),
    description: Optional[str] = Form(None, description="文档描述"),
    chunk_size: int = Form(512, description="分块大小"),
    chunk_overlap: int = Form(100, description="分块重叠"),
):
    """
    上传文档并索引

    支持的文件类型：
    - .txt: 普通文本文件
    - .md: Markdown 文件
    - .json: JSON 文件
    - .csv: CSV 文件
    """
    try:
        content = await file.read()
        file_name = file.filename or "unknown.txt"
        ext = Path(file_name).suffix.lower()

        if ext == ".pdf":
            # PDF 文件：写入临时文件，使用 PDFProcessor 提取文本
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp.write(content)
                tmp_path = tmp.name

            try:
                text_content = extract_pdf_text(tmp_path, use_ocr=True)
            finally:
                Path(tmp_path).unlink(missing_ok=True)

            if not text_content.strip():
                return DocumentUploadResponse(
                    success=False,
                    error="PDF 文件未能提取到文本内容（可能是扫描件且 OCR 不可用）",
                )
            logger.info(f"PDF 文本提取成功: {len(text_content)} 字符, file={file_name}")
        else:
            # 非 PDF 文件：文本解码
            try:
                text_content = content.decode("utf-8")
            except UnicodeDecodeError:
                text_content = content.decode("gbk", errors="replace")

        doc_manager = get_document_manager()
        result = await doc_manager.upload_document(
            file_content=text_content,
            file_name=file_name,
            description=description,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

        if result.get("success"):
            return DocumentUploadResponse(
                success=True,
                document_id=result.get("document_id"),
                file_name=result.get("file_name"),
                skipped=result.get("skipped"),
                version=result.get("version"),
                message=result.get("message"),
            )
        else:
            return DocumentUploadResponse(
                success=False,
                error=result.get("error"),
            )

    except Exception as e:
        logger.error(f"文档上传失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/list", response_model=DocumentListResponse)
async def list_documents(
    skip: int = 0,
    limit: int = 100,
    include_inactive: bool = False,
):
    """
    列出已上传的文档

    Args:
        skip: 跳过数量
        limit: 返回数量
        include_inactive: 是否包含已删除的文档
    """
    try:
        doc_manager = get_document_manager()
        docs = await doc_manager.list_documents(
            skip=skip,
            limit=limit,
            include_inactive=include_inactive,
        )

        return DocumentListResponse(
            documents=[DocumentInfo(**doc) for doc in docs],
            total=len(docs),
        )

    except Exception as e:
        logger.error(f"获取文档列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{document_id}", response_model=SimpleResponse)
async def delete_document(
    document_id: str,
    soft_delete: bool = True,
):
    """
    删除文档

    Args:
        document_id: 文档ID
        soft_delete: 是否软删除（默认软删除）
    """
    try:
        doc_manager = get_document_manager()
        result = await doc_manager.delete_document(
            document_id=document_id,
            soft_delete=soft_delete,
        )

        if not result.get("success"):
            if "not found" in result.get("error", "").lower():
                raise HTTPException(status_code=404, detail=result.get("error"))
            raise HTTPException(status_code=500, detail=result.get("error"))

        return SimpleResponse(**result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除文档失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{document_id}/versions")
async def get_document_versions(document_id: str):
    """
    获取文档版本历史

    Args:
        document_id: 文档ID
    """
    try:
        doc_manager = get_document_manager()
        versions = await doc_manager.get_document_versions(document_id)

        return {
            "document_id": document_id,
            "versions": versions,
        }

    except Exception as e:
        logger.error(f"获取文档版本历史失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class DocumentContentResponse(BaseModel):
    """文档内容响应"""

    success: bool
    content: Optional[str] = None
    name: Optional[str] = None
    error: Optional[str] = None


@router.get("/{document_id}/content", response_model=DocumentContentResponse)
async def get_document_content(document_id: str):
    """
    获取文档内容

    Args:
        document_id: 文档ID
    """
    try:
        doc_manager = get_document_manager()
        result = await doc_manager.get_document_content(document_id)

        if not result.get("success"):
            if "not found" in result.get("error", "").lower():
                raise HTTPException(status_code=404, detail=result.get("error"))
            raise HTTPException(status_code=500, detail=result.get("error"))

        return DocumentContentResponse(**result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取文档内容失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
