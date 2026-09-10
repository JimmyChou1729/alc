"""Show content ambiguity only, using the shared OCR triage policy."""

from alc_ocr_proofread.review_policy import issue_kind
import re


def chinese_notice(issue):
    reason = str(issue.get("reason", ""))
    if re.search(r"[\u4e00-\u9fff]", reason) and not re.search(r"[A-Za-z]{4,}", reason):
        return reason
    if issue.get("proposed_edit"):
        if "remove all text" in reason:
            return "模型建议删除此处内容，但会移除整个识别节点，因此保留原识别结果。"
        if "LaTeX command" in reason:
            return "修改位置涉及公式命令内部，为避免损坏公式，已保留原识别结果。"
        return "未能在识别内容中安全定位并应用这项修改，已保留原识别结果。"
    if issue_kind(issue) == "ambiguous":
        return "模型无法根据原 PDF 确定此处内容，已保留原识别结果，请对照原页核对。"
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
            unapplied.append({"page": number, "excerpt": issue.get("excerpt", ""), "reason": reason,
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
