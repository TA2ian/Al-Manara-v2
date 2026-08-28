# ADR-020: MVP Receipt Format and Attempt Policy

## Status

Accepted.

## Decision

PDF processing is outside the MVP.

Supported receipt image formats are JPEG, PNG, and WEBP only. Telegram-provided MIME metadata and filename extensions are not trusted; the infrastructure upload pipeline must perform streaming size enforcement and real MIME/magic-byte validation before durable acceptance.

Exactly one image is processed per receipt submission attempt. Multiple images sent as an album/media group or as a burst are not merged into one receipt. The application must select one deterministic submission boundary and reject additional images for the same active attempt with a clear message.

A customer receives at most three processing opportunities for the same receipt/order path:

1. first failed extraction/verification attempt → explain the concrete reason and request one replacement image;
2. second failed attempt → explain the concrete reason and provide the final retry opportunity;
3. third failed attempt → stop automated attempts and escalate the order/evidence to the administrator for manual inspection.

A successful extraction/linkage terminates the retry sequence. Retry attempts are bounded and idempotent; they cannot create multiple active processing jobs for the same order.

Temporary processing resources are cleaned after every attempt, including failure, timeout, and cancellation paths, in accordance with the storage/worker contracts.

## Security boundary

Receipt images are untrusted input. Processing is isolated from business-state writes, bounded by file size/dimensions/memory/time/queue limits, and produces data only. The application layer decides linkage, comparison, and Order transitions.
