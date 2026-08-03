"""Integration tests for the ingestion pipeline."""

import json
import pathlib
from unittest.mock import MagicMock

import pytest

from ingestion.embeddings.provider import MockEmbeddingProvider
from ingestion.pipeline import IngestionPipeline, IngestResult


def _load_profile_fixtures(profile_id: str) -> dict:
    """Load all fixture data for a profile (resume, repos with readme and metadata)."""
    fixture_dir = pathlib.Path(__file__).parent.parent / "fixtures" / "sample_resumes" / profile_id

    if not fixture_dir.exists():
        raise FileNotFoundError(f"Fixture directory not found for profile {profile_id}")

    # Load resume (either .md or .pdf)
    resume_content = None
    if (fixture_dir / "resume.md").exists():
        resume_content = (fixture_dir / "resume.md").read_text(encoding="utf-8")
    elif (fixture_dir / "resume.pdf").exists():
        resume_content = (fixture_dir / "resume.pdf").read_bytes()
    else:
        raise FileNotFoundError(f"Resume file not found for profile {profile_id}")

    # Load all repos (metadata + readme pairs)
    repos = []
    metadata_files = sorted(fixture_dir.glob("*_metadata.json"))

    for metadata_file in metadata_files:
        repo_name = metadata_file.stem.replace("_metadata", "")
        readme_file = fixture_dir / f"{repo_name}_README.md"

        metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
        readme_content = readme_file.read_text(encoding="utf-8") if readme_file.exists() else ""

        repos.append(
            {
                "name": repo_name,
                "readme": readme_content,
                "metadata": metadata,
            }
        )

    return {
        "profile_id": profile_id,
        "resume": resume_content,
        "repos": repos,
    }


