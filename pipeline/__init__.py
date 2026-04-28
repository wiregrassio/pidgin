# pidgin/pipeline — batch and sync dispatch paths for MLD generation and embedding.

from pidgin.pipeline.batch import (
    GenerationRequest,
    GenerationResult,
    EmbeddingRequest,
    EmbeddingResult,
    FunctionMldResult,
    AnthropicBatchRequest,
    AnthropicBatchResult,
    build_jsonl,
    build_embedding_jsonl,
    should_use_batch,
    parse_batch_results,
    parse_embedding_results,
    run_batch_generation,
    run_batch_embedding,
    run_embedding_mld_pipeline_for_functions,
    run_anthropic_batch,
)
from pidgin.pipeline.candidates import (
    ExpansionConfig,
    CandidateEvaluation,
    evaluate_with_expansion,
)
