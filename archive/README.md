# Archive Directory

This directory contains older scripts, flows, tests, and exports that were used during the development of the enhanced BookStack to FalkorDB pipeline.

## Directory Structure

### `old_scripts/`
Contains older utility scripts that have been superseded:
- `ingest_all_bookstack.py` - Early BookStack ingestion script
- `check_dependencies.py` - Dependency checking utility
- `test_export.bat` - Windows batch file for testing exports

### `old_flows/`
Contains previous versions of CocoIndex flow definitions:
- `bookstack_continuous.py` - Early continuous processing flow
- `bookstack_continuous_simple.py` - Simplified continuous flow
- `bookstack_live_sync.py` - Live synchronization attempt
- `bookstack_simple_no_llm.py` - Flow without LLM processing
- `bookstack_simple_working.py` - Working simple flow (basis for enhanced version)
- `bookstack_to_falkor.py` - Original enhanced flow with Neo4j targets
- `bookstack_to_falkor_continuous.py` - Continuous processing version
- `bookstack_to_falkor_fixed.py` - Fixed version attempts
- `bookstack_to_falkor_simple.py` - Simplified FalkorDB flow

### `old_tests/`
Contains test scripts used during development:
- `test_bookstack_api.py` - BookStack API connectivity tests
- `test_bookstack_simple.py` - Simple BookStack processing tests
- `test_direct_ingest.py` - Direct FalkorDB ingestion tests
- `test_dry_run.py` - Dry run testing
- `test_enhanced_extraction.py` - Entity extraction testing
- `test_final_enhanced_pipeline.py` - Final pipeline testing
- `test_flow.py` - CocoIndex flow testing
- `test_minimal.py` - Minimal functionality tests
- `test_simple_connection.py` - Basic connection tests
- `test_falkor_ingest.py` - FalkorDB ingestion tests

### `old_exports/`
Contains older BookStack export directories:
- `bookstack_export/` - Initial small export (4 pages)
- `bookstack_export_continuous/` - Continuous export attempts
- `bookstack_sync/` - Synchronization export attempts

## Current Production Files

The following files remain in the root directory as they are the current production versions:

### Active Scripts
- `export_all_bookstack.py` - Current BookStack export utility
- `run_cocoindex.py` - CocoIndex runner with environment setup
- `test_enhanced_localhost.py` - Current enhanced pipeline test
- `verify_enhanced_results.py` - Results verification script

### Active Flows
- `flows/bookstack_enhanced_localhost.py` - **Production enhanced pipeline**

### Active Data
- `bookstack_export_full/` - Current complete BookStack export (153 pages)

### Documentation
- `ENHANCED_PIPELINE_README.md` - Main project documentation
- `ENHANCED_PIPELINE_QUICK_REFERENCE.md` - Quick reference guide
- `COCOINDEX_GRAPHITI_FALKORDB_INTEGRATION.md` - Technical documentation
- `IMPLEMENTATION_SUMMARY.md` - Implementation summary

### Infrastructure
- `docker-compose.cocoindex.yml` - Docker setup for PostgreSQL
- `init-postgres.sql` - PostgreSQL initialization
- `start-cocoindex.ps1` - Environment startup script

## Development History

This archive represents the iterative development process of creating an enhanced BookStack to FalkorDB pipeline with the following key milestones:

1. **Initial API Integration** - Basic BookStack API connectivity
2. **Simple Flow Development** - Basic CocoIndex flow patterns
3. **FalkorDB Integration** - Direct graph database connectivity
4. **Enhanced Entity Extraction** - Beyond tags with LLM patterns
5. **Relationship Discovery** - Semantic relationship identification
6. **Multi-Level Deduplication** - Comprehensive entity normalization
7. **Production Integration** - Final localhost FalkorDB pipeline

## Usage Notes

These archived files are kept for reference and historical purposes. They may contain:
- Experimental approaches that didn't work
- Intermediate solutions that were improved upon
- Test data and validation scripts
- Development debugging utilities

**Do not use these files in production.** Use the current production files in the root directory instead.

## Final Achievement

The development process culminated in a successful enhanced pipeline that:
- ✅ Processes 153 BookStack pages
- ✅ Extracts 17 enhanced entities (TECHNOLOGY, CONCEPT, TAG types)
- ✅ Discovers 13 semantic relationships
- ✅ Creates 206 document-entity mentions
- ✅ Maintains Graphiti schema compliance
- ✅ Integrates with localhost FalkorDB
- ✅ Runs through CocoIndex with proper observability

---

*Archive created: 2025-09-14*
*Enhanced pipeline successfully deployed and operational*
