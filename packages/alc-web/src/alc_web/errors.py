"""User-facing explanations without exposing provider response bodies or secrets."""
from collections.abc import Mapping


def explain_error(error: Mapping, provider: Mapping | None = None) -> str:
    statuses = set()
    codes = set()
    source_structure_error = False
    def visit(value):
        nonlocal source_structure_error
        if isinstance(value, Mapping):
            for key, item in value.items():
                if key == 'message' and isinstance(item, str) and item.startswith((
                    'Figure panel layout ', 'Figure content ', 'caption ', 'conflicting caption ',
                    'multiple authored captions ', 'source notes in HTML ',
                    'unsupported Table cell presentation ', 'conflicting Table cell presentation ',
                    'HTML semantic heading ', 'HTML inline field ',
                )):
                    source_structure_error = True
                if key == 'http_status' and isinstance(item, int):
                    statuses.add(item)
                elif key in {'code', 'ac_error_code', 'category'} and isinstance(item, str):
                    codes.add(item)
                elif isinstance(item, (Mapping, list)):
                    visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)
    visit(error)
    if 404 in statuses and provider:
        from urllib.parse import urlsplit
        try:
            path = urlsplit(str(provider.get("base_url", ""))).path.rstrip("/")
        except ValueError:
            path = ""
        if path.endswith(("/chat/completions", "/responses", "/messages")):
            return '当前任务把完整 API 接口地址填进了 Base URL，程序追加接口路径后请求到了不存在的地址（404）。请把 Base URL 改为服务根地址（例如域名后只到 /v1），选择服务支持的协议，然后新建任务。旧任务的连接参数已固定，不会自动采用新配置。'
    if 404 in statuses:
        return '模型服务返回 404：没有找到请求的接口或模型。请在“模型与设置”核对 Base URL、协议类型和模型 ID；修正配置后重新新建任务；已创建任务的模型参数不会随设置自动改变。仅凭 404 暂时无法确定是哪一项配置错误。'
    if 402 in statuses:
        return '模型服务返回支付或余额不足错误（402）。请检查服务账户余额；已完成内容已保存，处理后可恢复。'
    if 'runtime_changed' in codes:
        return '任务已有进度与当前运行版本不兼容，已保留已有结果。需要先确认兼容迁移，避免混用不同版本的处理结果。'
    if 'timeout' in codes or 'provider_timeout' in codes:
        return '模型响应超时，已完成内容已保存。系统会在允许的次数内自动等待后重试，也可手动恢复。'
    if statuses & {401, 403}:
        return '模型服务拒绝了访问。请检查 API key 是否有效，以及账号是否有该模型的使用权限；修正后再恢复任务。'
    if 429 in statuses:
        return '模型服务限制了请求，可能达到调用频率或账号额度上限。请检查服务商额度，稍后重试，或在新任务中降低处理并发。'
    if any(s >= 500 for s in statuses):
        return '模型服务暂时出现服务器错误。已完成的进度会保留，可稍后恢复任务。'
    if 'provider_transport' in codes or 'transport' in codes:
        return '与模型服务的连接未能完成。请检查网络和所选 CLI/API 服务是否可用，然后恢复任务；已完成的进度会保留。'
    if 'provider_invalid_request' in codes:
        return '模型服务不接受当前请求。请检查所选协议、模型 ID 和参数是否受支持；修改模型参数后请重新新建任务。'
    if 'chapter_source_read_incomplete' in codes:
        return '伴读生成未通过原文读取完整性检查：部分原文没有完整读取记录。已完成的翻译和部分 Reader 已保留；这不是文档解析或校对次数错误。请使用更新后的流程新建伴读任务，程序会先准备完整章节内容。'
    if 'chapter_evidence_unavailable' in codes:
        return '伴读所需的原文或译文未能完整载入，尚未开始该章节的伴读生成。已完成的翻译已保留，可以恢复重试。'
    if 'chapter_evidence_too_large' in codes:
        return '该章节的原文和译文超过单次伴读的输入容量，未将截断内容交给模型。已完成的翻译已保留；请按章节拆分材料后处理。'
    if error.get('code') == 'source_attention':
        return '来源文件无法完整读取。若文档引用了图片或其他本地文件，请一并放在上传文件夹内，并使用文件夹内的相对路径。'
    if source_structure_error:
        return '原文中的图片、表格或文本结构未能可靠转换，任务在解析阶段暂停。原始文件和已完成结果已保留；这不是模型或并发设置错误。请尝试同一文章的其他格式，例如 PDF 或 HTML。'
    if error.get('code') == 'workflow_attention':
        return '任务在处理过程中暂停，当前记录不足以确定具体原因。已完成的进度会保留。'
    return '任务未能完成，暂未识别出具体原因。已完成的结果已保留。'
