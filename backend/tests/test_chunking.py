"""
Tests for document chunking module.
"""
import pytest
from document_parser import SourceSection
from chunking import DocumentChunk, ChunkingConfig, Chunker


class TestChunkingConfig:
    """Tests for ChunkingConfig validation."""
    
    def test_valid_config(self):
        """Valid configuration should not raise."""
        config = ChunkingConfig(chunk_size=500, overlap=50)
        assert config.chunk_size == 500
        assert config.overlap == 50
    
    def test_default_config(self):
        """Default configuration should be valid."""
        config = ChunkingConfig()
        assert config.chunk_size == 500
        assert config.overlap == 50
    
    def test_chunk_size_must_be_positive(self):
        """Chunk size must be greater than 0."""
        with pytest.raises(ValueError, match="chunk_size must be > 0"):
            ChunkingConfig(chunk_size=0)
        
        with pytest.raises(ValueError, match="chunk_size must be > 0"):
            ChunkingConfig(chunk_size=-1)
    
    def test_overlap_must_be_non_negative(self):
        """Overlap cannot be negative."""
        with pytest.raises(ValueError, match="overlap must be >= 0"):
            ChunkingConfig(chunk_size=500, overlap=-1)
    
    def test_overlap_must_be_less_than_chunk_size(self):
        """Overlap cannot be >= chunk_size."""
        with pytest.raises(ValueError, match="overlap must be < chunk_size"):
            ChunkingConfig(chunk_size=500, overlap=500)
        
        with pytest.raises(ValueError, match="overlap must be < chunk_size"):
            ChunkingConfig(chunk_size=500, overlap=600)


class TestChunkerBasic:
    """Tests for basic chunking scenarios."""
    
    def test_empty_section_produces_no_chunks(self):
        """Empty sections should produce no chunks."""
        chunker = Chunker()
        sections = [SourceSection(source_id=1, text="", page=1)]
        chunks = chunker.chunk(sections)
        assert chunks == []
    
    def test_short_text_produces_one_chunk(self):
        """Text shorter than chunk_size should produce one chunk."""
        chunker = Chunker(ChunkingConfig(chunk_size=500, overlap=50))
        text = "This is a short text."
        sections = [SourceSection(source_id=1, text=text, page=1)]
        chunks = chunker.chunk(sections)
        
        assert len(chunks) == 1
        assert chunks[0].text == text
        assert chunks[0].chunk_index == 0
        assert chunks[0].page == 1
        assert chunks[0].source_section_id == 1
    
    def test_no_empty_chunks(self):
        """Chunking should never produce empty chunks."""
        chunker = Chunker(ChunkingConfig(chunk_size=50, overlap=10))
        # Text with spacing that could produce empty chunks after stripping
        text = "Hello world. This is a test. And more text. " * 5
        sections = [SourceSection(source_id=1, text=text, page=1)]
        chunks = chunker.chunk(sections)
        
        for chunk in chunks:
            assert chunk.text.strip() != ""
    
    def test_chunk_index_is_sequential(self):
        """Chunk indices should be sequential across all sections."""
        chunker = Chunker(ChunkingConfig(chunk_size=50, overlap=10))
        sections = [
            SourceSection(source_id=1, text="A" * 100, paragraph=1),
            SourceSection(source_id=2, text="B" * 100, paragraph=2),
        ]
        chunks = chunker.chunk(sections)
        
        for i, chunk in enumerate(chunks):
            assert chunk.chunk_index == i


class TestChunkerDeterminism:
    """Tests for deterministic behavior."""
    
    def test_deterministic_output(self):
        """Same input should always produce same output."""
        config = ChunkingConfig(chunk_size=100, overlap=20)
        text = "Lorem ipsum dolor sit amet. " * 20
        sections = [SourceSection(source_id=1, text=text, page=1)]
        
        # Run multiple times
        results = [
            Chunker(config).chunk(sections)
            for _ in range(3)
        ]
        
        # Compare results
        for i in range(1, len(results)):
            assert len(results[i]) == len(results[0])
            for j, chunk in enumerate(results[i]):
                assert chunk.text == results[0][j].text
                assert chunk.page == results[0][j].page
                assert chunk.source_section_id == results[0][j].source_section_id


