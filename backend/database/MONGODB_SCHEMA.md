MongoDB Collections Setup

MongoDB stores raw OCR and AI processing results, making it easy to version and audit the detection pipeline.

Collections:
- ocr_results: Raw text extraction outputs
- symbol_detections: Bounding boxes and confidence scores for detected equipment
- processing_jobs: Status and metadata for each P&ID processing job
- ai_annotations: Manual corrections or annotations from users

Example schema (ocr_results):
{
  "job_id": "job-pid-001",
  "file_id": "pid-file-001",
  "timestamp": ISODate(),
  "results": [
    {
      "text": "P-101",
      "confidence": 0.95,
      "bounding_box": [100, 50, 150, 30]
    }
  ]
}
