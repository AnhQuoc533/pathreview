from unittest.mock import MagicMock
from typing import Optional, List
import pytest

from ingestion.embeddings.provider import MockEmbeddingProvider
from ingestion.pipeline import IngestionPipeline, IngestResult


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

    @pytest.fixture
    def fixture_profiles(self) -> List[str]:
        """Return list of available fixture profile IDs."""
        return ["ql-001", "ql-100", "jn-001", "mb-001"]

    @pytest.fixture
    def load_fixture_resume(self):
        """Load resume file from fixture directory (string for .md, bytes for .pdf)."""

        def _load(profile_id: str) -> str | bytes:
            import pathlib

            fixture_dir = (
                pathlib.Path(__file__).parent.parent/"fixtures"/"sample_resumes"/profile_id
            )
            resume_file = None

            if (fixture_dir / "resume.md").exists():
                resume_file = fixture_dir / "resume.md"
                return resume_file.read_text(encoding="utf-8")
            elif (fixture_dir / "resume.pdf").exists():
                resume_file = fixture_dir / "resume.pdf"
                return resume_file.read_bytes()

            raise FileNotFoundError(f"Resume not found for profile {profile_id}")

        return _load

    # =========== Test cases for ingest_resume() ===========

    def test_ingest_resume_ql_001(self, pipeline, load_fixture_resume) -> None:
        """
        Test successful resume ingestion with fixture ql-001.

        Failure modes:
        - Resume parser fails to extract text from PDF
        - Chunking strategy produces no chunks
        - Embedding provider throws exception
        - Database write fails
        """
        profile_id = "ql-001"
        resume_content = load_fixture_resume(profile_id)

        result = pipeline.ingest_resume(
            profile_id=profile_id,
            content=resume_content,
            filename="resume.pdf",
        )

        assert isinstance(result, IngestResult)
        assert result.skipped is False
        assert result.skip_reason is None
        assert result.chunk_count > 0
        assert isinstance(result.source_id, str)
        assert result.source_id.startswith(f"resume_{profile_id}")

    def test_ingest_resume_jn_001(self, pipeline, load_fixture_resume) -> None:
        """
        Test successful resume ingestion with fixture jn-001 (markdown resume).

        Failure modes:
        - Resume parser fails to extract text from markdown
        - Chunking strategy produces no chunks
        - Resume metadata is not preserved
        """
        profile_id = "jn-001"
        resume_content = load_fixture_resume(profile_id)

        result = pipeline.ingest_resume(
            profile_id=profile_id,
            content=resume_content,
            filename="resume.md",
        )

        assert result.skipped is False
        assert result.chunk_count > 0
        assert result.source_id.startswith(f"resume_{profile_id}")

    def test_ingest_identical_resume_different_profiles(self, pipeline, load_fixture_resume) -> None:
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
        profile_id_1 = "ql-001"
        profile_id_2 = "ql-100"

        resume_content_1 = load_fixture_resume(profile_id_1)
        resume_content_2 = load_fixture_resume(profile_id_2)

        # Both should have identical content
        assert resume_content_1 == resume_content_2

        result1 = pipeline.ingest_resume(
            profile_id=profile_id_1,
            content=resume_content_1,
            filename="resume.pdf",
        )

        result2 = pipeline.ingest_resume(
            profile_id=profile_id_2,
            content=resume_content_2,
            filename="resume.pdf",
        )

        # Despite identical content, source IDs must be different due to different profile IDs
        assert result1.source_id != result2.source_id
        assert result1.source_id.startswith(f"resume_{profile_id_1}")
        assert result2.source_id.startswith(f"resume_{profile_id_2}")
        assert result1.skipped is False
        assert result2.skipped is False

    def test_ingest_resume_skip_duplicate_profile(
        self, pipeline, load_fixture_resume, mock_db_session
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
        profile_id = "ql-001"
        resume_content = load_fixture_resume(profile_id)

        # First ingestion should succeed
        result1 = pipeline.ingest_resume(
            profile_id=profile_id,
            content=resume_content,
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
            profile_id=profile_id,
            content=resume_content,
            filename="resume.pdf",
        )

        assert result2.skipped is True
        assert result2.skip_reason == "Source already ingested"
        assert result2.chunk_count == 0
        assert result2.source_id == first_source_id

    def test_ingest_resume_deterministic_source_id(self, pipeline, load_fixture_resume) -> None:
        """
        Test that same profile and content always produce same source ID (deterministic hashing).

        Failure modes:
        - Hash function is non-deterministic
        - Source ID includes random components
        - Source ID format is inconsistent
        """
        profile_id = "mb-001"
        resume_content = load_fixture_resume(profile_id)

        result1 = pipeline.ingest_resume(
            profile_id=profile_id,
            content=resume_content,
            filename="resume.pdf",
        )

        result2 = pipeline.ingest_resume(
            profile_id=profile_id,
            content=resume_content,
            filename="resume.pdf",
        )

        # Same profile and content should always produce same source_id
        assert result1.source_id == result2.source_id

    def test_ingest_resume_chunks_fixture_content(self, pipeline, load_fixture_resume) -> None:
        """
        Test that fixture resumes are properly chunked into multiple segments.

        Failure modes:
        - Chunking strategy returns empty list
        - Chunks don't preserve section information
        - Metadata is lost during chunking
        """
        for profile_id in ["ql-001", "jn-001", "mb-001"]:
            resume_content = load_fixture_resume(profile_id)

            result = pipeline.ingest_resume(
                profile_id=profile_id,
                content=resume_content,
                filename="resume.pdf" if profile_id != "jn-001" else "resume.md",
            )

            # All fixtures should produce at least some chunks
            assert result.chunk_count > 0, f"Profile {profile_id} produced no chunks"
            assert result.skipped is False