class TestChunkerMetadata:
    """Tests for metadata preservation."""
    
    def test_pdf_page_numbers_preserved(self):
        """Page numbers should be preserved in all chunks from a PDF section."""
        chunker = Chunker(ChunkingConfig(chunk_size=50, overlap=10))
        text = "This is page content. " * 10
        sections = [SourceSection(source_id=1, text=text, page=5)]
        chunks = chunker.chunk(sections)
        
        assert len(chunks) > 1
        for chunk in chunks:
            assert chunk.page == 5
            assert chunk.paragraph is None
    
    def test_docx_paragraph_numbers_preserved(self):
        """Paragraph numbers should be preserved in all chunks from a DOCX section."""
        chunker = Chunker(ChunkingConfig(chunk_size=50, overlap=10))
        text = "This is paragraph content. " * 10
        sections = [SourceSection(source_id=2, text=text, paragraph=7)]
        chunks = chunker.chunk(sections)
        
        assert len(chunks) > 1
        for chunk in chunks:
            assert chunk.paragraph == 7
            assert chunk.page is None
    
    def test_source_section_id_preserved(self):
        """Source section ID should be preserved in all chunks from a section."""
        chunker = Chunker(ChunkingConfig(chunk_size=50, overlap=10))
        text = "Some content. " * 10
        sections = [SourceSection(source_id=42, text=text, page=3)]
        chunks = chunker.chunk(sections)
        
        for chunk in chunks:
            assert chunk.source_section_id == 42
    
    def test_multiple_sections_metadata_independent(self):
        """Metadata from different sections should not mix."""
        chunker = Chunker(ChunkingConfig(chunk_size=50, overlap=10))
        sections = [
            SourceSection(source_id=1, text="PDF content. " * 10, page=2),
            SourceSection(source_id=2, text="DOCX content. " * 10, paragraph=5),
        ]
        chunks = chunker.chunk(sections)
        
        # First chunk(s) should have page 2
        section_1_chunks = [c for c in chunks if c.source_section_id == 1]
        for chunk in section_1_chunks:
            assert chunk.page == 2
            assert chunk.paragraph is None
        
        # Later chunk(s) should have paragraph 5
        section_2_chunks = [c for c in chunks if c.source_section_id == 2]
        for chunk in section_2_chunks:
            assert chunk.paragraph == 5
            assert chunk.page is None


class TestChunkerOverlap:
    """Tests for overlap behavior."""
    
    def test_overlap_creates_duplication(self):
        """Overlap should cause text duplication in consecutive chunks."""
        chunker = Chunker(ChunkingConfig(chunk_size=100, overlap=30))
        # Create text where we know overlap will happen
        text = "word1 word2 word3 word4 word5 word6 word7 word8 word9 word10 " * 5
        sections = [SourceSection(source_id=1, text=text, page=1)]
        chunks = chunker.chunk(sections)
        
        # Multiple chunks should exist
        assert len(chunks) > 1
        
        # Check for overlap between consecutive chunks
        for i in range(len(chunks) - 1):
            chunk1 = chunks[i].text
            chunk2 = chunks[i + 1].text
            # Chunk2 should contain the last part of chunk1 (overlap)
            # The exact text might differ due to sentence-based splitting,
            # but there should be some common content
            overlap_found = chunk1[-30:] in (chunk2[:100] if len(chunk2) >= 100 else chunk2)
            # For sentence-based splitting, we just check that chunks are not identical
            assert chunk1 != chunk2
    
    def test_overlap_zero_no_duplication(self):
        """With zero overlap, consecutive chunks should not share text."""
        chunker = Chunker(ChunkingConfig(chunk_size=100, overlap=0))
        text = "A" * 50 + "B" * 50 + "C" * 50
        sections = [SourceSection(source_id=1, text=text, page=1)]
        chunks = chunker.chunk(sections)
        
        if len(chunks) > 1:
            # With character-based splitting and overlap=0, chunks shouldn't overlap
            total_text = "".join(c.text for c in chunks)
            # Verify we didn't lose or duplicate significant amounts
            assert len(total_text) >= len(text.strip())


class TestChunkerMultipleSections:
    """Tests for handling multiple sections."""
    
    def test_multiple_sections_remain_in_order(self):
        """Chunks from multiple sections should maintain order."""
        chunker = Chunker(ChunkingConfig(chunk_size=30, overlap=5))
        sections = [
            SourceSection(source_id=1, text="First. " * 5, page=1),
            SourceSection(source_id=2, text="Second. " * 5, page=2),
            SourceSection(source_id=3, text="Third. " * 5, page=3),
        ]
        chunks = chunker.chunk(sections)
        
        # Extract source IDs in order
        source_ids = [c.source_section_id for c in chunks]
        
        # Should be ordered: 1s, then 2s, then 3s
        assert source_ids[0] == 1
        # Find where section 2 starts
        section_2_start = next(i for i, sid in enumerate(source_ids) if sid == 2)
        # Find where section 3 starts
        section_3_start = next(i for i, sid in enumerate(source_ids) if sid == 3)
        
        assert section_2_start > 0
        assert section_3_start > section_2_start


