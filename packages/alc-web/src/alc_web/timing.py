"""Stage-aware work estimates; completed work never regresses on resume."""

import math


def percentage(stage, progress, output):
    ranges = {'queued': (0, 0), 'acquisition': (1, 4), 'parse': (4, 8),
              'language': (8, 12), 'glossary': (12, 25), 'translation': (25, 94),
              'companion': (8, 94), 'render': (94, 98), 'validate': (98, 99), 'completed': (99, 99)}
    base, end = ranges.get(stage, (0, 0))
    phase = progress.get('phase')
    if stage == 'companion':
        setup = {'source_preparation': 8, 'author_identity': 10, 'language_detection': 12,
                 'glossary': 15, 'translation': 25, 'guides': 68,
                 'chapter_join': 91, 'publication': 94, 'completed': 94}
        count = progress.get('total_chapters', 0)
        if type(count) is not int or count <= 0 or 'glossary_ready' not in progress:
            return setup.get(phase, 8)
        if progress['glossary_ready'] is not True:
            return setup.get(phase, 15) if phase in {'source_preparation', 'author_identity', 'language_detection'} else 15
        def fraction(key):
            value = progress.get(key, 0)
            return min(1, max(0, value / count)) if type(value) is int else 0
        def detailed(key, fallback):
            value = progress.get(key)
            return max(fallback, min(1, max(0, value))) if type(value) in (int, float) and math.isfinite(value) else fallback
        translated = detailed('translation_fraction', fraction('translated_chapters')) if progress.get('translation_required', True) else 1
        guided = detailed('guide_fraction', fraction('guided_chapters'))
        return 25 + 43 * translated + 23 * guided + 3 * fraction('completed_chapters')
    expected = {'glossary': 'glossary', 'translation': 'translation'}.get(stage)
    if expected and phase and phase != expected:
        return base
    if stage not in {'translation', 'glossary', 'companion'}:
        return base
    done, total = progress.get('completed_units'), progress.get('total_units')
    if type(done) is int and type(total) is int and total > 0:
        return base + (end-base) * min(1, max(0, done/total))
    return base


def initial_eta(job, percent):
    if job['state'] == 'completed':
        return [0, 0]
    if job['state'] not in {'running', 'delivering', 'queued'}:
        return None
    if job['phase'] in {'render', 'validate'}:
        return [5, 60]
    if job['spec'].get('output') == 'source':
        return [10, 90]
    size = job.get('detail', {}).get('document_bytes', 50000)
    scale = max(.3, min(30, size/50000))
    base = 900 if job['spec'].get('output') == 'companion' else 420
    left = max(.1, 1-percent/100)
    return [max(30, round(base*scale*left*.5)), max(60, round(base*scale*left*2))]
