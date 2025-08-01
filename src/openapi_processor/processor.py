"""Main OpenAPI Processor orchestrating the 5-phase pipeline."""

import logging
import os
from typing import TYPE_CHECKING, Any, Dict, Iterator, List

if TYPE_CHECKING:
    from ..cli.config import Config

logger = logging.getLogger(__name__)

from .chunk_assembler import ChunkAssembler
from .extractor import ElementExtractor
from .graph_builder import GraphBuilder
from .parser import OpenAPIParser
from .scanner import DirectoryScanner, ScannerConfig
from .validator import OpenAPIValidator, ValidatorConfig


class OpenAPIProcessor:
    """Main orchestrator for the OpenAPI processing pipeline."""

    def __init__(self, config: "Config"):
        """
        Initialize OpenAPI Processor with configuration.

        Args:
            config: Configuration object with all settings
        """
        self.config = config

        # Initialize subcomponents
        self.scanner = DirectoryScanner(
            ScannerConfig(
                skip_hidden_files=config.skip_hidden_files,
                supported_extensions=config.supported_extensions,
            )
        )
        self.parser = OpenAPIParser()
        self.validator = OpenAPIValidator(ValidatorConfig.from_config(config))
        self.extractor = ElementExtractor()
        self.graph_builder = GraphBuilder()
        self.assembler = ChunkAssembler()

        # Configuration
        self.log_progress = config.log_processing_progress

    def process_directory(self, specs_dir: str) -> List[Dict[str, Any]]:
        """
        Main entry point - orchestrates 5-phase pipeline.

        Args:
            specs_dir: Root directory containing OpenAPI specifications

        Returns:
            List of complete chunks ready for vector storage
        """
        if self.log_progress:
            logger.info(f"Processing OpenAPI specifications from: {specs_dir}")

        all_chunks = []

        # Phase 1: Directory Scanning
        file_paths = list(self._scan_directory(specs_dir))
        if self.log_progress:
            logger.info(f"Found {len(file_paths)} OpenAPI files")

        # Process each file through phases 2-5
        for file_path in file_paths:
            chunks = self._process_file(os.path.join(specs_dir, file_path), file_path)
            all_chunks.extend(chunks)

        if self.log_progress:
            logger.info(f"Generated {len(all_chunks)} total chunks")

        return all_chunks

    def _scan_directory(self, specs_dir: str) -> Iterator[str]:
        """Phase 1: Directory scanning."""
        try:
            return self.scanner.scan_for_openapi_files(specs_dir)
        except (FileNotFoundError, NotADirectoryError) as e:
            if self.log_progress:
                logger.info(f"Directory scan error: {e}")
            return iter([])

    def _process_file(self, full_path: str, relative_path: str) -> List[Dict[str, Any]]:
        """Phase 2-5: File processing through chunk generation."""
        if self.log_progress:
            logger.info(f"Processing: {relative_path}")

        try:
            # Phase 2: Parse file
            parse_result = self.parser.parse_file(full_path)
            if not parse_result.success:
                if self.log_progress:
                    logger.info(f"  Parse failed: {parse_result.error}")
                return []

            # Phase 2: Validate OpenAPI structure
            validation_result = self.validator.validate(parse_result.data)
            if not validation_result.is_valid:
                if self.log_progress:
                    logger.info(f"  Validation failed: {validation_result.errors}")
                return []

            # Phase 3: Extract elements
            elements = self.extractor.extract_elements(parse_result.data, relative_path)
            if self.log_progress:
                logger.info(f"  Extracted {len(elements)} elements")

            # Phase 4: Build reference graph
            elements_with_refs = self.graph_builder.build_reference_graph(elements)

            # Phase 5: Assemble final chunks (with adaptive splitting)
            chunks = self.assembler.assemble_chunks(elements_with_refs)

            if self.log_progress:
                logger.info(f"  Generated {len(chunks)} chunks")

            return chunks

        except Exception as e:
            if self.log_progress:
                logger.info(f"  Processing error: {e}")
            return []
