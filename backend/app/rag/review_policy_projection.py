"""Read-only projection of version-bound human decisions; never writes approvals."""
from datetime import datetime


def project_reviews(binding, events):
    """Use each reviewer's latest decision; disagreement/staleness stays held.

    Caller supplies a current binding from ReviewStore.current(), which verifies
    packet, crop, presentation and catalogue bytes. This pure function does not
    authenticate imported files or mint missing review dimensions.
    """
    latest={};issues=[]
    if not isinstance(binding,dict) or not binding.get('evidenceToken'):
        return {'reviews':{},'issues':['missing_current_evidence_binding'],'eligible':False}
    for event in events:
        if not isinstance(event,dict):
            issues.append('malformed_event');continue
        if event.get('kind')!='decision':continue
        receipt=event.get('receipt')
        if not isinstance(receipt,dict):
            issues.append('malformed_receipt');continue
        reviewer=receipt.get('reviewerIdentifier');dimension=receipt.get('dimension')
        if (receipt.get('reviewerKind')!='human' or not isinstance(reviewer,str) or not reviewer
            or reviewer!=event.get('reviewer') or not isinstance(dimension,str)
            or receipt.get('outcome') not in ('passed','failed','unresolved')
            or not isinstance(receipt.get('receiptId'),str) or not receipt['receiptId']):
            issues.append('invalid_human_attribution');continue
        try:
            timestamp=datetime.fromisoformat(event['timestamp'])
            if timestamp.tzinfo is None:raise ValueError('timezone required')
        except (KeyError,TypeError,ValueError):
            issues.append('invalid_decision_timestamp');continue
        key=(reviewer,dimension)
        if key in latest and timestamp==latest[key][0]:
            issues.append('ambiguous_decision_order')
        if key not in latest or timestamp>latest[key][0]:latest[key]=(timestamp,receipt)
    grouped={}
    for (_,dimension),(_,receipt) in latest.items():
        grouped.setdefault(dimension,[]).append(receipt)
    reviews={}
    for dimension,receipts in grouped.items():
        if any(r.get('binding')!=binding or r.get('evidenceToken')!=binding['evidenceToken'] for r in receipts):
            issues.append('stale_'+dimension+'_review');continue
        if any(r['outcome']!='passed' for r in receipts):
            issues.append('unresolved_or_failed_'+dimension+'_review');continue
        reviews[dimension]={'state':'passed','reviewer':'; '.join(sorted(r['reviewerIdentifier'] for r in receipts)),
            'evidence_refs':sorted(r['receiptId'] for r in receipts),
            'content_sha256':binding.get('contentHash'),'image_sha256':binding.get('cropImageHash'),
            'revision':binding.get('questionRevision'),'curriculum_version':binding.get('catalogueVersion'),
            'evidence_token':binding['evidenceToken']}
    if any(i in issues for i in ('malformed_event','malformed_receipt','invalid_human_attribution',
                                 'invalid_decision_timestamp','ambiguous_decision_order')):
        reviews={}
    return {'reviews':reviews,'issues':sorted(set(issues)),'eligible':False}
