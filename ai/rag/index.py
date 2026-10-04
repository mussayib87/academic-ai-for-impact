import hashlib
from pathlib import Path
from typing import Any

import joblib
import numpy as np
from sklearn.feature_extraction.text import HashingVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from backend.app.config import get_settings

SUPPORTED_SUFFIXES = {'.txt', '.md', '.pdf', '.docx'}
CHUNK_SIZE = 1200
CHUNK_OVERLAP = 160


def split_text(text: str) -> list[str]:
    normalized = ' '.join(text.split())
    return [normalized[start:start + CHUNK_SIZE] for start in range(0, max(1, len(normalized)), CHUNK_SIZE - CHUNK_OVERLAP) if normalized[start:start + CHUNK_SIZE].strip()]


def read_source(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise ValueError(f'Unsupported knowledge-base file type: {path.suffix}')
    if suffix in {'.txt', '.md'}:
        return path.read_text(encoding='utf-8')
    if suffix == '.pdf':
        from pypdf import PdfReader

        return '\n'.join(page.extract_text() or '' for page in PdfReader(path).pages)
    from docx import Document

    document = Document(path)
    paragraphs = [paragraph.text for paragraph in document.paragraphs]
    table_cells = [cell.text for table in document.tables for row in table.rows for cell in row.cells]
    return '\n'.join([*paragraphs, *table_cells])


def _embed(texts: list[str], model_name: str) -> tuple[np.ndarray, str, Any]:
    if model_name and not model_name.startswith('hashing-'):
        try:
            from sentence_transformers import SentenceTransformer

            model = SentenceTransformer(model_name)
            return np.asarray(model.encode(texts, normalize_embeddings=True)), f'sentence-transformers:{model_name}', model
        except (ImportError, OSError, RuntimeError):
            pass
    vectorizer = HashingVectorizer(n_features=2048, alternate_sign=False, norm='l2', ngram_range=(1, 2))
    return vectorizer.transform(texts).toarray(), 'hashing-vectorizer-development-fallback', None


def index_documents(root: Path | None = None, store_path: Path | None = None) -> dict[str, Any]:
    settings = get_settings()
    source_root = (root or Path(__file__).resolve().parents[2] / 'knowledge_base').resolve()
    output = store_path or settings.vector_store_path / 'index.joblib'
    chunks: list[dict[str, Any]] = []
    for source in sorted(path for path in source_root.rglob('*') if path.is_file() and path.name.lower() != 'readme.md' and path.suffix.lower() in SUPPORTED_SUFFIXES):
        text = read_source(source)
        digest = hashlib.sha256(text.encode('utf-8')).hexdigest()
        for chunk_index, chunk in enumerate(split_text(text)):
            chunks.append({'source': source.relative_to(source_root).as_posix(), 'chunk_index': chunk_index, 'text': chunk, 'checksum': digest})
    if not chunks:
        raise ValueError('No institutional text sources found. Add approved .txt or .md documents before indexing.')
    embeddings, provider, _ = _embed([item['text'] for item in chunks], settings.embedding_model_name)
    output.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({'chunks': chunks, 'embeddings': embeddings, 'embedding_provider': provider}, output)
    return {'documents': len({item['source'] for item in chunks}), 'chunks': len(chunks), 'embedding_provider': provider, 'index_path': str(output)}


def retrieve(query: str, top_k: int = 4, store_path: Path | None = None) -> dict[str, Any]:
    settings = get_settings()
    index_path = store_path or settings.vector_store_path / 'index.joblib'
    if not index_path.is_file():
        return {'matched': False, 'sources': [], 'message': 'No institutional policy has been inferred. no policy has been inferred. No verified institutional resource is currently configured.'}
    index = joblib.load(index_path)
    query_embedding, provider, _ = _embed([query], settings.embedding_model_name)
    scores = cosine_similarity(query_embedding, index['embeddings'])[0]
    ranked = np.argsort(scores)[::-1][:max(1, top_k)]
    sources = [
        {'source': index['chunks'][int(position)]['source'], 'chunk_index': index['chunks'][int(position)]['chunk_index'], 'text': index['chunks'][int(position)]['text'], 'score': float(scores[position])}
        for position in ranked if float(scores[position]) > 0
    ]
    return {
        'matched': bool(sources),
        'sources': sources,
        'embedding_provider': index.get('embedding_provider', provider),
        'message': '' if sources else 'No institutional policy has been inferred. no policy has been inferred. No verified institutional resource is currently configured.',
    }