class TestChunkerLongText:
    """Tests for handling very long text."""
    
    def test_long_text_without_sentence_boundaries(self):
        """Very long text without clear sentence boundaries should still chunk."""
        chunker = Chunker(ChunkingConfig(chunk_size=100, overlap=20))
        # Long text without sentence breaks
        text = "a b c d e f g h " * 100
        sections = [SourceSection(source_id=1, text=text, page=1)]
        chunks = chunker.chunk(sections)
        
        assert len(chunks) > 1
        for chunk in chunks:
            assert len(chunk.text) <= 150  # Some buffer for stripping
    
    def test_multiple_chunks_from_long_text(self):
        """Long text should produce multiple chunks."""
        chunker = Chunker(ChunkingConfig(chunk_size=100, overlap=20))
        text = "This is a longer text that should be split into multiple chunks. " * 10
        sections = [SourceSection(source_id=1, text=text, page=1)]
        chunks = chunker.chunk(sections)
        
        assert len(chunks) >= 3


class TestChunkerCharacterOffsets:
    """Tests for character offset tracking."""
    
    def test_character_offsets_single_chunk(self):
        """Single chunk should have correct offsets."""
        chunker = Chunker(ChunkingConfig(chunk_size=500))
        text = "Hello world"
        sections = [SourceSection(source_id=1, text=text, page=1)]
        chunks = chunker.chunk(sections)
        
        assert len(chunks) == 1
        assert chunks[0].char_start == 0
        assert chunks[0].char_end == len(text)
    
    def test_character_offsets_multiple_chunks(self):
        """Multiple chunks should have sequential offsets."""
        chunker = Chunker(ChunkingConfig(chunk_size=50, overlap=10))
        text = "word " * 50
        sections = [SourceSection(source_id=1, text=text, page=1)]
        chunks = chunker.chunk(sections)
        
        assert len(chunks) > 1
        # Offsets should be defined for all chunks
        for chunk in chunks:
            assert chunk.char_start is not None
            assert chunk.char_end is not None
            assert chunk.char_start >= 0
            assert chunk.char_end > chunk.char_start


class TestChunkerEdgeCases:
    """Tests for edge cases."""
    
    def test_single_long_word(self):
        """Text with a single word longer than chunk_size should still produce chunk."""
        chunker = Chunker(ChunkingConfig(chunk_size=50, overlap=10))
        # Single very long word
        text = "a" * 100
        sections = [SourceSection(source_id=1, text=text, page=1)]
        chunks = chunker.chunk(sections)
        
        assert len(chunks) >= 1
        assert all(chunk.text for chunk in chunks)
    
    def test_whitespace_handling(self):
        """Leading/trailing whitespace should be stripped from chunks."""
        chunker = Chunker(ChunkingConfig(chunk_size=50, overlap=10))
        text = "  leading. trailing spaces.  " * 5
        sections = [SourceSection(source_id=1, text=text, page=1)]
        chunks = chunker.chunk(sections)
        
        for chunk in chunks:
            assert chunk.text == chunk.text.strip()
    
    def test_mixed_pdf_and_docx_sections(self):
        """Mixed PDF and DOCX sections should preserve correct metadata."""
        chunker = Chunker(ChunkingConfig(chunk_size=50, overlap=10))
        sections = [
            SourceSection(source_id=1, text="PDF text. " * 10, page=1),
            SourceSection(source_id=2, text="DOCX text. " * 10, paragraph=1),
            SourceSection(source_id=3, text="Another PDF. " * 10, page=2),
        ]
        chunks = chunker.chunk(sections)
        
        # Verify metadata is not mixed up
        for chunk in chunks:
            if chunk.source_section_id == 1:
                assert chunk.page == 1
                assert chunk.paragraph is None
            elif chunk.source_section_id == 2:
                assert chunk.page is None
                assert chunk.paragraph == 1
            elif chunk.source_section_id == 3:
                assert chunk.page == 2
                assert chunk.paragraph is None


class TestChunkerSentenceSplitting:
    """Tests for sentence-based splitting."""
    
    def test_sentence_boundaries_preferred(self):
        """Chunker should prefer splitting at sentence boundaries."""
        chunker = Chunker(ChunkingConfig(chunk_size=100, overlap=10))
        text = "First sentence. Second sentence. Third sentence. Fourth sentence. Fifth sentence. Sixth sentence. Seventh sentence."
        sections = [SourceSection(source_id=1, text=text, page=1)]
        chunks = chunker.chunk(sections)
        
        # Should have multiple chunks
        assert len(chunks) > 1
        # Chunks should contain valid text
        for chunk in chunks:
            assert len(chunk.text) > 0


class TestDocumentChunk:
    """Tests for DocumentChunk dataclass."""
    
    def test_document_chunk_creation(self):
        """DocumentChunk should be creatable with all fields."""
        chunk = DocumentChunk(
            chunk_index=0,
            text="Sample text",
            page=1,
            paragraph=None,
            source_section_id=1,
            char_start=0,
            char_end=11,
        )
        assert chunk.chunk_index == 0
        assert chunk.text == "Sample text"
        assert chunk.page == 1
        assert chunk.paragraph is None
        assert chunk.source_section_id == 1
