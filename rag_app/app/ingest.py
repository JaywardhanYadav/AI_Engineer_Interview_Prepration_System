"""Ingest the interview PDFs into Dockerized Weaviate vector database.

Usage:
    python -m app.ingest            # incremental (only new / changed PDFs)
    python -m app.ingest --rebuild  # wipe and re-index everything in Weaviate

Features:
  * Persistent storage in Docker Weaviate volume.
  * SHA-256 file duplicate skipping.
  * Chunk-level normalization and hash deduplication.
  * Batch embedding and insertion into Weaviate.
  * Reports pages with and without extractable text.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone

from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf import PdfReader
from weaviate.classes.data import DataObject

from . import config
from .store import ensure_collection, get_embeddings, get_weaviate_client

MIN_PAGE_CHARS = 40  # below this a page is treated as "no extractable text"


def _sha256(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def load_manifest() -> dict:
    if config.MANIFEST_PATH.exists():
        return json.loads(config.MANIFEST_PATH.read_text(encoding="utf-8"))
    return {"files": {}, "chunk_hashes": []}


def save_manifest(manifest: dict) -> None:
    config.MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    config.MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def extract_pages(path) -> tuple[list[tuple[int, str]], int]:
    reader = PdfReader(str(path))
    pages = []
    for i, page in enumerate(reader.pages, start=1):
        try:
            text = _norm(page.extract_text() or "")
        except Exception:  # noqa: BLE001
            text = ""
        if len(text) >= MIN_PAGE_CHARS:
            pages.append((i, text))
    return pages, len(reader.pages)


def ingest(rebuild: bool = False) -> dict:
    if not config.OPENAI_API_KEY:
        sys.exit("OPENAI_API_KEY is missing. Copy .env.example to .env and set your key.")

    try:
        client = get_weaviate_client()
        if not client.is_ready():
            sys.exit("Weaviate is not ready. Make sure Docker is running: `docker compose up -d`")
    except Exception as e:
        sys.exit(f"Failed to connect to Weaviate at {config.WEAVIATE_HOST}:{config.WEAVIATE_HTTP_PORT}. Error: {e}\n"
                 "Please start it with: docker compose up -d")

    try:
        if rebuild:
            print("Wiping existing Weaviate collection and manifest...")
            if client.collections.exists(config.WEAVIATE_COLLECTION):
                client.collections.delete(config.WEAVIATE_COLLECTION)
            if config.MANIFEST_PATH.exists():
                config.MANIFEST_PATH.unlink()

        collection = ensure_collection(client)
        manifest = load_manifest()
        seen_file_hashes = {v["sha256"]: k for k, v in manifest["files"].items() if "sha256" in v}
        seen_chunks: set[str] = set(manifest.get("chunk_hashes", []))

        splitter = RecursiveCharacterTextSplitter(
            chunk_size=config.CHUNK_SIZE,
            chunk_overlap=config.CHUNK_OVERLAP,
        )
        embeddings = get_embeddings()

        pdfs = sorted(config.PDF_DIR.glob("*.pdf"))
        print(f"Found {len(pdfs)} PDFs in {config.PDF_DIR}\n")

        for pdf in pdfs:
            name = pdf.name
            digest = _sha256(pdf)

            if name in manifest["files"] and manifest["files"][name].get("sha256") == digest:
                print(f"  = {name}: already indexed")
                continue

            if digest in seen_file_hashes and seen_file_hashes[digest] != name:
                print(f"  ~ {name}: duplicate of '{seen_file_hashes[digest]}', skipped")
                manifest["files"][name] = {
                    "sha256": digest,
                    "duplicate_of": seen_file_hashes[digest],
                    "topic": config.topic_for(name),
                    "chunks": 0,
                }
                save_manifest(manifest)
                continue

            topic = config.topic_for(name)
            pages, total_pages = extract_pages(pdf)
            chunks_to_index: list[tuple[str, int, str]] = []  # (text, page_no, chunk_hash)
            dup_chunks = 0

            for page_no, text in pages:
                for chunk in splitter.split_text(text):
                    ch = hashlib.sha1(_norm(chunk).lower().encode()).hexdigest()
                    if ch in seen_chunks:
                        dup_chunks += 1
                        continue
                    seen_chunks.add(ch)
                    chunks_to_index.append((chunk, page_no, ch))

            # Batch embed and insert into Weaviate
            inserted_count = 0
            batch_size = 80
            for start in range(0, len(chunks_to_index), batch_size):
                batch_slice = chunks_to_index[start : start + batch_size]
                texts = [item[0] for item in batch_slice]
                vectors = embeddings.embed_documents(texts)

                data_objects = [
                    DataObject(
                        properties={
                            "text": item[0],
                            "source": name,
                            "page": item[1],
                            "topic": topic,
                            "chunk_hash": item[2],
                        },
                        vector=vec,
                    )
                    for item, vec in zip(batch_slice, vectors)
                ]

                res = collection.data.insert_many(data_objects)
                if res.has_errors:
                    print(f"    Warning: batch insertion errors on {name}: {res.errors}")
                inserted_count += len(data_objects)

            skipped_pages = total_pages - len(pages)
            print(
                f"  + {name} [{topic}]: {inserted_count} chunks indexed from {len(pages)}/{total_pages} pages"
                + (f", {skipped_pages} pages w/o text" if skipped_pages else "")
                + (f", {dup_chunks} duplicate chunks" if dup_chunks else "")
            )

            manifest["files"][name] = {
                "sha256": digest,
                "topic": topic,
                "chunks": inserted_count,
                "pages_total": total_pages,
                "pages_with_text": len(pages),
            }
            seen_file_hashes[digest] = name
            manifest["chunk_hashes"] = sorted(seen_chunks)
            save_manifest(manifest)

        manifest["chunk_hashes"] = sorted(seen_chunks)
        manifest["updated_at"] = datetime.now(timezone.utc).isoformat()
        save_manifest(manifest)

        total_chunks = sum(f.get("chunks", 0) for f in manifest["files"].values())
        print(f"\nIngestion complete! Total {total_chunks} chunks stored in Weaviate.")
        return manifest
    finally:
        client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rebuild", action="store_true", help="wipe and re-index everything in Weaviate")
    ingest(rebuild=parser.parse_args().rebuild)
