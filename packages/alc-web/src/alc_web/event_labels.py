"""Readable labels for task history; never display internal event identifiers."""
_LABELS = {
    'job.created': '任务已创建，等待开始', 'job.started': '开始处理文档',
    'job.finished': '本次处理已结束', 'job.local_recovery': '已恢复本地任务记录',
    'job.reader_repaired': '阅读页面已更新', 'source.acquired': '已取得原文',
    'llm_call_started': '准备请求模型', 'llm_provider_started': '模型正在处理',
    'llm_provider_finished': '模型已完成本次回复', 'llm_provider_failed': '模型请求失败',
    'llm_message': '正在交换模型处理内容', 'llm_pipe_activity': '模型仍在响应',
    'llm_usage': '已更新本次模型用量', 'llm_memory_guard_warning': '部分资源检查信息不可用',
    'optional_stage_skipped': '部分辅助信息未生成，正文继续处理', 'translation_progress': '已更新翻译进度', 'translation_fallback': '部分段落保留原文',
    'group_unit_finished': '已保存一部分处理结果', 'run_attempt_failed': '本次尝试未能完成',
    'run_warning': '处理过程中有提醒', 'run_terminal': '本轮处理已结束',
    'run_paused': '任务已暂停，等待继续',
    'proposer_reviewer_loop_started': '开始编写章节伴读',
    'proposer_reviewer_loop_finished': '章节伴读已完成',
    'proposer_reviewer_round_started': '开始一轮编写与审查',
    'proposer_reviewer_round_committed': '已保存本轮伴读结果',
    'proposer_reviewer_worker_started': '正在编写或审查伴读',
    'proposer_reviewer_worker_finished': '已完成一部分伴读编写或审查',
}


def event_label(event: dict) -> str:
    kind = event.get('kind')
    data = event.get('data') or {}
    if kind == 'job.control':
        return {'pause':'已请求暂停', 'resume':'已请求继续', 'cancel':'已请求取消',
                'retry_delivery':'重新生成交付文件'}.get(data.get('action'), '已更新任务操作')
    name = data.get('event') if kind == 'package.event' else kind
    return _LABELS.get(name, '任务进度已更新')
