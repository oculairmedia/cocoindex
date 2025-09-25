#!/usr/bin/env python3
"""Matrix to Graphiti extraction pipeline skeleton."""

from __future__ import annotations

import argparse
import logging
import os
from typing import Dict, Iterable, List, Optional

from cocoindex.matrix import (
    AnalysisConfig,
    EmbeddingConfig,
    MatrixConfig,
    MatrixEpisode,
    MatrixExtractor,
    MatrixGraphExporter,
    MatrixEmbeddingClient,
    analyze_episode,
)


logger = logging.getLogger("MatrixPipeline")


def configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract Matrix conversations into Graphiti-ready episodes")
    parser.add_argument(
        "--messages-per-room",
        type=int,
        default=200,
        help="Maximum number of recent messages to include per room",
    )
    parser.add_argument(
        "--max-rooms",
        type=int,
        default=None,
        help="Limit number of rooms processed in a single run",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Log episode summaries without sending to Graphiti",
    )
    parser.add_argument(
        "--graph-host",
        default=os.environ.get("MATRIX_GRAPH_HOST", "192.168.50.80"),
        help="FalkorDB host for Graphiti writes",
    )
    parser.add_argument(
        "--graph-port",
        type=int,
        default=int(os.environ.get("MATRIX_GRAPH_PORT", "6379")),
        help="FalkorDB port for Graphiti writes",
    )
    parser.add_argument(
        "--graph-name",
        default=os.environ.get("MATRIX_GRAPH_NAME", "graphiti_migration"),
        help="Graph name in FalkorDB",
    )
    parser.add_argument(
        "--skip-analysis",
        action="store_true",
        help="Skip LLM-based entity extraction and summary generation",
    )
    parser.add_argument(
        "--analysis-model",
        default=os.environ.get("MATRIX_ANALYSIS_MODEL"),
        help="Override analysis model name (defaults to env or gemma3:12b)",
    )
    parser.add_argument(
        "--analysis-ollama-url",
        default=os.environ.get("MATRIX_OLLAMA_URL"),
        help="Override Ollama base URL for analysis",
    )
    parser.add_argument(
        "--skip-embeddings",
        action="store_true",
        help="Skip embedding generation for episodes and entities",
    )
    parser.add_argument(
        "--embedding-provider",
        default=os.environ.get("MATRIX_EMBEDDING_PROVIDER"),
        help="Embedding provider identifier (ollama, openai, generic)",
    )
    parser.add_argument(
        "--embedding-url",
        default=os.environ.get("MATRIX_EMBEDDING_URL"),
        help="Embedding service URL",
    )
    parser.add_argument(
        "--embedding-model",
        default=os.environ.get("MATRIX_EMBEDDING_MODEL"),
        help="Embedding model identifier",
    )
    parser.add_argument(
        "--embedding-api-key",
        default=os.environ.get("MATRIX_EMBEDDING_API_KEY"),
        help="Embedding service API key (optional)",
    )
    parser.add_argument(
        "--embedding-timeout",
        type=int,
        default=None,
        help="Embedding request timeout in seconds",
    )
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    configure_logging(args.verbose)

    config = MatrixConfig.from_env()
    extractor = MatrixExtractor(config, log=logger)

    exporter: MatrixGraphExporter | None = None
    analysis_config: AnalysisConfig | None = None
    embedding_client: Optional[MatrixEmbeddingClient] = None

    try:
        if not args.dry_run:
            exporter = MatrixGraphExporter(
                host=args.graph_host,
                port=args.graph_port,
                graph_name=args.graph_name,
            )
        if not args.skip_analysis:
            base_config = AnalysisConfig()
            analysis_config = AnalysisConfig(
                model=args.analysis_model or base_config.model,
                ollama_url=args.analysis_ollama_url or base_config.ollama_url,
                temperature=base_config.temperature,
                max_predict=base_config.max_predict,
                request_timeout=base_config.request_timeout,
                fallback_keywords=base_config.fallback_keywords,
            )
        if not args.skip_embeddings:
            embed_config = EmbeddingConfig()
            if args.embedding_provider:
                embed_config.provider = args.embedding_provider.lower()
            if args.embedding_url:
                embed_config.url = args.embedding_url
            if args.embedding_model:
                embed_config.model = args.embedding_model
            if args.embedding_api_key:
                embed_config.api_key = args.embedding_api_key
            if args.embedding_timeout is not None:
                embed_config.timeout = args.embedding_timeout
            embedding_client = MatrixEmbeddingClient(embed_config)

        rooms = extractor.discover_rooms()
        if args.max_rooms is not None:
            rooms = rooms[: args.max_rooms]

        logger.info("Discovered %s rooms", len(rooms))
        episodes: List[MatrixEpisode] = []
        participant_cache: Dict[str, Optional[List[float]]] = {}

        for room in rooms:
            messages = extractor.fetch_recent_messages(
                room,
                limit=args.messages_per_room,
            )
            episode = extractor.build_episode(room, messages)
            if episode is None:
                logger.debug("Skipping room %s with no messages", room.room_id)
                continue

            analysis = None
            if analysis_config is not None:
                analysis = analyze_episode(episode, analysis_config)
                episode.analysis = analysis

            participant_embeddings: Dict[str, Optional[List[float]]] = {}
            if embedding_client is not None:
                episode.embedding = embedding_client.embed(episode.episode_body)
                for participant in episode.participants:
                    if participant not in participant_cache:
                        participant_cache[participant] = embedding_client.embed(participant)
                    participant_embeddings[participant] = participant_cache.get(participant)

                if analysis is not None:
                    for entity in analysis.entities:
                        source_text = entity.description or entity.name
                        entity.embedding = embedding_client.embed(source_text)

            episodes.append(episode)
            if args.dry_run:
                entity_count = len(analysis.entities) if analysis else 0
                logger.info(
                    "Episode: %s | messages=%s | participants=%s | range=%s→%s | entities=%s",
                    episode.name,
                    len(episode.messages),
                    ", ".join(episode.participants),
                    episode.time_start,
                    episode.time_end,
                    entity_count,
                )
                if analysis and analysis.summary:
                    logger.info("Summary: %s", analysis.summary[:280])
                if episode.embedding:
                    logger.info("Episode embedding dim: %s", len(episode.embedding))
            else:
                if exporter is None:
                    logger.warning("Exporter unavailable; skipping ingestion for %s", episode.name)
                else:
                    try:
                        exporter.export_episode(episode, analysis, participant_embeddings)
                    except Exception as exc:
                        logger.error("Failed to export episode %s: %s", episode.name, exc)
        logger.info("Generated %s episodes", len(episodes))
        return 0
    finally:
        extractor.close()


if __name__ == "__main__":
    raise SystemExit(main())
