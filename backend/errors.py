from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any


@dataclass
class AppError(Exception):
    code: str
    public_message: str
    http_status: int
    retryable: bool = False
    phase: str | None = None
    details_safe: dict[str, Any] | None = None


class ConfigurationError(AppError):
    def __init__(self, message: str = "模型服务尚未配置。") -> None:
        super().__init__("CONFIGURATION_ERROR", message, 503)


class DomainStateError(AppError):
    def __init__(self, message: str, code: str = "DOMAIN_STATE_ERROR") -> None:
        super().__init__(code, message, 409)


class ResourceNotFoundError(AppError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(code, message, 404)


class RequestValidationAppError(AppError):
    def __init__(self) -> None:
        super().__init__("REQUEST_VALIDATION_ERROR", "请求参数无效。", 422)


class ModelNotReadyError(AppError):
    def __init__(self) -> None:
        super().__init__("MODEL_NOT_READY", "模型服务尚未配置。", 503)


class HttpNotFoundError(AppError):
    def __init__(self) -> None:
        super().__init__("HTTP_NOT_FOUND", "请求的接口不存在。", 404)


class HttpMethodNotAllowedError(AppError):
    def __init__(self) -> None:
        super().__init__("HTTP_METHOD_NOT_ALLOWED", "当前请求方法不受支持。", 405)


class ModelSettingsAccessError(AppError):
    def __init__(self) -> None:
        super().__init__("MODEL_SETTINGS_ACCESS_DENIED", "本地模型配置接口未授权。", 403)


class DesktopAuthRequiredError(AppError):
    def __init__(self) -> None:
        super().__init__("DESKTOP_AUTH_REQUIRED", "本地桌面请求未通过授权。", 401)


class ModelSettingsValidationError(AppError):
    def __init__(self, message: str = "模型网关地址无效。") -> None:
        super().__init__("MODEL_SETTINGS_INVALID", message, 422)


class ModelCredentialStoreRequiredError(AppError):
    def __init__(self) -> None:
        super().__init__("MODEL_CREDENTIAL_STORE_REQUIRED", "生产模式不允许后端明文保存模型密钥，请通过桌面安全存储配置。", 409)


class UnexpectedBackendError(AppError):
    def __init__(self) -> None:
        super().__init__("BACKEND_UNEXPECTED_ERROR", "服务处理请求时出现未预期错误，请稍后重试。", 500, retryable=True)


class RequestRateLimitedError(AppError):
    def __init__(self) -> None:
        super().__init__("REQUEST_RATE_LIMITED", "请求过于频繁，请稍后重试。", 429, retryable=True)


class RequestBodyTooLargeError(AppError):
    def __init__(self) -> None:
        super().__init__("REQUEST_BODY_TOO_LARGE", "请求内容过大。", 413)


class ModelAuthenticationError(AppError):
    def __init__(self) -> None:
        super().__init__("MODEL_AUTHENTICATION_ERROR", "模型服务认证失败，请检查配置。", 503)


class ModelRateLimitError(AppError):
    def __init__(self, retry_after_seconds: float | None = None) -> None:
        bounded_retry_after = None
        if retry_after_seconds is not None:
            try:
                numeric_retry_after = float(retry_after_seconds)
            except (TypeError, ValueError):
                numeric_retry_after = 0.0
            if math.isfinite(numeric_retry_after) and numeric_retry_after > 0:
                bounded_retry_after = min(numeric_retry_after, 300.0)
        self.retry_after_seconds = bounded_retry_after
        details = (
            {"retry_after_seconds": bounded_retry_after}
            if bounded_retry_after is not None
            else None
        )
        super().__init__(
            "MODEL_RATE_LIMITED",
            "模型服务繁忙，请稍后重试。",
            429,
            retryable=True,
            details_safe=details,
        )


class ModelTimeoutError(AppError):
    def __init__(self) -> None:
        super().__init__("MODEL_TIMEOUT", "模型响应超时，请稍后重试。", 504, retryable=True)


class ModelUnavailableError(AppError):
    def __init__(self) -> None:
        super().__init__("MODEL_UNAVAILABLE", "模型服务暂时不可用，请稍后重试。", 503, retryable=True)


class WebSearchUnavailableError(AppError):
    def __init__(self) -> None:
        super().__init__("WEB_SEARCH_UNAVAILABLE", "在线检索服务暂时不可用，请检查网络后重试。", 503, retryable=True)


class ModelBadResponseError(AppError):
    def __init__(self, message: str = "模型返回内容无效。", code: str = "MODEL_BAD_RESPONSE") -> None:
        super().__init__(code, message, 502)


class ModelAccessError(AppError):
    def __init__(self, message: str = "当前密钥没有访问该模型的权限。") -> None:
        super().__init__("MODEL_ACCESS_DENIED", message, 403)


class ModelNotFoundError(AppError):
    def __init__(self, message: str = "指定的模型不存在或不可用。") -> None:
        super().__init__("MODEL_NOT_FOUND", message, 404)


class ModelProfileNotFoundError(AppError):
    def __init__(self) -> None:
        super().__init__("MODEL_PROFILE_NOT_FOUND", "指定的模型配置不存在。", 404)


class ModelProfileDisabledError(AppError):
    def __init__(self) -> None:
        super().__init__("MODEL_PROFILE_DISABLED", "指定的模型配置已停用。", 409)


class ModelProfileNeedsAttentionError(AppError):
    def __init__(self) -> None:
        super().__init__("MODEL_PROFILE_NEEDS_ATTENTION", "模型配置需要重新检查。", 409)


class ModelCapabilityUnsupportedError(AppError):
    def __init__(self) -> None:
        super().__init__("MODEL_CAPABILITY_UNSUPPORTED", "当前模型不支持所选能力。", 422)


class ModelFailoverExhaustedError(AppError):
    def __init__(self) -> None:
        super().__init__("MODEL_FAILOVER_EXHAUSTED", "可用模型服务均未能完成请求。", 503, retryable=True)


class ModelRuntimeSnapshotInvalidError(AppError):
    def __init__(self) -> None:
        super().__init__("MODEL_RUNTIME_SNAPSHOT_INVALID", "模型运行配置快照无效。", 422)


class ModelRuntimeApplyFailedError(AppError):
    def __init__(self) -> None:
        super().__init__("MODEL_RUNTIME_APPLY_FAILED", "模型运行配置应用失败。", 503)


class ModelStreamInterruptedError(AppError):
    def __init__(self) -> None:
        super().__init__("MODEL_STREAM_INTERRUPTED", "模型流式响应已中断。", 502, retryable=True)


class ProtocolValidationError(AppError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(code, message, 502)


class PersistenceError(AppError):
    def __init__(self) -> None:
        super().__init__("PERSISTENCE_ERROR", "本地数据保存失败，请稍后重试。", 500, retryable=True)


class ClientCancelledError(AppError):
    def __init__(self) -> None:
        super().__init__("CLIENT_CANCELLED", "生成已取消。", 499)


class ContentSafetyInputBlockedError(AppError):
    def __init__(self) -> None:
        super().__init__(
            "CONTENT_SAFETY_INPUT_BLOCKED",
            "请求未通过内容安全检查，请调整后重试。",
            422,
        )


class ContentSecretDetectedError(AppError):
    def __init__(self) -> None:
        super().__init__(
            "CONTENT_SECRET_DETECTED",
            "请求中可能包含密钥或凭据，已停止处理。",
            422,
        )


class ContentArtifactBlockedError(AppError):
    def __init__(self) -> None:
        super().__init__(
            "CONTENT_ARTIFACT_BLOCKED",
            "内容未通过安全检查，可以修改请求后重试。",
            422,
            retryable=True,
        )


class ContentCitationNotAllowedError(AppError):
    def __init__(self) -> None:
        super().__init__(
            "CONTENT_CITATION_NOT_ALLOWED",
            "内容包含未获许可的来源引用，请重试。",
            422,
            retryable=True,
        )


class SafetyReviewUnavailableError(AppError):
    def __init__(self) -> None:
        super().__init__(
            "SAFETY_REVIEW_UNAVAILABLE",
            "内容安全审核暂时不可用，请稍后重试。",
            503,
            retryable=True,
        )


class UnsafeRenderPayloadError(AppError):
    def __init__(self) -> None:
        super().__init__(
            "UNSAFE_RENDER_PAYLOAD",
            "内容包含不安全的渲染结构，已停止展示。",
            422,
        )


class KnowledgeFileTooLargeError(AppError):
    def __init__(self) -> None:
        super().__init__("KNOWLEDGE_FILE_TOO_LARGE", "单个文件不能超过 100 MB。", 422)


class KnowledgeFormatUnsupportedError(AppError):
    def __init__(self) -> None:
        super().__init__("KNOWLEDGE_FORMAT_UNSUPPORTED", "暂不支持这种文件格式。", 422)


class KnowledgeFileSignatureMismatchError(AppError):
    def __init__(self) -> None:
        super().__init__("KNOWLEDGE_FILE_SIGNATURE_MISMATCH", "文件内容与导入记录不一致。", 422)


class KnowledgeArchiveUnsafeError(AppError):
    def __init__(self) -> None:
        super().__init__("KNOWLEDGE_ARCHIVE_UNSAFE", "文件压缩结构不符合安全要求。", 422)


class KnowledgeDocumentEncryptedError(AppError):
    def __init__(self) -> None:
        super().__init__("KNOWLEDGE_DOCUMENT_ENCRYPTED", "暂不支持加密或密码保护的文件。", 422)


class KnowledgeParseTimeoutError(AppError):
    def __init__(self) -> None:
        super().__init__("KNOWLEDGE_PARSE_TIMEOUT", "资料解析超时，可以稍后重试。", 504, retryable=True)


class KnowledgeParseFailedError(AppError):
    def __init__(self) -> None:
        super().__init__("KNOWLEDGE_PARSE_FAILED", "资料解析失败，可以稍后重试。", 422, retryable=True)


class KnowledgeOcrPackRequiredError(AppError):
    def __init__(self) -> None:
        super().__init__("KNOWLEDGE_OCR_PACK_REQUIRED", "这份扫描资料需要安装本地 OCR 包。", 409)


class KnowledgeIndexUnavailableError(AppError):
    def __init__(self) -> None:
        super().__init__("KNOWLEDGE_INDEX_UNAVAILABLE", "本地知识库索引暂时不可用。", 503, retryable=True)


class KnowledgeImportCancelledError(AppError):
    def __init__(self) -> None:
        super().__init__("KNOWLEDGE_IMPORT_CANCELLED", "资料导入已取消。", 409)


class KnowledgeObjectMissingError(AppError):
    def __init__(self) -> None:
        super().__init__("KNOWLEDGE_OBJECT_MISSING", "本地资料文件不存在。", 404)


class KnowledgeCollectionConflictError(AppError):
    def __init__(self) -> None:
        super().__init__("KNOWLEDGE_COLLECTION_CONFLICT", "已存在同名知识库集合。", 409)


class KnowledgeImportNotRetryableError(AppError):
    def __init__(self) -> None:
        super().__init__(
            "KNOWLEDGE_IMPORT_NOT_RETRYABLE",
            "当前知识库导入任务不能重试。",
            409,
        )
