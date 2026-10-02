# Operator runbook

Short notes for things that look wrong but are expected.

## `/readiness` and OCR

The `"ocr"` field on `GET /readiness` is the recognition mode configured for **this
process** (usually the API). It reflects whether Tesseract is available here and
which pages would be read from their image if extraction ran in this container.

When preparation uses Celery (`SINHALA_READER_QUEUE=celery`), OCR runs in the
**worker** container, not in the API. A PNG upload can be recognised successfully
while the API still reports `"ocr": "broken"` or lists Tesseract as missing on this
process. That is normal: check worker logs and the prepared page quality, not the
API `"ocr"` field alone.

See also `infra/README.md` for rebuild and service layout.
