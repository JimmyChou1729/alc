"""Route-aware estimated work; elapsed time never represents verified completion."""
import math


def plan(job, seen, pages=0):
    spec = job['spec']
    pdf = 'ocr' in seen or 'ocr_proofread' in seen or (
        bool(spec.get('source_id')) and str(spec.get('title', '')).lower().endswith('.pdf'))
    ocr = pdf and spec.get('pdf_mode') != 'text_only'
    scale = max(.3, (pages / 10) ** .85) if pages else 1
    stages = [('acquisition', 8 if spec.get('source_url') else 2)]
    if ocr:
        stages.append(('ocr', 70 * scale))
        if spec.get('ocr_proofread') or 'ocr_proofread' in seen:
            stages.append(('ocr_proofread', 100 * (max(pages, 3) / 10) ** 1.3 if pages else 100))
    stages.append(('parse', 3))
    if spec.get('output') == 'companion':
        stages.append(('companion', 400 * scale))
    elif spec.get('output') != 'source':
        stages += [('language', 15), ('glossary', 110 * scale), ('translation', 140 * scale)]
    stages += [('render', 4), ('validate', 2)]
    return stages


def estimate(job, seen, elapsed, progress, pages=0, ocr_done=0):
    if job['state'] == 'completed':
        return 100
    if job['state'] == 'queued' and not seen:
        return 0
    stages = plan(job, seen, pages)
    total = sum(seconds for _, seconds in stages)
    base = 0
    for phase, seconds in stages:
        if phase == job['phase']:
            # Slow time-based movement is capped by this phase's budget.
            fraction = min(1, max(0, elapsed / (seconds * 1.5)))
            done, count = progress.get('completed_units'), progress.get('total_units')
            if phase == 'ocr_proofread' and pages:
                done, count = ocr_done, pages
            if phase in {'translation', 'glossary', 'ocr_proofread'} and (not progress.get('phase') or progress.get('phase') == phase or phase == 'ocr_proofread'):
                if type(done) is int and type(count) is int and count > 0:
                    fraction = max(fraction, min(1, done / count))
            if phase == 'companion':
                from .timing import percentage
                fraction = max(fraction, min(1, max(0, (percentage('companion', progress, '') - 8) / 86)))
            return min(99, math.floor(99 * (base + seconds * fraction) / total))
        base += seconds
    return 0
