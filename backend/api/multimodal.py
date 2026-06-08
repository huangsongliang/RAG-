"""多模态问答 API 路由"""

import tempfile
from pathlib import Path
from typing import List, Optional
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from backend.chain.multimodal_chain import get_multimodal_rag_chain
from backend.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/multimodal", tags=["多模态问答"])


class MultimodalChatResponse(BaseModel):
    """多模态聊天响应"""

    answer: str
    session_id: str
    image_descriptions: List[str] = []
    references: List[dict] = []


class ImageDescriptionResponse(BaseModel):
    """图片描述响应"""

    description: str


@router.post("/chat", response_model=MultimodalChatResponse)
async def multimodal_chat(
    message: str = Form(..., description="用户消息"),
    files: List[UploadFile] = File(default=[]),
    session_id: Optional[str] = Form(None),
    use_rag: bool = Form(True),
    top_k: int = Form(3),
):
    """多模态聊天接口（FormData 上传图片+文本）"""
    try:
        sid = session_id or str(uuid4())
        allowed_extensions = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}
        tmp_paths: List[str] = []
        tmp_files: List[str] = []

        for file in files:
            if not file.filename:
                continue
            file_ext = Path(file.filename).suffix.lower()
            if file_ext not in allowed_extensions:
                raise HTTPException(status_code=400, detail=f"不支持的图片格式: {file_ext}")

            content = await file.read()
            with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as tmp_file:
                tmp_file.write(content)
                tmp_paths.append(tmp_file.name)
                tmp_files.append(tmp_file.name)

        try:
            mm_chain = get_multimodal_rag_chain()
            result = await mm_chain.async_run(
                query=message,
                image_paths=tmp_paths,
                top_k=top_k,
                use_rag=use_rag,
            )

            return MultimodalChatResponse(
                answer=result["answer"],
                session_id=sid,
                image_descriptions=result.get("image_descriptions", []),
                references=result.get("references", []),
            )
        finally:
            for p in tmp_files:
                if Path(p).exists():
                    Path(p).unlink()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"多模态聊天失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"多模态聊天失败: {str(e)}")


@router.post("/chat/image-only")
async def chat_with_image_only(
    message: str = Form(..., description="用户消息"),
    file: UploadFile = File(...),
):
    """仅使用图片进行问答（不进行 RAG 检索）"""
    try:
        if not file.filename:
            raise HTTPException(status_code=400, detail="文件名不能为空")

        allowed_extensions = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}
        file_ext = Path(file.filename).suffix.lower()

        if file_ext not in allowed_extensions:
            raise HTTPException(status_code=400, detail=f"不支持的图片格式: {file_ext}")

        with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as tmp_file:
            content = await file.read()
            tmp_file.write(content)
            tmp_file_path = tmp_file.name

        try:
            mm_chain = get_multimodal_rag_chain()
            answer = await mm_chain.async_answer_with_images(
                query=message,
                image_paths=[tmp_file_path],
                context="",
            )

            description = mm_chain.vision_processor.describe_image(tmp_file_path)

            return {
                "answer": answer,
                "image_description": description,
                "image_name": file.filename,
            }

        finally:
            if Path(tmp_file_path).exists():
                Path(tmp_file_path).unlink()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"图片问答失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"图片问答失败: {str(e)}")


@router.post("/describe")
async def describe_image(file: UploadFile = File(...)):
    """描述单张图片"""
    try:
        if not file.filename:
            raise HTTPException(status_code=400, detail="文件名不能为空")

        allowed_extensions = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}
        file_ext = Path(file.filename).suffix.lower()

        if file_ext not in allowed_extensions:
            raise HTTPException(status_code=400, detail=f"不支持的图片格式: {file_ext}")

        with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as tmp_file:
            content = await file.read()
            tmp_file.write(content)
            tmp_file_path = tmp_file.name

        try:
            mm_chain = get_multimodal_rag_chain()
            description = mm_chain.vision_processor.describe_image(tmp_file_path)

            return {
                "description": description,
                "image_name": file.filename,
            }

        finally:
            if Path(tmp_file_path).exists():
                Path(tmp_file_path).unlink()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"图片描述失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"图片描述失败: {str(e)}")


@router.post("/extract-text")
async def extract_text_from_image(file: UploadFile = File(...)):
    """从图片中提取文字"""
    try:
        if not file.filename:
            raise HTTPException(status_code=400, detail="文件名不能为空")

        allowed_extensions = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}
        file_ext = Path(file.filename).suffix.lower()

        if file_ext not in allowed_extensions:
            raise HTTPException(status_code=400, detail=f"不支持的图片格式: {file_ext}")

        with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as tmp_file:
            content = await file.read()
            tmp_file.write(content)
            tmp_file_path = tmp_file.name

        try:
            mm_chain = get_multimodal_rag_chain()
            text = mm_chain.vision_processor.extract_text_from_image(tmp_file_path)

            return {
                "text": text,
                "image_name": file.filename,
            }

        finally:
            if Path(tmp_file_path).exists():
                Path(tmp_file_path).unlink()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"图片文字提取失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"图片文字提取失败: {str(e)}")


@router.post("/batch/descriptions")
async def batch_describe_images(files: List[UploadFile] = File(...)):
    """批量描述多张图片"""
    results = []
    errors = []

    for file in files:
        try:
            if not file.filename:
                errors.append({"file": "unknown", "error": "文件名为空"})
                continue

            allowed_extensions = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}
            file_ext = Path(file.filename).suffix.lower()

            if file_ext not in allowed_extensions:
                errors.append({"file": file.filename, "error": f"不支持的格式: {file_ext}"})
                continue

            with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as tmp_file:
                content = await file.read()
                tmp_file.write(content)
                tmp_file_path = tmp_file.name

            try:
                mm_chain = get_multimodal_rag_chain()
                description = mm_chain.vision_processor.describe_image(tmp_file_path)

                results.append(
                    {
                        "file": file.filename,
                        "description": description,
                        "status": "success",
                    }
                )

            finally:
                if Path(tmp_file_path).exists():
                    Path(tmp_file_path).unlink()

        except Exception as e:
            errors.append({"file": file.filename, "error": str(e)})

    return {
        "success_count": len(results),
        "error_count": len(errors),
        "results": results,
        "errors": errors,
    }


@router.get("/supported-models")
async def get_supported_models():
    """获取支持的视觉模型"""
    return {
        "models": [
            {
                "provider": "openai",
                "name": "GPT-4o",
                "description": "OpenAI 最新多模态模型，支持图片理解和分析",
                "api_key_required": True,
            },
            {
                "provider": "anthropic",
                "name": "Claude 3 Opus",
                "description": "Anthropic 高级多模态模型",
                "api_key_required": True,
            },
            {
                "provider": "qwen",
                "name": "Qwen-VL-Max",
                "description": "阿里通义千问视觉大模型",
                "api_key_required": True,
            },
        ]
    }
