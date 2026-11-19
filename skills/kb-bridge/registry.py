"""Canonical operation registry for the kb-bridge dispatcher."""

OPS = {
    "list-competitor-coverage": "handlers.list_competitor_coverage",
    "list-topics": "handlers.list_topics",
    "publish-article": "handlers.publish_article",
    "read-case": "handlers.read_case",
    "read-exemplar": "handlers.read_exemplar",
    "read-reference": "handlers.read_reference",
    "read-title-patterns": "handlers.read_title_patterns",
    "read-topic-strategy": "handlers.read_topic_strategy",
    "read-video-fingerprint": "handlers.read_video_fingerprint",
    "read-video-visual": "handlers.read_video_visual",
    "retrieve": "handlers.retrieve",
    "write-aihot": "handlers.write_aihot",
    "write-case": "handlers.write_case",
    "write-fingerprint": "handlers.write_fingerprint",
    "write-qual": "handlers.write_qual",
    "write-retro": "handlers.write_retro",
    "write-title-patterns": "handlers.write_title_patterns",
    "write-topic-qual": "handlers.write_topic_qual",
}

# These operations describe local configuration only; they do not open a vault
# or create receipts. Keep their standalone, standard-library execution path.
LOCAL_OPS = frozenset({"read-topic-strategy"})
