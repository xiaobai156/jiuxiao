from __future__ import annotations

from v2.domain.models import DocumentMethod, RecordSet

CANONICAL_ZODIACS = "鼠牛虎兔龙蛇马羊猴鸡狗猪"


def select_current_content_mode(
    record_set: RecordSet,
    requested_issues: tuple[int, ...],
) -> RecordSet:
    """Select the source mode represented by today's target block.

    The same site can publish its current formula as ordinary DOM text on one
    day and as a linked image on another day.  The target issue's block, not a
    fixed parser preference, decides which mode is authoritative.  If both
    modes contain the target block, retain both so the validator can reject a
    real disagreement (or verify identical duplicate presentations).
    """
    requested = set(requested_issues)
    if not requested:
        return record_set

    target_methods = {
        block.document_method
        for block in record_set.blocks
        if requested.intersection(block.observed_issues)
    }
    target_methods.update(
        record.evidence.document_method
        for record in record_set.records
        if record.issue in requested
    )
    supported_modes = {
        DocumentMethod.BROWSER_DOM.value,
        DocumentMethod.IMAGE_OCR.value,
    }
    target_methods &= supported_modes

    # A DOM title commonly contains the current issue number, while the
    # actual nine-zodiac payload for that same block is an image.  The title
    # block must not win source selection merely because it observed the
    # issue; prefer the mode that produced a valid target candidate.  If both
    # modes produced one, retain both so the validator can resolve identical
    # duplicates or reject a real conflict.
    target_record_methods = {
        record.evidence.document_method
        for record in record_set.records
        if record.issue in requested
    }
    target_record_methods &= supported_modes
    if len(target_record_methods) == 1:
        target_methods = target_record_methods

    if len(target_methods) != 1:
        return record_set

    selected_method = next(iter(target_methods))
    return RecordSet(
        records=tuple(
            record
            for record in record_set.records
            if record.evidence.document_method == selected_method
        ),
        blocks=tuple(
            block
            for block in record_set.blocks
            if block.document_method == selected_method
        ),
    )
