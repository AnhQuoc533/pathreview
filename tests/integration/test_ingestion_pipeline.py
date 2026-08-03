from unittest.mock import MagicMock

import pytest

from ingestion.embeddings.provider import MockEmbeddingProvider
from ingestion.pipeline import IngestionPipeline


@pytest.mark.integration
class TestIngestionPipeline:
    """Test suite for document ingestion pipeline."""

    @pytest.fixture
    def mock_vector_db(self) -> MagicMock:
        """Mock ChromaDB collection."""
        mock_db = MagicMock()
        # Mock the add() method (called by batch_processor)
        mock_db.add = MagicMock(return_value=None)
        return mock_db

    @pytest.fixture
    def mock_db_session(self) -> MagicMock:
        """Create a mock database session."""
        # Mock the query() method used in _check_skip()
        session = MagicMock()
        session.filter_by.return_value.first.return_value = None
        return session

    @pytest.fixture
    def pipeline(self, mock_vector_db: MagicMock, mock_db_session: MagicMock) -> IngestionPipeline:
        """Create an IngestionPipeline with mocked dependencies."""
        return IngestionPipeline(
            vector_db=mock_vector_db,
            db_session=mock_db_session,
            embedding_provider=MockEmbeddingProvider(),
        )
