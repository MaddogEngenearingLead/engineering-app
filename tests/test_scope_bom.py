from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from reportlab.lib.colors import red
from reportlab.pdfgen import canvas

from app.config import settings
from app.main import create_app
from app.services import scope_bom


class ScopeBomTests(unittest.TestCase):
    def test_legend_keyword_scoring(self):
        result = scope_bom.score_legend_candidates([
            {"page": 1, "text": "Drawing title"},
            {"page": 2, "text": "Instrument Key and abbreviations"},
        ])
        self.assertTrue(result["found"])
        self.assertEqual(result["page"], 2)

    def test_instrument_letter_decoder(self):
        result = scope_bom.decode_instrument_tag("PIT-101")
        self.assertEqual(result["description"], "Pressure Indicator Transmitter")
        self.assertEqual(result["source"], "instrument_letter_decoder")
        self.assertGreater(result["confidence"], 0.5)

    def test_color_meanings_and_page_overrides(self):
        result = scope_bom.detect_colour_meanings(
            [{"page": 1, "colours": ["red", "green", "blue"]}],
            {"found": True, "page": 1},
        )
        self.assertEqual(result["meanings"], {"red": "demo", "green": "new", "blue": "future"})
        pages = scope_bom.classify_pages(
            [{"page": 1, "text": "Title project revision", "tags": [], "tag_set": set(),
              "colours": ["red"]}],
            demo_pages=[1],
            colour_result=result,
        )
        self.assertEqual(pages[0]["work_class"], "demo")
        self.assertEqual(pages[0]["source"], "user_override")
        self.assertEqual(pages[0]["page_role"], "title_page")

    def test_unknown_colour_requests_clarification(self):
        result = scope_bom.detect_colour_meanings(
            [{"page": 1, "colours": ["other"]}],
            {"found": False, "page": None},
        )
        self.assertEqual(result["unknown_colours"], ["other"])

    def test_page_signatures_pair_by_jaccard(self):
        pages = scope_bom.classify_pages([
            {"page": 1, "text": "", "tag_set": {"TK-1", "PI-1"}, "tags": [], "colours": []},
            {"page": 2, "text": "", "tag_set": {"TK-1"}, "tags": [], "colours": []},
            {"page": 3, "text": "", "tag_set": {"MOV-1"}, "tags": [], "colours": []},
        ])
        self.assertEqual(pages[0]["similar_pages"][0], {"page": 2, "similarity": 0.5})
        self.assertEqual(pages[2]["similar_pages"], [])

    def test_scope_cross_check(self):
        result = scope_bom.cross_check_scope(
            "Replace PI101 and inspect TK - 9",
            [{"tag": "PI-101"}],
            [],
        )
        self.assertEqual(result["matched_tags"], ["PI-101"])
        self.assertEqual(result["unmatched_tags"], ["TK-9"])
        self.assertEqual(result["status"], "needs_clarification")

    def test_scope_cross_check_ignores_non_tag_references(self):
        result = scope_bom.cross_check_scope(
            "See Rev 2 and Phase 3",
            [{"tag": "PI-101"}],
            [],
        )
        self.assertEqual(result["mentioned_tags"], [])
        self.assertEqual(result["unmatched_tags"], [])
        self.assertEqual(result["status"], "matched")

    def test_scope_cross_check_flags_conflicting_page_classifications(self):
        result = scope_bom.cross_check_scope(
            "Replace PI-101",
            [{"tag": "PI-101", "pages": [1, 2]}],
            [
                {"page": 1, "work_class": "demo", "source": "user_override"},
                {"page": 2, "work_class": "new", "source": "colour_legend"},
            ],
        )
        self.assertEqual(result["ambiguous_tags"], ["PI-101"])
        self.assertEqual(result["status"], "needs_clarification")

    @patch("app.services.scope_bom.export_bom_to_pdf", return_value="/tmp/bom.pdf")
    @patch("app.services.scope_bom.extract_content_signatures")
    def test_build_scoped_bom_unified_result(self, extract, export):
        extract.return_value = [{
            "page": 1,
            "text": "Instrument legend",
            "tags": [{"tag": "PI-101", "type": "pressure_indicator", "confidence": 0.85,
                      "source": "regex_extraction"}],
            "tag_set": {"PI-101"},
            "colours": ["red"],
        }]
        result = scope_bom.build_scoped_bom(
            "source.pdf",
            "Replace PI-101",
            demo_pages=[1],
            job_id="job-1",
            source_file="source.pdf",
        )
        self.assertEqual(result["materials"][0]["description"], "Pressure Indicator")
        self.assertEqual(result["materials"][0]["description_source"], "instrument_letter_decoder")
        self.assertEqual(result["materials"][0]["classification_source"], "user_override")
        self.assertFalse(result["needs_clarification"])
        self.assertEqual(result["export_status"], "completed")
        export.assert_called_once()

    @patch("app.services.scope_bom.export_bom_to_pdf", side_effect=OSError("disk full"))
    @patch("app.services.scope_bom.extract_content_signatures")
    def test_missing_legend_and_export_failure_are_explicit(self, extract, _export):
        extract.return_value = [{
            "page": 1,
            "text": "PI-101",
            "tags": [{"tag": "PI-101", "type": "pressure_indicator", "confidence": 0.85}],
            "tag_set": {"PI-101"},
            "colours": [],
        }]
        with self.assertLogs("app.services.scope_bom", level="ERROR"):
            result = scope_bom.build_scoped_bom(
                "source.pdf", job_id="job-2", source_file="source.pdf"
            )
        self.assertTrue(result["needs_clarification"])
        self.assertTrue(any("legend" in prompt.lower() for prompt in result["clarification_prompts"]))
        self.assertEqual(result["export_status"], "failed")
        self.assertEqual(result["export_error"], scope_bom.EXPORT_FAILURE_MESSAGE)

    @patch("app.services.scope_bom.extract_content_signatures", return_value=[])
    def test_page_override_outside_document_range_is_rejected(self, _extract):
        with self.assertRaises(ValueError):
            scope_bom.build_scoped_bom(
                "source.pdf", demo_pages=[1], job_id="job-3", source_file="source.pdf"
            )

    def test_extract_page_signature_from_pdf(self):
        with tempfile.TemporaryDirectory() as directory:
            pdf_path = Path(directory) / "source.pdf"
            document = canvas.Canvas(str(pdf_path))
            document.setFillColor(red)
            document.drawString(72, 720, "PI-101")
            document.setFillColorRGB(0, 0, 0)
            document.drawString(72, 690, "Instrument Legend")
            document.save()
            signatures = scope_bom.extract_content_signatures(str(pdf_path))
        self.assertEqual(signatures[0]["page"], 1)
        self.assertIn("PI-101", signatures[0]["tag_set"])
        self.assertIn("red", signatures[0]["colours"])

    def test_unreadable_pdf_raises_typed_document_error(self):
        with tempfile.TemporaryDirectory() as directory:
            pdf_path = Path(directory) / "invalid.pdf"
            pdf_path.write_bytes(b"not a PDF")
            with self.assertRaises(scope_bom.InvalidDocumentError):
                scope_bom.extract_content_signatures(str(pdf_path))

    def test_pdf_export_creates_file(self):
        with tempfile.TemporaryDirectory() as directory:
            output = scope_bom.export_bom_to_pdf(
                job_id="job-test",
                source_file="drawing.pdf",
                materials=[{
                    "item_number": 1,
                    "tag_id": "PI-101",
                    "description": "Pressure Indicator",
                    "type": "pressure_indicator",
                    "quantity": 1,
                    "unit": "ea",
                    "confidence": 0.8,
                }],
                output_dir=directory,
            )
            self.assertTrue(Path(output).is_file())

    @patch("app.services.scope_bom.extract_content_signatures", return_value=[])
    def test_no_tags_returns_clarification_without_export(self, _extract):
        result = scope_bom.build_scoped_bom(
            "source.pdf", job_id="job-empty", source_file="source.pdf"
        )
        self.assertTrue(result["needs_clarification"])
        self.assertEqual(result["export_status"], "not_generated")
        self.assertEqual(result["materials"], [])

    @patch("app.services.scope_bom.export_bom_to_pdf", return_value="/tmp/bom.pdf")
    @patch("app.services.scope_bom.extract_content_signatures")
    def test_specialized_level_switch_description_is_preserved(self, extract, _export):
        extract.return_value = [{
            "page": 1,
            "text": "Instrument Legend",
            "tags": [{"tag": "LSL-1", "type": "level_switch_low", "confidence": 0.85}],
            "tag_set": {"LSL-1"},
            "colours": [],
        }]
        result = scope_bom.build_scoped_bom(
            "source.pdf", job_id="job-low-switch", source_file="source.pdf"
        )
        self.assertEqual(result["materials"][0]["description"], "Level Switch (Low)")

    @patch("app.services.scope_bom.export_bom_to_pdf", return_value="/tmp/bom.pdf")
    @patch("app.services.scope_bom.extract_content_signatures")
    def test_tag_with_conflicting_page_classes_is_ambiguous(self, extract, _export):
        tag = {"tag": "PI-101", "type": "pressure_indicator", "confidence": 0.85}
        extract.return_value = [
            {"page": 1, "text": "Instrument Legend", "tags": [tag],
             "tag_set": {"PI-101"}, "colours": []},
            {"page": 2, "text": "", "tags": [tag],
             "tag_set": {"PI-101"}, "colours": []},
        ]
        result = scope_bom.build_scoped_bom(
            "source.pdf",
            demo_pages=[1],
            new_work_pages=[2],
            job_id="job-ambiguous",
            source_file="source.pdf",
        )
        material = result["materials"][0]
        self.assertIsNone(material["work_class"])
        self.assertEqual(material["classification_source"], "ambiguous_pages")
        self.assertEqual(result["ambiguous_material_tags"], ["PI-101"])
        self.assertTrue(result["needs_clarification"])


class ScanRouteTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.upload_dir = settings.upload_dir
        settings.upload_dir = self.temp_dir.name
        self.client = TestClient(create_app())

    def tearDown(self):
        settings.upload_dir = self.upload_dir
        self.temp_dir.cleanup()

    def test_scan_uses_scoped_service_and_returns_common_fields(self):
        result = {
            "detected_assets": [],
            "materials": [],
            "page_classifications": [],
            "ambiguous_material_tags": [],
            "scope_check": {"status": "matched"},
            "legend": {"found": True},
            "colour_analysis": {"meanings": {}},
            "needs_clarification": True,
            "clarification_prompts": ["Confirm legend."],
            "bom_pdf": None,
            "export_status": "not_generated",
            "export_error": None,
            "extracted_text_length": 20,
        }
        with patch("app.api.routes.build_scoped_bom", return_value=result) as build:
            response = self.client.post(
                "/api/scan",
                files={"file": ("drawing.pdf", b"%PDF", "application/pdf")},
                data={
                    "demo_pages": "[1, 2]",
                    "new_work_pages": "3",
                    "highlight_mapping": '{"red":"demo"}',
                },
            )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "needs_clarification")
        self.assertIn("clarification_prompts", payload)
        self.assertIn("export_status", payload)
        self.assertEqual(build.call_args.kwargs["demo_pages"], [1, 2])
        self.assertEqual(build.call_args.kwargs["new_work_pages"], [3])
        self.assertEqual(build.call_args.kwargs["highlight_mapping"], {"red": "demo"})

    def test_scan_rejects_invalid_overrides(self):
        response = self.client.post(
            "/api/scan",
            files={"file": ("drawing.pdf", b"%PDF", "application/pdf")},
            data={"demo_pages": "[0]"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("clarification_prompts", response.json())

    def test_scan_reports_out_of_range_overrides_as_client_error(self):
        with patch(
            "app.api.routes.build_scoped_bom",
            side_effect=scope_bom.ScopeOverrideError(
                "Page overrides are outside the document range."
            ),
        ):
            response = self.client.post(
                "/api/scan",
                files={"file": ("drawing.pdf", b"%PDF", "application/pdf")},
                data={"demo_pages": "2"},
            )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Page overrides conflict", response.json()["message"])

    def test_scan_hides_internal_processing_errors(self):
        with self.assertLogs("app.api.routes", level="ERROR"):
            with patch("app.api.routes.build_scoped_bom", side_effect=RuntimeError("secret internal detail")):
                response = self.client.post(
                    "/api/scan",
                    files={"file": ("drawing.pdf", b"%PDF", "application/pdf")},
                )
        self.assertEqual(response.status_code, 500)
        self.assertNotIn("secret internal detail", response.text)

    def test_scan_rejects_unsupported_upload(self):
        response = self.client.post(
            "/api/scan",
            files={"file": ("drawing.txt", b"text", "text/plain")},
        )
        self.assertEqual(response.status_code, 400)

    def test_scan_rejects_unreadable_pdf(self):
        response = self.client.post(
            "/api/scan",
            files={"file": ("drawing.pdf", b"not a PDF", "application/pdf")},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["message"], "The uploaded file is not a readable PDF.")


if __name__ == "__main__":
    unittest.main()
