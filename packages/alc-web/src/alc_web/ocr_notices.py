"""Present source ambiguities and unapplied OCR work separately."""

from alc_ocr_proofread.review_policy import issue_kind
import re



def structure_notice_kind(issue):
    """Classify presentation only; retain the original model assessment."""
    reason = str(issue.get("reason", ""))
    if re.search(r"terminal period|sentence[- ]ending punctuation|句末[标句]点|句末标点", reason, re.I):
        return "punctuation", "标点待补全"
    if re.search(r"superscript (?:footnote|structure)|footnote marker|literal (?:sup|sub) tags|脚注(?:标记|格式)", reason, re.I):
        return "footnote", "脚注格式待调整"
    if re.search(r"math(?:ematical)? (?:node|structure|notation)|formula|equation|math node|数学|公式", reason, re.I):
        return "math", "数学内容待核对"
    return "structure", "结构调整暂未完成"


def chinese_notice(issue):
    reason = str(issue.get("reason", ""))
    if re.search(r"[\u4e00-\u9fff]", reason) and not re.search(r"[A-Za-z]{4,}", reason):
        return reason
    if issue.get("proposed_edit"):
        if issue.get("code") == "edit_overlap":
            return "多项修订指向原文中重叠的位置，无法同时应用；已保留原识别结果。"
        if "single editable text node" in reason:
            counts = re.search(r"Requested occurrence (\d+); found (\d+) matching spans", reason)
            if counts:
                return f"建议修改第 {counts[1]} 处，但原页中只找到 {counts[2]} 处完全匹配的片段。已保留原识别结果。"
            return "指定的原文片段或出现序号未匹配到单个节点。可能存在空格差异、序号不符，或文字与公式分属不同节点。"
        if "remove all text" in reason:
            return "模型建议删除此处内容，但会移除整个识别节点，因此保留原识别结果。"
        if "LaTeX command" in reason:
            return "修改位置涉及公式命令内部，为避免损坏公式，已保留原识别结果。"
        return "未能在识别内容中安全定位并应用这项修改，已保留原识别结果。"
    if "Inline structure repair was not independently verified" in reason:
        return "结构修复未取得有效的独立复核确认，或与其他修订冲突，已保留原识别结果。"
    if "Inline structure proposal could not be applied safely" in reason:
        return "结构提案未满足段落定位或局部修改条件，已保留原识别结果。"
    if issue_kind(issue) == "ambiguous":
        return "模型无法根据原 PDF 确定此处内容，已保留原识别结果，请对照原页核对。"
    kind, _label = structure_notice_kind(issue)
    if kind == "punctuation":
        return "模型提示句末标点未完整保留；这属于标点补全，不代表整段内容缺失。"
    if kind == "footnote":
        return "模型提示脚注标记的格式未正确保留，需对照原页调整。"
    if re.search(r"heading.*missing|heading.*absent", reason, re.I):
        return "原 PDF 中的小节标题未包含在识别结果中，当前校对未能补入该标题。"
    if re.search(r"extra|duplicat", reason, re.I):
        return "识别结果中可能含有多余或重复的公式节点，当前校对未能调整其结构。"
    if re.search(r"missing|omitted|absent", reason, re.I):
        return "原 PDF 中的部分内容或公式结构未完整保留，当前校对未能补全，请对照原页核对。"
    return "此处需要调整识别内容的结构，当前校对未能完成，已保留原识别结果。"


def summarize_notices(candidate):
    items, raw_count, excluded_count = [], 0, 0
    unapplied = []
    for page in candidate["pages"]:
        number = page["page_number"]
        for issue in page.get("diagnostics", []):
            edit = issue.get("proposed_edit")
            if edit:
                if edit.get("before") == edit.get("after"):
                    continue
                reason = edit.get("reason") or issue.get("reason", "")
            elif issue.get("kind") == "limitation" and issue.get("excerpt"):
                reason = issue.get("reason", "")
            else:
                continue
            detail_kind, detail_label = structure_notice_kind(issue) if not edit else ("revision", "修订未应用")
            unapplied.append({"page": number, "excerpt": issue.get("excerpt", ""), "reason": reason,
                              "category": "revision" if edit else "structure",
                              "category_label": detail_label, "detail_kind": detail_kind,
                              "before": edit.get("before") if edit else None,
                              "after": edit.get("after") if edit else None,
                              "display_reason": chinese_notice(issue)})
        for issue in page.get("uncertainties", []):
            raw_count += 1
            if issue_kind(issue) != "ambiguous":
                excluded_count += 1
                continue
            excerpt, reason = (
                str(issue.get("excerpt", "")).strip(),
                str(issue.get("reason", "")).strip(),
            )
            item = next(
                (
                    i
                    for i in items
                    if i["excerpt"] == excerpt and i["records"][0]["reason"] == reason
                ),
                None,
            )
            if item is None:
                item = {
                    "category": "ambiguity",
                    "label": "原文内容存在歧义",
                    "message": "模型无法从原页可靠确定此处文字，已保留原识别结果。",
                    "excerpt": excerpt,
                    "pages": [],
                    "records": [],
                }
                items.append(item)
            if number not in item["pages"]:
                item["pages"].append(number)
            item["records"].append(
                {"page": number, "excerpt": excerpt, "reason": reason, "display_reason": chinese_notice(issue)}
            )
    return {
        "raw_count": raw_count,
        "excluded_count": excluded_count,
        "display_count": len(items),
        "items": items,
        "unapplied_items": unapplied,
    }
