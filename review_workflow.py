"""A photo result summarized from human position labels, never AI predictions."""
def effective_review(result):
    existing = result.get('image_review')
    if existing:
        return existing  # Preserve prior explicit human whole-image decisions.
    candidates = result.get('candidates', [])
    labels = result.get('human_reviews', {})
    if not candidates or any(str(c['id']) not in labels for c in candidates):
        return {}
    values = [labels[str(c['id'])] for c in candidates]
    if any(value not in ('screw','normal','uncertain') for value in values):
        return {}
    decision = 'uncertain' if 'uncertain' in values else 'screw' if 'screw' in values else 'no_screw_seen'
    return dict(decision=decision, by='human_positions',
                at=result.get('candidate_reviews_updated_at', ''))


def summarize_positions(result, at):
    result.pop('image_review', None)
    result['candidate_reviews_updated_at'] = at
    summary = effective_review(result)
    if summary:
        result['image_review'] = summary
    return summary
