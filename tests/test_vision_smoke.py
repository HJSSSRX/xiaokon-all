"""Smoke tests for tools.vision — verifies imports and basic API shape."""
import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestVisionImports:
    def test_import_ocr(self):
        from tools.vision.ocr import image_to_text, image_to_data, screenshot_to_text, OCRResult
        assert callable(image_to_text)
        assert callable(image_to_data)
        assert callable(screenshot_to_text)
        assert OCRResult is not None

    def test_import_mindmap(self):
        from tools.vision.mindmap_parser import parse_mindmap_image, mindmap_to_kb, MindMapNode
        assert callable(parse_mindmap_image)
        assert callable(mindmap_to_kb)
        assert MindMapNode is not None

    def test_module_init_exports(self):
        import tools.vision
        assert hasattr(tools.vision, "image_to_text")
        assert hasattr(tools.vision, "parse_mindmap_image")
        assert hasattr(tools.vision, "__version__")


class TestOCRFallback:
    def test_image_to_text_nonexistent_file(self):
        from tools.vision.ocr import image_to_text, OCRResult
        result = image_to_text("nonexistent_file_xyz.png")
        assert isinstance(result, OCRResult)
        # Should have error message for nonexistent file
        assert result.error or result.text == ""

    def test_image_to_data_nonexistent_file(self):
        from tools.vision.ocr import image_to_data, OCRResult
        result = image_to_data("nonexistent_file_xyz.png")
        assert isinstance(result, OCRResult)
        assert result.blocks == []


class TestMindMapFallback:
    def test_parse_nonexistent_file(self):
        from tools.vision.mindmap_parser import parse_mindmap_image, MindMapNode
        result = parse_mindmap_image("nonexistent_file_xyz.png")
        assert isinstance(result, MindMapNode)
        assert "ERROR" in result.text.upper()
