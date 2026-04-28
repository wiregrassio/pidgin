# MODULE: pidgin.prompts
# Provenance: tools/prompts/generate.md (v0.1)
# DOES: Structured XML prompts for the MLD convergence pipeline.
# V0.2 migration: generate.md rules/examples migrated to converge.xml.

from .templates import assemble_xml_prompt, AssembledPrompt, Principle, PRINCIPLES, load_principle_registry
