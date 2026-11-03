"""Run at image build time so the embedding model works offline. OCR models live in the docling container."""

from app.services import embeddings


def main() -> None:
    embeddings.embed(["warm up"])
    print("models ready")


if __name__ == "__main__":
    main()