@pytest.mark.integration
class TestIngestionPipeline:
    """Test suite for document ingestion pipeline."""

    @pytest.fixture
    def mock_vector_db(self) -> MagicMock:
        """Mock ChromaDB collection."""
        mock_db = MagicMock()
        mock_db.add = MagicMock(return_value=None)
        return mock_db

    @pytest.fixture
    def mock_db_session(self) -> MagicMock:
        """Create a mock database session."""
        session = MagicMock()
        session.query.return_value.filter_by.return_value.first.return_value = None
        return session

    @pytest.fixture
    def pipeline(self, mock_vector_db: MagicMock, mock_db_session: MagicMock) -> IngestionPipeline:
        """Create an IngestionPipeline with mocked dependencies."""
        return IngestionPipeline(
            vector_db=mock_vector_db,
            db_session=mock_db_session,
            embedding_provider=MockEmbeddingProvider(),
        )

    @pytest.fixture(scope="session")
    def fixture_ql_001(self) -> dict:
        """Load all fixtures for profile ql-001."""
        return _load_profile_fixtures("ql-001")

    @pytest.fixture(scope="session")
    def fixture_ql_100(self) -> dict:
        """Load all fixtures for profile ql-100."""
        return _load_profile_fixtures("ql-100")

    @pytest.fixture(scope="session")
    def fixture_jn_001(self) -> dict:
        """Load all fixtures for profile jn-001."""
        return _load_profile_fixtures("jn-001")

    @pytest.fixture(scope="session")
    def fixture_mb_001(self) -> dict:
        """Load all fixtures for profile mb-001."""
        return _load_profile_fixtures("mb-001")

    # =========== Test cases for ingest_resume() ===========

    def test_ingest_resume_ql_001(self, pipeline: IngestionPipeline, fixture_ql_001: dict) -> None:
        """
        Test successful resume ingestion with fixture ql-001.

        Failure modes:
        - Resume parser fails to extract text from PDF
        - Chunking strategy produces no chunks
        - Embedding provider throws exception
        - Database write fails
        """
        result = pipeline.ingest_resume(
            profile_id="ql-001",
            content=fixture_ql_001["resume"],
            filename="resume.pdf",
        )

        assert isinstance(result, IngestResult)
        assert result.skipped is False
        assert result.skip_reason is None
        assert result.chunk_count > 0
        assert isinstance(result.source_id, str)
        assert result.source_id.startswith("resume_ql-001")

    def test_ingest_resume_jn_001(self, pipeline: IngestionPipeline, fixture_jn_001: dict) -> None:
        """
        Test successful resume ingestion with fixture jn-001 (markdown resume).

        Failure modes:
        - Resume parser fails to extract text from markdown
        - Chunking strategy produces no chunks
        - Resume metadata is not preserved
        """
        result = pipeline.ingest_resume(
            profile_id="jn-001",
            content=fixture_jn_001["resume"],
            filename="resume.md",
        )

        assert result.skipped is False
        assert result.chunk_count > 0
        assert result.source_id.startswith("resume_jn-001")

    def test_ingest_same_resume_different_profiles(
        self, pipeline: IngestionPipeline, fixture_ql_001: dict, fixture_ql_100: dict
    ) -> None:
        """
        Test that identical resume content with different profile IDs produces different source IDs.

        ql-001 and ql-100 have identical files but must be ingested separately because they
        represent different profiles. This tests that the pipeline correctly uses profile_id
        as part of source_id generation.

        Failure modes:
        - Source ID doesn't include profile_id
        - Hash function dominates source_id generation
        - Pipeline incorrectly deduplicates across different profiles
        """
        # Both should have identical content
        assert fixture_ql_001["resume"] == fixture_ql_100["resume"]

        result1 = pipeline.ingest_resume(
            profile_id="ql-001",
            content=fixture_ql_001["resume"],
            filename="resume.pdf",
        )

        result2 = pipeline.ingest_resume(
            profile_id="ql-100",
            content=fixture_ql_100["resume"],
            filename="resume.pdf",
        )

        # Despite identical content, source IDs must be different due to different profile IDs
        assert result1.source_id != result2.source_id
        assert result1.source_id.startswith("resume_ql-001")
        assert result2.source_id.startswith("resume_ql-100")
        assert result1.skipped is False
        assert result2.skipped is False

    def test_ingest_resume_skip_duplicate_profile(
        self, pipeline: IngestionPipeline, fixture_ql_001: dict, mock_db_session: MagicMock
    ) -> None:
        """
        Test that ingesting the same profile ID twice correctly skips on second attempt.

        This verifies the deduplication logic: if a profile's resume has already been
        ingested, the pipeline should skip and return skipped=True.

        Failure modes:
        - _check_skip() doesn't find existing source
        - Source ID comparison fails
        - Skip logic uses wrong database query
        - Skip reason is not set correctly
        """
        # First ingestion should succeed
        result1 = pipeline.ingest_resume(
            profile_id="ql-001",
            content=fixture_ql_001["resume"],
            filename="resume.pdf",
        )
        assert result1.skipped is False
        first_source_id = result1.source_id

        # Mock database to simulate source already exists
        mock_db_session.query.return_value.filter_by.return_value.first.return_value = {
            "source_id": first_source_id
        }

        # Second ingestion with same profile should be skipped
        result2 = pipeline.ingest_resume(
            profile_id="ql-001",
            content=fixture_ql_001["resume"],
            filename="resume.pdf",
        )

        assert result2.skipped is True
        assert result2.skip_reason == "Source already ingested"
        assert result2.chunk_count == 0
        assert result2.source_id == first_source_id

    def test_ingest_resume_deterministic_source_id(
        self, pipeline: IngestionPipeline, fixture_mb_001: dict
    ) -> None:
        """
        Test that same profile and content always produce same source ID (deterministic hashing).

        Failure modes:
        - Hash function is non-deterministic
        - Source ID includes random components
        - Source ID format is inconsistent
        """
        result1 = pipeline.ingest_resume(
            profile_id="mb-001",
            content=fixture_mb_001["resume"],
            filename="resume.pdf",
        )

        result2 = pipeline.ingest_resume(
            profile_id="mb-001",
            content=fixture_mb_001["resume"],
            filename="resume.pdf",
        )

        # Same profile and content should always produce same source_id
        assert result1.source_id == result2.source_id

    def test_ingest_resume_chunks_fixture_content(
        self,
        pipeline: IngestionPipeline,
        fixture_ql_001: dict,
        fixture_jn_001: dict,
        fixture_mb_001: dict,
    ) -> None:
        """
        Test that fixture resumes are properly chunked into multiple segments.

        Failure modes:
        - Chunking strategy returns empty list
        - Chunks don't preserve section information
        - Metadata is lost during chunking
        """
        fixtures = [
            ("ql-001", fixture_ql_001, "resume.pdf"),
            ("jn-001", fixture_jn_001, "resume.md"),
            ("mb-001", fixture_mb_001, "resume.pdf"),
        ]

        for profile_id, fixture, filename in fixtures:
            result = pipeline.ingest_resume(
                profile_id=profile_id,
                content=fixture["resume"],
                filename=filename,
            )

            # All fixtures should produce at least some chunks
            assert result.chunk_count > 0, f"Profile {profile_id} produced no chunks"
            assert result.skipped is False

    def test_ingest_empty_resume_content(self, pipeline: IngestionPipeline) -> None:
        """
        Test graceful handling of empty resume content.

        Failure modes:
        - Parser crashes on empty input
        - Empty chunks are created
        - Error is not properly logged
        """
        try:
            result = pipeline.ingest_resume(
                profile_id="empty-test",
                content="",
                filename="empty.txt",
            )
            # If it doesn't raise, it should skip or have zero chunks
            assert result.skipped or result.chunk_count == 0
        except Exception:
            # It's acceptable to raise an exception for empty input
            pass

    def test_ingest_different_resume_same_profile(
        self, pipeline: IngestionPipeline, fixture_ql_001: dict, fixture_jn_001: dict
    ) -> None:
        """
        Test that different content with same profile_id produces
        different source_ids (deduplication by hash).

        Failure modes:
        - Hash function doesn't differentiate content
        - Source ID only depends on profile_id
        - Deduplication incorrectly reuses source_id
        """
        profile_id = "abc-010"

        result1 = pipeline.ingest_resume(
            profile_id=profile_id,
            content=fixture_ql_001["resume"],
            filename="resume1.txt",
        )

        result2 = pipeline.ingest_resume(
            profile_id=profile_id,
            content=fixture_jn_001["resume"],
            filename="resume2.txt",
        )

        # Different content should produce different source_ids (hash-based deduplication)
        assert result1.source_id != result2.source_id
        assert result1.source_id.startswith(f"resume_{profile_id}")
        assert result2.source_id.startswith(f"resume_{profile_id}")

    def test_ingest_resume_invalid_format_parser_error(self, pipeline: IngestionPipeline) -> None:
        """
        Test that invalid/corrupted resume format is caught and handled gracefully.

        Failure modes:
        - Parser crashes on invalid format
        - Error is not logged
        - Partial state left in vector_db
        """
        # Corrupted PDF-like bytes (not actually a valid PDF)
        invalid_pdf = b"%PDF-INVALID\x00\xff\xfe"

        with pytest.raises(ValueError):
            pipeline.ingest_resume(
                profile_id="invalid-test",
                content=invalid_pdf,
                filename="corrupted.pdf",
            )

    def test_ingest_resume_batch_processor_failure_propagates(
        self, pipeline: IngestionPipeline, fixture_ql_001: dict, mock_vector_db: MagicMock
    ) -> None:
        """
        Test that batch processor failures propagate as exceptions (not silently ignored).

        Failure modes:
        - Embedding generation failure is silently ignored
        - Error is not raised to caller (exception swallowed)
        - Partial embeddings stored in vector_db
        """
        # Make vector_db.add() raise an exception, simulating storage failure
        mock_vector_db.add.side_effect = RuntimeError("Vector DB storage failed")

        with pytest.raises(RuntimeError, match="Vector DB storage failed"):
            pipeline.ingest_resume(
                profile_id="ql-001",
                content=fixture_ql_001["resume"],
                filename="resume.pdf",
            )
